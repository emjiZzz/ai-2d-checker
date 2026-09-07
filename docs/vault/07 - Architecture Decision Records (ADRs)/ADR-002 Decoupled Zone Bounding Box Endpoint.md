---
title: ADR-002 Decoupled Zone Bounding Box Endpoint
type: adr
tags: [adr, architecture, api, schemas, gemini, zone-detector]
status: accepted
date: 2026-07-28
---

# 🏗️ ADR-002 — Decoupled Zone Bounding Box Endpoint

## ❓ Context & Problem Statement
To maximize RAG transparency and allow engineers to visually debug zone detection (`title`, `title_upper_left`, `bom`, `tolerance`, `notes`, `iso`, `views`), we needed to expose zone bounding box coordinates `(xmin, ymin, xmax, ymax)` to the desktop UI.

Initial proposals considered embedding an `Optional[dict]` onto `PhysicalComparisonResponse` or `ComparisonDiagnostics`. However, code analysis revealed a critical blocking defect:
> **Gemini LLM API Schema Validation Error**: `PhysicalComparisonResponse` is passed directly as Gemini's `response_schema` in `gemini_client.py:75`. A bare `dict` field converts to open-ended `additionalProperties` in OpenAPI schema, which Gemini rejects with a **`400 INVALID_ARGUMENT`** error on *every request*.

---

## 💡 Decision Drivers
1. **Gemini Schema Safety**: Must not add open-ended dicts or unconstrained shapes to Gemini response schemas.
2. **Zero LLM Token Cost**: Inspecting zone bounding boxes should be instant ($0.00 cost) without triggering expensive AI Vision / LLM comparison passes.
3. **Cache Independence**: Cached audit JSON payloads should not prevent viewing real-time zone boxes.

---

## 🎯 Architecture Decision
We decoupled zone bounding box fetching into a dedicated, standalone REST endpoint:
$$\mathbf{\text{GET /api/v1/drawings/\{id\}/zones}}$$

```mermaid
flowchart TD
    Client[Desktop App UI] -->|1. GET /drawings/{id}/zones| Endpoint["routers/drawings.py"]
    Endpoint -->|2. Pure DXF BBox Math| Detector["table_extractor / zone_detector.py"]
    Detector -- 3. Return Fixed ZoneBBox Model --> Client
    Client -->|4. Imperative Draw| Canvas["CanvasRenderer (Zero LLM Cost)"]
```

---

## ✅ Consequences & Benefits
- **Zero API Cost**: Zone bounding boxes compute via pure geometry without calling Gemini or consuming tokens. **Not instant, though**: measured end-to-end at ~220ms on a 528-entity A2 sheet (three consecutive runs, 0.220/0.220/0.226s), because `_expand_bbox` flood-fills over every entity. An earlier revision of this ADR claimed ~5ms, which was never measured and is off by ~44x. Cost scales with entity count, so the endpoint is fetched lazily on toggle and cached client-side per drawing id — do not call it eagerly on drawing load.
- **Robust Gemini Safety**: `PhysicalComparisonResponse` remains a clean, fixed-field model safe for Gemini's `response_schema`.
- **Independent Debugging**: Developers can inspect drawing zones for a single drawing before or without running a full comparison.

---

## 🔗 Related Notes
- See [[Zone Detector & Bounding Boxes]]
- See [[Gotcha - Comparison Cache Invalidation]]
- Return to [[00 - Map of Content (MOC)]]
