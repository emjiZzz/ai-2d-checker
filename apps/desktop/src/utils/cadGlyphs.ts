/**
 * The glyph sets a Japanese CAD sheet spells one symbol with, as character-class SOURCES.
 *
 * ## Why these are constants and not four copies of a character class
 *
 * `cleanCadText`/`normalizeEntityValue` transcode the DXF escape `%%c` to **U+2300 ⌀**, so that
 * is the character that actually reaches every downstream classifier. Three of them were written
 * against `[ØøφΦ]` — U+00D8, U+00F8, U+03C6, U+03A6 — and matched **none** of it:
 *
 *   * `comparisonTaxonomy.inferFeatureKey` could not see `6×⌀145` as a material specification,
 *     and it only appeared under the right heading because the BOM branch's catch-all happened
 *     to name that heading. Fixing the catch-all to answer `other` is what exposed this.
 *   * the same function's `drawing_views` branch could not see `⌀145` as a hole property, so it
 *     fell through to `dimensions`.
 *   * `manualCheckCategories.inferCategoryForEntity` had both gaps again.
 *
 * Every one of those failed by producing a *plausible* answer, which is why none of them
 * surfaced as a bug report until someone read a checklist closely.
 *
 * `entityPicking.ts` had the complete set all along (`DIAMETER_MARKS`) because comparing two
 * spellings of one dimension is its whole job. It now derives from here rather than declaring
 * its own, so there is one answer to "what does a diameter look like" instead of two that agree
 * today.
 *
 * Interpolated into a `[...]` class, so nothing here may contain `]`, `^`, `-` or a backslash.
 */

/** Diameter: ⌀ (U+2300, what `%%c` becomes), ø/Ø, φ/ϕ (Greek phi), ф (Cyrillic ef). */
export const DIAMETER_CHARS = '⌀øØφϕф';

/** Multiplication, as written on a sheet: `×`, its lookalikes, and full-width `ｘ`. */
export const MULTIPLY_CHARS = '*xX×✕✖⨯⨉ｘ';

/**
 * Strip residual AutoCAD MTEXT markup and convert the legacy control escapes to the symbols
 * they render as. **This is the form the UI displays, so it is the form that must be classified.**
 *
 * ## Why it lives here and not in `renderEntities.ts`
 *
 * It was a rendering helper for its whole life, and the taxonomy classifiers in `utils/`
 * consequently could not reach it without importing the canvas renderer. So they classified the
 * **raw stored text** while every card on screen showed `cleanCadText(...)` of it — two readings
 * of one value, and only one of them was what the engineer could see.
 *
 * That is not a theoretical gap. Real BOM values out of `storage/cache/`:
 *
 * ```
 * 'SS400 %%c55×15'   'S45C %%c265×25'   '0.28'   '10.81'   '表ニヨル'
 * ```
 *
 * A size cell reaches the classifier as `6×%%c145` and reaches the eye as `6×⌀145`. The
 * material-size rule needs digits on both sides of the `×`, and raw text puts `%%c` there, so
 * the cell fell to "Other / Unclassified" **while displaying a value that plainly is a size**.
 * Worse, it was positional: `%%c55×15` (diameter × thickness) matched on its `55×15` and
 * `6×%%c145` (count × diameter) did not, so the same column classified two ways depending on
 * where the escape happened to sit.
 *
 * `renderEntities.ts` re-exports it, so no existing importer changed.
 *
 * **Classify what the user sees.** Any rule reading marking or finding text must run on this
 * output, never on `ref_text`/`rev_text` directly.
 */
export const cleanCadText = (text?: string | null): string => {
  if (!text) return "";
  let clean = text;
  clean = clean.replace(/ラ/g, "x");
  clean = clean.replace(/[{}]/g, "");
  clean = clean.replace(/\\[A-Za-z][^;]*;/g, "");
  clean = clean.replace(/\\P/g, " ");
  // Convert legacy AutoCAD control escape codes to standard engineering symbols
  clean = clean.replace(/%%c/gi, "⌀");
  clean = clean.replace(/%%d/gi, "°");
  clean = clean.replace(/%%p/gi, "±");
  clean = clean.replace(/%%[uo]/gi, "");
  return clean.trim();
};
