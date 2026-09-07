# Title-Block False-Findings — Implementation Plan

Status: Phase 3 implemented · Owner: TBD · Date: 2026-08-04
Related vault: [[Gotcha - Title Upper-Left Double-Reported by Scale]],
[[Gotcha - SCALE Field Read the Date Column]],
[[Gotcha - Mislocated OCR Crop and Ungrounded Misreads]]

## Problem

After the `drawing_views` WAKU fix (which took `drawing_views` markings 56 → 4), the remaining
visible markers on the comparison are `title_block` findings, and **most of them are false**.
The two drawings are a reference/revision pair of the *same* part (`M7452A1N01`) and carry the
**same** metadata values, yet the comparison reports them as changed.

The failures are all the same shape: **a field is extracted on one side and comes back `NONE`
on the other**, so the comparison emits a confident `REMOVED`/`ADDED`/`CHANGED` for a value
that is actually present and unchanged on both sheets.

## Evidence — live session `6a70638323a3c653772bc3d8`

8 `comparison_title_block` violations were persisted. Verdict against the actual sheets:

| Finding | Verdict | Why |
| :-- | :-- | :-- |
| `Unit No.: 45 vs NONE` (REMOVED) | **false** | rev has `45` (present in entities at y≈273) |
| `Part No.: 2A1 vs NONE` (REMOVED) | **false** | rev has `2A1` |
| `T. Q'ty: 4 vs NONE` (REMOVED) | **false** | rev has `4` |
| `Stock Q'ty: 0 vs bP` (CHANGED) | **false** | garbled Shift-JIS read of the same `0` cell |
| `SCALE: NONE vs 1/2.5` (ADDED) | **false** | ref shows `1:2.5`; ref extraction missed it |
| `DESIGNED: NONE vs 澤田` (ADDED) | **false** | ref has a designer value; ref extraction missed it |
| `DRAWN: NONE vs ZHR` (ADDED) | **false** | ref has a drawn-by value; ref extraction missed it |
| `DWG. No.: M7452A1N01 vs NONE` (REMOVED) | **false** | *both* sheets are `M7452A1N01` |
| `Prev Dwg 2589→9324`, date `2010→2026` (not all persisted as TB) | **real** | genuine revision edits |

So ≈7 of 8 are extraction artifacts; a small number of genuine title-block edits exist
underneath the noise.

## Two extraction paths, two distinct failure modes

The `title_block` category is fed by **two independent extractors**. A finding's format tells
you which one emitted it (per [[Gotcha - SCALE Field Read the Date Column]]):

- `Title Block (Upper-Left) <field>: A vs B` → **Path A**, `extract_title_ul_kv`
  (`orchestrator.py:474`), the upper-left metadata table.
- `Title block <FIELD> checked: A vs B` → **Path B**, `BOMAnalyzer.extract_title_block` +
  `inject_title_block_markings` (`orchestrator.py:435`, `marking_builder.py`), the bottom
  title block via OCR + spatial heuristics.

### Path A — upper-left metadata table (`extract_title_ul_kv`)

Confirmed root cause on this pair (from a direct entity probe):

- `extract_title_ul_kv` groups the region into y-**bands**, then assumes **the last (lowest)
  band is the value row** and everything above is headers.
- On the **reference** (large coordinates) the metadata table is well separated from the notes
  block (values at y≈685, notes at y≈599), so the heuristic works → `45/2A1/4/0` extracted.
- On the **revision** (compact SolidWorks sheet, ~2.5× smaller) the **notes block is crammed
  directly beneath the metadata table** (values at y≈273; notes `材質調質施工…` at y≈246, 236,
  226…). Whatever the detected `title_upper_left` bbox admits below the values becomes the
  bottom band, so the heuristic reads **a note line as the value row**, and the real `45/2A1/4`
  are misclassified as headers → no clean field pair → `NONE`.
- Contributing: the band threshold is a **hardcoded `4.0` units**. Rev's two header rows sit
  **3.3 units apart** (they merge) while ref's sit ~8 apart (they don't) — the same
  scale-dependent banding fragility recorded in
  [[Gotcha - Title Upper-Left Double-Reported by Scale]]. The token-based `match_title_ul_pairs`
  fix from that note prevents *double*-reporting, but cannot rescue a side that extracted
  nothing.

### Path B — bottom title block (`extract_title_block`, OCR + spatial)

Root-cause family is already documented, and the deep cause was explicitly *recorded but not
fixed*:

- The OCR crop is the detected `title` zone rendered to an image. When both sheets shared the
  `aspect-1.414` template, the shared fractions fit one sheet and **mislocated the other's
  crop**, so OCR returned nulls / misreads — see
  [[Gotcha - Mislocated OCR Crop and Ungrounded Misreads]] ("a proper crop fix needs per-layout
  templates … recorded, not attempted").
- `resolve_field` trusts any non-null OCR value and falls back to a spatial read on nulls; the
  `SCALE`-reads-the-date and grounding fixes ([[Gotcha - SCALE Field Read the Date Column]])
  hardened specific fields but the extraction remains **asymmetric and corpus-sensitive**.
- Note: the offending template was deleted earlier this session, so the crop now uses each
  drawing's **detected** title zone. Whether that alone resolves the ref-side `SCALE/DESIGNED/
  DRAWN` nulls and the rev-side `DWG. No.` null must be **re-measured**, not assumed.

## The structural issue (why this keeps recurring)

Every fix in the vault history above is a **per-field, per-corpus** repair of one extraction
bug. The comparison itself treats `value vs NONE` as a confident edit, so **any** extraction
gap on one side manufactures a false finding. Because the extractors are heuristic and
scale-sensitive, new layouts keep producing new gaps — a whack-a-mole with no floor.

The durable insight: **asymmetric extraction (`value` on one side, `NONE` on the other) is far
more often an extraction miss than a real change** — especially when the "missing" value is
demonstrably present in the raw entity text on that side.

## Plan (phased)

### Phase 0 — Instrumentation & ground truth (no behavior change)

Make the asymmetry visible and confirm the Path A mechanism before changing logic.

1. Log, once per comparison, the full extracted field set for **both** sides (UL pairs + bottom
   fields), so a glance shows which fields are `NONE` on which side.
2. Behind a debug flag, log the detected `title_upper_left` bbox and the band structure
   `extract_title_ul_kv` computed (band y-centres, which band was chosen as values). This
   confirms/【refutes】 the notes-intrusion hypothesis with certainty.
3. **Exit criterion:** a single log line per run that would have made this diagnosis a
   30-second read.

### Phase 1 — Path A: robust value-band selection

Stop notes (or anything below the table) from being mistaken for the value row.

1. **Constrain the UL region.** Subtract the detected `notes` (and other sibling) boxes from
   the UL entity pool before banding — reuse `views_exclusions()` / `VIEWS_EXCLUDED_ZONES`
   rather than trusting the raw `title_upper_left` bbox.
2. **Replace "last band = values"** with "the band **directly below the header band(s)** within
   a bounded gap." Values sit ~7–10 units below their headers, not 30+; a band separated by a
   large gap is another table/notes, not the values.
3. **Make the band threshold scale-relative** (a fraction of sheet height or median text
   height), retiring the hardcoded `4.0` — same remedy family as the UL gotcha.
4. **Tests** (`tests/test_title_ul_matching.py` / `test_extraction_logic.py`): a compact layout
   with an intruding note line below the value row; assert `45/2A1/4` extract and MATCH, and
   that the note is never selected as the value band.

### Phase 2 — Path B: crop & grounding after template removal

> **CORRECTION (2026-08-04): the "stale OCR cache from the template era" hypothesis is DEAD.**
> `crop_title_block_image` → `compute_title_block_bbox` → the **sync** `extract_dynamic_regions(
> entities)` (`table_extractor.py:6`), which does **not** apply any zone template — only the
> `_async` variant does, and only when passed `render_bounds`. The crop is therefore
> template-independent and always has been in this code; deleting the `aspect-1.414` template
> did **not** change it. Bumping `OCR_CACHE_VERSION` would re-OCR the *same* crop and reproduce
> the same nulls. Verified against the two live cache files: ref OCR'd only `DWG_NO`
> (everything else null); rev OCR'd everything **except** `DWG_NO` — the mislocated/partial-crop
> signature, from the entity-based crop itself, not a template.

So the real cause is the **reference detected-`title` crop (and/or the `resolve_field` spatial
fallback) failing** for `SCALE`/`DRAWN`/`DESIGNED`. Revised Phase 2:

1. Measure the detected `title` bbox for the reference and render the crop; confirm whether it
   frames the ref title block or clips it. (Blocked as of 2026-08-04: the reference was
   re-ingested and its entities moved to a new `drawing_id` — the old id is empty — so this
   needs a stable repro first.)
2. If the crop is sound but OCR still nulls, fix the `resolve_field` spatial fallback so a
   null-OCR field is recovered from CAD text (`中川`, `1:2.5` are present in ref entities).
3. Ensure `DWG. No.` grounding works in **both** directions (the rev-`NONE` case — currently
   masked as MATCHED by the Phase 3 corroboration guard, but ideally extracted directly).
4. **Tests** following the existing `test_extraction_logic.py` grounding patterns.

This is corpus-fragile, per-field work (every prior fix here is `n≈1 pair`) — sequence it only
against a stable repro, and prefer the Phase 3 guard's floor over chasing each field.

> **RESOLVED (2026-08-04) — and it was neither the crop nor the OCR.** With a stable repro
> (re-uploaded pair), running `extract_title_block` directly on the reference's entities with
> `ocr_results=None` returned every field correctly (`DRAWN=中川`, `SCALE=1:2.5`, `DESIGNED`,
> `TITLE`, `QTY=4`). The spatial extractor was never broken. The real cause is upstream in the
> orchestrator: `ref_title_input = [e for e in ref_entities if not is_in_bbox(e, tolerance_bbox)]`
> excludes the tolerance table from title extraction, **but the tolerance box is over-wide**
> (`x 45..1042`, `y 76..299` — nearly full-width, per the diag) and therefore also covers the
> bottom-right **title block** (its fields sit at `y≈90`). So the title entities were deleted
> before extraction ever ran, and every field read NONE.
>
> **Fix:** `keep_for_title_extraction(entity, tolerance_bbox, title_bbox)` — drop an entity only
> when it is in the tolerance box AND NOT in the title box, so the tolerance *table* is still
> excluded but the title block is preserved. Verified on the repro: fields restore. Cache
> `v30 → v31`. Test: `tests/test_title_input_filter.py`. This is a geometry-scoping fix, not
> per-field OCR tuning, so it is far less corpus-fragile than the whack-a-mole this section
> feared.
>
> Effect: `DRAWN` and `SCALE` now extract on the reference, so the two findings become correct
> **CHANGED** (`中川 → ZHR`, `1:2.5 → 1/2.5`) instead of false **ADDED (NONE vs …)**. (`SCALE`
> notation `:`↔`/` is a *deliberate* CHANGED per [[Gotcha - SCALE Field Read the Date Column]].)

### Phase 3 — Structural false-positive guard (the durable fix, highest leverage)

Before emitting any one-sided title finding (`value vs NONE`):

1. **Corroborate absence.** Scan the `NONE` side's raw entity text within the field's expected
   region for the counterpart value (normalized). If it is present, the field was **mis-
   extracted, not removed** → suppress the finding (or downgrade to a low-confidence
   informational note), never `REMOVED`/`ADDED`.
2. **Degraded-extraction gate.** When one side's title extraction is broadly empty against a
   full counterpart (e.g. ≥N fields `NONE` on one side only), mark the whole `title_block`
   category **low-confidence** instead of manufacturing per-field edits.

This is the floor the whack-a-mole has lacked: even when an extractor misses a field, the
comparison will not assert a change for a value that demonstrably exists on the sheet.

**IMPLEMENTED (2026-08-04).** Sub-point 1 (corroborate absence) landed for both paths:

- Path B — `inject_title_block_markings` (`marking_builder.py`): the old MACHINE-CODE-only
  bilateral guard is generalized to every title field, region-scoped to the title bbox with
  `match_level=2` (exact + clean substring, no fuzzy prefix). Call site passes `ref/rev_title_bbox`.
- Path A — the upper-left loop (`orchestrator.py`): same guard against each side's
  `title_upper_left` bbox before emitting a one-sided UL finding.
- Cache `COMPARISON_CACHE_VERSION` → **v30**. Tests: `tests/test_title_block_corroboration.py`
  (mis-extraction → MATCHED; genuine edit → stays flagged; short-numeric-outside-region → no
  false corroborate).

Expected effect on the live pair: the "same value, one-sided extraction" false findings
(`DWG. No. M7452A1N01`, `Unit No. 45`, `Part No. 2A1`, `T. Q'ty 4`) resolve to MATCHED. The
harder cases remain for Phases 1–2 and are **not** fixed by this guard: `SCALE NONE vs 1/2.5`
(notation `:`↔`/`, values genuinely differ as strings), `DESIGNED/DRAWN` (ref missed a
*different* value, so there is nothing to corroborate), and `Stock Q'ty 0 vs bP` (a garbled
Shift-JIS read reported CHANGED, which the guard deliberately does not touch).

Sub-point 2 (degraded-extraction gate) is not yet implemented.

### Cross-cutting

- **Cache:** bump `COMPARISON_CACHE_VERSION` (`cache_manager.py`) with a one-line `# vN:` note —
  mandatory after any extraction/comparison change (cached audits otherwise serve the old
  result).
- **Vault:** new gotcha "Title-Block False Findings from Asymmetric Extraction," linked from the
  MOC and cross-linked to the three notes above.
- **Known pre-existing (not this work):** `tests/test_vision_ocr_grounding.py` — 2 failures
  (`MockEntity` lacks `layer`).

## Sequencing & risk

- **Phase 0 first** — cheap, de-risks everything after it.
- **Phase 3 delivers the largest false-positive reduction with the least corpus-fragility.** If
  the goal is "stop false findings" rather than "perfect extraction," prioritize it.
- **Phases 1 & 2 improve extraction correctness but are corpus-sensitive** — the vault history
  shows every such fix is `n≈1 pair`. Gate each behind a regression test measured on this pair,
  and re-measure column/band spacing before trusting constants on a new customer's standard.

## Open questions (need your call before Phase 1)

1. **Priority:** eliminate false findings fast (Phase 3 first) or improve extraction correctness
   first (Phases 1–2)?
2. **Scope of title-block comparison:** should genuine title-block metadata edits (revision
   date `2010→2026`, drawn-by, previous-dwg-no `2589→9324`) be **reported as findings**, or is
   title-block metadata out of scope for this comparison (i.e. should the category only ever
   flag the *drawing*, never the stamp)? This determines whether Phase 3 suppresses one-sided
   findings outright or merely demotes the false ones.
