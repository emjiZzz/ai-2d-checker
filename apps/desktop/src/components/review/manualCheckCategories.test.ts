import { describe, it, expect } from 'vitest';
import { CATEGORY_KEYS, CATEGORY_OPTIONS, categoryLabel } from './manualCheckCategories';
import { COMPARISON_TAXONOMY } from '../../utils/comparisonTaxonomy';

/**
 * The stamp modal's category list must be the taxonomy, not a copy of it.
 *
 * A marking filed under a category the backend rejects is a stamp the engineer made and lost;
 * one filed under a category the backend accepts but no report groups by is worse, because it
 * is silently dropped from every downstream count. `ground_truth.py` validates against
 * `taxonomy.Category` directly, so any drift here is a client that offers choices the server
 * refuses.
 */

describe('manual check categories', () => {
  it('derives its keys from the taxonomy mirror rather than restating them', () => {
    // `tests/test_taxonomy_consistency.py` already pins COMPARISON_TAXONOMY against
    // taxonomy.py, so deriving from it inherits that guarantee for free.
    expect([...CATEGORY_KEYS].sort()).toEqual(Object.keys(COMPARISON_TAXONOMY).sort());
  });

  it('offers all six canonical categories', () => {
    // Six, not four. The checklist panel's own list omits `isometric_view` — one of the four
    // recorded false-negative classes — and a category with no heading is one an engineer does
    // not think to look for.
    expect(CATEGORY_KEYS).toHaveLength(6);
    expect(CATEGORY_KEYS).toContain('isometric_view');
    expect(CATEGORY_KEYS).toContain('other_engineering_references');
  });

  it('labels every category, so a new one cannot appear unlabelled', () => {
    for (const key of CATEGORY_KEYS) {
      expect(categoryLabel(key), `${key} has no label`).not.toBe(key);
    }
  });

  it('exposes options in taxonomy order with matching labels', () => {
    expect(CATEGORY_OPTIONS.map((o) => o.key)).toEqual([...CATEGORY_KEYS]);
    expect(CATEGORY_OPTIONS.every((o) => o.label.length > 0)).toBe(true);
  });
});
