/**
 * Which uploaded formats are drawings and which are 3D models.
 *
 * This list was copy-pasted into four places, and `.icd` moving sides is exactly the kind of
 * change that leaves one copy behind: an iCAD file classified 3D opens the 3D workspace and
 * fetches a glTF the backend no longer generates for it, with no error anywhere.
 *
 * `.icd` is a drawing here. An iCAD file carries both a 3D model and 2D drawing content, and
 * the backend converts the 2D half to DXF -- see `infrastructure/cad/icd_converter.py`. The
 * 3D half needs a licence the install does not have.
 *
 * Mirrors `DrawingIngestionService.ALLOWED_EXTENSIONS`; pinned by
 * `tests/test_drawing_format_consistency.py`, because no runtime type-sharing exists across
 * the two languages.
 */

/** Formats parsed into 2D entities and compared. */
export const DRAWING_FORMATS = ["dwg", "dxf", "pdf", "icd"] as const;

/** Formats tessellated into a glTF mesh for the 3D workspace. */
export const MODEL_3D_FORMATS = ["step", "stp", "iges", "igs", "sldprt", "sldasm"] as const;

/** Everything the upload path accepts. Widened to string so callers can test a raw extension. */
export const ACCEPTED_FORMATS: readonly string[] = [...DRAWING_FORMATS, ...MODEL_3D_FORMATS];

export function isDrawingFormat(extension: string | undefined | null): boolean {
  return DRAWING_FORMATS.includes((extension || "") as (typeof DRAWING_FORMATS)[number]);
}

export function is3DModelFormat(extension: string | undefined | null): boolean {
  return MODEL_3D_FORMATS.includes((extension || "") as (typeof MODEL_3D_FORMATS)[number]);
}
