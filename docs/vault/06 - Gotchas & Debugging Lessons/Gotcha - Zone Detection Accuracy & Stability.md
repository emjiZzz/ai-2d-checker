---
title: Gotcha - Zone Detection Accuracy & Stability
type: gotcha
tags: [gotcha, zone-detector, bounding-box, measurement, coordinate-space]
status: partially-resolved
date: 2026-07-28
---

# 🔥 Gotcha — Zone Detection Accuracy & Stability

Making the zone boxes visible (see [[ADR-002 Decoupled Zone Bounding Box Endpoint]]) immediately showed that [[Zone Detector & Bounding Boxes]] produces badly wrong boxes on real drawings. This note records what was measured, what was fixed, and what is still broken — so the next person starts from evidence rather than from the overlay's first impression.

All figures below are measured across a 6-drawing corpus (3 reference/revision pairs, KMTI A-series sheets), not estimated.

---

## 📏 Measured state — RE-MEASURED 2026-07-29

The table below it is the **original** measurement and is kept for comparison; these are the
current numbers, taken after ELLIPSE/SPLINE ingestion, geometric `iso` detection, the
cap-then-pad fix and the Shift-JIS repair.

Corpus is now 4 drawings (2 pairs, part numbers A0N01 and A1N01) rather than the original 6.

| Zone | Spread then → now | Detected | Mean area | Anchors matched |
| :--- | :--- | :--- | ---: | :--- |
| `bom` | 4.6 → **1.7pp** | 4/4 | 2.7% | same 4 on every drawing |
| `iso` | 0.0 (never found) → **1.8pp** | **2/4** | 8.6% | geometric |
| `views` | 33.0 → **0.0pp** | 4/4 | **100.0%** (was 119.7% — see below) | derived |
| `tolerance` | 64.2 → **11.3pp** | **4/6 → 4/4** | 28.5% | same 3 on every drawing |
| `notes` | 37.1 → **11.3pp** | 4/6 → 4/4 | 27.8% | same 3 on every drawing |
| `title` | 12.9 → **11.6pp** | 4/4 | 21.0% | same 6, plus `訂正` on 2 of 4 |
| `title_upper_left` | 3.8 → **25.8pp** | 4/4 | 6.0% | same 8 on every drawing |

### ✅ `tolerance` is explained, and it was the Shift-JIS bug

64.2pp → 11.3pp, and detection 4/6 → 4/4. The anchors matched on all four drawings are
`tolerances unless otherwise specified`, `roughness range` and **`表面粗さ`** — and `表` is
`0x95 0x5C`, one of the characters that
[[Gotcha - AutoCAD Control Escape Codes|MTEXT stripping was destroying]]. That anchor could
not match before the repair, so the zone fell back or seeded from fewer anchors on the
drawings where the other two phrases were absent.

`notes` improved for the same reason and by the same amount.

### ❌ Negative result — the anchor-disagreement hypothesis is dead

The standing suspicion was that `title`/`tolerance` instability came from *different anchors
matching on different sheets* — `tolerance` carries 23 anchors, several generic. **Measured:
every zone matched an identical anchor set on all four drawings**, the single exception being
`訂正` on two of four for `title`.

So the remaining spread is **not** anchor disagreement. Do not re-investigate that. Logging
survives as `zones["_anchor_matches"]` so the question can be re-asked cheaply on a new corpus.

### 🔍 What the remaining spread actually is

The four drawings are two AutoCAD-authored sheets and two SolidWorks-derived ones, and the two
within each group produce **near-identical boxes**. The spread is therefore bimodal — a real
difference between two authoring toolchains, not detector jitter. `title_upper_left` is the
clearest case: `x 0.039..0.230` on the AutoCAD sheets versus `x 0.032..0.418` on the SW ones,
which is what turned its 3.8pp into 25.8pp when the corpus composition changed.

> [!IMPORTANT]
> That makes `title_upper_left`'s apparent regression a **corpus change, not a detector
> change**. Comparing a spread figure across two different corpora measures the corpora.

### ✅ `views` is now a predicate

`_derive_views_zone` returns **the sheet**, and `in_views(x, y, regions)` carries the
exclusion. Measured after the change: **0.0pp spread, 100.0% area** on all four drawings.

Two defects were fixed at once. The old content-percentile box was **not a bound** (119.7% of
sheet — larger than the drawing, because the percentile is taken over content extending past
the line-derived frame and then padded), and **not exact either** (anything in the outer 5% of
the drawing area fell outside it, so containment produced false negatives exactly at the sheet
edges where views content legitimately reaches).

> [!WARNING]
> `views` now reports **0.0pp spread**. That is not the detector becoming perfect — it is the
> box being the sheet by definition, so it cannot vary. Exactly the trap Trap 1 records for
> `iso`'s old 0.0pp. Never read this row as a stability measurement; the meaningful question
> for `views` is whether `in_views()` classifies points correctly, not where its box sits.

One consequence worth knowing: with no template, the zone editor now seeds `views` at the full
sheet rather than a content-shaped box. A pinned template still wins, so a user who has aligned
`views` sees their own box.

Subtlety in the implementation: `_derive_views_zone` is passed `bounds`, **not** the
`(min_x..max_y)` effective rect. Those fall back to a literal `0..1000` placeholder when a
drawing has no measurable frame, and returning it would mark `views` `content_aware` —
claiming a measurement of a sheet that could not be measured, and breaking the frontend's
`isPlaceholderOnly` overlay guard. Pinned by
`test_zone_overlay_endpoint.py::test_real_detector_with_no_sheet_bounds_flags_every_zone_as_placeholder`,
which caught exactly that regression.

### 🚩 Things this surfaced

1. **`views` covered 119.7% of the sheet** — larger than the drawing itself, because
   `_derive_views_zone` padded a 5–95 percentile of content that extends past the line-derived
   bounds. **Fixed the same day**; see "views is now a predicate" below.
2. **`title` (21.0%) and `tolerance` (28.5%) overlap heavily** — on the AutoCAD sheets
   `title` is `x 0.280..0.880, y 0.053..0.403` and `tolerance` is `x 0.041..0.991,
   y 0.103..0.403`. Both are safe zones excluded from comparison, so the overlap is not
   currently harmful, but any per-zone attribution across them is ambiguous.

---

## 📏 Measured state (original, 6-drawing corpus — superseded above)

**Positional spread** = the largest variation of any of the four fractional box edges across the corpus, in percentage points of sheet. Low = the zone sits in the same place on every drawing.

| Zone | Spread | Detected `content_aware` | Class |
| :--- | ---: | :--- | :--- |
| `title_upper_left` | 3.8pp | 6/6 | frame furniture |
| `bom` | 4.6pp | 6/6 | frame furniture |
| `title` | 12.9pp | 6/6 | furniture, still noisy |
| `views` | 33.0pp | 6/6 | floating content |
| `notes` | 37.1pp | 4/6 | floating content |
| `tolerance` | 64.2pp | 4/6 | expected furniture, behaves as floating |
| `iso` | 0.0pp | **0/6** → now 3/6 (the 3 that have one) | **was never detected**; fixed — see [[Gotcha - Dropped ELLIPSE & SPLINE Geometry]] |

---

## ⚠️ Trap 1 — `iso`'s perfect stability is an artifact — **RESOLVED**

`iso` reports **0.0pp spread**, which reads as the most stable zone in the system. It is the opposite: no drawing in the corpus has *ever* resolved `iso` content-aware, so all six carry the identical percentage-grid guess. Zero variance across six identical guesses is **absence of detection**, not stability.

> [!WARNING]
> Never read a stability metric without its detection rate. An earlier analysis in this project read `iso`'s 0.0% reference-vs-revision agreement as evidence the zone was reliable; it was evidence the zone had never been found.

> [!SUCCESS]
> **Root cause found and fixed — see [[Gotcha - Dropped ELLIPSE & SPLINE Geometry]].**
> The suspicion below was half right. An isometric view does carry no distinguishing text,
> so `ZONE_ANCHORS["iso"]` could never match. But the deeper reason no geometric detector
> would have worked either is that `EntityMapper.map_any` had **no branch for `ELLIPSE` or
> `SPLINE`** and dropped both at ingestion — 90% of one iso view's entities never reached
> the database. `iso` is now detected from ellipse density (a circle seen at an angle
> projects to an ellipse), which separates the corpus completely: 38/63/10 ellipses on the
> three sheets with an iso view, 0/0/0 on the three without.
>
> Note the *non-orthogonal line cluster* idea floated below was measured and is **worse** —
> dimension arrowheads and surface-finish blocks are also drawn near 30°. Details in the
> new note's negative-results section.

The original hypothesis, kept for the record: an isometric view often carries **no distinguishing text at all**, which would make text-anchored detection structurally the wrong tool for it. `ZONE_ANCHORS["iso"]` lists `isometric`, `iso view`, `等角図`, `立体図` — none of which appear on these sheets. Candidate fixes are geometric (a cluster of non-orthogonal lines outside the orthographic views) or AI vision.

---

## 🛠️ Fixed — caps were applied before padding

`_expand_bbox` enforced `max_w`/`max_h` **inside** the growth loop, then added `BBOX_PADDING = 30.0` to all four sides on return. Every content-aware box therefore came out up to `2 * padding` oversized in each axis, and `ZONE_MAX_LIMITS` were not actually limits.

Concretely: `title` grew to 259 units (inside its 286-unit cap) and returned at 319 — **39.1% of sheet height against a declared 35% ceiling**.

Fixed by padding and then clamping back inside the caps, trimming symmetrically so the box stays centred on the cluster found. Effect:

| Zone | Spread before → after | Mean area before → after |
| :--- | :--- | :--- |
| `title` | 17.7 → 12.9pp | 22.9% → 17.4% |
| `views` | 40.4 → 33.0pp | 85.9% → 78.9% |
| `notes` | 39.9 → 37.1pp | 27.8% → 13.8% |
| `tolerance` | 72.8 → 64.2pp | 31.3% → 23.1% |

Real but partial. **The hypothesis that `title`/`tolerance` instability was purely padding contamination is disproved** — both are printed sheet furniture that should not move, and both remain unstable after the fix.

> [!IMPORTANT]
> This changed zone geometry on every drawing, and the whole backend suite still passed — **nothing asserted on box size at all**. `tests/test_zone_detector_caps.py` now pins the cap invariant. `COMPARISON_CACHE_VERSION` was bumped to `v8`; see [[Gotcha - Comparison Cache Invalidation]] for why that is mandatory after any zone-geometry change.

---

## ❌ Negative result — scale-relative padding does not help

`BBOX_PADDING` is absolute, so 30 units is 2.5× more significant on the corpus's 327-unit-tall sheet than on its 817-unit one. That looked like an obvious driver of cross-sheet divergence.

Implemented as a fraction of sheet height calibrated to be a no-op on the reference sheet, then measured: `title_upper_left` and `bom` improved by 0.4pp and 0.3pp, **`views` got worse by 3.0pp** and `notes` by 0.6pp, `title` and `tolerance` unchanged. Net neutral-to-negative, so it was reverted.

**Do not retry this without new evidence.** Absolute padding is conceptually odd across scales but is measurably not what drives zone instability here.

---

## 🧭 Trap 2 — two coordinate spaces with opposite Y directions

Zone geometry lives in two spaces, and they disagree on Y. Getting the conversion backwards produces a *vertically mirrored* set of boxes, which looks plausible because most zones sit near the sheet's vertical centre.

| Space | Y direction | Used by |
| :--- | :--- | :--- |
| Detected boxes (`GET /drawings/{id}/zones`) | **Y-up** (CAD) — larger `y` is nearer the top | `worldToScreen`, which applies the flip |
| `customRegions` / template fractions | **Y-down** — fraction 0 is the top | the ROI drag hit-test, which does *not* invert |

Both are correct in their own space. Converting between them **flips Y and swaps min/max**: a zone's CAD `ymax` becomes its fractional `yMin`. The conversion lives in exactly one place, `apps/desktop/src/utils/zoneFractions.ts`.

Verified against real entity coordinates rather than reasoning: the two notes lines in `M7452A0N01_reference.dxf` sit at CAD y=599.5 and y=577.9 within bounds y −37.125…779.625, and they render 22% down from the sheet top, which is where they visibly are. Unflipped would place them at 78%.

> [!TIP]
> The `title` default in `DEFAULT_CUSTOM_REGIONS` is `yMin: 0.75` — a *bottom*-right title block at a *high* fraction. If that looks wrong to you, you are thinking in CAD Y-up.

---

## 🧩 Trap 3 — zones are per drawing, not per template

Reference and revision share a sheet *template*, not their *content extent*: notes can be one long sentence on one sheet and an ordered list on the other. Measured on one pair, `views` differs by **23.2pp in height** between the two sides.

The backend has always modelled this correctly — all four orchestrators compute `ref_regions` and `rev_regions` independently. Any UI or storage that keeps a single shared zone set contradicts the engine it feeds and will clip one side or swallow neighbouring content on the other, producing false mismatches.

Note also that `title`, `tolerance` and `iso` can show *exactly* 0.0pp reference-vs-revision difference. That is not agreement — it is both sides being clamped to the same cap.

---

## 📋 Practical guidance

1. **Every aligned zone is saved to the template** (changed 2026-07-29, commit `fe643f4`). The old two-class model — furniture templatable, `notes`/`iso` per-drawing only — was dropped deliberately: a zone the user places by hand should stay there, and `RESET` is the way back to detection. `STABLE_ZONES` (`title_upper_left`, `bom`, `title`, `tolerance`, `views`) no longer gates saving; it only drives the `*` caveat marker in the zone picker. The measurement behind that marker still stands — `notes` genuinely moves and `iso` is absent on roughly half the sheets, so pinning either fixes ONE position for every sheet of the layout. Note also that regions are merged `{...reference, ...revision}`, so the **revision's** box wins wherever the two sides were aligned differently.
2. **`views`'s 33.0pp spread does not mean `views` moves.** That figure comes from `_derive_views_zone`, which takes the 5–95 percentile of *content* coordinates, so it measures where the geometry happens to sit — not where the sheet's drawing area is. The area is fixed by the sheet template; the content inside it is not. Those are different quantities and the measurement only ever addressed the second. `views` was misclassified as floating on the strength of it.
3. **`views` IS a predicate now — use `in_views()`.** Resolved 2026-07-29; see the section below. The box is the sheet, and `zone_detector.in_views(x, y, regions)` is the real test: `inside(sheet) AND NOT inside(any other zone)`. **Any consumer that treats `views` as a containment region must call `in_views()`, or pass `views_exclusions()` alongside the box** — the raw box is only the outer bound and admits every title block, BOM row and notes line on the sheet.
4. **Hand-aligned zones are ground truth.** Once furniture is pinned, IoU of detected vs pinned boxes turns detector work from eyeballing into measurement.

---

## 🪤 Trap 4 — a pinned box is a ceiling, not just a floor

Applying a template used to be `result[zone_key] = bbox`, a straight overwrite of the
detected box. For fixed furniture that is correct. For **`bom` it was lossy**, and silently:

A template is aligned against whatever drawing the user happened to have open. A BOM aligned
on a **one-row** sheet is a shallow band. A later drawing with **three rows** extends further
down — and those extra rows fell *outside* the pinned zone and were dropped from BOM
extraction entirely. No warning, no diagnostic; the pinned box made the zone **worse than
detection** on exactly the drawings that most needed it.

`bom` is now in `GROWABLE_PINNED_ZONES` and unions the pinned box with the detected one.
Two constraints that are load-bearing:

- **Only grow against a `content_aware` detection.** `extract_dynamic_regions` *always*
  populates every zone, falling back to the percentage grid. Unioning unconditionally would
  inflate the pinned `bom` to the grid guess's 36% × 40% of sheet — making the template look
  ignored while technically being applied.
- **Refuse a runaway rather than clamping it.** If the union breaches `ZONE_MAX_LIMITS` the
  detection is not believable, so the pinned box is returned untouched. Clamping would trim
  symmetrically and move the edges the user aligned by hand, which is the worse failure.

Fixed furniture (`title`, `tolerance`, `title_upper_left`) deliberately does **not** grow —
growing against a mis-detection could only corrupt a box the user already got right. Neither
does `views`, where the pinned area is the entire point.

> [!TIP]
> The general lesson: pinning is not free. Ask of every templatable zone whether its content
> can grow, and if it can, the template box is a floor rather than an outline.

---

## 🪤 Trap 5 — an independently-detected zone reports unchanged content twice

The engine diffs each zone against its counterpart independently, which is what stops a note
being mis-paired with a dimension. But `notes` and `iso` are detected **per drawing** — as
they must be, since they genuinely move — so the box can capture a *different subset of the
same block* on each side.

Measured on the M7452A0N01 pair: the reference lays its notes out in **two columns** and the
revision in **one**. Three lines fell inside the reference's notes box and outside the
revision's; two fell the other way. Each was then diffed against a pool that could not
contain it, and emitted twice:

```
drawing_views  REMOVED  完成時、バリ、キリ粉はなきこと     <- ref's views pool
notes_section  ADDED    完成時、バリ、キリ粉はなきこと     <- rev's notes pool
```

**Five unchanged lines produced ten findings** — a quarter of the report. The partition was
working exactly as designed; the flaw is that a partition computed independently on each side
can disagree, and a disagreement is indistinguishable from a real edit at the point of diff.

`marking_reconciler.reconcile_relocated_markings` collapses these after the per-zone diffs
are combined. Measured on the real cached run: **38 → 32 findings, ADDED+REMOVED 21 → 9.**

Three constraints that are load-bearing:

- **Unambiguous pairs only** — the normalized text must appear exactly once among REMOVED and
  once among ADDED. A `1` deleted from the BOM and an unrelated `1` added in the title block
  must never merge into "unchanged"; a wrong merge silently destroys a finding, a missed merge
  only leaves noise that was already there.
- **Reuse the differ's own normalizer.** If two strings would have paired inside one pool they
  must reconcile across pools, or the same NFKC/width rules apply in one place and not the other.
- **`MATCHED`, not a new `MOVED` status.** `PhysicalComparisonResponse.status` is handed to
  Gemini as its `response_schema`; adding a value would change what the LLM engines are invited
  to emit, for a defect only the deterministic engine has. The relocation goes in `details`.

### Content that both moved AND changed — resolved by a second, fuzzy pass

`硬度HS35～38度` → `硬度HS35～38` (trailing 度 dropped) landed in different buckets, so the
per-zone diffs never compared the two. The exact pass declines to merge them — the text is not
identical — so it stayed one REMOVED plus one ADDED, with the actual edit never stated
anywhere.

Pairing on similarity risks the opposite failure: inventing a CHANGED that conceals a genuine
deletion alongside a genuine addition. Four independent guards, **all** of which must hold:

1. **Similarity ≥ 0.82** — keeps a dropped suffix, rejects merely same-shaped strings.
2. **Mutually best** — the REMOVED's best candidate must be that ADDED, and vice versa.
3. **Margin ≥ 0.08 over the runner-up** — if two candidates score within that, the pairing is
   a guess and *both* are left alone. A wrong merge destroys a finding; a missed merge only
   leaves noise that was already there.
4. **Bounded movement** (≤ 0.25 of sheet), checked in the normalized frame because the two
   drawings are not necessarily in the same coordinate space. Skipped when coordinates or
   bounds are unavailable — it is a guard, not a requirement.

Strings under 4 characters are excluded outright: `8.7` vs `8.65` scores 0.57 and `45` vs `46`
scores 0.5, so no threshold separates a real edit from a coincidence at that length.

Measured on the corpus pair's 38 real findings, the fuzzy pass merged **exactly one** — the
`度` case above. Combined with the exact pass: 38 → 31 findings, ADDED+REMOVED 21 → 7.

See [[Gotcha - Reference and Revision in Different Coordinate Spaces]] for the other half of
the false-finding load, which had the same REMOVED+ADDED signature from an unrelated cause.

---

## 🪤 Trap 6 — the zone template was write-only

`fetchZoneTemplate` existed in `apps/desktop/src/services/drawingsApi.ts` and had **zero call
sites**. `TwoDWorkspace` imported `saveZoneTemplate` and not the loader.

The result was a feature that looked broken and was in fact half-working:

- **Saving worked.** The template reached MongoDB, and `extract_dynamic_regions_async` →
  `resolve_zone_overrides` applied it during every comparison. Pinned zones genuinely
  affected the audit.
- **Loading never happened.** Opening the zone editor re-seeded from the detector every
  time, so the user saw their alignment apparently discarded and re-dragged the same boxes.

The editor was therefore showing a *different set of zones than the comparison actually ran
on* — the worst of both, because the discrepancy was invisible from either side. What the
user reports is "the zone boxes go back to default"; the template is fine, sitting in the
database with the right signature.

`seedCustomRegionsFromDetected` now takes the template as a fourth argument and applies it
**last, on every open**, mirroring the backend's precedence:

```
DEFAULT_CUSTOM_REGIONS  <  detected boxes  <  hand-aligned template
```

The subtlety that made a first attempt insufficient: the action skips seeding entirely when
`customRegions[drawingId]` already exists, to avoid re-seeding the detector over the user's
work. But `customRegions` is **restored from localStorage on reload**, so it exists before
the user has touched a single handle. Applying the template only on a fresh seed therefore
still left pinned zones reverting to detector boxes on most opens.

So the two sources are now treated differently, which is the whole point:

- **The detector** seeds only a drawing with no alignment yet — re-seeding would destroy the
  user's work.
- **The template** is re-applied every time. It is an explicit, named, persisted decision
  covering every drawing of the sheet layout; `customRegions` is one drawing's scratch state.
  A pinned zone belongs in its pinned place every time the editor opens. `RESET` is the way
  back to pure detection.

Zones the template does *not* pin (`notes`, `iso`) keep whatever alignment the drawing had.

> [!IMPORTANT]
> **No Y flip on the template layer.** `ZoneFractions` is stored Y-DOWN precisely so it
> matches `customRegions`, so pinned zones transfer directly. Detected boxes are CAD Y-up and
> *do* need `zoneBoxToFractions`. Applying the flip to both mirrors every pinned zone, which
> looks plausible because zones cluster near the sheet's vertical centre — see Trap 2.
> Pinned by `zoneTemplateSeeding.test.ts::template fractions are applied without a Y flip`.

### The guess marker had the same bug, visually

`renderZoneEditor` decided dashed-border-and-`?` from `detected[key].confidence ===
'content_aware'` alone. A pinned zone is **by definition not something the detector
anchored**, so the user's own hand-aligned boxes were drawn as guesses — exactly backwards,
since an explicit human decision outranks `content_aware`.

`pinnedKeys` is now threaded from `reviewStore.pinnedZoneKeys` through `CanvasRenderer` into
the renderer, and a pinned zone draws solid with no `?`. Note it is read from the subscribed
map rather than the `getPinnedZoneKeys` getter: a getter call inside the render effect does
not re-run it when the template finishes loading asynchronously.

`resetCustomRegions` clears the pinned marks too — otherwise plain detector boxes would keep
claiming to be human-aligned.

> [!TIP]
> The general lesson: when a persisted setting appears not to stick, check whether anything
> ever *reads* it before assuming the write path is broken. Here the write path, the storage,
> the signature and the backend consumer were all correct — and the feature was simultaneously
> working (in the audit) and invisible (in the editor), which is why it read as data loss.

There is still **no way to list or delete templates** — the router exposes only
`GET/PUT /zone-templates/{signature}`, and nothing in the UI enumerates them. Combined with
`zone_signature()` bucketing on aspect ratio alone (every A-series sheet is 1.414), a user
with several layouts has one shared template they cannot inspect.

---

## 🔗 Related Notes
- See [[Zone Detector & Bounding Boxes]]
- See [[ADR-002 Decoupled Zone Bounding Box Endpoint]]
- See [[Gotcha - Comparison Cache Invalidation]]
- Return to [[00 - Map of Content (MOC)]]
