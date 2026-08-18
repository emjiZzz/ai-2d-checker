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
