import { RefObject } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { writeFile } from "@tauri-apps/plugin-fs";

interface DrawingCanvasHandle {
  exportImage?: (exportWidth?: number, exportHeight?: number) => string;
}

interface UseComplianceReportExportParams {
  oldDrawing: any;
  newDrawing: any;
  violations: any[];
  complianceScore: number | null;
  canvasRefs: {
    old: RefObject<DrawingCanvasHandle | null>;
    new: RefObject<DrawingCanvasHandle | null>;
  };
}

/**
 * Builds and saves the compliance audit PDF report. Extracted verbatim from
 * TwoDWorkspace.tsx's inline exportToPDF (Phase 11, frontend remediation
 * plan) — pure jsPDF document construction and layout math, with the
 * component staying responsible only for triggering it and passing in the
 * canvas refs/data it already holds.
 */
export function useComplianceReportExport({
  oldDrawing,
  newDrawing,
  violations,
  complianceScore,
  canvasRefs
}: UseComplianceReportExportParams) {
  const exportToPDF = async () => {
    try {
      const criticalCount = violations.filter((v) => v.severity === "critical").length;
      const highCount = violations.filter((v) => v.severity === "high").length;
      const medCount = violations.filter((v) => v.severity === "medium").length;
      const lowCount = violations.filter((v) => v.severity === "low").length;

      // Dynamically import jsPDF to reduce initial bundle size
      const { jsPDF } = await import("jspdf");
      const doc = new jsPDF({
        orientation: "landscape",
        unit: "px",
        format: [1200, 800]
      });

      doc.setFillColor(15, 15, 20);
      doc.rect(0, 0, 1200, 800, "F");

      doc.setTextColor(255, 255, 255);
      doc.setFont("Helvetica", "bold");
      doc.setFontSize(28);
      doc.text("KMTI AI compliance Report", 50, 60);

      doc.setFont("Helvetica", "normal");
      doc.setFontSize(14);
      doc.setTextColor(161, 161, 170);
      doc.text(`Generated: ${new Date().toLocaleString()}`, 50, 90);

      doc.setFont("Helvetica", "bold");
      doc.setFontSize(18);
      doc.setTextColor(0, 229, 255);
      doc.text("AUDITED DOCUMENTS", 50, 150);

      doc.setFont("Helvetica", "normal");
      doc.setFontSize(13);
      doc.setTextColor(228, 228, 231);
      doc.text(`Reference Drawing: ${oldDrawing?.file_name || "N/A"}`, 50, 180);
      doc.text(`KMTI drawing (Revision): ${newDrawing?.file_name || "N/A"}`, 50, 205);

      doc.setFont("Helvetica", "bold");
      doc.setFontSize(18);
      doc.setTextColor(0, 229, 255);
      doc.text("COMPLIANCE AUDIT METRICS", 50, 265);

      doc.setFillColor(24, 24, 27);
      doc.rect(50, 290, 1100, 100, "F");

      doc.setFontSize(36);
      doc.setTextColor(16, 185, 129);
      doc.text(`${complianceScore || 0}%`, 90, 355);

      doc.setFontSize(11);
      doc.setTextColor(161, 161, 170);
      doc.text("COMPLIANCE SCORE", 90, 375);

      doc.setFontSize(24);
      doc.setTextColor(239, 68, 68);
      doc.text(`${criticalCount}`, 400, 345);
      doc.setFontSize(11);
      doc.setTextColor(161, 161, 170);
      doc.text("CRITICAL", 400, 365);

      doc.setFontSize(24);
      doc.setTextColor(249, 115, 22);
      doc.text(`${highCount}`, 580, 345);
      doc.setFontSize(11);
      doc.setTextColor(161, 161, 170);
      doc.text("HIGH SEVERITY", 580, 365);

      doc.setFontSize(24);
      doc.setTextColor(234, 179, 8);
      doc.text(`${medCount}`, 780, 345);
      doc.setFontSize(11);
      doc.setTextColor(161, 161, 170);
      doc.text("MEDIUM SEVERITY", 780, 365);

      doc.setFontSize(24);
      doc.setTextColor(59, 130, 246);
      doc.text(`${lowCount}`, 980, 345);
      doc.setFontSize(11);
      doc.setTextColor(161, 161, 170);
      doc.text("LOW SEVERITY", 980, 365);

      doc.setFont("Helvetica", "bold");
      doc.setFontSize(18);
      doc.setTextColor(0, 229, 255);
      doc.text("CRITICAL ENGINEERING INFRACTIONS & CORRECTIONS", 50, 435);

      let currentY = 470;
      doc.setFont("Helvetica", "normal");
      doc.setFontSize(12);

      const criticalViolations = violations.filter(v => v.severity === "critical" || v.severity === "high");
      if (criticalViolations.length === 0) {
        doc.setTextColor(16, 185, 129);
        doc.text("No critical or high severity infractions identified in this drawing revision.", 50, currentY);
      } else {
        criticalViolations.forEach((v, index) => {
          if (index < 5) {
            doc.setFillColor(index % 2 === 0 ? 20 : 25, index % 2 === 0 ? 20 : 25, index % 2 === 0 ? 25 : 30);
            doc.rect(50, currentY, 1100, 50, "F");

            doc.setTextColor(239, 68, 68);
            doc.setFont("Helvetica", "bold");
            doc.setFontSize(11);
            doc.text(`[${v.severity.toUpperCase()}] ${v.category}`, 70, currentY + 22);

            doc.setTextColor(228, 228, 231);
            doc.setFont("Helvetica", "normal");
            doc.setFontSize(10);
            doc.text(`${v.description}`, 70, currentY + 38);

            doc.setTextColor(0, 229, 255);
            doc.text(`Fix: ${v.recommendation}`, 650, currentY + 22);
            doc.setTextColor(161, 161, 170);
            doc.text(`Ref: ${v.standard_reference || "General"}`, 650, currentY + 38);

            currentY += 56;
          }
        });
      }

      const leftImgData = canvasRefs.old.current?.exportImage?.();
      const rightImgData = canvasRefs.new.current?.exportImage?.();

      if (leftImgData) {
        doc.addPage([1200, 800], "landscape");
        doc.setFillColor(15, 15, 20);
        doc.rect(0, 0, 1200, 800, "F");
        doc.setTextColor(255, 255, 255);
        doc.setFont("Helvetica", "bold");
        doc.setFontSize(20);
        doc.text("ORIGINAL REFERENCE DRAWING OVERVIEW", 50, 50);
        doc.addImage(leftImgData, "PNG", 50, 80, 1100, 670);
      }

      if (rightImgData) {
        doc.addPage([1200, 800], "landscape");
        doc.setFillColor(15, 15, 20);
        doc.rect(0, 0, 1200, 800, "F");
        doc.setTextColor(255, 255, 255);
        doc.setFont("Helvetica", "bold");
        doc.setFontSize(20);
        doc.text("REVISION DRAWING OVERVIEW (WITH COMPLIANCE MARKINGS)", 50, 50);
        doc.addImage(rightImgData, "PNG", 50, 80, 1100, 670);
      }

      const arrayBuffer = doc.output("arraybuffer");
      const uint8Array = new Uint8Array(arrayBuffer);

      const filePath = await save({
        filters: [{
          name: "PDF Document",
          extensions: ["pdf"]
        }],
        defaultPath: "compliance-report.pdf"
      });

      if (filePath) {
        await writeFile(filePath, uint8Array);
      }
    } catch (error) {
      console.error("PDF generation failed:", error);
    }
  };

  return { exportToPDF };
}
