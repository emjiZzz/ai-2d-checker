import { useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { writeFile } from "@tauri-apps/plugin-fs";

import { exportCanvasImage } from "../components/review/canvasExportRegistry";
import {
  ChecklistRow,
  ChecklistSectionData,
  renderChecklistSheets,
} from "../components/review/complianceChecklistSheet";
import { CATEGORY_KEYS, categoryLabel } from "../components/review/manualCheckCategories";
import {
  REPORT_CONTENT_MM,
  REPORT_PAGE_MM,
  REPORT_RASTER_PX_PER_MM,
} from "../components/review/reportPageGeometry";
import { markerTypeOf } from "../components/review/markerStyles";
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

  const exportToPDF = async () => {
    if (isExporting) return;
    setIsExporting(true);
    try {
      const { jsPDF } = await import("jspdf");
      // Millimetres, not `px`. jsPDF's `px` unit is 96/72 pt per pixel unless you opt into its
      // `px_scaling` hotfix, which made the old `[1200, 800]` page 564 x 376 mm — larger than A2,
      // and a page on which "a 7 mm margin" is not a statement about anything.
      const doc = new jsPDF({
        orientation: "landscape",
        unit: "mm",
        format: [REPORT_PAGE_MM.width, REPORT_PAGE_MM.height],
      });

      // ---- Page 1: the revision drawing, with its marks ----------------------------------
      //
      // The drawing fills the page to a uniform 7 mm on every side. There is no header band:
      // a caption cannot share an edge with a 7 mm top margin, and the page is the drawing.
      const generatedAt = new Date().toLocaleString();

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

      // ---- Page 2 (onward): the checklist ------------------------------------------------
      const sections = buildSections();
      const itemCount = sections.reduce((n, s) => n + s.rows.length, 0);
      const findingCount = sections.reduce(
        (n, s) => n + s.rows.filter((r) => r.status !== "MATCHED").length,
        0,
      );

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
      for (const page of checklistPages) {
        doc.addPage([REPORT_PAGE_MM.width, REPORT_PAGE_MM.height], "landscape");
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
      }

      const arrayBuffer = doc.output("arraybuffer");
      const uint8Array = new Uint8Array(arrayBuffer);

      const filePath = await save({
        filters: [{ name: "PDF Document", extensions: ["pdf"] }],
        defaultPath: sanitizeFileStem(newDrawing?.file_name) + "-compliance-report.pdf",
      });

      if (filePath) {
        await writeFile(filePath, uint8Array);
      }
    } catch (error: any) {
      // Surfaced, not swallowed. This used to end at `console.error` inside a Tauri window with
      // no visible devtools, so a failed export was indistinguishable from a cancelled save
      // dialog — the user clicked Export and nothing at all happened.
      console.error("PDF generation failed:", error);
      alert("Compliance report export failed: " + (error?.message || String(error)));
    } finally {
      setIsExporting(false);
    }
  };

  return { exportToPDF, isExporting };
}
