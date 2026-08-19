---
title: Learned Model Card
type: learned-model
tags: [learned-model, hitl]
---

# 🧠 Learned Correction Model — Card

> Auto-generated on each retrain. The compiled model is `finding_classifier.joblib` in this
> folder; this note is the human-readable summary. Trained purely on human corrections —
> no LLM involved.

- **Last trained**: 2026-08-19T01:43:37.183321+00:00
- **Total corrections**: 243
- **Verdict labels**: 127  (thresholds to activate: 40 labels **and** ≥30.0% minority class)
- **Category labels**: 7
- **Verdict model**: ✅ active
- **Exact-match overrides**: 40 matched, 30 changed, 7 reclassified

## Metrics
```json
{'verdict_cv_accuracy': 0.7709, 'verdict_class_balance': {'0': 73, '1': 54}, 'verdict_minority_share': 0.4252, 'verdict_majority_baseline': 0.5748}
```

## Sample of learned "not a real change" patterns
- `notes_section|4ロール:12(2x6台)->4ロール:12(2x6台)`
- `drawing_views|center0.25mmx5->center0.25mmx5`
- `title_block|original->revision`
- `title_block|none->none`
- `drawing_views|none->8`
- `drawing_views|none->a`
- `drawing_views|continuous0.25mmx19->continuous0.25mmx1`
- `drawing_views|r3->none`
- `drawing_views|geometry:24line,3polyline->`
- `drawing_views|center0.25mm->center0.25mm`

## Changelog
- 2026-08-19T01:43:37.183321+00:00 — trained on 243 corrections (verdict labels: 127, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:43:26.308324+00:00 — trained on 243 corrections (verdict labels: 127, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:43:15.226765+00:00 — trained on 241 corrections (verdict labels: 125, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:43:05.080035+00:00 — trained on 240 corrections (verdict labels: 124, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:42:52.999841+00:00 — trained on 239 corrections (verdict labels: 123, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:42:42.178252+00:00 — trained on 238 corrections (verdict labels: 122, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:18:51.152389+00:00 — trained on 237 corrections (verdict labels: 121, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:18:41.383874+00:00 — trained on 236 corrections (verdict labels: 120, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:18:18.522174+00:00 — trained on 235 corrections (verdict labels: 119, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:18:09.166161+00:00 — trained on 235 corrections (verdict labels: 119, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:17:55.483973+00:00 — trained on 233 corrections (verdict labels: 117, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:17:34.947347+00:00 — trained on 232 corrections (verdict labels: 116, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:17:24.067291+00:00 — trained on 231 corrections (verdict labels: 115, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:17:00.026233+00:00 — trained on 230 corrections (verdict labels: 114, category labels: 7); verdict model ACTIVE.
- 2026-08-19T01:16:26.296616+00:00 — trained on 229 corrections (verdict labels: 113, category labels: 7); verdict model ACTIVE.
- 2026-08-17T09:38:28.731478+00:00 — trained on 228 corrections (verdict labels: 112, category labels: 7); verdict model ACTIVE.
- 2026-08-17T09:33:13.419862+00:00 — trained on 228 corrections (verdict labels: 112, category labels: 7); verdict model ACTIVE.
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
