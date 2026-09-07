---
title: Copilot AI Streaming Engine
type: backend
tags: [backend, copilot, streaming, sse, gemini]
---

# 💬 Copilot AI Streaming Engine

The **Copilot Assistant** (`services/backend/infrastructure/ai/copilot/streaming_engine.py`) provides real-time AI conversation and CAD engineering guidance inside the desktop workspace.

---

## ⚡ Real-Time Streaming Architecture

```mermaid
flowchart LR
    User[User Question in Chat UI] --> SSE["Server-Sent Events (SSE) Endpoint"]
    SSE --> Copilot["streaming_engine.py"]
    Copilot --> Context["Gather Room Context (Drawings, BOM, Violations)"]
    Context --> GeminiStream["Gemini SDK Stream Response"]
    GeminiStream --> UIStream["Stream Tokens to Chat Drawer UI"]
```

1. **Context-Aware Assistance**: Automatically feeds current room findings, BOM discrepancies, and active drawing metadata into the system prompt.
2. **Server-Sent Events (SSE)**: Streams text tokens incrementally to the desktop UI for instant response rendering.

---

## 🔗 Related Notes
- Return to [[00 - Map of Content (MOC)]]
- See [[System Overview]]
- See [[AI Vision Engine (Live DXF)]]
