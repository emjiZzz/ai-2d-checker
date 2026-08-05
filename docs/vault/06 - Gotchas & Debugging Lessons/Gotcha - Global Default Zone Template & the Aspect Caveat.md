---
title: Gotcha - Global Default Zone Template & the Aspect Caveat
type: gotcha
tags: [gotcha, zone-templates, comparison, cache, coordinate-spaces, backend, frontend]
status: resolved
date: 2026-08-03
---

# 🔥 Gotcha — The Global Default Zone Template Is a *Fallback*, and It Scales Proportionally

## 🧭 Context

Zone templates are keyed by an **aspect-ratio signature** (`aspect-1.414`, …). During a comparison
the backend already resolves a sheet's template automatically by signature
([`resolve_zone_overrides`](../../../services/backend/infrastructure/audit/bom/zone_template_resolver.py))
— the frontend "Apply" button never gated the audit. A sheet whose aspect matched **no** saved
template just got plain detection.

A drawing has now been designated the **global default**: a fallback so any unmatched sheet inherits
its pinned zones. Two things about how it works are easy to get wrong.

## ⚠️ Behaviour 1 — Fallback precedence: specific wins, default fills gaps

`resolve_zone_overrides` looks up the sheet's own signature first; **only if that misses** does it
fall back to the template flagged `is_default`. A sheet that has its own aspect-specific template is
never overridden by the default — the more precise, hand-aligned fit always wins. The default only
covers sheets nobody has aligned directly. Do not "simplify" this into an unconditional override:
that throws away every per-aspect alignment, including the specific templates the user saved.

The default is designated by an explicit `is_default` flag on `ZoneTemplateDocument`, **not** by the
name "Default". Exactly one document may hold it — the set-default endpoint
(`PUT /zone-templates/{signature}/default`) clears every other before setting the new one. Enforce
that invariant at the write, never by hoping only one row has the flag.

## ⚠️ Behaviour 2 — The aspect caveat (the reason to warn the user)

Template zones are stored as **fractions of `render_bounds`**, so the default's boxes scale
*proportionally* onto whatever sheet inherits them. On a sheet with a genuinely different aspect
ratio, a box pinned at "79–92% down, 37–93% across" lands at those proportions — which may sit over
the wrong content. This is not a bug to fix; it is intrinsic to a single fallback covering every
shape. For this corpus (A-series, all ≈1.414) every sheet shares the aspect, so divergence is rare —
but the Saved Templates modal and this note say so out loud, because a plausible-looking misplaced
box is exactly the kind of silent wrong answer this vault exists to prevent.

No new coordinate maths: the fallback reuses `fractions_to_absolute_bbox` with the *current* sheet's
`render_bounds`, so the Y-DOWN→Y-UP flip stays in its one existing place. See
[[Gotcha - Reference and Revision in Different Coordinate Spaces]] for why that flip is load-bearing.

### Safe zones are hardened against this (cache v28)

The aspect caveat first bit through the `tolerance` safe zone: a misplaced pinned tolerance box
**replaced** the content-anchored detection, so the real 表示外公差 table stopped being excluded and
got diffed as **BOM** (a "bill of materials / MATCHED" marking landing on the tolerance table, far
from the actual BOM). Root cause: `extract_dynamic_regions_async` let a template box overwrite every
zone, including zones that are *never compared*.

Fix (`table_extractor.SAFE_ANCHORED_ZONES = {"tolerance", "shim"}`): for these **safe** zones — whose
box exists only to EXCLUDE furniture, never to compare — a `content_aware` detection now **outranks**
the template. The template is skipped when detection anchored the zone, and applied only as a fallback
when detection missed. So a misplaced template box can no longer move a safe zone off its real table.
Compared zones (`title`, `bom`, `views`, …) are unchanged: there the user's pin still wins.

## 🧨 The cache bump you cannot skip

Adding the fallback changes **zone extraction** for previously-unmatched sheets, which changes
comparison output. Per hard constraint #2, `COMPARISON_CACHE_VERSION` was bumped **v25 → v26**;
without it, cached comparisons for those sheets keep serving pre-default results and the feature
looks broken. Note the asymmetry: **changing *which* template is default later is not a code change
and does not re-bump the version.** That staleness is cleared the same way as saving any template
after a comparison was cached — hit **Re-test** (force_refresh). See
[[Gotcha - Comparison Cache Invalidation]] and [[Gotcha - Re-test and the Four Caches]].

## 🛠️ Where it lives

- Resolver fallback: `zone_template_resolver.py::resolve_zone_overrides`.
- Flag + single-default endpoint: `domain/models/zone_template.py` (`is_default`),
  `api/routers/zone_templates.py` (`PUT …/default`, `GET /zone-templates-default`).
- Editor consistency: `TwoDWorkspace.tsx::openZoneEditing` falls back to
  `fetchDefaultZoneTemplate()` when the signature template is null, so the on-screen editor shows the
  same zones the audit resolves to (the "editor disagrees with the audit" class of bug the seeding
  comments already fight).

## 🧪 Guards

- `tests/test_zone_template_resolver.py::TestDefaultFallback` — default used when the signature
  misses; specific template wins when present (default lookup never runs); no match + no default → `{}`.
- `tests/test_zone_templates_router.py` — setting a default clears the prior one; clearing touches
  nothing else; unknown signature → 404.

## 🔗 Related Notes
- See [[Gotcha - Zone Detection Accuracy & Stability]] and [[Gotcha - Reference and Revision in Different Coordinate Spaces]].
- See [[Gotcha - Comparison Cache Invalidation]] — the cache lever this change had to pull.
- Return to [[00 - Map of Content (MOC)]]
