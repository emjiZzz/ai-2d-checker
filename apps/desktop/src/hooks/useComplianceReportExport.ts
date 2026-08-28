import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { writeFile } from "@tauri-apps/plugin-fs";
import { join } from "@tauri-apps/api/path";

import { exportCanvasImage } from "../components/review/canvasExportRegistry";
import { fetchVectorSheet, type VectorSheetMarker } from "../services/exportApi";
import {
  ChecklistRow,
  ChecklistSectionData,
  renderChecklistSheets,
} from "../components/review/complianceChecklistSheet";
import { CATEGORY_KEYS, categoryLabel } from "../components/review/manualCheckCategories";
import {
  REPORT_CONTENT_MM,
  REPORT_MARGIN_MM,
  REPORT_PAGE_MM,
  REPORT_RASTER_PX_PER_MM,
} from "../components/review/reportPageGeometry";
import { markerTypeOf } from "../components/review/markerStyles";
import { reportFileNames, splitReportDocuments } from "../components/review/reportDocuments";
import { useIsManualCheckRoom } from "./useManualCheckRoom";
import { useWorkspaceStore } from "../stores/workspaceStore";

/**
 * The compliance report: the checked drawing, then what was checked on it.
 *
 * ## The report is exactly two things
 *
 * Page 1 is the REVISION sheet as the engineer left it — every marking, annotation pin and
 * finding drawn where it sits on the drawing. Page 2 is the checklist behind those marks.
 * Nothing else, by the owner's call (2026-08-24).
 *
 * It used to open on a metrics cover page and then print the reference drawing as well. Both are
 * gone. The cover restated four counts the checklist itself carries, and the reference sheet is
 * the drawing nobody is auditing — a reader flipping to page 2 of three found the sheet with no
 * marks on it, which is the one page the report has no reason to contain.
 *
 * The checklist runs onto page 3 and beyond when it is long. That is not a violation of "two
 * pages": a truncated checklist would drop findings an engineer recorded, and a report is not
 * allowed to be shorter than its own evidence. Each continued page says so in its header.
 *
 * ## Page 1 and page 2 are the same data
 *
 * Both sides come from the store, and the marks on the drawing and the rows in the table are read
 * from the same arrays — so a finding cannot appear on one and not the other. That is also why
 * this hook takes no arguments any more: it had four, the two call sites passed different things,
 * and only one of them passed canvas refs at all, which is why the manual-check room's report
 * came out with blank drawing pages.
 */

const STATUS_ORDER = ["MISMATCHED", "REMOVED", "CHANGED", "ADDED", "CONFLICT", "MATCHED"];

function severityStatus(severity: string): string {
  return severity === "critical" || severity === "high" ? "MISMATCHED" : "CHANGED";
}

function sortRows(rows: ChecklistRow[]): ChecklistRow[] {
  // Findings first, matches last. A checklist read top-down should answer "what is wrong with this
  // revision" before it answers "what is fine", and MATCHED rows are usually the bulk of them.
  return [...rows].sort((a, b) => {
    const ai = STATUS_ORDER.indexOf(a.status);
    const bi = STATUS_ORDER.indexOf(b.status);
    return (ai === -1 ? STATUS_ORDER.length : ai) - (bi === -1 ? STATUS_ORDER.length : bi);
  });
}

/**
 * jsPDF's zlib level for embedded images — and the difference between a report that opens and one
 * that does not.
 *
 * `addImage` without it embeds the DECODED pixels, uncompressed: measured at **112 MB** for this
 * report's four pages, against **0.9 MB** with it, byte-for-byte identical output otherwise
 * (Flate is lossless). That is not a size preference. The previous report asked
 * `CanvasRenderer` for two 7016x4960 sheets and embedded both raw — roughly a quarter of a
 * gigabyte of PDF — which is why its drawing pages arrived blank in a viewer while its text
 * pages rendered fine.
 */
const IMAGE_COMPRESSION = "FAST" as const;

/**
 * What the last export did, for the caller to show. `null` once it has been on screen long enough.
 *
 * `cancelled` earns its place: the dialog opens only AFTER the sheet has been rendered and the
 * checklist rasterised, which is ~17 s on a dense drawing. Backing out at that point otherwise
 * looks exactly like a completed export — the button says "Building…", then stops saying it, and
 * nothing else changes.
 */
export type ExportStatus =
  | null
  | { kind: "saved"; folder: string; names: string[]; paths: string[] }
  | { kind: "cancelled" };

/** How long a confirmation stays up. Long enough to read a folder path, short enough to trust. */
const STATUS_VISIBLE_MS = 10_000;

/**
 * What the export is doing, for the overlay to say out loud.
 *
 * Named phases rather than one "Working…" because the wait is not short and it is not uniform:
 * the drawing pass alone is ~14 s of the ~17 s backend time — 258 strings tessellated into glyph
 * outlines — and the checklist rasterises on the MAIN THREAD, so the window is genuinely
 * unresponsive during it. A progress message that never changes for seventeen seconds is read as
 * a hang, and the user's next move is to click again.
 *
 * ⚠ `folder` matters most. The picker opens partway through, and a user who has been watching a
 * blocking overlay does not expect to be asked for something.
 */
const PHASE = {
  drawing: "Rendering the drawing sheet…",
  checklist: "Building the checklist…",
  folder: "Waiting for you to choose a folder…",
  writing: "Writing the PDFs…",
} as const;

function sanitizeFileStem(name: string | undefined): string {
  const stem = (name || "compliance").replace(/\.[^.]+$/, "");
  return stem.replace(/[^A-Za-z0-9._-]+/g, "_").slice(0, 80) || "compliance";
}


export function useComplianceReportExport() {
  const isManualCheckRoom = useIsManualCheckRoom();
  const oldDrawing = useWorkspaceStore((s) => s.oldDrawing);
  const newDrawing = useWorkspaceStore((s) => s.newDrawing);
  const markings = useWorkspaceStore((s) => s.markings);
  const annotations = useWorkspaceStore((s) => s.annotations);
  const violations = useWorkspaceStore((s) => s.violations);

  // Rasterising four pages and Flate-compressing them takes several seconds on the main thread.
  // Without this the button is inert for that whole time and the only honest reading of it is
  // that the click did not register — which is what people do next, producing a second export.
  const [isExporting, setIsExporting] = useState(false);
  const [exportStatus, setExportStatus] = useState<ExportStatus>(null);
  const [exportPhase, setExportPhase] = useState<string | null>(null);

  /**
   * The confirmation clears itself, because nothing else will.
   *
   * Both call sites are toolbars with no room for a dismissable banner, and a "Saved" that stays
   * put becomes indistinguishable from a "Saved" about the export before this one — which is
   * worse than no confirmation, since it reports success for work that has not happened yet.
   */
  useEffect(() => {
    if (!exportStatus) return;
    const timer = setTimeout(() => setExportStatus(null), STATUS_VISIBLE_MS);
    return () => clearTimeout(timer);
  }, [exportStatus]);

  /** Open the saved pair in the OS file manager, with the drawing selected. */
  const revealExport = async () => {
    if (exportStatus?.kind !== "saved") return;
    try {
      const { revealItemInDir } = await import("@tauri-apps/plugin-opener");
      await revealItemInDir(exportStatus.paths[0]);
    } catch (error) {
      // Not an alert. The files ARE written — failing to open a file manager is a footnote, and
      // interrupting a successful export with a modal about it reads as the export having failed.
      console.warn("Could not reveal the exported files:", error);
    }
  };

  /**
   * The checklist, from whichever record this room actually holds.
   *
   * A manual-check room's truth is what the engineer stamped; an AI room's is what the engine
   * found. They are never both live — `CanvasRenderer` forces the engine's markers off in a
   * manual room, so printing violations there would put rows in the table that page 1 does not
   * mark.
   */
  const buildSections = (): ChecklistSectionData[] => {
    const sections: ChecklistSectionData[] = [];

    if (isManualCheckRoom) {
      for (const key of CATEGORY_KEYS) {
        const rows = markings
          .filter((m) => m.category === key && !m.retracted_at)
          .map<ChecklistRow>((m) => ({
            status: m.status,
            reference: m.ref_text || "—",
            revision: m.rev_text || "—",
            note: [m.notes, m.is_bulk ? "bulk" : ""].filter(Boolean).join(" · "),
          }));
        if (rows.length) sections.push({ label: categoryLabel(key), rows: sortRows(rows) });
      }
    } else {
      const byCategory = new Map<string, ChecklistRow[]>();
      for (const v of violations) {
        const key = v.category || "other_engineering_references";
        const rows = byCategory.get(key) ?? [];
        rows.push({
          // `markerTypeOf` before the severity fallback, for the same reason the canvas uses it:
          // it is the engine's own verdict, and a report that renames CHANGED to HIGH describes
          // the finding in a vocabulary the drawing's marker does not use.
          status: markerTypeOf(v) ?? severityStatus(v.severity),
          reference: v.original_value || "—",
          revision: v.description || "—",
          note: [v.recommendation, v.standard_reference].filter(Boolean).join(" · "),
        });
        byCategory.set(key, rows);
      }
      for (const [key, rows] of byCategory) {
        sections.push({ label: categoryLabel(key), rows: sortRows(rows) });
      }
    }

    // Pins are drawn on page 1 too, so they belong in the table that explains page 1.
    const pins = annotations.filter((a) => !newDrawing?.id || a.drawing_id === newDrawing.id);
    if (pins.length) {
      sections.push({
        label: "Annotations & Notes",
        rows: pins.map<ChecklistRow>((a) => ({
          status: "ADDED",
          reference: "—",
          revision: a.content || "Annotation pin",
          note: a.severity ? String(a.severity).toUpperCase() : "",
        })),
      });
    }

    return sections;
  };

  /**
   * What page 1 has drawn on it, in the drawing's own coordinates.
   *
   * Read from the same arrays `buildSections` reads, and filtered the same way, so a mark on the
   * sheet and a row in the table cannot disagree. The REVISION side throughout — page 1 is the
   * revision sheet, so `rev_coordinates` / `coordinates`, never the `ref_` pair.
   *
   * Badges only, no labels: the canvas draws a badge with a status glyph and nothing else, and
   * the text behind each mark is already on the checklist page. `SheetMarker.label` exists on the
   * wire if a labelled variant is ever wanted; leaving it empty is what keeps page 1 a picture of
   * the review rather than a second checklist.
   */
  const buildMarkers = (): VectorSheetMarker[] => {
    const markers: VectorSheetMarker[] = [];

    if (isManualCheckRoom) {
      for (const m of markings) {
        if (m.retracted_at || !m.rev_coordinates) continue;
        markers.push({ x: m.rev_coordinates[0], y: m.rev_coordinates[1], status: m.status });
      }
    } else {
      for (const v of violations) {
        if (!v.coordinates) continue;
        markers.push({
          x: v.coordinates[0],
          y: v.coordinates[1],
          // `markerTypeOf` first, matching the canvas and the checklist: it is the engine's own
          // verdict, and a report that renames CHANGED to HIGH describes the finding in a
          // vocabulary the drawing's marker does not use.
          status: markerTypeOf(v) ?? severityStatus(v.severity),
        });
      }
    }

    for (const a of annotations) {
      if (!a.coordinates) continue;
      if (newDrawing?.id && a.drawing_id !== newDrawing.id) continue;
      markers.push({ x: a.coordinates[0], y: a.coordinates[1], status: "ADDED" });
    }

    return markers;
  };

  const exportToPDF = async () => {
    if (isExporting) return;
    setIsExporting(true);
    /** Page 1's vector bytes, or null once the backend has been tried and could not supply them. */
    let sheetBytes: Uint8Array | null = null;
    /**
     * Why the vector page was not used. Non-null means the reader is getting the raster page.
     *
     * The two are not interchangeable and the difference is visible: the vector page is
     * searchable, copyable and sharp at any zoom; the raster one is a 304 dpi photograph of the
     * canvas. So a downgrade is REPORTED rather than absorbed — a button that silently produces
     * one of two different documents is the shape this file already had to fix once, when a
     * failed export was indistinguishable from a cancelled save dialog.
     */
    let vectorFailure: string | null = null;
    try {
      const { jsPDF } = await import("jspdf");
      const generatedAt = new Date().toLocaleString();

      // ---- Page 1: the revision drawing, with its marks ----------------------------------
      //
      // Vectors from the backend when it can be reached, the canvas raster when it cannot. The
      // vector page carries the same sheet as real paths plus a searchable text layer; the
      // raster one is a 304 dpi photograph of the canvas. Which one arrived is reported at the
      // end — see `SheetSource`.
      if (newDrawing?.id) {
        try {
          setExportPhase(PHASE.drawing);
          sheetBytes = await fetchVectorSheet(newDrawing.id, {
            markers: buildMarkers(),
            // The backend defaults to A4 landscape anyway; sending the page explicitly means the
            // two halves of this document cannot end up on different paper if either changes.
            pageWidthMm: REPORT_PAGE_MM.width,
            pageHeightMm: REPORT_PAGE_MM.height,
            marginMm: REPORT_MARGIN_MM,
          });
        } catch (error: any) {
          vectorFailure = error?.message || String(error);
        }
      } else {
        vectorFailure = "no revision drawing is loaded";
      }

      // Millimetres, not `px`. jsPDF's `px` unit is 96/72 pt per pixel unless you opt into its
      // `px_scaling` hotfix, which made the old `[1200, 800]` page 564 x 376 mm — larger than A2,
      // and a page on which "a 7 mm margin" is not a statement about anything.
      //
      // In the vector path this document holds ONLY the checklist; page 1 arrives from the
      // backend and the two are bound below.
      const doc = new jsPDF({
        orientation: "landscape",
        unit: "mm",
        format: [REPORT_PAGE_MM.width, REPORT_PAGE_MM.height],
      });

      if (!sheetBytes) {
        // The drawing fills the page to a uniform margin on every side. There is no header band:
        // a caption cannot share an edge with a 3 mm top margin, and the page is the drawing.
        doc.setFillColor(255, 255, 255);
        doc.rect(0, 0, REPORT_PAGE_MM.width, REPORT_PAGE_MM.height, "F");

        // Captured at the CONTENT box's own aspect ratio so the sheet is fitted inside the PNG
        // rather than stretched into the page — `renderContent`'s export branch letterboxes on
        // white, and asking it for a differently-shaped canvas is what puts a CAD drawing out of
        // proportion in a printed report.
        const revisionImage = exportCanvasImage(
          "rev",
          Math.round(REPORT_CONTENT_MM.width * REPORT_RASTER_PX_PER_MM),
          Math.round(REPORT_CONTENT_MM.height * REPORT_RASTER_PX_PER_MM),
        );

        if (revisionImage) {
          doc.addImage(
            revisionImage,
            "PNG",
            REPORT_CONTENT_MM.x,
            REPORT_CONTENT_MM.y,
            REPORT_CONTENT_MM.width,
            REPORT_CONTENT_MM.height,
            undefined,
            IMAGE_COMPRESSION,
          );
        } else {
          // Loud rather than a white rectangle. A blank page-1 was the previous report's actual
          // behaviour in a manual-check room and it read as a rendering glitch, not as a missing
          // canvas.
          doc.setFillColor(240, 240, 245);
          doc.rect(
            REPORT_CONTENT_MM.x,
            REPORT_CONTENT_MM.y,
            REPORT_CONTENT_MM.width,
            REPORT_CONTENT_MM.height,
            "F",
          );
          doc.setTextColor(239, 68, 68);
          doc.setFontSize(12);
          doc.text(
            "Revision drawing could not be captured - open the KMTI drawing panel and export again.",
            REPORT_CONTENT_MM.x + 10,
            REPORT_CONTENT_MM.y + 14,
          );
        }
      }

      // ---- Page 2 (onward): the checklist ------------------------------------------------
      const sections = buildSections();
      const itemCount = sections.reduce((n, s) => n + s.rows.length, 0);
      const findingCount = sections.reduce(
        (n, s) => n + s.rows.filter((r) => r.status !== "MATCHED").length,
        0,
      );

      setExportPhase(PHASE.checklist);
      const checklistPages = renderChecklistSheets(sections, {
        title: isManualCheckRoom ? "MANUAL CHECK CHECKLIST" : "COMPLIANCE CHECKLIST",
        subtitle:
          sanitizeFileStem(newDrawing?.file_name) +
          "  ·  checked against  " +
          sanitizeFileStem(oldDrawing?.file_name) +
          "  ·  " +
          generatedAt,
        tally: itemCount + " items  ·  " + findingCount + " findings",
      });

      // Full-bleed: the checklist sheet draws its own 12 mm inner margin, and its canvas is cut to
      // the paper's aspect ratio (`CHECKLIST_PAGE_H` is derived from it), so placing it edge to
      // edge neither stretches it nor leaves a seam.
      //
      // In the vector path `doc` is still empty, so the FIRST checklist sheet goes onto the page
      // jsPDF already created rather than after a blank one — a `new jsPDF()` always starts with
      // a page whether you wanted it or not.
      checklistPages.forEach((page, index) => {
        if (index > 0 || !sheetBytes) {
          doc.addPage([REPORT_PAGE_MM.width, REPORT_PAGE_MM.height], "landscape");
        }
        doc.addImage(
          page,
          "PNG",
          0,
          0,
          REPORT_PAGE_MM.width,
          REPORT_PAGE_MM.height,
          undefined,
          IMAGE_COMPRESSION,
        );
      });

      // ---- Two documents, written side by side -------------------------------------------
      //
      // The drawing and the checklist were never really one PDF: in the vector path page 1
      // arrives from the backend as a COMPLETE document and `doc` holds only the checklist. They
      // used to be bound together here with pdf-lib; they are saved as a pair instead, so the
      // drawing can be handed to someone without the findings attached and stays a file a CAD
      // viewer opens directly.
      //
      // The rule lives in `reportDocuments.ts` because the two paths are NOT symmetrical and the
      // asymmetry is invisible in the output — see that module.
      const { drawing: drawingBytes, checklist: checklistBytes } = await splitReportDocuments(
        sheetBytes,
        doc.output("arraybuffer"),
        checklistPages.length,
      );

      // ⚠ A FOLDER picker, not a save dialog, and the reason is Tauri's scope model rather than
      // taste. `tauri-plugin-dialog` grants access to exactly what it returned — `save()` calls
      // `allow_file(&path)` for that one path, `open({directory:true})` calls
      // `allow_directory(&path, recursive)`. Asking for a filename and writing a SECOND file
      // beside it is therefore unauthorised, and fails with "forbidden path ... not allowed on
      // the scope for `allow-write-file`" anywhere outside this app's static
      // `fs:allow-home-write-recursive` scope. It shipped that way and worked only under HOME.
      setExportPhase(PHASE.folder);
      const folder = await open({
        directory: true,
        multiple: false,
        recursive: true,
        title: "Choose a folder for the drawing and checklist PDFs",
      });

      if (typeof folder !== "string") {
        // Cancelled. Reported rather than absorbed: the picker only appears after the sheet has
        // been rendered, so by here the user has watched "Building…" for long enough that a
        // silent return to the idle button reads as a finished export.
        setExportStatus({ kind: "cancelled" });
        return;
      }

      {
        setExportPhase(PHASE.writing);
        const stem = sanitizeFileStem(newDrawing?.file_name);
        const names = reportFileNames(stem);
        const written: string[] = [names.drawing];

        await writeFile(await join(folder, names.drawing), drawingBytes);
        if (checklistBytes) {
          await writeFile(await join(folder, names.checklist), checklistBytes);
          written.push(names.checklist);
        } else {
          // Not an alert: an export with no rows is a legitimate outcome, not a downgrade. But a
          // file the user expected and did not get has to be findable somewhere.
          console.info("No checklist rows, so only the drawing was written.");
        }

        // The names are decided here and the folder was chosen by the user, so neither is
        // guessable from the button. Saying WHAT was written and WHERE is the whole confirmation.
        setExportStatus({
          kind: "saved",
          folder,
          names: written,
          paths: await Promise.all(written.map((name) => join(folder, name))),
        });

        if (vectorFailure) {
          console.warn("Vector sheet unavailable, exported the canvas capture:", vectorFailure);
        }
      }
    } catch (error: any) {
      // Surfaced, not swallowed. This used to end at `console.error` inside a Tauri window with
      // no visible devtools, so a failed export was indistinguishable from a cancelled save
      // dialog — the user clicked Export and nothing at all happened.
      console.error("PDF generation failed:", error);
      alert("Compliance report export failed: " + (error?.message || String(error)));
    } finally {
      setIsExporting(false);
      setExportPhase(null);
    }
  };

  return { exportToPDF, isExporting, exportPhase, exportStatus, revealExport };
}
