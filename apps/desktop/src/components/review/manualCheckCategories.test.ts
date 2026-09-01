import { describe, it, expect } from 'vitest';
import { CATEGORY_KEYS, CATEGORY_OPTIONS, categoryLabel, findMarkingForEntity, categoryForZone, inferCategoryForEntity } from './manualCheckCategories';
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

describe('findMarkingForEntity — one entity, one judgement', () => {
  const m = (over: Record<string, any> = {}) => ({
    id: 'm1',
    status: 'MATCHED',
    retracted_at: null,
    ref_handle: 'A1',
    rev_handle: 'B2',
    ...over,
  });

  it('finds the marking already recorded against this entity', () => {
    // The menu reports instead of offering when this returns something. Without it the same
    // value could be filed MATCHED and then ADDED — two live human statements contradicting
    // each other, which is worse than none because nothing downstream can tell them apart.
    expect(findMarkingForEntity([m()], { side: 'ref', handle: 'A1' })?.id).toBe('m1');
    expect(findMarkingForEntity([m()], { side: 'rev', handle: 'B2' })?.id).toBe('m1');
  });

  it('does not confuse the two sheets', () => {
    // The same handle can exist on both drawings, and a marking on the reference says nothing
    // about the revision's entity of that name.
    expect(findMarkingForEntity([m()], { side: 'rev', handle: 'A1' })).toBeNull();
  });

  it('ignores a retracted marking, so the entity can be marked again', () => {
    // Removing a record is how an engineer changes their mind. If the retracted row still
    // blocked the entity, the correction would be impossible and the button pointless.
    expect(
      findMarkingForEntity([m({ retracted_at: '2026-08-18T00:00:00Z' })], { side: 'ref', handle: 'A1' }),
    ).toBeNull();
  });

  it('treats an entity with no handle as unmarked rather than guessing', () => {
    // A block-exploded child carries no handle. Matching on absence would make every such entity
    // match every other one — one marking would lock out the whole block.
    expect(findMarkingForEntity([m({ ref_handle: null })], { side: 'ref', handle: null })).toBeNull();
    expect(findMarkingForEntity([m({ ref_handle: null })], { side: 'ref', handle: undefined })).toBeNull();
  });

  it('matches on HANDLE, which is what survives a re-extraction', () => {
    // `/reextract` mints new entity ids; handles persist. Keying on id would stop finding
    // anything the first time a drawing was re-extracted, and the double-marking this prevents
    // would come back with no visible cause.
    const withoutHandles = [m({ ref_handle: null, rev_handle: null })];
    expect(findMarkingForEntity(withoutHandles, { side: 'ref', handle: 'A1' })).toBeNull();
  });
});

describe('categoryForZone — deriving a category from where the entity sits', () => {
  it('maps the four zones that correspond to a category', () => {
    expect(categoryForZone('views')).toBe('drawing_views');
    expect(categoryForZone('notes')).toBe('notes_section');
    expect(categoryForZone('bom')).toBe('bill_of_materials');
    expect(categoryForZone('iso')).toBe('isometric_view');
  });

  it('treats both title blocks as the title block', () => {
    // `title_upper_left` is a second title block on some sheets, not a different kind of thing.
    expect(categoryForZone('title')).toBe('title_block');
    expect(categoryForZone('title_upper_left')).toBe('title_block');
  });

  it('declines to guess for a zone the taxonomy has no category for', () => {
    // `other_engineering_references` means "unclassified", so filing a tolerance table there
    // would be a claim rather than an absence — and a wrong claim is worse than a question.
    expect(categoryForZone('tolerance')).toBeNull();
    expect(categoryForZone('shim')).toBeNull();
  });

  it('declines when the entity is in no zone at all', () => {
    expect(categoryForZone(null)).toBeNull();
    expect(categoryForZone(undefined)).toBeNull();
    expect(categoryForZone('')).toBeNull();
  });

  it('only ever returns a category the taxonomy still has', () => {
    // The guard that matters after a backend rename: a marking filed under a category the engine
    // has never heard of is not a corrupt row, it is an INVISIBLE one — every downstream
    // group-by drops it silently.
    for (const zone of ['views', 'notes', 'bom', 'title', 'title_upper_left', 'iso']) {
      expect(CATEGORY_KEYS).toContain(categoryForZone(zone));
    }
  });
});

describe('inferCategoryForEntity — automatic category inference', () => {
  it('prefers explicit zone when defined', () => {
    expect(inferCategoryForEntity('bom', 'ø125')).toBe('bill_of_materials');
    expect(inferCategoryForEntity('views', 'SS400')).toBe('drawing_views');
  });

  it('infers drawing views for dimensions and geometric entities outside zones', () => {
    expect(inferCategoryForEntity(null, 'ø125')).toBe('drawing_views');
    expect(inferCategoryForEntity(null, '100')).toBe('drawing_views');
    expect(inferCategoryForEntity(null, 'C0.5')).toBe('drawing_views');
    expect(inferCategoryForEntity(null, '4-M8')).toBe('drawing_views');
    expect(inferCategoryForEntity(null, '', 'LINE')).toBe('drawing_views');
  });

  it('infers bill of materials for material codes, stock sizes, and weights', () => {
    expect(inferCategoryForEntity(null, 'SS400')).toBe('bill_of_materials');
    expect(inferCategoryForEntity(null, '6 × ø145')).toBe('bill_of_materials');
    expect(inferCategoryForEntity(null, '0.78kg')).toBe('bill_of_materials');
  });

  it('infers title block for metadata fields', () => {
    expect(inferCategoryForEntity(null, 'SCALE 1:1')).toBe('title_block');
    expect(inferCategoryForEntity(null, '1:1.5')).toBe('title_block');
    expect(inferCategoryForEntity(null, '1/1.4')).toBe('title_block');
    expect(inferCategoryForEntity(null, '04/12/22')).toBe('title_block');
    expect(inferCategoryForEntity(null, '2026/07/03')).toBe('title_block');
    expect(inferCategoryForEntity(null, 'DWG NO: M745221')).toBe('title_block');
    expect(inferCategoryForEntity(null, 'M745221N01')).toBe('title_block');
    expect(inferCategoryForEntity(null, 'FSRS2')).toBe('title_block');
    expect(inferCategoryForEntity(null, '2589')).toBe('title_block');
    expect(inferCategoryForEntity(null, '9324')).toBe('title_block');
    expect(inferCategoryForEntity(null, 'Roll Cassette 12" Mill')).toBe('title_block');
    expect(inferCategoryForEntity(null, 'ロールカセット 12"ミル')).toBe('title_block');
  });

  it('returns null for blank or completely ambiguous text so the engineer is asked', () => {
    expect(inferCategoryForEntity(null, '')).toBeNull();
    expect(inferCategoryForEntity(null, '   ')).toBeNull();
  });
});
