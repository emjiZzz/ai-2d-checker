import json
from pathlib import Path
from typing import Optional, Dict, Any
from ...storage.path_resolver import get_storage_root
from ....logger import logger
from ....domain.models.comparison_method import DETERMINISTIC

class ComparisonCacheManager:
    """Manages serialization and invalidation of structured visual drawing comparisons."""

    # Bump this whenever a change to comparison LOGIC (not the input files) could change
    # the output for an already-cached (ref, rev, method) triple: orchestrator/prompt
    # changes, extraction/normalization fixes, BOM override logic, coordinate resolution,
    # etc. Without this, a bug fix silently has no effect for any drawing pair a user
    # already ran a comparison on -- the cache keeps serving the pre-fix result until
    # someone thinks to manually clear it. Content-hash alone (ref_hash/rev_hash) only
    # catches the file changing, not the code that interprets it changing.
    # v3: (historical — the methods this note describes were removed in ADR-006) hybrid's
    # disputed-finding resolution and crop selection both changed, invalidating cached
    # "hybrid" results. Kept in the version log because the log is a record of why each
    # number was burned, and a gap would read as a mistake.
    # v7: Added MAP, Part No. anchors to title_upper_left in zone_detector.py to exclude top-left administrative table (45 | 2A0 | 4 | 0) from drawing_views.
    # v8: zone_detector._expand_bbox now clamps the padded box back inside max_w/max_h.
    # Padding was previously applied *after* the growth loop returned, so every
    # content-aware zone came out up to 2*BBOX_PADDING oversized in each axis and
    # ZONE_MAX_LIMITS were not actually limits (measured: `title` at 39.1% of sheet height
    # against a declared 35% ceiling). Zone geometry changed on every drawing in the corpus
    # -- mean area fell 22.9%->17.4% for `title`, 27.8%->13.8% for `notes` -- and those boxes
    # feed BOM row extraction, category assignment in result_parser, safe-zone exclusion and
    # crop-verifier tiles. Every cached comparison therefore predates the corrected geometry.
    # v9: hand-aligned zone templates now actually apply. The resolver previously failed to
    # import (relative path one level too shallow) and the caller swallowed it, so every v8
    # entry was computed with detection only. It also lacked the CAD Y flip, which would have
    # mirrored every pinned zone, and converted fractions against the detected geometry frame
    # rather than render_bounds. All three are fixed and templates are wired into all four
    # orchestrators, so v8 results do not reflect any pinned zone.
    # v10: ELLIPSE and SPLINE are now ingested (entity_mapper.map_any had no branch for
    # either and returned None, so both were dropped at extraction -- 111 ellipses and 46
    # splines across the 6-drawing corpus, every one of them on a drawing carrying an
    # isometric view; 38 of the 42 entities in one such view). Two things change for any
    # cached pair: the comparison engine now sees geometry it was previously blind to, so
    # those features can be reported as ADDED/REMOVED/CHANGED for the first time, and
    # zone_detector now resolves `iso` geometrically from ellipse density instead of
    # falling back to a percentage-grid guess on every drawing. That moves the `iso` box
    # and, because `views` is derived by exclusion, the `views` box with it.
    # v11: `views` became templatable, and a pinned `bom` now grows against a content-aware
    # detection instead of overwriting it. Both change zone geometry. The bom overwrite was
    # actively lossy -- a template aligned on a one-row BOM clipped the extra rows off any
    # later drawing, dropping them from BOM extraction silently -- so cached results for any
    # pair using a pinned template can be missing BOM rows entirely. Pinned `views` also
    # changes sub-view clustering and drawing_views coordinate resolution, both of which now
    # subtract the sibling zones via zone_detector.views_exclusions().
    # v12: SpatialDiffer matches in a normalized frame (each drawing's own render_bounds)
    # instead of raw CAD units. The two sides of a comparison are not necessarily in the same
    # coordinate space -- a DXF without a paper-space viewport stays in model units while one
    # with a viewport is projected to paper units. Measured on the M7452A0N01 pair that is a
    # 2.500x scale difference, and since the old pre-alignment estimated a translation only,
    # unchanged title-block text was emitted as REMOVED on one side and ADDED on the other.
    # Every cached result for a pair whose two drawings differ in scale contains those false
    # findings, so all of them predate a correct diff.
    # v13: unambiguous REMOVED/ADDED pairs of identical text are collapsed into a single
    # MATCHED finding (marking_reconciler). The zone partition is computed independently for
    # each drawing, so the same line of text can fall inside the notes box on one side and
    # outside it on the other; it is then diffed against two pools that cannot contain it and
    # reported twice. Measured on the M7452A0N01 pair, 21 of 38 findings were ADDED/REMOVED
    # and 12 of those were six unchanged items counted twice. Cached results predate the
    # collapse and contain those duplicates.
    # v14: Shift-JIS characters whose CP932 trail byte is `\`, `{`, `}` or `~` are no longer
    # mutilated by MTEXT markup stripping (utils/text.py::strip_mtext). Markup was being
    # stripped from the byte-preserving string, before transcode_value decodes it, so e.g.
    # 施 (0x8E 0x7B) lost its trail byte to the `{` strip. Confirmed byte-for-byte against
    # the corruption stored in the database: 素材調質施工 -> 素材調質詩H.
    # This changes zone detection as well as text: ZONE_ANCHORS["tolerance"] contains
    # 表示外公差, which was stored as 侮ｦ外公差 and could never match, so the tolerance zone
    # resolved differently. NOTE this is an INGESTION fix -- drawings already extracted still
    # hold the corrupted text and must be re-ingested; the cache bump alone is not enough.
    # v15: geometry is compared for the first time (geometry_differ). SpatialDiffer pools on
    # entity_type == 'text', so lines, circles, arcs, ellipses and splines were never diffed
    # and a feature carrying no text was invisible to the audit -- most visibly an entire
    # isometric view present on the revision and not the reference, which reported nothing
    # (diff_views also returns [] the moment either pool is empty). Unmatched geometry is now
    # clustered and reported as ADDED/REMOVED regions, so every cached result is missing that
    # class of finding entirely.
    # v16: marking_reconciler gained a second pass for content that both MOVED and CHANGED.
    # The exact pass only merges identical text, so a line that was edited *and* landed in a
    # different zone stayed a deletion plus an unrelated addition, with the actual edit never
    # stated. Measured on the corpus pair: 素材調質施工 硬度HS35～38度 -> 硬度HS35～38 (trailing
    # 度 dropped) now reports as one CHANGED instead of two findings. Guarded by similarity,
    # mutual-best pairing, an ambiguity margin and a bounded-movement check, so it merged
    # exactly one pair on that pair's 38 findings.
    # v17: `views` is the sheet rectangle, and the exclusion that defines it moved into the
    # `zone_detector.in_views()` predicate. It was previously the 5-95 percentile of
    # non-excluded content plus padding, which measured 119.7% of the sheet across the corpus
    # -- larger than the drawing it described -- while also producing false negatives in the
    # outer 5%. Zone geometry changes on every drawing, and `views` feeds sub-view clustering,
    # drawing_views coordinate resolution and category attribution.
    # v18: `safe_filter` inputs changed. Pillar 1 (vault_sync) now reads only
    # `docs/vault/08 - Client Domain & CAD Rules/` instead of the entire vault, and strips
    # fenced code blocks before scanning — the tolerance keyword set went from 62 entries (44
    # of them multi-hundred-character markdown blobs captured across code fences) to the 18
    # real terms. Those blobs were inert, so this alone does not change output; what does is
    # that learned dismissal patterns from AutoDocEngine are now READ BACK and excluded, which
    # never happened before. A pair whose client has learned rules will produce fewer findings.
    # v19: three category-attribution fixes, all touching which zone a finding lands in.
    # (a) Sheet-frame grid labels are now actually excluded: `is_margin_grid_text` compared
    #     against ASCII "A".."H"/"1".."12" without NFKC, so the full-width labels this
    #     standard draws (Ａ, １) never matched and the filter was inert at its one call
    #     site — the labels stayed in the zone-detection pool and bridged clusters edge to
    #     edge (reference `tolerance` measured x 8.4->411.6, 21.4% of the sheet). Threshold
    #     also raised 6% -> 9% (labels measure 6.27-8.52%).
    # (b) Amendment/revision-table column headers excluded from drawing_views by exact text.
    # (c) Amendment-table values and the A/B/C/D row-letter column reclassified from
    #     drawing_views to title_block by proximity to the header cluster (relabel only,
    #     never dropped).
    # Zone boxes move on every drawing, so this changes category attribution and coordinate
    # resolution for every zone, not just the amendment table.
    # v20: shim table (シム表) is its own zone. Detected on its own text anchor (no
    # percentage fallback, so it is simply absent on sheets without one), excluded from the
    # drawing_views pool, and compared as a new `shim_table` category. Findings that used to
    # land in drawing_views now move to shim_table, so cached drawing_views output is stale.
    # v21: spatial_differ no longer pairs unrelated text as CHANGED. A cross-text pair within
    # the distance threshold is now kept only if the two strings are a plausible in-place edit
    # (>=0.40 char similarity, or both numeric/dimensional); otherwise both fall through to the
    # REMOVED + ADDED sweep. Fixes notes like '2 ロール：4' being reported as CHANGED into an
    # unrelated fabrication note. Affects notes/iso/drawing_views/shim (the diff_views path).
    # v22: BOM extraction now captures a "refer to table" deferral row (item number next to a
    # 表ニヨル / 表による pointer). It has only two cells, so the >=4-cell row filter dropped it and
    # the BOM comparison came back empty on drawings whose materials live in a separate table.
    # Fallback only -- an ordinary populated BOM is unaffected.
    # v23: a title-block OCR value that grounds to NO text on the drawing is now treated as a
    # likely misread and the spatially-extracted value is preferred instead. Gemini misread a
    # mislocated reference title-block crop as DWG_NO 'ME17227N24' (real: 'M745227N01') and
    # that ungrounded value used to override the correct spatial reading. Grounded OCR values
    # are still trusted; only ungrounded ones defer to spatial.
    # v24: title-block upper-left fields now match across drawings by shared header token
    # instead of exact combined key. The header banding uses a fixed y-threshold, so a
    # large-coordinate drawing splits a field's stacked English/Japanese labels into two
    # header bands (key 'Unit No. / ユニットNo.') while a small-coordinate one merges them (key
    # 'Unit No.'); the exact-key match then double-reported every identical value as
    # REMOVED + ADDED. Token matching pairs them, so unchanged UL values read MATCHED.
    # v25: the shim table (シム表) is now a SAFE zone like tolerance, not a compared category.
    # Its rows are still excluded from drawing_views, but they are no longer diffed as their
    # own `shim_table` category -- assembly-thickness reference data does not change
    # meaningfully between revisions. The shim_table findings and response section are gone.
    # v26: global default zone-template fallback. A sheet whose aspect matches no saved template
    # now inherits the designated default template's pinned zones (zone_template_resolver.py),
    # changing zone extraction -- and therefore comparison output -- for previously-unmatched
    # sheets. Signature-specific templates still win. Changing WHICH template is default later is
    # not a code change and does not re-bump this; that staleness is cleared by Re-test/force_refresh.
    # v27: drawing_views is now scoped to the `views` zone box (scope_entities_to_views) instead of
    # the residual of everything-minus-other-zones. Content that sat inside no zone box is no longer
    # compared; a sheet with no views box yields an empty drawing_views category. Strict, no fallback.
    # v28: safe zones (tolerance, shim) now keep their content-anchored detection instead of letting a
    # template box replace it (table_extractor.SAFE_ANCHORED_ZONES). A misplaced template box could
    # move the tolerance zone off the real 表示外公差 table and expose it to the BOM/views comparison;
    # anchoring the safe zone by content keeps it excluded regardless of template placement.
    # v29: drawing_views furniture filter now recognizes the romanized frame layer "WAKU" (= 枠), not
    # just the kanji. KMTI AutoCAD sheets keep all title/tolerance/BOM furniture on layer "WAKU"; its
    # lower rows sit below the tolerance box and were being diffed as drawing_views (e.g. "2589", "2.5").
    # v30: title-block comparison (both the bottom block and the upper-left metadata table) now applies
    # a bilateral corroboration guard — a field read on one side but NONE on the other is reported
    # MATCHED, not a false REMOVED/ADDED, when the value is actually present in the other drawing's
    # title region. Fixes false findings like "DWG. No. M7452A1N01 vs NONE" and "Unit No. 45 vs NONE".
    # v31: title extraction no longer drops title-block entities that fall inside an over-wide
    # tolerance box (keep_for_title_extraction). The tolerance box often spans the full bottom strip
    # and was swallowing the bottom-right title block, so DRAWN/SCALE/DESIGNED/TITLE read NONE on the
    # reference; now the tolerance table is excluded without blanking the title block.
    # v32: title-field extraction is now aware of the title block's ruled cell boundaries. A
    # 'below' proximity search rejects any candidate separated from its label by a vertical rule
    # (title_block_extractor._separated_by_rule), so "Previous Dwg. No." no longer reads the
    # tolerance table's Fabrication cell across the divider. JOB NO now searches 'right'
    # (dx_tol=22) and reads its real value, surfacing a 2589 -> 9324 change that previously read
    # NONE vs NONE. Corroboration of a short (<=3 char) title value now requires an exact
    # whole-string hit, so "1" can no longer be corroborated by the "1" inside "M7452A1N01".
    # v33: the geometry pass added in v15 is REMOVED (geometry_differ.py deleted, all three
    # call sites gone). Findings like "Geometry: 10 line" name a count and a primitive type but
    # no engineering content, so a checker cannot act on them and they crowded out the text
    # findings. Every cached result carries them; this bump drops them. Known cost, accepted:
    # a zone present on only one sheet and carrying no text again reports nothing, because
    # diff_views returns [] when either pool is empty. See v15's note for what was lost.
    # v34: three new title-block comparisons. (a) TITLE is read from the cell BESIDE its label
    # and split per ruled row -- the old 'below' search walked into the drawing-number cell and
    # returned 'M7452A1N01' as the title. (b) The two 名称 rows are compared separately, so a
    # change confined to the upper row is not merged with a matching lower row. (c) DATE
    # (作成年月日 / Y/M/D) is extracted and compared for the first time, under a new
    # `creation_date` taxonomy feature. Also fixes field_labels_map keying the title as "NAME"
    # while the extractor returns "TITLE" -- the lookup missed on every drawing, so the title
    # produced no marking at all. Cached results are missing all three findings.
    # v35: every marker anchor is now the CENTRE of the text it marks, not a character-width
    # past its right edge. renderEntities.ts draws the glyph centred on the coordinate, so the
    # old offset carried the tick off the end of long values and, in the title block, outside
    # the ruled cell the value lives in -- so it appeared to annotate whatever sat to the right.
    # The formula was hand-copied to 12 places in Python and 8 in TypeScript; it now lives in
    # bom/anchors.py::marker_anchor and markerGenerator.ts::markerAnchor. Cached results carry
    # the old coordinates for every finding.
    # v36: DIMENSION entities are compared for the first time. The differ's pools filtered
    # `entity_type == 'text'`, so every dimension on every drawing was dropped before comparison
    # and could never receive a checkmark (⌀120, ⌀260, ⌀140, 22.7±0.02 on the measured pair, now
    # 4 MATCHED). Two supporting changes ride along: _get_entity_coords reads dimension geometry
    # (text_point/def_point — dimensions have no `insert`, so they all resolved to the origin)
    # and returns None instead of (0,0) when unanchorable; and dimensions are compared on their
    # numeric `measurement` + kind rather than display text, because the same unchanged
    # dimension is authored as a `%%c120` override on one sheet and left to the dimension style
    # on the other. Every cached result is missing all dimension findings.
    #
    # Also in v36: feature_classifier NFKC-folds before matching. Every rule in it is written in
    # ASCII while this corpus writes callouts FULLWIDTH, so `Ｃ１` (a chamfer) missed the chamfer
    # rule and was filed under "Other / Unclassified"; likewise fullwidth radii, plain dimensions
    # and tolerances. The `feature` on cached drawing_views/notes findings is therefore stale.
    # v37: zone scoping anchors a DIMENSION at its `text_point` instead of the centroid of its
    # geometry points (zone_detector.entity_anchor). That centroid is the midpoint between the
    # measured feature and the value, a place where nothing is drawn, and on a long dimension it
    # can land in a sibling zone the dimension is nowhere near. The reference ⌀260 on
    # M7452A1N01 was scoped into the tolerance safe zone that way and dropped from the
    # drawing_views pool, while the revision's ⌀260 stayed in -- so an unchanged dimension came
    # back ADDED with no REMOVED counterpart. Cached results carry the wrong status for any
    # dimension whose span crosses a zone boundary.
    #
    # Also in v37: the `tolerance` zone no longer floods along line geometry, and grows on a
    # decoupled wide-X/tight-Y radius instead of the isotropic CLUSTER_RADIUS. It was blowing
    # out to BOTH caps (0.95w x 0.30h exactly) on both drawings of that pair and reaching ~150
    # units up into the drawing area. `tolerance` is a SAFE zone that `views` subtracts, so
    # everything it over-covered -- `22.7±0.02`, the `6-6.6キリ11ザグリ深6.5` callout, the
    # section marks -- was silently dropped from drawing_views and never compared. Cached
    # results are missing those findings entirely.
    # v38: section designations (`Ａ－Ａ`) and their arrow labels are recognised, and then
    # SUPPRESSED from the drawing_views checklist (orchestrator.DROP_SECTION_CALLOUT_LABELS).
    # Two output changes ride on this, so both directions of the cache are stale: a `Ａ－Ａ`
    # that survives classification now carries feature `additional_views` instead of `other`,
    # and the designation plus its lone-letter cut arrows no longer appear as findings at all.
    # A v37 entry therefore still shows the three "Other / Unclassified" rows this drops.
    # v39: title-upper-left fields pair across the English/Japanese halves of a bilingual
    # header (orchestrator._TITLE_UL_SYNONYMS). Where the reference emitted `コードNO.` and the
    # revision `PART NO.` for the same column, the field never paired and its identical value
    # was reported twice — once as `230 → NONE`, once as `NONE → 230`, both flipped to MATCHED
    # by the bilateral corroboration guard. A v38 entry still shows that duplicate row pair.
    # v40: title-block field extraction no longer reads the upper-left table
    # (keep_for_title_extraction now excludes `title_upper_left` the way it already excluded
    # `tolerance`). The bottom title block's QTY field searches for `T. Q'ty` / `総製作個数`,
    # which is the upper-left table's own column header, so the proximity search walked up the
    # sheet and read that table's cell — surfacing one physical cell twice in the title_block
    # checklist, as `QTY (QUANTITY)` and again as `T. Q'TY / 総製作個数`, both grounded to the
    # same marker. A v39 entry still carries the duplicate QTY row.
    # v41: Machine Type/Code, Unit No./Unit Code and Part No. no longer get checklist items of
    # their own. They are SEGMENTS of the drawing number split across its ruled sub-cells
    # (`M745203N01` = `M745` + `203` + `N01`), so the side panel showed four items for one
    # identifier and three could not change without the DWG No. changing too. Dropped only when
    # the DWG No. is shown to contain them (utils/text.is_component_of_dwg_no) — an uncorroborated
    # component keeps its row rather than vanishing on a sheet where DWG No. failed to extract.
    # The DWG No. card's label loses its sub-header list for the same reason. A v40 entry still
    # shows the three component rows and the long label.
    # v42: a zone can be RESHAPED into a polygon in the alignment editor (a node inserted on an
    # edge), and containment now honours that outline instead of the bounding box —
    # scope_entities_to_views for `views`, views_exclusions/safe_filter for the siblings. A
    # sheet whose template carries a reshaped zone therefore has a different drawing_views pool
    # than its v41 entry. Inert on templates of plain rectangles, which is every zone nobody has
    # reshaped. See bom/zone_geometry.py.
    # v43: a BOM row that changed in several columns is ONE finding, not one per column. The
    # builder collected a marking per cell, so a row where three cells moved together produced
    # three checklist items where a checker — and the eval corpus's annotation guideline — sees
    # one. MATCHED cells are untouched and still get a per-column verification row; only the
    # non-MATCHED cells of a row collapse, anchored on the first changed column in bom_cols
    # order. A single-changed-cell row is byte-identical to its v42 entry. See
    # marking_builder.inject_bom_markings.
    # v43 also: a structured title-block/BOM value shorter than
    # ComparisonParams.min_structured_value_length (3) no longer suppresses its text-twins in
    # the generic zone passes. That net is keyed on text alone and applied sheet-wide, so a BOM
    # row numbered `1` was deleting a standalone `１` from the notes pool on BOTH sides and
    # making its removal unreportable. Measured: recall 0.85 -> 0.87, notes_section recall
    # 0.92 -> 1.00, no new false positives. A v42 entry silently under-reports those.
    # See orchestrator._collect_structured_text_values.
    # v44: elliptical arcs that wrap through 2pi were tessellated backwards. A DXF ellipse
    # always sweeps counter-clockwise from start_param to end_param, so `end < start` means it
    # crosses zero -- but `_tessellate_ellipse` took the raw difference and swept the short way
    # round, placing the arc on the WRONG SIDE of its own ellipse. The wrap only appears after
    # block explosion (definitions store (180, 360); the INSERT transform rewrites it to
    # (180, 0)), so 9 of 33 arcs on a real isometric view were mirrored onto arcs already
    # drawn, leaving the other half empty and the flange rendered as a broken crescent.
    # This invalidates cached audits because `_detect_iso_zone` sizes the `iso` zone from
    # `_largest_ellipse_cluster`, whose extent is computed from exactly these points -- a
    # half-covered ring yields a smaller, offset iso box than a complete one.
    # See EntityMapper._tessellate_ellipse and
    # docs/vault/06 - .../Gotcha - A Blurry CAD Canvas and Its Four Causes.
    # v45: the hand-aligned sheet template was re-drawn. `bom` and `title_upper_left` had bottom
    # edges that cut through their own header rows, and the column between `title_upper_left` and
    # `bom` belonged to no zone at all -- so content there was silently unzoned, which the
    # annotation guideline treats as out of scope rather than as a finding. Every zone box moved
    # and `views` became a 12-vertex outline, so drawing_views' pool, the safe-zone exclusions and
    # each finding's category all differ from their v44 entries. Measured over the eval corpus:
    # rows belonging to no zone 9 -> 1. See
    # docs/vault/06 - .../Gotcha - A Zone Template Gap Hid Half of a Real Change.
    # v45 also: the `仕上げ` anchor is removed from `notes` zone detection. It matched `仕上げ記号`
    # in the bottom-left tolerance block, dragging the detected notes box across the sheet so it
    # covered neither that label nor the real notes. This invalidates cached audits only for
    # sheets with NO pinned `notes` zone -- where a template pins it, detection is overridden and
    # the change is inert (verified: eval byte-identical with the zone pinned). Folded into this
    # bump rather than taking v46, because v45 has not shipped and a second invalidation would
    # cost a re-run for no added safety. See zone_detector.ZONE_ANCHORS and
    # tests/test_notes_zone_anchors.py.
    # v46: `extract_title_ul_kv` no longer assumes the LOWEST band of the upper-left table is
    # its values row. That is a positional assumption, and it holds only while the zone box
    # stops at the bottom of the table -- on M745227N01 the default `aspect-1.374` template
    # applied to a 1.414 sheet put the reference's box bottom at y=762.99 against a value row
    # at y=822, so a note at y=767.5 was read as the values and the real values (45/227/16組/0)
    # became headers. A band is now dropped only when it BOTH fails to fill the table's columns
    # and sits at an outlying row gap. Measured over every stored sheet: the value band moves on
    # M745227N01's reference and on nothing else, so cached audits for the other 11 pairs are
    # invalidated for no behaviour change -- taken anyway rather than shipping a version whose
    # meaning depends on which sheet you loaded. See orchestrator.ul_value_band_index,
    # tests/test_title_ul_value_band.py, and
    # docs/vault/06 - .../Gotcha - The Lowest Row Is Not the Values Row.
    #
    # v46 also, folded in because v46 has not shipped and each alone invalidates the same
    # entries: `partition_ul_pairs` releases a value with no counterpart anywhere back to the
    # zone that covers it, instead of reporting a one-sided change AND suppressing that text
    # sheet-wide. Release is conditional on another zone actually covering the value, because
    # `title_upper_left` is subtracted from the `views` pool and an uncaught release would be a
    # silent false negative. See tests/test_title_ul_release.py.
    #
    # ⛔ A THIRD change was written under this bump and REVERTED the same day, before shipping:
    # `extract_title_ul_kv` subtracting the sibling zones' shapes before banding. It measured
    # well on three unlabelled sheets and was a regression on the corpus that scores --
    # detection-only F1 0.7736 -> 0.7339, fp 10 -> 14, tp 41 -> 40, three new `title_block`
    # false positives. **The templated eval could not see it**: all three v46 mechanisms are
    # byte-identical at F1 0.9231 with zones pinned, because a pinned box does not over-reach so
    # none of them ever fires. That is why `tools/eval.py --no-templates` now exists. Do not
    # re-land the subtraction as a per-call-site exclusion list; see orchestrator's
    # `extract_title_ul_kv` docstring and zone_ownership.py.
    #
    # v47: **the notes pool is chosen per ENTITY, not per box.** `extract_note_entities` +
    # `notes_classifier.classify_notes` replace `extract_zone_entities(..., notes_bbox, ...)`,
    # `views_exclusions` takes `omit=("notes",)` and the claimed notes are subtracted from the
    # `views` pool by identity instead, and ownership between overlapping zones now comes from
    # one arbitration (`zone_ownership.py`) rather than four ad-hoc exclusion lists.
    #
    # The zone this replaces has no drawn boundary on these sheets (ruled-border IoU ceiling
    # 0.08) and is grown from text anchors, so it moves when the text moves — including when the
    # change under test is itself an added note. On M7452A0N01-rev-mut005 the same four notes
    # rows sit at IDENTICAL coordinates on both sides, inside the reference's detected box
    # (38.0, 202.6, 60.0, 251.0) and outside the revision's (65.0, 202.6, 254.0, 231.8), and
    # report as seven false REMOVEDs. A content predicate cannot disagree with itself.
    #
    # Every cached audit is invalidated because notes scoping changed on BOTH paths. Measured:
    # detection-only F1 0.7736 -> 0.8367 (P 0.8039 -> 0.9535, R unchanged, fp 10 -> 2,
    # notes_section P 0.59 -> 0.93 at R 1.00); templated F1 unchanged at 0.9231. See
    # tests/test_notes_entity_classifier.py, tests/test_zone_ownership.py and
    # docs/vault/06 - .../Gotcha - Adding a Note Destroys the Notes Zone.
    #
    # v47 also, folded in because v47 has not shipped and each change alone invalidates the same
    # entries. Both come from one owner report on M745227N01 -- `４ロール：１２（２×６台）` ADDED
    # with no REMOVED counterpart on a sheet carrying it on both sides:
    #   * **`title_upper_left` subtracts from `views` only what it CLAIMED**, not its whole box.
    #     The reference's copy sits 4.5 units inside that box (y=767.5 vs a bottom edge at
    #     y=763.0) while its sibling 24 units lower falls outside and paired correctly -- and the
    #     UL extractor had already cut that row as not-a-values-row. Claimed by the zone for
    #     exclusion, unclaimed by it for comparison, compared by nobody: a silent false negative.
    #     `extract_title_ul_kv` now returns its claimed entity ids alongside its pairs.
    #     **The rule for any zone: only take content out of the shared pool if you will compare
    #     it.** Everything else falls through to `views`.
    #   * **cross-text pairs are ordered by proximity AND similarity** (`spatial_differ`,
    #     `CROSS_TEXT_SIMILARITY_WEIGHT`). Proximity alone crossed the two production-count lines
    #     once both were present -- the block moved 0.055 normalized against a 0.025 row pitch,
    #     so each line's nearest neighbour was its sibling -- reporting `4 ロール：12 (2x6台)` ->
    #     `２ロール：　４（２×２台）`, a false claim that reads as a 4-roll spec becoming 2-roll.
    # Both verified on the reported pair; both leave BOTH baselines byte-identical, because
    # M745227N01 is one of the six pairs the runner skips for having no labels.
    #
    # v48: **`ZONE_MAX_LIMITS["shim"]` was smaller than the table it caps** -- 0.35 of sheet
    # height against a drawn シム表 of 337.5 units on an 891-unit sheet (37.9%). The box came
    # out 311.8 tall, its cap to the unit, and the bottom row `総厚サ 6mm` (y=311.1) sat
    # **35.8 units below the bottom edge of its own zone**, fell through to the `drawing_views`
    # pool, and was compared and marked -- reported from a live review, where `shim` is a SAFE
    # zone like `tolerance` and none of its rows may be compared at all. Height 0.35 -> 0.45.
    # Now 0 rows uncovered on both sides, and the only thing inside the box but outside the
    # drawn table is the table's own title, drawn above its top rule and part of it.
    #
    # ⚠ This was invisible to every published number and will stay invisible: `M745227N01` is
    # the ONLY corpus pair carrying a shim table and it is one of the six the runner skips for
    # having no labels. Both baselines are byte-identical across this change. Verified directly
    # on the pair instead -- see tests/test_shim_safe_zone.py.
    #
    # ⛔ Not fixed by re-reading the drawn table. That was implemented on 2026-08-12 and
    # reverted the same day on the owner's call; this is the minimal alternative and it touches
    # no pairing code.
    #
    # v48 also, folded in because v48 is unshipped and it invalidates the same entries: a
    # **SAFE-ZONE NET** in `orchestrator`, after `resolve_marking_coordinates`. `shim` and
    # `tolerance` are never compared, but that invariant was being kept in three different
    # places and three different ways -- `safe_filter` guards only the drawing_views pool, the
    # BOM and title-block injections consult no zone at all, and coordinate resolution can move
    # a marking after all of those decisions were taken. It was reported violated from live
    # reviews twice in one day. Now enforced once, where every marking has final coordinates.
    # Keyed on `zone_ownership.owner_of`, NOT on a bare box test: the revision's `tolerance`
    # box over-reaches into the title block on M745227N01 and 7 real `title_block` findings sit
    # inside it, which `title` correctly claims by precedence. Measured: drops 0 findings on
    # that pair and leaves both baselines byte-identical. It is a net, not a fix -- anything it
    # ever drops is a bug upstream of it, and it logs each drop so that bug is findable.
    #
    # v49: **`line_attributes` produces findings.** The sub-item has existed since the checklist
    # was grouped and no generator has ever assigned it -- `feature_classifier` names Generator B
    # as its intended source and ADR-006 deleted Generator B -- so the card was reachable only
    # through its empty state, which reads "No changes detected." It reported a clean result for
    # every comparison this system has ever run, on a check that never ran.
    # `line_attribute_differ` now profiles each side's stroke geometry by (linetype, lineweight),
    # resolved through the layer table, and emits one row per line attribute either drawing draws
    # with: MATCHED on both sides, ADDED/REMOVED when only one side uses it. Counts are shown but
    # never drive a status -- see that module for why, and for the measured row-count basis of
    # the key. Every cached audit is invalidated because drawing_views gains rows and its rollup
    # status can flip to CHANGED on a one-sided line attribute.
    #
    # v50: **an uncorroborated OCR title-block value is no longer promoted to a field.**
    # `resolve_field`'s grounding-miss branch returned the OCR string whenever the spatial
    # search also came back NONE -- i.e. it trusted the value in the one case where *nothing*
    # corroborated it. On M745227N01 that published `ME17227N24`, a string appearing nowhere on
    # either drawing, as a REMOVED title_block finding; the real `M745227N01` was rejected by
    # `_separated_by_rule` because it sits across a ruled divider from its own `DWG.No.` label.
    # Now returns NONE and lets the spatial path own the field. The split-value case is
    # unaffected -- it is decided by the substring branch, which requires a spatial reading to
    # exist. Cached audits are invalidated because any title-block field resolved through that
    # branch can change value, which changes findings.
    #
    # v51: **Mach. code / Unit Code got a checklist item of its own.** The marking already
    # carried the combined label " Mach. code /  Unit Code", but `title_feature_map` had no
    # entry for it, so every one of these findings was tagged `OTHER_FEATURE_KEY` and rendered
    # under "Other / Unclassified". New `title_block.machine_unit_code` covers 機器記号 AND
    # ユニット記号 as ONE item, the same way the DWG No. is one item for its ruled sub-cells --
    # the value spans both cells on this client's sheets (`FSRS2`) and the extractor already
    # reads it as one string. The `feature` tag travels on the cached marking, so every cached
    # audit carries the old `other` value and would render the finding in the wrong card.
    #
    # v52: **line attributes report the line TYPES used, not stroke tallies.** Reported by the
    # owner against the live card: `CENTER 0.25MM X9` as a heading over a body reading x8 vs x9,
    # and `CONTINUOUS 0.25mm x20` vs `x2` badged MATCHED. The count was baked into `describe()`,
    # so it was the card's headline, part of the row's IDENTITY (the same line type rendered as
    # a different card whenever a re-trace moved the tally) and the string the canvas fuzzy-
    # matched on -- while `status` explicitly ignores counts. This card answers "what kind of
    # line types does the drawing use", which is a question about the SET; the count is still
    # computed and is simply not claimed. Every cached audit carries the old count-bearing
    # `text_content` / `original_value`, so all of them render the old card.
    COMPARISON_CACHE_VERSION = "v52"

    @staticmethod
    def _get_cache_path(
        ref_drawing_id: str,
        rev_drawing_id: str,
        ref_hash: str,
        rev_hash: str,
        method: str = DETERMINISTIC
    ) -> Path:
        cache_dir = get_storage_root() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Naming format: gemini_comparison_{version}_{method}_{ref_drawing_id}_{rev_drawing_id}_{ref_hash}_{rev_hash}.json
        # `method` is a path segment so two methods could never serve each other's cached
        # output for the same drawing pair. Only one method remains (ADR-006), so it no longer
        # discriminates anything — kept because it is the seam a second method would need, and
        # because renaming it out would be a third gratuitous invalidation.
        # Renaming `rag` -> `deterministic` orphaned the pre-rename entries by design; that was
        # measured at one real v42 file before it was done.
        # This aligns with api/routers/drawings.py cache invalidation glob/string check, which only
        # substring-matches on drawing_id and doesn't care about the extra segments.
        version = ComparisonCacheManager.COMPARISON_CACHE_VERSION
        filename = f"gemini_comparison_{version}_{method}_{ref_drawing_id}_{rev_drawing_id}_{ref_hash}_{rev_hash}.json"
        return cache_dir / filename

    @classmethod
    def get_cached_comparison(
        cls,
        ref_drawing_id: str,
        rev_drawing_id: str,
        ref_hash: str,
        rev_hash: str,
        method: str = DETERMINISTIC
    ) -> Optional[Dict[str, Any]]:
        """Retrieves comparison payload if a valid cache hit exists."""
        cache_file = cls._get_cache_path(ref_drawing_id, rev_drawing_id, ref_hash, rev_hash, method)
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                logger.info(f"Comparison cache hit ({method}) for reference {ref_drawing_id} and revision {rev_drawing_id}")
                return payload
            except Exception as e:
                logger.error(f"Failed to read comparison cache: {e}")
        return None

    @classmethod
    def set_cached_comparison(
        cls,
        ref_drawing_id: str,
        rev_drawing_id: str,
        ref_hash: str,
        rev_hash: str,
        payload: Dict[str, Any],
        method: str = DETERMINISTIC
    ) -> None:
        """Saves comparison payload to cache."""
        cache_file = cls._get_cache_path(ref_drawing_id, rev_drawing_id, ref_hash, rev_hash, method)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.debug(f"Comparison cache stored ({method}) at: {cache_file.name}")
        except Exception as e:
            logger.error(f"Failed to write comparison cache: {e}")

    # REMOVED (ADR-006): `CANDIDATE_CACHE_VERSION` and the `hybrid_candidates_*` read/write
    # pair. They were a second version lever, separate from COMPARISON_CACHE_VERSION on
    # purpose, so a change to hybrid's reconciliation could invalidate the final result
    # without discarding what each generator had produced. With `hybrid` gone there is one
    # method, one stage and one lever.
    #
    # Any `hybrid_candidates_*.json` left in `storage/cache/` is now orphaned. They are not
    # deleted here — nothing reads them, they cost only disk, and a cache directory is not
    # something this class should garbage-collect on import.

    OCR_CACHE_VERSION = "v1"

    @staticmethod
    def _get_ocr_cache_path(drawing_id: str, file_hash: str) -> Path:
        cache_dir = get_storage_root() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Naming format: title_block_ocr_{OCR_CACHE_VERSION}_{drawing_id}_{file_hash}.json
        filename = f"title_block_ocr_{ComparisonCacheManager.OCR_CACHE_VERSION}_{drawing_id}_{file_hash}.json"
        return cache_dir / filename

    @classmethod
    def get_cached_ocr(cls, drawing_id: str, file_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieves single-drawing OCR key-value payloads if cache exists."""
        cache_file = cls._get_ocr_cache_path(drawing_id, file_hash)
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                logger.info(f"Title block OCR cache hit for drawing {drawing_id}")
                return payload
            except Exception as e:
                logger.error(f"Failed to read title block OCR cache: {e}")
        return None

    @classmethod
    def set_cached_ocr(cls, drawing_id: str, file_hash: str, payload: Dict[str, Any]) -> None:
        """Stores single-drawing OCR findings to cache."""
        cache_file = cls._get_ocr_cache_path(drawing_id, file_hash)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.debug(f"Title block OCR cache stored at: {cache_file.name}")
        except Exception as e:
            logger.error(f"Failed to write title block OCR cache: {e}")

    @classmethod
    def clear_cache_for_drawing(cls, drawing_id: str) -> None:
        """Removes all cache files associated with a specific drawing."""
        cache_dir = get_storage_root() / "cache"
        if not cache_dir.exists():
            return
            
        count = 0
        try:
            for cache_file in cache_dir.glob("*.json"):
                if drawing_id in cache_file.name:
                    cache_file.unlink()
                    count += 1
            if count > 0:
                logger.info(f"Cleared {count} cache files for drawing {drawing_id}")
        except Exception as e:
            logger.error(f"Failed to clear cache for drawing {drawing_id}: {e}")
