---
title: Data Flow & Pipelines
type: architecture
tags: [architecture, data-flow, pipeline, sequence]
---

# 🔄 Data Flow & Pipelines

This document outlines the complete sequence of events from file upload to 2D view rendering, audit execution, and PDF report compilation.

---

## 🛰️ Complete End-to-End Pipeline

```mermaid
sequenceDiagram
    autonumber
    actor Engineer as User / Engineer
    participant UI as Desktop UI (Tauri / React)
    participant API as FastAPI Backend
    participant CAD as ezdxf / ODA Converter
    participant DB as MongoDB (Beanie)
    participant LLM as Gemini AI SDK

    Engineer->>UI: Upload .dxf / .dwg files
    UI->>API: POST /api/v1/drawings/upload
    API->>CAD: Parse DXF Entities & Render PNG
    CAD-->>API: Extracted Entities + PNG Path
    API->>DB: Save DrawingDocument & ExtractedEntities
    API-->>UI: Upload Completed

    Engineer->>UI: Select Room & Click "Run Comparison"
    UI->>API: POST /api/v1/audits/physical-comparison (method)
    
    alt method == "rag"
        API->>API: Run Deterministic RAG (SpatialDiffer + BOMAnalyzer)
    else method == "ai_vision"
        API->>CAD: Read physical .dxf on disk -> build_clean_dxf_manifest
        API->>LLM: Gemini Cascade (Manifest + PNG)
        LLM-->>API: Gemini Response JSON
        API->>API: Deterministic Item Injectors + Spatial Proximity Matcher
    end

    API->>DB: Persist AuditSession & AuditViolations
    API-->>UI: Return PhysicalComparisonResponse
    UI->>Engineer: Render Canvas Markings & Checklist Cards
```

---

## 🔗 Related Notes
- Return to [[00 - Map of Content (MOC)]]
- See [[System Overview]]
- See [[RAG Engine (Deterministic)]]
- See [[AI Vision Engine (Live DXF)]]
