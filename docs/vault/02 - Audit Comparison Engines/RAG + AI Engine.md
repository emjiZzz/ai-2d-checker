---
title: RAG + AI Engine
type: engine
tags: [engine, rag-ai, gemini, structured-context]
---

# 🤖 RAG + AI Engine

The **RAG + AI Engine** (`method == "rag_ai"`) combines database-ingested structured CAD context (`ExtractedEntity` models from MongoDB) with Gemini LLM reasoning.

---

## 🛠️ Pipeline Flow

```mermaid
flowchart TD
    DB[(MongoDB ExtractedEntities)] --> ContextBuilder["build_structured_context"]
    ContextBuilder --> JSONContext[JSON Structured Context]
    PNG[Drawing PNG Renders] & JSONContext --> Prompt["build_multimodal_contents"]
    Prompt --> Gemini[Gemini Cascade]
    Gemini --> Parser["result_parser (parse_and_normalize_gemini_json)"]
    Parser --> Overrides["apply_deterministic_overrides (BOM & Title Block)"]
    Overrides --> Response["PhysicalComparisonResponse"]
```

---

## 🔗 Related Notes
- Return to [[00 - Map of Content (MOC)]]
- See [[RAG Engine (Deterministic)]]
- See [[AI Vision Engine (Live DXF)]]
