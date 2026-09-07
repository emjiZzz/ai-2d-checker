---
title: Gotcha - Zone Template Pollution (Non-Zone Keys)
type: gotcha
tags: [gotcha, zone-template, persistence, schema, data-corruption]
status: resolved
date: 2026-08-03
---

# 🔥 Gotcha — Zone Template Pollution (Non-Zone Keys)

## ⚠️ The Problem

Hand-aligned zone templates were silently persisted with non-zone metadata keys. A saved template with signature `aspect-1.414` claimed to apply 9 "zones":

```
['bom', 'drawing_id', 'iso', 'notes', 'render_bounds', 'title', 'title_upper_left', 'tolerance', 'views']
```

`drawing_id` and `render_bounds` are **metadata fields on the zones response**, not actual comparison zones. They leaked into the stored template and inflated its key count, making audits look corrupted when they were structurally sound.

## 🔍 Root Cause

Two codepaths, neither with a whitelist of valid zone keys:

1. **Frontend**: `apps/desktop/src/components/review/SavedTemplatesModal.tsx::handleSaveTemplate()` built the `zones` payload by copying **every key** from `getRegionsFor()` using spread syntax (`{...oldReg, ...newReg}`). Response metadata like `drawing_id` and `render_bounds` came along for the ride.

2. **Backend**: `services/backend/api/routers/zone_templates.py::ZoneTemplateUpsertRequest.zones` accepted `dict[str, ZoneFractions]` with **any string key**, with no validation. The request validator passed, and the corrupted template was persisted verbatim to MongoDB.

The valid zone keys had always existed in the codebase as ordered tuples for render order (`ZONE_KEYS` in `services/backend/api/routers/drawings.py:263` and `apps/desktop/src/services/drawingsApi.ts:54`), but were never enforced as a membership whitelist at the persistence layer.

## 💥 Why it is insidious — a red herring for comparison correctness

The pollution is **completely harmless to the audit result**, and that is precisely why it went unnoticed.

`resolve_zone_overrides()` in `services/backend/infrastructure/audit/comparison/zone_template_resolver.py` produces an absolute bounding box for every key in the overrides dict, including the polluting ones. But `drawing_id` and `render_bounds` are never used as comparison zones — nothing consumes them downstream. The stored template was quietly corrupt in structure (9 keys instead of ≤8), yet the comparison ran correctly because it simply ignored the garbage keys.

> [!WARNING]
> **This pollution is NOT the cause of bad markings.** A field log showing a template with spurious keys is alarming, but it is a red herring. If zone checkmarks appear in the wrong place, that is a separate issue. Do not mistake stored-data corruption for comparison-logic corruption.

The **actual cause** of misplaced title/BOM checkmarks in this codebase was an independent issue: aspect-only signature collision — two different sheet layouts colliding to `aspect-1.414` and sharing a single global template. See [[Gotcha - Global Default Zone Template & the Aspect Caveat]].

**Negative result recorded:** Tracing a stored template's corrupted key list does not explain spurious markings. The two problems are orthogonal. Testing the pollution fix in isolation showed zero change to comparison output, confirming the leak was benign to audit correctness.

## 🛠️ The Fix

Three-part solution, already landed:

1. **Canonical whitelist on the domain model**: Added `VALID_ZONE_KEYS` (frozenset) to `services/backend/domain/models/zone_template.py`:
   ```python
   VALID_ZONE_KEYS: frozenset[str] = frozenset({
       'views', 'notes', 'bom', 'title', 'tolerance', 'iso', 'title_upper_left', 'shim'
   })
   ```
   This mirrors the ordered `ZONE_KEYS` tuple that already existed in `drawings.py` and `drawingsApi.ts`.

2. **Backend validation**: Added `@field_validator("zones")` to `ZoneTemplateUpsertRequest` in `zone_templates.py`:
   - Strips any key outside `VALID_ZONE_KEYS`
   - Logs a warning when it does
   - Does **not** raise a 400 error, so existing clients keep working (forward-compatible)

3. **Frontend filtering**: The template save loop in `SavedTemplatesModal.tsx` now filters zones to `ZONE_KEYS` before serialization, ensuring only valid keys reach the backend.

## 🧪 Guard

Regression test suite in `tests/test_zone_template_pollution.py` (3 tests, passing):
- Verify that a template with extra keys gets them stripped on save
- Verify that after stripping, comparison output is identical to the clean template
- Verify that the stored template in MongoDB contains only valid keys

## 🔗 Related Notes
- See [[Gotcha - Global Default Zone Template & the Aspect Caveat]] — the actual cause of misplaced markings, distinct from this data-corruption issue
- See [[Gotcha - Zone Detection Accuracy & Stability]] — background on how templates override detection
- Return to [[00 - Map of Content (MOC)]]
