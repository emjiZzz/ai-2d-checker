/**
 * The glyph sets a Japanese CAD sheet spells one symbol with, as character-class SOURCES.
 *
 * Constants rather than four copies of a character class, because the copies disagreed.
 * `cleanCadText` transcodes the DXF escape `%%c` to U+2300 ⌀, so that is what reaches every
 * downstream classifier -- and three of them were written against `[ØøφΦ]`, which matches none of
 * it. `inferFeatureKey` could not see `6×⌀145` as a material specification or `⌀145` as a hole
 * property, and `inferCategoryForEntity` had both gaps again. Each failed by returning a
 * plausible answer from its own catch-all, which is why none surfaced until someone read a
 * checklist closely. `entityPicking.ts` had the complete set all along and now derives from here,
 * so there is one answer to what a diameter looks like rather than two that agree today.
 *
 * Interpolated into a `[...]` class, so nothing here may contain `]`, `^`, `-` or a backslash.
 */

/** Diameter: ⌀ (U+2300, what `%%c` becomes), ø/Ø, φ/ϕ (Greek phi), ф (Cyrillic ef). */
export const DIAMETER_CHARS = '⌀øØφϕф';

/** Multiplication, as written on a sheet: `×`, its lookalikes, and full-width `ｘ`. */
export const MULTIPLY_CHARS = '*xX×✕✖⨯⨉ｘ';

/**
 * Strip residual AutoCAD MTEXT markup and convert the legacy control escapes to the symbols they
 * render as. This is the form the UI displays, so it is the form that must be classified.
 *
 * It lives here rather than in `renderEntities.ts` because it was a rendering helper for its
 * whole life, so the `utils/` classifiers could not reach it without importing the canvas
 * renderer. They classified raw stored text while every card showed `cleanCadText` of it -- two
 * readings of one value, and only one of them visible to the engineer. Real cached BOM values are
 * `'SS400 %%c55×15'` and `'S45C %%c265×25'`, so a size cell reaches the classifier as `6×%%c145`
 * and the eye as `6×⌀145`; the material-size rule needs digits on both sides of the `×` and fell
 * through to Other. It was also positional -- `%%c55×15` matched on its `55×15` while `6×%%c145`
 * did not -- so one column classified two ways depending on where the escape sat.
 * `renderEntities.ts` re-exports it, so no importer changed.
 *
 * Classify what the user sees. Any rule reading marking or finding text must run on this output,
 * never on `ref_text` or `rev_text` directly.
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
