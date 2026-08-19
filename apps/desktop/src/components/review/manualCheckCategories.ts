import { COMPARISON_TAXONOMY } from '../../utils/comparisonTaxonomy';

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
  bill_of_materials: 'BOM',
  title_block: 'Title Block',
  isometric_view: 'Isometric View',
  other_engineering_references: 'Other References',
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
