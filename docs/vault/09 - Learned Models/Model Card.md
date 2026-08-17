---
title: Learned Model Card
type: learned-model
tags: [learned-model, hitl]
---

# 🧠 Learned Correction Model — Card

> Auto-generated on each retrain. The compiled model is `finding_classifier.joblib` in this
> folder; this note is the human-readable summary. Trained purely on human corrections —
> no LLM involved.

- **Last trained**: 2026-08-17T07:48:42.809282+00:00
- **Total corrections**: 228
- **Verdict labels**: 112  (thresholds to activate: 40 labels **and** ≥30.0% minority class)
- **Category labels**: 7
- **Verdict model**: ✅ active
- **Exact-match overrides**: 38 matched, 24 changed, 7 reclassified

## Metrics
```json
{'verdict_cv_accuracy': 0.7328, 'verdict_class_balance': {'0': 71, '1': 41}, 'verdict_minority_share': 0.3661, 'verdict_majority_baseline': 0.6339}
```

## Sample of learned "not a real change" patterns
- `notes_section|[removed]originalelementmissingintrace:c2`
- `title_block|jobno(jobnumber)`
- `drawing_views|総厚サ6mm`
- `drawing_views|145`
- `drawing_views|1`
- `drawing_views|center0.25mm`
- `drawing_views|continuous1mmx1`
- `title_block|field`
- `title_block|revision`
- `drawing_views|none`

## Changelog
- 2026-08-17T07:48:42.809282+00:00 — trained on 228 corrections (verdict labels: 112, category labels: 7); verdict model ACTIVE.
- 2026-08-17T07:22:50.609252+00:00 — trained on 228 corrections (verdict labels: 112, category labels: 7); verdict model ACTIVE.
- 2026-08-17T07:17:12.433648+00:00 — trained on 228 corrections (verdict labels: 112, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:34:23.418084+00:00 — trained on 227 corrections (verdict labels: 111, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:34:15.709270+00:00 — trained on 226 corrections (verdict labels: 110, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:34:04.477982+00:00 — trained on 225 corrections (verdict labels: 109, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:33:55.987961+00:00 — trained on 224 corrections (verdict labels: 108, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:33:40.861086+00:00 — trained on 223 corrections (verdict labels: 107, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:33:19.508310+00:00 — trained on 222 corrections (verdict labels: 106, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:33:11.519819+00:00 — trained on 221 corrections (verdict labels: 106, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:32:15.556150+00:00 — trained on 220 corrections (verdict labels: 106, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:32:07.529461+00:00 — trained on 219 corrections (verdict labels: 106, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:31:59.998149+00:00 — trained on 218 corrections (verdict labels: 106, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:31:49.707479+00:00 — trained on 217 corrections (verdict labels: 106, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:31:39.308661+00:00 — trained on 216 corrections (verdict labels: 105, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:31:31.374973+00:00 — trained on 215 corrections (verdict labels: 104, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:31:15.915478+00:00 — trained on 214 corrections (verdict labels: 103, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:31:08.782606+00:00 — trained on 213 corrections (verdict labels: 102, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:30:50.543631+00:00 — trained on 212 corrections (verdict labels: 102, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:30:36.925685+00:00 — trained on 211 corrections (verdict labels: 102, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:30:29.063609+00:00 — trained on 212 corrections (verdict labels: 103, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:30:14.874099+00:00 — trained on 211 corrections (verdict labels: 102, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:30:03.773967+00:00 — trained on 210 corrections (verdict labels: 102, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:29:47.957172+00:00 — trained on 209 corrections (verdict labels: 102, category labels: 7); verdict model ACTIVE.
- 2026-08-17T06:29:29.730975+00:00 — trained on 208 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:29:26.565517+00:00 — trained on 207 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:29:22.933707+00:00 — trained on 206 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:29:19.836826+00:00 — trained on 205 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:29:00.251970+00:00 — trained on 204 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:28:56.804677+00:00 — trained on 203 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:28:51.529958+00:00 — trained on 202 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:28:46.876692+00:00 — trained on 201 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:28:39.024391+00:00 — trained on 200 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:28:06.128353+00:00 — trained on 199 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:28:03.230686+00:00 — trained on 198 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:27:57.380201+00:00 — trained on 197 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:27:53.629119+00:00 — trained on 196 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:27:50.433196+00:00 — trained on 195 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:27:47.918459+00:00 — trained on 194 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:27:42.910959+00:00 — trained on 193 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
- 2026-08-17T06:27:13.772527+00:00 — trained on 192 corrections (verdict labels: 101, category labels: 7); verdict model HELD (class imbalance, minority 29.7%).
