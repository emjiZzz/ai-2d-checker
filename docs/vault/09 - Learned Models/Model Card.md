---
title: Learned Model Card
type: learned-model
tags: [learned-model, hitl]
---

# 🧠 Learned Correction Model — Card

> Auto-generated on each retrain. The compiled model is `finding_classifier.joblib` in this
> folder; this note is the human-readable summary. Trained purely on human corrections —
> no LLM involved.

- **Last trained**: 2026-08-03T00:09:22.729833+00:00
- **Total corrections**: 22
- **Verdict labels**: 21  (threshold to activate model: 40)
- **Category labels**: 1
- **Verdict model**: ⏳ warming up (21/40)
- **Exact-match overrides**: 11 matched, 1 changed, 1 reclassified

## Metrics
```json
{}
```

## Sample of learned "not a real change" patterns
- `title_block|qty(quantity)`
- `title_block|stockqty(stockqty)`
- `title_block|scale(sheetscale)`
- `title_block|jobno(jobnumber)`
- `title_block|unitno(unitnumber)`
- `title_block|partno(partnumber)`
- `title_block|ブシュ`
- `title_block|field`
- `title_block|machinecode/unitcode`
- `drawing_views|geometry:4line,1polyline`

## Changelog
- 2026-08-03T00:09:22.729833+00:00 — trained on 22 corrections (verdict labels: 21, category labels: 1); verdict model warming up.
