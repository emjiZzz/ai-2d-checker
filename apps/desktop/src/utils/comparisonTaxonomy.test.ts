import { describe, expect, it } from 'vitest';
import {
  COMPARISON_TAXONOMY,
  OTHER_FEATURE_KEY,
  computeEngineeringMatrix,
  inferFeatureKey,
  inferFeatureKeyForPair,
  isTitleBlockText,
} from './comparisonTaxonomy';

/**
 * Sub-item placement for Bill of Materials values.
 *
 * A manual marking carries no `feature` — `ManualCheckMarking` has `category`, `ref_text` and
 * `rev_text` and nothing finer — so in a manual-check room `inferFeatureKey` is the *whole*
 * story for where a stamped value appears in the panel. That is why these are text-level
 * assertions on real cell contents rather than a mirror of the rule list.
 */
describe('inferFeatureKey — bill_of_materials', () => {
  const bom = (text: string) => inferFeatureKey('bill_of_materials', text);

  it('files a bare decimal as a weight, because that is what a BOM weight cell looks like', () => {
    // The regression this exists for. `0.78` and `0.41`/`0.39` are 素材重量 / 仕上重量 cells;
    // the unit is in the column header, never in the cell, so the `kg` rule cannot fire and
    // all three used to reach the catch-all and be reported as Material Specification.
    expect(bom('0.78')).toBe('material_weight');
    expect(bom('0.41')).toBe('material_weight');
    expect(bom('0.39')).toBe('material_weight');
  });

  it('still prefers an explicit unit when the cell carries one', () => {
    expect(bom('0.78kg')).toBe('material_weight');
    expect(bom('素材重量')).toBe('material_weight');
  });

  it('does not let the decimal rule steal a specification', () => {
    // Anchored, so a size with a decimal in it is still a size.
    expect(bom('6×⌀145')).toBe('material_specification');
    expect(bom('6×145.5')).toBe('material_specification');
    expect(bom('材料寸法')).toBe('material_specification');
  });

  it('files a material designation as Material Type', () => {
    expect(bom('SS400')).toBe('material_type');
    expect(bom('SUS304')).toBe('material_type');
    expect(bom('材質')).toBe('material_type');
  });

  it('answers `other` rather than guessing when nothing matches', () => {
    // The default was `material_specification`, which put a heading no human chose and no rule
    // supported onto every value the seven rules did not recognise. A wrong label is
    // indistinguishable from a right one at a glance; `other` is legible as a failure.
    expect(bom('ﾃﾞｰﾀ無し')).toBe(OTHER_FEATURE_KEY);
    expect(bom('---')).toBe(OTHER_FEATURE_KEY);
  });

  it('honours an explicit backend feature over any text guess', () => {
    // The backend tags from the COLUMN, which is strictly better evidence than the text.
    expect(inferFeatureKey('bill_of_materials', '0.78', undefined, 'material_specification')).toBe(
      'material_specification',
    );
  });
});

describe('computeEngineeringMatrix — the Other bucket', () => {
  const namedBomItems = COMPARISON_TAXONOMY.bill_of_materials.length;

  const bomOf = (rows: Array<{ text: string; status: string }>) =>
    computeEngineeringMatrix(
      rows.map((r) => ({ category: 'bill_of_materials', text: r.text, status: r.status })),
    ).categories.find((c) => c.categoryKey === 'bill_of_materials')!;

  it('is absent when nothing is unclassified, so coverage is unchanged', () => {
    const cat = bomOf([{ text: 'SS400', status: 'MATCHED' }]);
    expect(cat.items.map((i) => i.key)).not.toContain(OTHER_FEATURE_KEY);
    expect(cat.totalItems).toBe(namedBomItems);
  });

  it('appears — and is counted — as soon as something lands in it', () => {
    // The loop walks the named sub-items only, so before this an `other` finding was in no row
    // of the matrix and in none of its totals: a discrepancy missing from the summary reads as
    // a clean audit.
    const cat = bomOf([{ text: '---', status: 'CHANGED' }]);
    const other = cat.items.find((i) => i.key === OTHER_FEATURE_KEY);
    expect(other).toBeDefined();
    expect(other!.verdict).toBe('DISCREPANCY');
    expect(other!.changedCount).toBe(1);
    expect(cat.discrepancyItems).toBe(1);
    expect(cat.totalItems).toBe(namedBomItems + 1);
  });

  it('routes a weight change to Material Weight, not Material Specification', () => {
    const cat = bomOf([{ text: '0.39', status: 'CHANGED' }]);
    const byKey = Object.fromEntries(cat.items.map((i) => [i.key, i]));
    expect(byKey.material_weight.findingsCount).toBe(1);
    expect(byKey.material_specification.findingsCount).toBe(0);
  });
});

describe('inferFeatureKey — the ⌀ that `%%c` transcodes to', () => {
  // `cleanCadText` turns the DXF escape `%%c` into U+2300 ⌀, and every character class in this
  // file was written against `[ØøφΦ]` — U+00D8, U+00F8, U+03C6, U+03A6 — so none of them could
  // see it. Both branches still returned a plausible feature from their catch-all, which is why
  // this never surfaced as a bug: the answer was wrong, not missing.
  it('reads a diameter callout as a hole property, not a plain dimension', () => {
    expect(inferFeatureKey('drawing_views', '⌀145')).toBe('hole_properties');
    expect(inferFeatureKey('drawing_views', '4-⌀8')).toBe('hole_properties');
    // The spellings that always worked must keep working.
    expect(inferFeatureKey('drawing_views', 'ø125')).toBe('hole_properties');
  });

  it('reads a ⌀ material size as a specification', () => {
    expect(inferFeatureKey('bill_of_materials', '6×⌀145')).toBe('material_specification');
    expect(inferFeatureKey('bill_of_materials', '28×⌀185')).toBe('material_specification');
  });
});

describe('inferFeatureKey — the RAW stored text, not the displayed text', () => {
  /**
   * The defect the ⌀ tests above missed, because they were written against the string the CARD
   * shows. Callers pass `m.rev_text` straight off the marking, and the card renders
   * `cleanCadText` of that same field — so a rule tested on the display form is not tested at
   * all. These strings are verbatim out of `storage/cache/`.
   */
  const bom = (text: string) => inferFeatureKey('bill_of_materials', text);

  it('classifies a size cell that stores its diameter as %%c', () => {
    // The screenshot's row. Stored `6×%%c145`, displayed `6×⌀145`, was landing in Other.
    expect(bom('6×%%c145')).toBe('material_specification');
  });

  it('was positional before, and must not be now', () => {
    // `%%c55×15` matched on its `55×15` while `6×%%c145` did not, so one column classified two
    // ways depending on where the escape sat. Both are real cached values.
    expect(bom('SS400 %%c55×15')).toBe('material_specification');
    expect(bom('S45C %%c265×25')).toBe('material_specification');
  });

  it('folds the CP932 mis-decode of × the same way the canvas does', () => {
    // `cleanCadText` maps `ラ` → `x`; classifying the raw string leaves a Katakana between the
    // two numbers and no size rule can match it.
    expect(bom('6ラ%%c145')).toBe('material_specification');
  });

  it('sees through MTEXT markup', () => {
    // Note the escaped backslash: `'{\A1;0.78}'` in TS is the string `{A1;0.78}`, which cleans
    // to `A1;0.78` and is then a legitimate `A\d+` material code. The alignment tag needs a real
    // backslash to be one.
    expect(bom('{\\A1;0.78}')).toBe('material_weight');
  });

  it('reads a raw diameter callout in a drawing view as a hole property', () => {
    expect(inferFeatureKey('drawing_views', '%%c145')).toBe('hole_properties');
  });
});

describe('isTitleBlockText — same normalization', () => {
  it('is not defeated by MTEXT braces', () => {
    expect(isTitleBlockText('M745221N01')).toBe(true);
    // `^[A-Z]` fails on the brace, so the drawing number stopped being a drawing number.
    expect(isTitleBlockText('{M745221N01}')).toBe(true);
  });

  it('is one implementation', async () => {
    // `manualCheckCategories.ts` held a byte-identical copy until 2026-09-01 and re-exports now.
    // Identical copies are exactly the ones that drift, and this pair had already started to.
    const mod = await import('../components/review/manualCheckCategories');
    expect(mod.isTitleBlockText).toBe(isTitleBlockText);
  });
});

describe('inferFeatureKey — every distinct BOM value in the committed corpus', () => {
  /**
   * Verbatim `text_content` values from the BOM markings in `storage/cache/`, in the raw form the
   * classifier is actually handed. Chosen examples proved nothing here: the ⌀ tests written first
   * used the *displayed* spelling and passed while the panel was visibly wrong, and this sweep is
   * what caught the two remaining defects — the `%%c` escape and the hyphen separator.
   */
  const CORPUS: [string, string][] = [
    ['1', 'quantity'],
    ['S45C %%c265×25', 'material_specification'],
    ['S45C %%c265×20', 'material_specification'],
    ['SS400 %%c55×15', 'material_specification'],
    // Same cell as the line above, on the other sheet of the same pair — the reference writes the
    // separator as a hyphen. These MUST agree, or one finding's ORIGINAL and REVISION are filed
    // under two different headings.
    ['SS400 %%c55-15', 'material_specification'],
    ['SS400 6×%%c145', 'material_specification'],
    ['SS400 4.5×40×52', 'material_specification'],
    ['オイレス#300 25×45×180', 'material_specification'],
    ['10.81', 'material_weight'],
    ['8.65', 'material_weight'],
    ['5.31', 'material_weight'],
    ['0.28', 'material_weight'],
    ['0.07', 'material_weight'],
    ['1.42', 'material_weight'],
    ['15.13', 'material_weight'],
    // 「表ニヨル」— "as per the table". A deferral, not a value; `other` is the honest answer.
    ['表ニヨル', OTHER_FEATURE_KEY],
  ];

  it.each(CORPUS)('%s → %s', (text, expected) => {
    expect(inferFeatureKey('bill_of_materials', text)).toBe(expected);
  });
});

describe('inferFeatureKeyForPair — every title-block pair in the committed corpus', () => {
  /**
   * `[ref, rev, expected]`, verbatim from the title-block markings in `storage/cache/`.
   *
   * The expected column is not invented here: for all but the two noted below it is the feature
   * the BACKEND assigns from the field key it read (`marking_builder.title_feature_map`,
   * `classify_title_ul_feature`). That makes this an agreement test between the two paths — the
   * AI checklist groups on the backend's `feature` and the manual panel infers from text, and
   * when they disagree the same value is filed under two headings depending on which room you
   * opened.
   */
  const CORPUS: [string, string, string][] = [
    // 設計 / 製図. The reported row: the reference is a known signatory and the revision is not,
    // and `m.rev_text || m.ref_text` asked only the revision — so the pair fell to the Machine
    // Name default with the evidence sitting in its other half.
    ['橋本', '津田', 'designed'],
    ['中川', 'ZHR', 'drawn'],
    // Neither side is a known signatory, and 設計 and 製図 both hold a bare surname with
    // nothing in the string to separate them. `other` is the honest answer; Machine Name was not.
    ['津田', '津田', OTHER_FEATURE_KEY],

    // 尺度. Two parts.
    ['1:1.5', '1/1.4', 'scale'],
    ['1:2.5', '1/2.5', 'scale'],
    ['1:1', '1/1', 'scale'],
    ['1:3', '1/3', 'scale'],
    ['1:4', '1/4', 'scale'],
    // Y/M/D. Three parts — and the reported row: this was filed under Scale, because the scale
    // rule's `(SCALE|尺度)?` prefix was optional and it was not anchored.
    ['04/12/22', '2026/07/03', 'creation_date'],
    ['2010/09/13', '2026/07/03', 'creation_date'],

    // TITLE and TITLE (2nd line) — the free-text identity fields the Machine Name default exists
    // for. All of these reach it, and the backend calls them `machine_name` too.
    ['Roll Cassette 12"Mill', 'ロールカセット 12"ミル', 'machine_name'],
    ['', '押ェ板', 'machine_name'],
    ['', 'カラ－', 'machine_name'],
    ['', 'シム', 'machine_name'],
    ['', '基準スペーサー：3', 'machine_name'],
    ['', 'ライナ－', 'machine_name'],
    ['', 'バランスビ－ム', 'machine_name'],
    ['', '廻リ止メ', 'machine_name'],
    // Upper-left Unit No. / Part No. — `classify_title_ul_feature` also answers `machine_name`.
    ['', '45', 'machine_name'],
    ['', '2A1', 'machine_name'],
    ['', '206', 'machine_name'],

    ['2589', '9324', 'job_number'],
    ['', 'FSRS2', 'machine_unit_code'],
    // The sheet's own DWG No. The taxonomy has no item for it, and `title_feature_map` says
    // `other` — so claiming `previous_drawing_number` on the shape alone was the panel
    // disagreeing with the engine about a value on every sheet.
    ['', 'M745221N01', OTHER_FEATURE_KEY],
    ['', 'M7452A2N01', OTHER_FEATURE_KEY],

    ['', '16組', 'quantity'],
  ];

  it.each(CORPUS)('%s → %s = %s', (ref, rev, expected) => {
    expect(inferFeatureKeyForPair('title_block', ref, rev)).toBe(expected);
  });

  it('leaves a bare integer on the Machine Name default, which the backend gets right and text cannot', () => {
    // T. Q'ty is `4`; the upper-left Part No. is `206`. Both are bare integers in the same zone
    // and only the field label separates them. Recorded rather than guessed at — the same limit
    // as the BOM's `No.` vs `Q'ty`.
    expect(inferFeatureKeyForPair('title_block', '', '4')).toBe('machine_name');
  });
});

describe('inferFeatureKeyForPair — how the two sides combine', () => {
  it('prefers the revision whenever the revision identifies anything', () => {
    expect(inferFeatureKeyForPair('title_block', '橋本', '2026/07/03')).toBe('creation_date');
  });

  it('falls back to the reference only when the revision could not tell', () => {
    expect(inferFeatureKeyForPair('title_block', '1:1.5', '津田')).toBe('scale');
  });

  it('returns the fallback when neither side identifies anything', () => {
    expect(inferFeatureKeyForPair('title_block', 'シム', '押ェ板')).toBe('machine_name');
  });

  it('still honours an explicit backend feature over both', () => {
    expect(inferFeatureKeyForPair('title_block', '橋本', '津田', undefined, 'drawn')).toBe('drawn');
  });
});

describe('inferFeatureKeyForPair — only `other` defers to the other side', () => {
  /**
   * The regression this exists for. `inferFeatureKeyForPair` first deferred on each category's
   * FALLBACK as well, on the theory that a fallback means "could not tell". For `drawing_views`
   * the fallback is `dimensions`, which is a substantive answer — a bare `145` IS a plain
   * dimension — so treating it as a shrug sent every one of these to the reference, which
   * matched the diameter rule, and Drawing Views emptied into Hole Properties while Dimensions
   * read *Pending*.
   *
   * Expected values are the backend's own, for these exact strings, out of `storage/cache/`.
   */
  it('keeps a dimension whose reference happened to carry a ⌀', () => {
    expect(inferFeatureKeyForPair('drawing_views', 'ø145', '145')).toBe('dimensions');
    expect(inferFeatureKeyForPair('drawing_views', 'ø100', '100')).toBe('dimensions');
    expect(inferFeatureKeyForPair('drawing_views', 'ø125', '125')).toBe('dimensions');
  });

  it('still reads a real hole callout as one', () => {
    expect(inferFeatureKeyForPair('drawing_views', '6-6.6キリ11ザグリ深6.5', '６－９キリ')).toBe(
      'hole_properties',
    );
  });

  it('does not let a reference override a substantive note classification', () => {
    // `standard_notes` is `notes_section`'s fallback and is equally substantive: a notes-zone
    // finding IS some kind of note, which is the argument `classify_notes_feature` makes for the
    // same default on the backend. The reference being a SPECIAL note must not reclassify it.
    expect(inferFeatureKeyForPair('notes_section', '特記事項', 'ミガキ仕上ゲ')).toBe('standard_notes');
  });

  it('ignores a side with no text, because an absent half is not evidence', () => {
    // An ADDED finding has an empty reference. `inferFeatureKey('')` returns the branch fallback,
    // so an unguarded empty half answers `machine_name` and overrides a revision that had
    // correctly resolved to `other` — which put every drawing number back under Machine Name.
    expect(inferFeatureKeyForPair('title_block', '', 'M745221N01')).toBe(OTHER_FEATURE_KEY);
    expect(inferFeatureKeyForPair('title_block', null, '津田')).toBe(OTHER_FEATURE_KEY);
  });
});
