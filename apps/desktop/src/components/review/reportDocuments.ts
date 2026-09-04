/**
 * Which pages end up in which file when the compliance report is saved as a pair.
 *
 * Split out of `useComplianceReportExport` on 2026-08-25, when the report stopped being one
 * merged PDF. The rule is worth its own module for one reason: the two paths are not
 * symmetrical, and the asymmetry is invisible in the output.
 *
 * * Vector path — the backend returns page 1 as a complete PDF and jsPDF holds *only* the
 *   checklist. Nothing has to be taken apart.
 * * Raster fallback — the backend could not supply a vector sheet, so jsPDF drew the canvas
 *   capture as its own page 0 and the checklist after it. Here the split is real work.
 *
 * Get the fallback branch backwards and the file named `-drawing.pdf` opens on a checklist sheet.
 * It is a valid PDF, it is the right size, and it looks like a successful export right up until
 * someone goes looking for the drawing — the failure mode this whole pipeline specialises in.
 *
 * Kept free of Tauri, React and jsPDF so it can be tested against real `pdf-lib` documents rather
 * than a pile of mocks asserting that the code calls the functions it calls.
 */

/** A saved report: the drawing sheet, and the checklist when there is one. */
export interface ReportDocuments {
  drawing: Uint8Array;
  /** `null` when the report has no checklist rows — a legitimate outcome, not a failure. */
  checklist: Uint8Array | null;
}

/**
 * A new PDF holding just `indices` of `source`, in that order.
 *
 * Copied, not deleted. The obvious alternative — load the document twice and `removePage`
 * the unwanted half from each — leaves every object those pages referenced still in the file: the
 * fonts, the 304 dpi page images, all of it. Both halves come out roughly the size of the whole
 * and neither looks wrong. Copying pulls across only what the kept pages actually reference.
 */
async function extractPages(source: any, indices: number[]): Promise<Uint8Array> {
  const { PDFDocument } = await import("pdf-lib");
  const out = await PDFDocument.create();
  const copied = await out.copyPages(source, indices);
  for (const page of copied) out.addPage(page);
  return out.save();
}

/**
 * Split one export into the drawing file and the checklist file.
 *
 * @param sheetBytes      the backend's vector sheet, or `null` if it could not be fetched
 * @param checklistPdf    jsPDF's output — the checklist alone, or page 1 + checklist in fallback
 * @param checklistPages  how many checklist sheets were RENDERED
 */
export async function splitReportDocuments(
  sheetBytes: Uint8Array | null,
  checklistPdf: ArrayBuffer,
  checklistPages: number,
): Promise<ReportDocuments> {
  if (sheetBytes) {
    // `checklistPages`, not the PDF's own page count. A `new jsPDF()` always starts with one
    // page whether or not anything was drawn on it, so a report with no rows would otherwise save
    // a blank second file that reads as a bug in the checklist rather than as an empty result.
    return {
      drawing: sheetBytes,
      checklist: checklistPages > 0 ? new Uint8Array(checklistPdf) : null,
    };
  }

  const { PDFDocument } = await import("pdf-lib");
  const whole = await PDFDocument.load(checklistPdf);
  const indices = whole.getPageIndices();
  return {
    drawing: await extractPages(whole, indices.slice(0, 1)),
    checklist: indices.length > 1 ? await extractPages(whole, indices.slice(1)) : null,
  };
}

/**
 * The two BARE filenames for one export. Join them onto the chosen directory yourself.
 *
 * Bare names, and the export asks for a FOLDER rather than a filename, because of Tauri's
 * scope model — not as a UI preference. `tauri-plugin-dialog` grants filesystem access to
 * exactly what the dialog returned: `save()` calls `allow_file(&path)` for that one path, while
 * `open({ directory: true })` calls `allow_directory(&path, recursive)`. So a save dialog
 * authorises one file, and deriving a sibling from its path writes somewhere never granted.
 *
 * That is not a theoretical concern — it shipped. The first version of this feature asked for a
 * filename and wrote `<chosen>-drawing.pdf` beside it, which failed for any location outside the
 * capability's static scope (`fs:allow-home-write-recursive`) with *"forbidden path … not allowed
 * on the scope for `allow-write-file`"*. It worked in the developer's home directory and nowhere
 * else, which is the worst way for a permissions bug to behave.
 *
 * Returned bare so this stays a pure rule with no separator guessing — the caller joins them with
 * `@tauri-apps/api/path`'s `join`, which knows the platform's separator.
 */
export function reportFileNames(stem: string): { drawing: string; checklist: string } {
  const safe = stem.replace(/\.pdf$/i, "");
  return { drawing: `${safe}-drawing.pdf`, checklist: `${safe}-checklist.pdf` };
}
