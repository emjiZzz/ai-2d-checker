---
title: Learned Model Card
type: learned-model
tags: [learned-model, hitl]
---

# 🧠 Learned Correction Model — Card

> Auto-generated on each retrain. The compiled model is `finding_classifier.joblib` in this
> folder; this note is the human-readable summary. Trained purely on human corrections —
> no LLM involved.

- **Last trained**: 2026-08-17T02:37:43.054561+00:00
- **Total corrections**: 104
- **Verdict labels**: 92  (thresholds to activate: 40 labels **and** ≥30.0% minority class)
- **Category labels**: 6
- **Verdict model**: ⛔ held — count met (92/40) but the minority class is 13.0% against a 30.0% floor. Needs `confirmed_valid` / `verdict_changed`, not more `dismissed`.
- **Exact-match overrides**: 52 matched, 3 changed, 6 reclassified

## Metrics
```json
{'verdict_abstained': {'reason': 'class_imbalance', 'minority_share': 0.1304, 'required': 0.3, 'detail': "92 labels meet MIN_TRAIN=40, but the minority class is 13.0% of the corpus against a 30.0% floor. Add class-1 corrections (confirmed_valid, verdict_changed); more 'dismissed' makes this worse."}, 'verdict_class_balance': {'0': 80, '1': 12}, 'verdict_minority_share': 0.1304}
```

## Sample of learned "not a real change" patterns
- `title_block|jobno(jobnumber)`
- `title_block|0`
- `drawing_views|a`
- `bill_of_materials|0.39`
- `drawing_views|271`
- `drawing_views|geometry:4line,1polyline`
- `drawing_views|279`
- `drawing_views|none`
- `drawing_views|center0.25mmx5`
- `title_block|stockqty(stockqty)`

## Changelog
- 2026-08-17T02:37:43.054561+00:00 — trained on 104 corrections (verdict labels: 92, category labels: 6); verdict model HELD (class imbalance, minority 13.0%).
- 2026-08-17T02:37:17.053895+00:00 — trained on 103 corrections (verdict labels: 91, category labels: 6); verdict model HELD (class imbalance, minority 13.2%).
- 2026-08-17T02:36:46.937383+00:00 — trained on 102 corrections (verdict labels: 90, category labels: 6); verdict model HELD (class imbalance, minority 13.3%).
- 2026-08-17T02:36:44.398566+00:00 — trained on 103 corrections (verdict labels: 91, category labels: 6); verdict model HELD (class imbalance, minority 13.2%).
- 2026-08-17T02:36:39.248343+00:00 — trained on 102 corrections (verdict labels: 90, category labels: 6); verdict model HELD (class imbalance, minority 13.3%).
- 2026-08-17T02:36:35.843602+00:00 — trained on 103 corrections (verdict labels: 91, category labels: 6); verdict model HELD (class imbalance, minority 13.2%).
- 2026-08-17T02:36:05.672459+00:00 — trained on 102 corrections (verdict labels: 90, category labels: 6); verdict model HELD (class imbalance, minority 13.3%).
- 2026-08-17T02:09:54.754206+00:00 — trained on 101 corrections (verdict labels: 89, category labels: 6); verdict model HELD (class imbalance, minority 13.5%).
- 2026-08-17T02:09:34.420927+00:00 — trained on 100 corrections (verdict labels: 88, category labels: 6); verdict model HELD (class imbalance, minority 13.6%).
- 2026-08-17T01:58:07.759987+00:00 — trained on 99 corrections (verdict labels: 87, category labels: 6); verdict model HELD (class imbalance, minority 13.8%).
- 2026-08-17T01:57:57.725143+00:00 — trained on 98 corrections (verdict labels: 86, category labels: 6); verdict model HELD (class imbalance, minority 14.0%).
- 2026-08-17T01:16:35.687250+00:00 — trained on 97 corrections (verdict labels: 85, category labels: 6); verdict model HELD (class imbalance, minority 14.1%).
- 2026-08-17T01:05:42.900285+00:00 — trained on 96 corrections (verdict labels: 84, category labels: 6); verdict model HELD (class imbalance, minority 14.3%).
- 2026-08-17T01:05:24.963496+00:00 — trained on 95 corrections (verdict labels: 83, category labels: 6); verdict model HELD (class imbalance, minority 13.2%).
- 2026-08-17T01:05:23.640202+00:00 — trained on 94 corrections (verdict labels: 82, category labels: 6); verdict model HELD (class imbalance, minority 13.4%).
- 2026-08-17T01:05:22.189738+00:00 — trained on 93 corrections (verdict labels: 81, category labels: 6); verdict model HELD (class imbalance, minority 13.6%).
- 2026-08-17T01:05:21.550491+00:00 — trained on 92 corrections (verdict labels: 80, category labels: 6); verdict model HELD (class imbalance, minority 13.8%).
- 2026-08-17T01:03:45.112409+00:00 — trained on 91 corrections (verdict labels: 79, category labels: 6); verdict model HELD (class imbalance, minority 13.9%).
- 2026-08-17T01:02:42.295004+00:00 — trained on 90 corrections (verdict labels: 78, category labels: 6); verdict model HELD (class imbalance, minority 14.1%).
- 2026-08-17T01:01:44.936234+00:00 — trained on 89 corrections (verdict labels: 77, category labels: 6); verdict model HELD (class imbalance, minority 14.3%).
- 2026-08-17T00:59:56.965398+00:00 — trained on 88 corrections (verdict labels: 76, category labels: 6); verdict model HELD (class imbalance, minority 14.5%).
- 2026-08-17T00:59:53.406303+00:00 — trained on 87 corrections (verdict labels: 75, category labels: 6); verdict model HELD (class imbalance, minority 14.7%).
- 2026-08-17T00:59:50.488012+00:00 — trained on 86 corrections (verdict labels: 74, category labels: 6); verdict model HELD (class imbalance, minority 14.9%).
- 2026-08-17T00:59:47.987655+00:00 — trained on 87 corrections (verdict labels: 75, category labels: 6); verdict model HELD (class imbalance, minority 14.7%).
- 2026-08-17T00:41:56.533317+00:00 — trained on 86 corrections (verdict labels: 47, category labels: 6); verdict model HELD (class imbalance, minority 23.4%).
- 2026-08-17T00:39:15.044440+00:00 — trained on 86 corrections (verdict labels: 47, category labels: 6); verdict model HELD (class imbalance, minority 23.4%).
- 2026-08-17T00:36:36.768238+00:00 — trained on 85 corrections (verdict labels: 47, category labels: 6); verdict model HELD (class imbalance, minority 23.4%).
- 2026-08-17T00:36:35.952734+00:00 — trained on 84 corrections (verdict labels: 46, category labels: 6); verdict model HELD (class imbalance, minority 23.9%).
- 2026-08-17T00:36:34.943809+00:00 — trained on 83 corrections (verdict labels: 45, category labels: 6); verdict model HELD (class imbalance, minority 24.4%).
- 2026-08-17T00:35:46.869023+00:00 — trained on 82 corrections (verdict labels: 44, category labels: 6); verdict model HELD (class imbalance, minority 25.0%).
- 2026-08-17T00:35:45.655183+00:00 — trained on 81 corrections (verdict labels: 43, category labels: 6); verdict model HELD (class imbalance, minority 25.6%).
- 2026-08-17T00:35:33.824087+00:00 — trained on 80 corrections (verdict labels: 42, category labels: 6); verdict model HELD (class imbalance, minority 26.2%).
- 2026-08-17T00:35:32.370751+00:00 — trained on 79 corrections (verdict labels: 41, category labels: 6); verdict model HELD (class imbalance, minority 24.4%).
- 2026-08-16T23:58:44.393592+00:00 — trained on 78 corrections (verdict labels: 40, category labels: 6); verdict model HELD (class imbalance, minority 25.0%).
- 2026-08-11T09:47:41.387275+00:00 — trained on 77 corrections (verdict labels: 39, category labels: 6); verdict model warming up.
- 2026-08-11T09:47:37.921118+00:00 — trained on 76 corrections (verdict labels: 39, category labels: 6); verdict model warming up.
- 2026-08-11T09:47:32.518090+00:00 — trained on 75 corrections (verdict labels: 39, category labels: 6); verdict model warming up.
- 2026-08-11T09:46:26.469406+00:00 — trained on 74 corrections (verdict labels: 39, category labels: 6); verdict model warming up.
- 2026-08-11T09:45:47.712569+00:00 — trained on 73 corrections (verdict labels: 39, category labels: 6); verdict model warming up.
- 2026-08-11T02:52:40.031702+00:00 — trained on 72 corrections (verdict labels: 38, category labels: 6); verdict model warming up.
- 2026-08-11T02:52:37.499571+00:00 — trained on 71 corrections (verdict labels: 37, category labels: 6); verdict model warming up.
