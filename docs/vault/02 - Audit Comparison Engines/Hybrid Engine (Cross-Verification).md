---
title: Hybrid Engine (Cross-Verification)
type: engine
status: removed
tags: [engine, hybrid, cross-verification, crop-verifier]
---

# ⚖️ Hybrid Engine (Cross-Verification)

> [!WARNING] **REMOVED 2026-08-07 — this engine no longer exists.**
> `method == "hybrid"` was deleted, backend and frontend, by
> [[ADR-006 Removing the Three AI Comparison Methods]], which closed the deletion question
> [[ADR-004 Deterministic-Only Scope]] had explicitly left open. Implementation:
> `hybrid_orchestrator.py + crop_verifier.py + reconciler.py` — recoverable from git history only.
>
> **This note is kept as the record of what the engine did and why**, not as a description of
> the system. Everything below is past tense in fact if not in grammar. `comparison_method` is
> now `Literal["rag"]`, and the deterministic differ is the only engine there is.


The **Hybrid Engine** (`method == "hybrid"`) is the dual-generator cross-verification engine. It runs both Generator A (Deterministic RAG) and Generator B (AI Vision) in parallel, then uses a Crop Verifier to reconcile any disputes.

---

## 🏛️ Dual-Generator Reconciliation Pipeline

```mermaid
flowchart TD
    Ref & Rev Drawings --> GenA["Generator A (Deterministic RAG)"]
    Ref & Rev Drawings --> GenB["Generator B (AI Vision LLM)"]
    
    GenA --> CandA[Candidates A]
    GenB --> CandB[Candidates B]
    
    CandA & CandB --> CandidateMatcher["Candidate Matcher"]
    
    CandidateMatcher -->|Both Agreed| ConfirmedBoth["Status: CONFIRMED_BOTH"]
    CandidateMatcher -->|Disputed / Single Source| CropVerifier["Crop Verifier (Image Sub-tile Visual Inspection)"]
    
    CropVerifier -->|Verifier Decision| ConfirmedSingle["Status: CONFIRMED_SINGLE / CORRECTED"]
    CropVerifier -->|Unresolved| Conflict["Status: CONFLICT (Flagged for Engineer Review)"]
```

---

## 🎯 Verification Outcomes

- **`confirmed_both`**: Both Generator A and Generator B agreed on the finding. High confidence!
- **`confirmed_single`**: Generators disagreed, but Crop Verifier visually inspected the CAD sub-tile and confirmed one side.
- **`corrected_to_matched`**: Crop Verifier inspected the sub-tile image and found no real difference, overriding false alarms to `MATCHED`.
- **`conflict`**: Crop Verifier could not verify either side; flagged for human review.

---

## 🔗 Related Notes
- Return to [[00 - Map of Content (MOC)]]
- See [[RAG Engine (Deterministic)]]
- See [[AI Vision Engine (Live DXF)]]
