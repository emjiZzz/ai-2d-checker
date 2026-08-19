---
title: Learned Model Card
type: learned-model
tags: [learned-model, hitl]
---

# 🧠 Learned Correction Model — Card

> Auto-generated on each retrain. The compiled model is `finding_classifier.joblib` in this
> folder; this note is the human-readable summary. Trained purely on human corrections —
> no LLM involved.

- **Last trained**: 2026-08-19T09:13:23.465678+00:00
- **Total corrections**: 261
- **Verdict labels**: 140  (thresholds to activate: 40 labels **and** ≥30.0% minority class)
- **Category labels**: 7
- **Verdict model**: ✅ active
- **Exact-match overrides**: 38 matched, 35 changed, 7 reclassified

## Metrics
```json
{'verdict_cv_accuracy': 0.7923, 'verdict_class_balance': {'0': 73, '1': 67}, 'verdict_minority_share': 0.4786, 'verdict_majority_baseline': 0.5214}
```

## Sample of learned "not a real change" patterns
- `drawing_views|continuous0.25mm->continuous0.25mm`
- `drawing_views|continuous0.25mmx19->continuous0.25mmx1`
- `notes_section|2ロール:4(2x2台)->none`
- `bill_of_materials|1->1`
- `drawing_views|none->continuous0.5mmx17`
- `title_block|partno(partnumber)->`
- `title_block|ブシュ->`
- `title_block|none->none`
- `title_block|scale(sheetscale)->`
- `drawing_views|none->8`

## Changelog
- 2026-08-19T09:13:23.465678+00:00 — trained on 261 corrections (verdict labels: 140, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:51:49.723758+00:00 — trained on 260 corrections (verdict labels: 140, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:51:39.802648+00:00 — trained on 260 corrections (verdict labels: 140, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:51:26.815504+00:00 — trained on 260 corrections (verdict labels: 140, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:51:15.046216+00:00 — trained on 258 corrections (verdict labels: 138, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:50:51.921479+00:00 — trained on 256 corrections (verdict labels: 136, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:50:18.590806+00:00 — trained on 255 corrections (verdict labels: 135, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:49:57.144371+00:00 — trained on 254 corrections (verdict labels: 135, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:49:22.384650+00:00 — trained on 253 corrections (verdict labels: 135, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:49:11.678310+00:00 — trained on 252 corrections (verdict labels: 135, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:47:31.878623+00:00 — trained on 251 corrections (verdict labels: 135, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:47:19.843383+00:00 — trained on 251 corrections (verdict labels: 135, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:47:08.957952+00:00 — trained on 251 corrections (verdict labels: 135, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:46:57.466237+00:00 — trained on 250 corrections (verdict labels: 134, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:46:47.275038+00:00 — trained on 247 corrections (verdict labels: 131, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:46:37.413777+00:00 — trained on 246 corrections (verdict labels: 130, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:46:28.039418+00:00 — trained on 245 corrections (verdict labels: 129, category labels: 7); verdict model ACTIVE.
- 2026-08-19T08:46:17.914860+00:00 — trained on 244 corrections (verdict labels: 128, category labels: 7); verdict model ACTIVE.
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
