/**
 * Canonical sub-item taxonomy for the checklist UI (docs/checklist-taxonomy-grouping-
 * implementation-plan.md). Hand-mirrored from
 * services/backend/infrastructure/audit/comparison/taxonomy.py — there is no runtime
 * type-sharing mechanism between the two languages in this repo, so keeping these two
 * files in sync is a discipline, not something automatic (see the cross-check test in
 * Phase 8 of the plan doc). If you edit one, edit the other.
 *
 * `category` (one of the 6 top-level values already on CanvasMarking) is a coarse
 * grouping; `feature` is a finer one, scoped within a category, used to group the
 * checklist panel into named sub-sections instead of one flat list per category.
 */

import { DIAMETER_CHARS, MULTIPLY_CHARS, cleanCadText } from './cadGlyphs';

export interface FeatureItem {
  key: string;
  label: string;
}

// Appended by grouping code, not part of the arrays below — every category implicitly
// accepts findings that don't confidently match any of its named sub-items.
export const OTHER_FEATURE_KEY = "other";
export const OTHER_FEATURE_LABEL = "Other / Unclassified";

// Sub-items with no real extraction signal today (see the plan doc, decision 6) —
// rendered with a distinct "not yet supported" treatment instead of the normal
// "no changes detected" empty state, so they don't read as "checked and clean" when
// nothing was actually checked.
//
// `origin`, `alignment_of_views` and `text_attributes` joined `line_name` on 2026-08-14:
// no backend code can assign any of them (their intended producer was Generator B, which
// ADR-006 deleted), so each was reporting a clean result for a check that never ran.
//
// Membership here HIDES rows — ChecklistPanel checks `isDeferred` before `hasRows`, so a
// deferred key that ever carries findings drops them silently. Remove a key here in the same
// change that gives it a producer, exactly as `line_attributes` did.
//
// Mirrors DEFERRED_FEATURES in the backend taxonomy; kept in step by
// tests/test_taxonomy_consistency.py::test_deferred_features_match.
export const DEFERRED_FEATURE_KEYS: ReadonlySet<string> = new Set([
  "origin",
  "alignment_of_views",
  "text_attributes",
  "line_name",
]);

export const COMPARISON_TAXONOMY: Record<string, FeatureItem[]> = {
  drawing_views: [
    { key: "origin", label: "Origin" },
    { key: "alignment_of_views", label: "Alignment of Views" },
    { key: "line_attributes", label: "Line Attributes" },
    { key: "dimensions", label: "Dimensions" },
    { key: "hole_properties", label: "Hole Properties" },
    { key: "chamfer_radius", label: "Chamfer / Radius" },
    { key: "machining_symbol", label: "Machining Symbol" },
    { key: "welding_symbol", label: "Welding Symbol" },
    { key: "geometric_tolerances", label: "Geometric Tolerances" },
    { key: "additional_views", label: "Additional Views" },
    { key: "text_attributes", label: "Text Attributes" },
  ],
  notes_section: [
    { key: "standard_notes", label: "Standard Notes" },
    { key: "special_notes", label: "Special Notes" },
  ],
  bill_of_materials: [
    { key: "material_type", label: "Material Type" },
    { key: "material_specification", label: "Material Specification" },
    { key: "quantity", label: "Quantity" },
    { key: "material_weight", label: "Material Weight" },
    { key: "ballooning", label: "Ballooning" },
    { key: "remarks", label: "Remarks" },
    { key: "numbering_arrangement", label: "Numbering & Arrangement" },
  ],
  title_block: [
    { key: "machine_name", label: "Machine Name" },
    { key: "line_name", label: "Line Name" },
    { key: "scale", label: "Scale" },
    { key: "creation_date", label: "Date of Creation" },
    { key: "designed", label: "Designed" },
    { key: "drawn", label: "Drawn" },
    { key: "quantity", label: "Total Quantity (T. Q'ty)" },
    { key: "stock_quantity", label: "Stock Quantity" },
    { key: "unit_number", label: "Unit No." },
    { key: "part_number", label: "Part No. / Code No." },
    { key: "job_number", label: "Job Number" },
    // 機器記号 + ユニット記号 — one item for both cells, mirroring taxonomy.py. See the note
    // there: the value spans both cells on this client's sheets and is extracted as one string.
    { key: "machine_unit_code", label: "Machine Code / Unit Code" },
    { key: "cross_reference_number", label: "Cross Reference Number" },
    { key: "previous_drawing_number", label: "Previous Drawing Number" },
    { key: "revision_code", label: "Revision Code" },
  ],
  isometric_view: [
    { key: "orientation", label: "Orientation" },
    { key: "scale", label: "Scale" },
    { key: "location", label: "Location" },
  ],
  other_engineering_references: [
    { key: "tree_view_properties", label: "Tree View Properties / Link" },
    { key: "excel_additional_info", label: "Excel (Additional Information)" },
  ],
};

/**
 * Robust detection of Title Block text, including drawing numbers, machine codes,
 * scales (e.g. 1:1.5, 1/1.4), dates (e.g. 04/12/22, 2026/07/03), job numbers (e.g. 2589, 9324),
 * and machine/part names (e.g. Roll Cassette 12" Mill, ロールカセット 12"ミル).
 */
export function isTitleBlockText(text?: string | null): boolean {
  if (!text) return false;
  // The DISPLAYED form, not the stored one — see `cleanCadText`. Every rule below is anchored or
  // word-boundaried, so MTEXT markup left in place breaks them: `{M745221N01}` fails rule 1's
  // `^[A-Z]` on the brace.
  const clean = cleanCadText(text);
  if (!clean) return false;

  // 1. Drawing Numbers / Part Codes (e.g. M745221N01, M745206N01)
  if (DRAWING_NUMBER_RE.test(clean)) return true;

  // 2. Machine Code / Unit Code (e.g. FSRS2, FSRS)
  if (/^[A-Z]{2,}\d+[A-Z\d\-_]*/i.test(clean) || /\bFSRS\d*\b/i.test(clean)) return true;

  // 3. Scale (e.g. 1:1.5, 1/1.4, 1:1, 1/1, SCALE 1:1)
  if (/(SCALE|尺度)?\s*(\d+(\.\d+)?\s*[:/]\s*\d+(\.\d+)?)/i.test(clean)) return true;

  // 4. Dates (e.g. 04/12/22, 2026/07/03, 2026-07-03)
  if (/\b\d{2,4}[\/.-]\d{1,2}[\/.-]\d{1,4}\b/.test(clean)) return true;

  // 5. Machine Name / Part Name / Line Name (e.g. Roll Cassette 12" Mill, ロールカセット 12"ミル, 押工板)
  if (/ロールカセット|カセット|ミル|Cassette|Mill|押工板|機名|品名|ライン/i.test(clean)) return true;
  if (/\b(Roll\s+Cassette|Mill)\b/i.test(clean)) return true;

  // 6. Job Numbers in title block (e.g. 2589, 9324)
  if (/^(2589|9324)$/.test(clean) || /工事番号|job\s*no/i.test(clean)) return true;

  // 7. Standard Title Block keywords and labels
  if (/機名|品名|ライン|尺度|日付|設計|製図|工事番号|改訂|TITLE|DRAWING NO|DWG|SCALE|DATE|REV|DESIGNED|DRAWN|図面番号|図番|整理番号|受領/i.test(clean)) return true;

  return false;
}

/** Ordered sub-item list for a category, with the "Other" bucket always appended last. */
export function getTaxonomyWithOther(category: string): FeatureItem[] {
  const items = COMPARISON_TAXONOMY[category] ?? [];
  return [...items, { key: OTHER_FEATURE_KEY, label: OTHER_FEATURE_LABEL }];
}

/** Display label for a feature key within a category, falling back to the shared 'Other' label. */
export function featureLabel(category: string, featureKey: string | undefined | null): string {
  if (featureKey) {
    const item = (COMPARISON_TAXONOMY[category] ?? []).find(i => i.key === featureKey);
    if (item) return item.label;
  }
  return OTHER_FEATURE_LABEL;
}

/**
 * Callouts that spell a diameter, built from the shared glyph set rather than from a
 * hand-written character class.
 *
 * The classes these replace were `[ØøφΦ]`, and `cleanCadText` transcodes the DXF escape `%%c`
 * to **U+2300 ⌀** — which is in none of them. So `⌀145` was invisible to the hole-property rule
 * and `6×⌀145` was invisible to the material-specification rule, on text that reaches here from
 * every drawing in the corpus. Both then fell through to their branch's catch-all and came out
 * looking classified. See `utils/cadGlyphs.ts`.
 *
 * Module-level and non-global: built once, and `.test` on a `/g` regex would carry `lastIndex`
 * between calls.
 */
const HOLE_COUNT_RE = new RegExp(`\\d+[-x×]\\s*[${DIAMETER_CHARS}MＭ]?\\d+`, 'i');
const DIAMETER_VALUE_RE = new RegExp(`[${DIAMETER_CHARS}]\\s*\\d+`);

/**
 * This client's known title-block signatories.
 *
 * **A lookup, not a rule, and incomplete by construction.** It was written inline as
 * `/design|設計|橋本|増田/` and `/draw|製図|ZHR/`, which reads like a pattern and is not one: of
 * the four signatures in the corpus — `橋本` and `津田` on 設計, `中川` and `ZHR` on 製図 — this
 * list holds two. It cannot be completed either, because the next revision is signed by whoever
 * signs it. Named and separated so nobody mistakes it for a rule again.
 *
 * It still earns its place: when it matches, the answer is right, and `inferFeatureKeyForPair`
 * only needs it to match ONE side of a finding — `橋本 → 津田` resolves through the reference.
 */
const KNOWN_SIGNATORIES = {
  designed: /橋本|増田/,
  drawn: /ZHR/i,
};

/**
 * A bare Japanese personal name: exactly two CJK ideographs and nothing else.
 *
 * Deliberately narrow. It exists to keep an unrecognised signature out of the Machine Name
 * default, not to identify people.
 */
const PERSONAL_NAME_RE = /^[一-鿿]{2}$/;

/**
 * A drawing number: `M745221N01`, `M7452A2N01`, `M745230A01`.
 *
 * **`\d{5,}` was wrong and had been wherever it was written.** Half this corpus's drawing
 * numbers are `M` + a FOUR-digit job block + an alphanumeric tail (`M7452` + `A2N01`), so
 * `^[A-Z]\d{5,}` matched `M745221N01` and missed `M7452A1N01`, `M7452A2N01` and `M745230A01`
 * — on the two pairs currently queued for labelling. It is one constant now because
 * `isTitleBlockText` uses it to decide a marking belongs to the title block at all, and
 * `inferFeatureKey` uses it to decide which sub-item: the two disagreeing would reroute a
 * drawing number into the title block and then fail to recognise it there.
 */
const DRAWING_NUMBER_RE = /^[A-Z]\d{4,}[A-Z\d\-_]*$/i;

/**
 * A material size: `6×⌀145`, `28×185`, `50x50`, `⌀55-15`.
 *
 * The separator comes from `MULTIPLY_CHARS` because a sheet writes it several ways — the hardcoded
 * `[*x×]` this replaces missed `✕ ✖ ⨯ ⨉` and full-width `ｘ`, the same shortfall as the diameter
 * class one line up. `entityPicking.MULTIPLY_MARKS` folds exactly this set for exactly this reason.
 */
const MATERIAL_SIZE_RE = new RegExp(`[\\d.]+\\s*[${MULTIPLY_CHARS}]\\s*[\\d.${DIAMETER_CHARS}]+`, 'i');

/**
 * Infers the fine-grained engineering sub-item (feature) from a marking or finding
 * when its `feature` property is not explicitly set.
 */
export function inferFeatureKey(
  category: string | undefined,
  text?: string,
  entityType?: string,
  explicitFeature?: string,
): string {
  if (explicitFeature && explicitFeature !== OTHER_FEATURE_KEY) {
    return explicitFeature;
  }

  const cat = category || 'drawing_views';
  // **Classify what the user sees.** Callers pass raw `ref_text`/`rev_text` off the marking,
  // and every card renders `cleanCadText` of that same field — so without this line the rules
  // below judge a string nobody is looking at. It is not a near-miss: a real size cell is stored
  // `6×%%c145` and shown `6×⌀145`, and the material-size rule needs digits either side of the
  // `×`. Normalised HERE rather than at each call site, because there are four of them and the
  // fifth will not remember.
  const clean = cleanCadText(text);

  if (cat === 'drawing_views') {
    // Chamfer / Radius: C0.5, R2, C1, etc.
    if (/^[CRＣＲ]\s*\d+/i.test(clean) || /chamfer|radius|面取り/i.test(clean)) {
      return 'chamfer_radius';
    }
    // Hole Properties: 4-ø8, 2-M6, ø10, 6-9キリ, etc.
    if (
      HOLE_COUNT_RE.test(clean) ||
      DIAMETER_VALUE_RE.test(clean) ||
      /^M\d{1,2}(?:\s*[*x×]\s*[\d.]+)?$/i.test(clean) ||
      /キリ|タップ|深さ|穴/i.test(clean)
    ) {
      return 'hole_properties';
    }
    // Machining Symbol: Ra, Rz, ▽, etc.
    if (/[▽▼√]/.test(clean) || /\b(Ra|Rz|Ry)\b/i.test(clean) || /仕上げ|粗さ/i.test(clean)) {
      return 'machining_symbol';
    }
    // Welding Symbol:
    if (/溶接|weld/i.test(clean)) {
      return 'welding_symbol';
    }
    // Geometric Tolerances:
    if (/[◎⟂∥⌓⌒↗⌖⌯]/.test(clean) || /幾何公差|同軸|直角度|平行度|真直度|平面度/i.test(clean)) {
      return 'geometric_tolerances';
    }
    // Origin / Alignment:
    if (/origin|原点/i.test(clean)) return 'origin';
    if (/alignment|整列/i.test(clean)) return 'alignment_of_views';
    // Line Attributes:
    if (entityType === 'LINE' || entityType === 'ARC' || entityType === 'CIRCLE') return 'line_attributes';
    // Default for drawing views entities/texts: Dimensions!
    return 'dimensions';
  }

  if (cat === 'notes_section') {
    if (/special|特記|注記/i.test(clean)) return 'special_notes';
    return 'standard_notes';
  }

  if (cat === 'bill_of_materials') {
    // 1. Ballooning
    if (/balloon|風船|バルーン/i.test(clean)) return 'ballooning';

    // 2. Remarks
    if (/remarks|備考/i.test(clean)) return 'remarks';

    // 3. Numbering & Arrangement
    if (/numbering|arrangement|番号|順序/i.test(clean)) return 'numbering_arrangement';

    // 4. Material Weight
    // The two columns are `素材重量Kg / Material Wt(kg)` and `仕上重量Kg / Finished Wt(kg)`, so a
    // cell carrying any of that header wording is the strongest signal available.
    if (/重量/.test(clean) || /\b(weight|wt)\b/i.test(clean)) return 'material_weight';
    // A value carrying its own unit. Anchored to a LEADING NUMBER (or a lone unit) so a material
    // code ending in G is not read as grams — and note that the `\b(kg|g)\b` this replaces never
    // fired on `0.78kg` at all, because there is no word boundary between `8` and `k`. It managed
    // to be simultaneously too loose and too tight.
    if (/^\d+(\.\d+)?\s*(kg|g)$/i.test(clean) || /^(kg|g)$/i.test(clean)) return 'material_weight';
    if (/\d\s*kg\b/i.test(clean)) return 'material_weight';
    // A BOM weight cell is a BARE DECIMAL -- `0.78`, `0.41`, `.5`. The unit lives in the column
    // HEADER (`素材重量Kg / Material Wt(kg)`, `仕上重量Kg / Finished Wt(kg)`) and never in the
    // cell, so the unit rule above cannot fire on extracted cell text -- which is why every
    // weight fell through to the catch-all and was reported as Material Specification. The
    // backend reads the same signal off the same cells: `marking_builder.inject_bom_markings`
    // normalises the two weight columns with `float()` and a `\.\d{2}$` match.
    //
    // Anchored (not `search`), so a specification like `6×145.5` cannot be claimed here; and
    // checked AFTER the unit forms, so `0.78kg` still resolves by the stronger signal.
    if (/^\d*\.\d+$/.test(clean)) return 'material_weight';

    // 5. Quantity
    // A bare INTEGER is equally the `No.` column and the `Q'ty` column — both are small
    // counting numbers — and text alone cannot separate them; only the cell's COLUMN can, and a
    // manual marking carries no column. Left on quantity, which is where it went before, rather
    // than moved on a guess. The backend does not have this problem: it tags from the column.
    if (/qty|quantity|個数|数量/i.test(clean) || /^\d+\s*(pcs|個)?$/i.test(clean)) return 'quantity';

    // 6. Material Specification (size / 型式 — the `材料寸法/型式 / Dimension` column)
    if (MATERIAL_SIZE_RE.test(clean) || /寸法|型式|仕様/i.test(clean)) return 'material_specification';
    // A cell naming a DIAMETER is stating a size, whatever separator follows it — and it has to
    // be checked before Material Type below, because on this client's sheets the material and
    // its size share one text run (`SS400 ⌀55×15`, `S45C ⌀265×25`, real cached values).
    //
    // Without this, one cell classified two ways across a single finding: the corpus holds
    // `Code checked: SS400 ⌀55-15 vs SS400 ⌀55×15` — the same value, the reference writing the
    // separator as a hyphen and the revision as `×`. The `×` side matched the size rule and the
    // `-` side fell through to Material Type, so a finding's ORIGINAL and REVISION would have
    // been filed under two different headings.
    if (DIAMETER_VALUE_RE.test(clean)) return 'material_specification';

    // 7. Material Type (SS400, SUS304, … — the `材質 / Code` column)
    if (/^(SS\d+|SUS\d+|S\d+C|SCM\d+|SPCC|SPHC|AL|A\d+|FC\d+|FCD\d+|SKD\d+|MC|POM|BRASS|C3604)/i.test(clean) || /材質|材料/i.test(clean)) {
      return 'material_type';
    }

    // No confident match. `other`, not a guess.
    //
    // This returned `material_specification` until 2026-09-01, and it was the only branch in
    // this function that answered a question it had not managed to work out. Everything the
    // seven rules above did not recognise — weights especially — arrived in the checklist under
    // a sub-item heading no human had chosen and no rule supported. That is the expensive
    // shape: a wrong label is indistinguishable from a right one at a glance, so the engineer
    // has no way to see that the classification failed.
    //
    // The backend counterpart states the rule this restores: "Every function here degrades to
    // `taxonomy.OTHER_FEATURE_KEY` on no confident match — never guesses past what the pattern
    // actually supports" (feature_classifier.py); `normalize_feature` says the same.
    //
    // A caller that renders only `COMPARISON_TAXONOMY[category]` will DROP what lands here.
    // Render `getTaxonomyWithOther(category)`, or append the Other bucket once it is populated
    // (`ManualMarkingList`, `computeEngineeringMatrix` both do). A marking an engineer stamped
    // that vanishes from the panel is worse than one filed under the wrong heading.
    return OTHER_FEATURE_KEY;
  }

  if (cat === 'title_block') {
    if (/Roll|Cassette|Mill|ロールカセット|カセット|ミル|machine|機名/i.test(clean)) return 'machine_name';

    // **Both of these are anchored, and that is the whole fix.** The scale rule used to read
    // `/(SCALE|尺度)?\s*(\d+(\.\d+)?\s*[:/]\s*\d+(\.\d+)?)/` — keyword OPTIONAL, no anchors — so
    // it was really "a number, a colon or slash, another number", which every date on every sheet
    // satisfies. `2026/07/03` matched on its leading `2026/07`, and because scale was tested
    // first the entire Date of Creation row was filed under Scale while Date of Creation read
    // *Pending*.
    //
    // A ratio is exactly TWO parts and a date is exactly THREE, so with both anchored to a full
    // match neither can claim the other and the order between them stops mattering. Reordering
    // alone would not have worked: `1/1.4` is a scale, and the date separator class has to
    // include `.` for `2026.07.03`, so a date rule tested first reads `1/1.4` as three parts.
    if (/^\d+(\.\d+)?\s*[:/]\s*\d+(\.\d+)?$/.test(clean) || /scale|尺度/i.test(clean)) return 'scale';
    if (/^\d{1,4}[\/.-]\d{1,2}[\/.-]\d{1,4}$/.test(clean) || /date|日付|年月日/i.test(clean)) {
      return 'creation_date';
    }

    // Upper-right title block / header cells
    if (/ユニット(\s*No)?|unit\s*no/i.test(clean)) return 'unit_number';
    if (/コード(\s*No)?|part\s*no/i.test(clean)) return 'part_number';
    if (/在庫(棚入庫)?|stock\s*q'?ty/i.test(clean)) return 'stock_quantity';
    if (/総製作個数|t\.?\s*q'?ty/i.test(clean)) return 'quantity';

    // `組` is a counter ("16組" = 16 sets), so it states a quantity outright. A BARE integer does
    // not: on these sheets it is equally the upper-left Part No./Unit No. code and a T. Q'ty
    // value, and only the field label separates them — the same limit as the BOM's bare integer.
    if (/qty|数量|個数|^\d+\s*組$/i.test(clean)) return 'quantity';
    if (/job|工事|^(2589|9324|\d{4,5})$/i.test(clean)) return 'job_number';
    if (/unit|code|機器|ユニット|FSRS/i.test(clean) || /^[A-Z]{2,}\d+$/i.test(clean)) return 'machine_unit_code';
    // "PREVIOUS drawing number" needs the word PREVIOUS. This used to claim any `M745221N01`-shaped
    // string, which is the sheet's OWN number — `marking_builder`'s `title_feature_map` deliberately
    // sends `DWG NO` to `other` because the taxonomy has no item for the current drawing number, so
    // the two paths disagreed about a value that appears on every sheet. The panel and the AI
    // checklist filing one drawing number two ways is worse than either answer.
    if (/prev|旧図|旧図番|前図/i.test(clean)) return 'previous_drawing_number';
    if (/cross|参考|関連/i.test(clean)) return 'cross_reference_number';
    if (/rev|改訂|版/i.test(clean)) return 'revision_code';

    // The two signature cells. The LABEL is the real signal; the names are a lookup — see
    // KNOWN_SIGNATORIES for what that list is and why it cannot be relied on alone.
    if (/design|設計/i.test(clean) || KNOWN_SIGNATORIES.designed.test(clean)) return 'designed';
    if (/draw|製図/i.test(clean) || KNOWN_SIGNATORIES.drawn.test(clean)) return 'drawn';
    // A name the lookup does not know. 設計 and 製図 both hold a bare surname and **nothing in
    // the string says which** — only the field label does, and a manual marking carries no
    // field. `other` rather than let it fall to the Machine Name default below, which is how
    // `橋本 → 津田` came to sit under Machine Name with the two signature rows reading *Pending*.
    //
    // The shape is measured, not chosen: all three signatories in the corpus (`津田`, `橋本`,
    // `中川`) are exactly two CJK ideographs, and none of the seven TITLE-2nd-line part names
    // are (`押ェ板` is three and mixed, `廻リ止メ` four, the rest katakana). A two-kanji part
    // name would be misread by this — it has not appeared, and the trade is worth it because
    // the alternative misfiles a person as the machine.
    if (PERSONAL_NAME_RE.test(clean)) return OTHER_FEATURE_KEY;

    // The sheet's OWN drawing number (`M745221N01`). The taxonomy has no item for it — only
    // `previous_drawing_number` and `cross_reference_number`, which it is neither — so `other` is
    // the answer, and it is the answer `marking_builder`'s `title_feature_map` already gives for
    // the `DWG NO` field. Stated explicitly rather than left to the Machine Name default below,
    // which would put a drawing number under the machine's name on every sheet in the corpus.
    if (DRAWING_NUMBER_RE.test(clean)) return OTHER_FEATURE_KEY;

    // Default: the free-text identity fields. Unlike the BOM branch's old catch-all this one is
    // **measured** — of the 15 corpus values that reach it, 12 are the TITLE / TITLE (2nd line)
    // part name or an upper-left Part No./Unit No. code, all of which the backend's own
    // `title_feature_map` and `classify_title_ul_feature` also call `machine_name`. The three it
    // got wrong were the signatures, and the rule above is what takes them out of its way.
    return 'machine_name';
  }

  if (cat === 'isometric_view') {
    if (/scale|尺度/i.test(clean)) return 'scale';
    if (/location|位置/i.test(clean)) return 'location';
    return 'orientation';
  }

  if (cat === 'other_engineering_references') {
    if (/excel/i.test(clean)) return 'excel_additional_info';
    return 'tree_view_properties';
  }

  return OTHER_FEATURE_KEY;
}

/**
 * Resolve a finding's sub-item from **both** of its texts, preferring whichever side a rule can
 * actually identify.
 *
 * ## Why one side is not enough
 *
 * Callers used to pass `m.rev_text || m.ref_text` — the revision, always, and the reference only
 * when the revision was empty. A finding is a *pair*, and the identifying half is not reliably
 * the revision. The live case: `設計` changed from `橋本` to `津田`. `橋本` is one of the known
 * signatories and `津田` is not, so reading the revision first produced the Machine Name default
 * and the whole row was filed under Machine Name while Designed read *Pending* — with the
 * evidence that would have settled it sitting in the other half of the same finding.
 *
 * The rule is "more evidence beats less", not "the reference wins": the revision is still asked
 * first and still wins whenever it identifies anything. Only a fallback answer defers, and only
 * to a non-fallback one.
 *
 * This is why it is not the same as calling `inferFeatureKey` twice and picking either — a
 * fallback is a real answer for a value nothing identifies (`押ェ板` genuinely is the title), so
 * it must lose only to a *specific* answer, never to another fallback.
 */
export function inferFeatureKeyForPair(
  category: string | undefined,
  refText?: string | null,
  revText?: string | null,
  entityType?: string,
  explicitFeature?: string | null,
): string {
  if (explicitFeature && explicitFeature !== OTHER_FEATURE_KEY) return explicitFeature;

  const cat = category || 'drawing_views';

  // **`other` is the ONLY answer that defers, and the reason is worth reading before widening
  // it.** The first version also deferred on each category's *fallback* — the branch's last
  // `return` — on the theory that a fallback means "could not tell". For two categories it does
  // not: `drawing_views` falls back to `dimensions` and `notes_section` to `standard_notes`, and
  // both are substantive. A bare `145` **is** a plain dimension; that is an answer, not a shrug.
  //
  // The damage was immediate and it was reported: `⌀145 → 145` had the revision correctly reading
  // `dimensions`, that got treated as a non-answer, the reference `⌀145` was consulted and
  // matched the diameter rule, and the whole Drawing Views category emptied into Hole Properties
  // with Dimensions left showing *Pending*. Three rows moved that nobody asked to move.
  //
  // `other` alone is enough for what this function was built for: `橋本 → 津田` defers because
  // `津田` resolves to `other` through the personal-name rule — a specific key, but explicitly
  // "no identification" — not because `machine_name` happens to be the title block's fallback.
  // A side with no text is not evidence, and must not get a vote. An ADDED finding has an
  // empty reference, and `inferFeatureKey('')` returns the branch's fallback — so without this
  // an empty half would answer `machine_name` and override a revision that had correctly
  // resolved to `other`, putting every drawing number back under Machine Name.
  const answerFor = (text?: string | null): string | null =>
    cleanCadText(text) ? inferFeatureKey(cat, text ?? undefined, entityType) : null;

  const fromRev = answerFor(revText);
  if (fromRev && fromRev !== OTHER_FEATURE_KEY) return fromRev;

  const fromRef = answerFor(refText);
  if (fromRef && fromRef !== OTHER_FEATURE_KEY) return fromRef;

  // Neither side identified anything. Prefer the revision's answer, then the reference's, and
  // fall back to the branch default only when the finding carries no text at all.
  return fromRev ?? fromRef ?? inferFeatureKey(cat, undefined, entityType);
}

export interface MatrixItemSummary {
  key: string;
  label: string;
  isDeferred: boolean;
  verdict: 'PASS' | 'DISCREPANCY' | 'NO_SIGNAL' | 'UNCHECKED';
  verdictLabel: string;
  findingsCount: number;
  changedCount: number;
  addedCount: number;
  removedCount: number;
  matchedCount: number;
}

export interface CategoryMatrixSummary {
  categoryKey: string;
  categoryLabel: string;
  items: MatrixItemSummary[];
  totalItems: number;
  passedItems: number;
  discrepancyItems: number;
  deferredItems: number;
}

export interface EngineeringMatrixOverview {
  categories: CategoryMatrixSummary[];
  totalItems: number;
  totalPassed: number;
  totalDiscrepancies: number;
  totalDeferred: number;
  coveragePercent: number;
}

const CATEGORY_DISPLAY_NAMES: Record<string, string> = {
  drawing_views: 'Drawing Views',
  notes_section: 'Notes',
  bill_of_materials: 'Bill of Materials',
  title_block: 'Title Block',
  isometric_view: 'Isometric View',
  other_engineering_references: 'Others',
};

/**
 * Computes the 6-category / 34-sub-item engineering verification matrix from finding rows or markings.
 */
export function computeEngineeringMatrix(
  findingsOrMarkings: Array<{ category?: string; feature?: string | null; status?: string; text?: string; ref_text?: string; rev_text?: string; entity_type?: string }>,
  mode: 'ai' | 'manual' = 'ai',
): EngineeringMatrixOverview {
  const categories: CategoryMatrixSummary[] = [];
  let totalItems = 0;
  let totalPassed = 0;
  let totalDiscrepancies = 0;
  let totalDeferred = 0;

  for (const [catKey, namedItems] of Object.entries(COMPARISON_TAXONOMY)) {
    // The Other bucket is scored only when something actually lands in it, so an audit with
    // nothing unclassified still reports the taxonomy's own item count and its coverage
    // percentage is unchanged. When something DOES land there it has to be counted: this loop
    // walks the named sub-items alone, so a finding classified `other` -- which `inferFeatureKey`
    // now returns for a BOM value it cannot place, and which the backend returns for DWG_NO and
    // TITLE -- was in no row of the matrix and in none of its totals. A discrepancy missing from
    // the summary reads as a clean audit.
    const anyOther = findingsOrMarkings.some((f) => {
      const targetText = f.text || f.rev_text || f.ref_text || '';
      const effCat = (f.category === 'drawing_views' && isTitleBlockText(targetText))
        ? 'title_block'
        : (f.category || 'drawing_views');
      if (effCat !== catKey) return false;
      return inferFeatureKeyForPair(effCat, f.ref_text, targetText, f.entity_type, f.feature) === OTHER_FEATURE_KEY;
    });
    const featureItems = anyOther ? getTaxonomyWithOther(catKey) : namedItems;
    const catLabel = CATEGORY_DISPLAY_NAMES[catKey] || catKey;
    const items: MatrixItemSummary[] = [];
    let catPassed = 0;
    let catDiscrepancies = 0;
    let catDeferred = 0;

    for (const feat of featureItems) {
      const isDeferred = DEFERRED_FEATURE_KEYS.has(feat.key);
      const matching = findingsOrMarkings.filter((f) => {
        const targetText = f.text || f.rev_text || f.ref_text || '';
        const effCat = (f.category === 'drawing_views' && isTitleBlockText(targetText))
          ? 'title_block'
          : (f.category || 'drawing_views');
        const cMatch = effCat === catKey;
        if (!cMatch) return false;
        const resolvedFeature = inferFeatureKeyForPair(effCat, f.ref_text, targetText, f.entity_type, f.feature);
        return resolvedFeature === feat.key;
      });

      let changedCount = 0;
      let addedCount = 0;
      let removedCount = 0;
      let matchedCount = 0;

      for (const m of matching) {
        const s = (m.status || '').toUpperCase();
        if (s.includes('CHANGE') || s.includes('MIS') || s === 'CONFLICT') changedCount++;
        else if (s.includes('ADD')) addedCount++;
        else if (s.includes('REMOV')) removedCount++;
        else if (s.includes('MATCH')) matchedCount++;
      }

      const discCount = changedCount + addedCount + removedCount;
      let verdict: 'PASS' | 'DISCREPANCY' | 'NO_SIGNAL' | 'UNCHECKED' = 'PASS';
      let verdictLabel = '✓ PASS';

      if (discCount > 0) {
        verdict = 'DISCREPANCY';
        verdictLabel = `⚠️ ${discCount} ${discCount === 1 ? 'FINDING' : 'FINDINGS'}`;
        catDiscrepancies++;
      } else if (matching.length > 0 && matchedCount > 0) {
        verdict = 'PASS';
        verdictLabel = '✓ PASS';
        catPassed++;
      } else if (mode === 'manual') {
        // In manual check mode: if no markings recorded yet, it is pending verification
        verdict = 'UNCHECKED';
        verdictLabel = '⚪ PENDING';
        catDeferred++;
      } else if (isDeferred && matching.length === 0) {
        verdict = 'NO_SIGNAL';
        verdictLabel = '⚪ NO SIGNAL';
        catDeferred++;
      } else {
        verdict = 'PASS';
        verdictLabel = '✓ PASS';
        catPassed++;
      }

      items.push({
        key: feat.key,
        label: feat.label,
        isDeferred,
        verdict,
        verdictLabel,
        findingsCount: matching.length,
        changedCount,
        addedCount,
        removedCount,
        matchedCount,
      });
    }

    totalItems += featureItems.length;
    totalPassed += catPassed;
    totalDiscrepancies += catDiscrepancies;
    totalDeferred += catDeferred;

    categories.push({
      categoryKey: catKey,
      categoryLabel: catLabel,
      items,
      totalItems: featureItems.length,
      passedItems: catPassed,
      discrepancyItems: catDiscrepancies,
      deferredItems: catDeferred,
    });
  }

  const coveragePercent = totalItems > 0 ? Math.round(((totalPassed + totalDiscrepancies) / totalItems) * 100) : 100;

  return {
    categories,
    totalItems,
    totalPassed,
    totalDiscrepancies,
    totalDeferred,
    coveragePercent,
  };
}
