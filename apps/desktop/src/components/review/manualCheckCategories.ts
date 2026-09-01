import { COMPARISON_TAXONOMY, isTitleBlockText } from '../../utils/comparisonTaxonomy';
import { DIAMETER_CHARS, MULTIPLY_CHARS, cleanCadText } from '../../utils/cadGlyphs';

/**
 * Diameter and size callouts, from the shared glyph set.
 *
 * These read `[ØøφΦ]` until 2026-09-01 and therefore matched none of the **U+2300 ⌀** that
 * `cleanCadText` produces from the DXF `%%c` escape — so `⌀125` did not read as a drawing view
 * and `6×⌀145` did not read as a bill-of-materials value. Both still returned a category, from
 * the generic fallthrough at the bottom of `inferCategoryForEntity`, which is why the gap was
 * invisible. `utils/cadGlyphs.ts` has the full set and the rest of the story.
 */
const MATERIAL_SIZE_RE = new RegExp(`[\\d.]+\\s*[${MULTIPLY_CHARS}]\\s*[\\d.${DIAMETER_CHARS}]+`, 'i');
const DIAMETER_VALUE_RE = new RegExp(`[${DIAMETER_CHARS}]\\s*[\\d.]+`);
const HOLE_COUNT_RE = new RegExp(`\\d+[-x×]\\s*[${DIAMETER_CHARS}MＭ]?\\d+`, 'i');

/**
 * The six categories a marking can carry, for the stamp modal's selector.
 *
 * ## The keys are derived, not copied
 *
 * `Object.keys(COMPARISON_TAXONOMY)` is the TS mirror of `taxonomy.py`, and
 * `tests/test_taxonomy_consistency.py` parses both files and fails if either side moves alone.
 * Deriving from it means this list cannot drift from what the backend will accept — and a
 * marking filed under a category the backend rejects is a stamp the engineer made and lost.
 *
 * A third hand-written list was the obvious alternative (`CorrectionControls.tsx` has one, and
 * `ground_truth.py` reads `taxonomy.Category` directly). Three copies of one rule is the drift
 * this codebase has already paid for four times.
 *
 * Labels are local because no shared category-label map exists — only feature labels. They are
 * cosmetic, and `manualCheckCategories.test.ts` pins that the map covers exactly the derived
 * keys, so a new category cannot appear unlabelled.
 */

const LABELS: Record<string, string> = {
  drawing_views: 'Drawing Views',
  notes_section: 'Notes',
  bill_of_materials: 'Bill of Materials',
  title_block: 'Title Block',
  isometric_view: 'Isometric View',
  other_engineering_references: 'Others',
};

export const CATEGORY_KEYS: readonly string[] = Object.keys(COMPARISON_TAXONOMY);

export function categoryLabel(key: string): string {
  return LABELS[key] ?? key;
}

export const CATEGORY_OPTIONS: readonly { key: string; label: string }[] = CATEGORY_KEYS.map(
  (key) => ({ key, label: categoryLabel(key) }),
);

/**
 * The live marking already recorded against this entity, if there is one.
 *
 * ## Why this has to exist
 *
 * Without it an entity can be marked twice. The menu offered the full status list whatever had
 * already been recorded, so the same value could be filed MATCHED and then ADDED — two human
 * statements contradicting each other, both live, with nothing downstream able to say which the
 * engineer meant. In a corpus whose whole value is that every row is a person's judgement, that
 * is the most expensive kind of bad data: it looks exactly like good data.
 *
 * ## Matched on HANDLE, not entity id
 *
 * A DXF handle survives re-extraction; an entity id does not — `/reextract` mints new ones, and
 * `EntityAddress` exists precisely because of that. Matching on id would quietly stop finding
 * anything the first time a drawing was re-extracted, and the symptom would be the double-marking
 * this prevents, returning silently.
 *
 * Side matters too: the same handle can appear on both sheets, and a marking recorded against the
 * reference says nothing about the revision's entity of the same name.
 */
export function findMarkingForEntity<
  T extends { retracted_at?: string | null; ref_handle?: string | null; rev_handle?: string | null },
>(markings: T[], picked: { side: 'ref' | 'rev'; handle?: string | null } | null): T | null {
  // A block-exploded child carries no handle. Nothing can be concluded from that — every such
  // entity would match every other — so it is treated as unmarked rather than guessed at.
  if (!picked?.handle) return null;
  const key = picked.side === 'ref' ? 'ref_handle' : 'rev_handle';
  return (
    markings.find((m) => !m.retracted_at && m[key] && m[key] === picked.handle) ?? null
  );
}

/**
 * Which category an entity belongs to, given the zone it sits in.
 *
 * ## This is a convenience, and it is recorded as one
 *
 * Every marking written through this map carries `category_source: 'zone'`. That is not
 * bookkeeping — the mutation corpus's attribution figure is a known tautology because its labels
 * come from `zone_detector` (moving the zone boxes shifted attribution 0.81 → 0.74 with no engine
 * change at all), and the human pairs were the first attribution numbers here that were not.
 * Deriving the category re-creates exactly that circularity, so the rows have to be separable
 * from the ones a person chose or the whole figure quietly reverts to measuring the detector
 * against itself.
 *
 * ## The two vocabularies do not line up one-to-one
 *
 * Zones are regions of a sheet; categories are kinds of finding. Four map cleanly. The rest do
 * not, and are deliberately left unmapped rather than forced:
 *
 * - `tolerance` and `shim` are tables the comparison treats separately and the taxonomy has no
 *   category for — guessing `other_engineering_references` would file them under a bucket that
 *   means "unclassified", which is a claim rather than an absence;
 * - `title_upper_left` is a second title block on some sheets, so it does map;
 * - an entity in NO measured zone gets nothing, and the engineer is asked.
 *
 * `null` therefore means "ask", not "unknown category". The caller must not substitute a default.
 */
const ZONE_TO_CATEGORY: Record<string, string> = {
  views: 'drawing_views',
  notes: 'notes_section',
  bom: 'bill_of_materials',
  title: 'title_block',
  title_upper_left: 'title_block',
  iso: 'isometric_view',
};

export function categoryForZone(zone: string | null | undefined): string | null {
  if (!zone) return null;
  const category = ZONE_TO_CATEGORY[zone] ?? null;
  // Pinned against the live taxonomy rather than trusted: a category renamed on the backend
  // would otherwise be written into markings that every downstream group-by silently drops.
  return category && CATEGORY_KEYS.includes(category) ? category : null;
}

/**
 * Re-exported, not reimplemented.
 *
 * This file carried a byte-identical 30-line copy of `isTitleBlockText` until 2026-09-01, used
 * only by `inferCategoryForEntity` below while every other caller imported the original. The
 * two were still in agreement, which is what makes the shape dangerous rather than harmless:
 * fixing the original to classify `cleanCadText(text)` instead of the raw stored string
 * corrected one copy and left this one deciding categories off `{...}` MTEXT markup and `%%c`
 * escapes. Duplication in this codebase does not announce itself by breaking -- it keeps
 * working while the copies slowly disagree, and the output stays plausible.
 */
export { isTitleBlockText } from '../../utils/comparisonTaxonomy';

/**
 * Infers the category for an entity from its zone, or falls back to intelligent
 * text & CAD entity heuristics. If it is genuinely ambiguous or blank, returns null so the user is prompted.
 */
export function inferCategoryForEntity(
  zone: string | null | undefined,
  text?: string,
  entityType?: string,
): string | null {
  const fromZone = categoryForZone(zone);
  if (fromZone) return fromZone;

  // The DISPLAYED form. Raw entity text carries `%%c` escapes and MTEXT markup, and every rule
  // below is written against the symbols those render as — see `cleanCadText`.
  const clean = cleanCadText(text);

  // 1. Bill of Materials (BOM)
  if (
    /^(SS\d+|SUS\d+|S\d+C|SCM\d+|SPCC|SPHC|AL|A\d+|FC\d+|FCD\d+|SKD\d+|MC|POM|BRASS|C3604)/i.test(clean) ||
    MATERIAL_SIZE_RE.test(clean) ||
    /材質|個数|数量|重量|素材重量|仕上重量|寸法|型式|仕様|備考/i.test(clean) ||
    /\b(kg|g|weight)\b/i.test(clean) ||
    /\d+(\.\d+)?\s*(kg|g)\b/i.test(clean)
  ) {
    return 'bill_of_materials';
  }

  // 2. Title Block
  if (isTitleBlockText(clean)) {
    return 'title_block';
  }

  // 3. Notes
  if (/注記|特記|NOTE|NOTES|GENERAL NOTES/i.test(clean)) {
    return 'notes_section';
  }

  // 4. Isometric View
  if (/ISOMETRIC|等角図|3D VIEW/i.test(clean)) {
    return 'isometric_view';
  }

  // 5. Drawing Views (Dimensions, Tolerances, Chamfers, Holes, Geometry, Line/Arc/Circle)
  if (
    /^[CRＣＲ]\s*\d+/i.test(clean) ||
    DIAMETER_VALUE_RE.test(clean) ||
    HOLE_COUNT_RE.test(clean) ||
    /^M\d{1,2}(?:\s*[*x×]\s*[\d.]+)?$/i.test(clean) ||
    /^[+-]?\d+(\.\d+)?([°deg]|\s*±\s*[\d.]+)?$/i.test(clean) ||
    /[▽▼√◎⟂∥⌓⌒↗⌖⌯]/.test(clean) ||
    /キリ|タップ|深さ|穴|面取り|幾何公差/i.test(clean) ||
    entityType === 'LINE' ||
    entityType === 'ARC' ||
    entityType === 'CIRCLE' ||
    entityType === 'LWPOLYLINE' ||
    entityType === 'DIMENSION'
  ) {
    return 'drawing_views';
  }

  // Standard numeric or alphanumeric CAD text (e.g. 125, 40, 18, 4 ロール)
  if (clean.length > 0 && /[\d\w]/.test(clean)) {
    return 'drawing_views';
  }

  // Genuinely ambiguous / blank: prompt the engineer with category selector
  return null;
}
