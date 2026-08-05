---
title: Hybrid Engine (Cross-Verification)
type: engine
tags: [engine, hybrid, cross-verification, crop-verifier]
---

# ⚖️ Hybrid Engine (Cross-Verification)

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
