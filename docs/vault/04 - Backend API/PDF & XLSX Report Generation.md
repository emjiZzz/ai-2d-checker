---
title: PDF & XLSX Report Generation
type: backend
tags: [backend, pdf, xlsx, reportlab, redline]
---

# 📄 PDF & XLSX Report Generation

The report export subsystem (`ReportGenerator` in `services/backend/infrastructure/audit/report_generator.py`) generates official audit PDF reports and detailed technical Excel sheets.

---

## 🛠️ Export Pipeline

```mermaid
flowchart TD
    Session[Audit Session & Violations] --> Decision{Export Format?}
    
    Decision -->|PDF| Redline["RedlineWriter (Embed DXF Redline Bounding Markers)"]
    Redline --> ReportLab["ReportLab Compilation"]
    ReportLab --> OfficialPDF["AI-2D-Checker_Report.pdf"]
    
    Decision -->|XLSX| OpenPyXL["OpenPyXL Multi-Sheet Compilation"]
    OpenPyXL --> StructuredExcel["AI-2D-Checker_Report.xlsx"]
```

1. **PDF Compilation (`/api/v1/reports/{session_id}/pdf`)**:
   - Embeds redline blueprint exports with color-coded violation boxes (`RedlineWriter`).
   - Formats non-conformances into structured tables sorted by severity (`critical`, `high`, `medium`, `low`).

2. **XLSX Technical Sheets (`/api/v1/reports/{session_id}/xlsx`)**:
   - Exports structured multi-tab Excel sheets containing BOM discrepancies, Title Block changes, and Drawing View checklist items.

---

## 🔗 Related Notes
- Return to [[00 - Map of Content (MOC)]]
- See [[RAG Engine (Deterministic)]]
- See [[System Overview]]
