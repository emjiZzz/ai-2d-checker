---
title: Standards Knowledge — Rule Bundle Format
type: architecture
tags: [architecture, second-brain, knowledge, rules, schema, contract, privacy]
status: unbuilt — the R3 contract, retired 2026-08-10 with its stage
date: 2026-08-07
retired: 2026-08-10 (ADR-009; R3 never started, so no bundle was ever produced)
schema_version: 1
related: [ADR-008 The Second Brain — Retrieval-Only Local Knowledge, ADR-009 Retiring the Standards Knowledge Track, Standards Knowledge — Staged Plan, ADR-005 Local-Only Processing with Cloud Licensing]
---

# 📦 Standards Knowledge — Rule Bundle Format

> [!CAUTION] **Unbuilt.** This is R3's contract, and R3 was retired before it started —
> [[ADR-009 Retiring the Standards Knowledge Track]], 2026-08-10. **No bundle has ever been produced and
> nothing reads this schema.** It is kept as a design record, not as a spec anything implements: if
> the track reopens (`standard_chunks > 0` plus ≥30 human labels — see ADR-009), this is the
> starting point rather than a blank page. **Two things in it outlive the stage** and are recorded
> in ADR-009 as surviving constraints: the minimized feedback payload
> `(pattern, category, count, client_id)`, and the reason for stripping **at the edge** rather than
> at the transport layer. `schema_version: 1` has never been issued.

The contract between **vendor**, **edge**, and (later) **cloud**. Decisions:
[[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] · Work:
[[Standards Knowledge — Staged Plan]]

> [!IMPORTANT] Markdown is the **authoring** format. The bundle is the **distribution** format.
> Nobody hand-edits a bundle, and nothing at runtime parses markdown. That split is the whole
> point: today `VaultSyncManager` parses prose notes at runtime, which is why *"writing a gotcha
> note that quoted a Japanese anchor changed what `safe_filter` excluded from comparison"*
> ([[00 - AI Agent Navigation & System Gap Analysis]]). A compiled bundle makes documentation
> and runtime input structurally different artifacts.

---

## Two tiers

| Tier | Authored by | Shipped via | Scope |
| :--- | :--- | :--- | :--- |
| `baseline` | vendor, from domain knowledge | **installer**, pinned per release | all customers |
| `overlay` | learned from one client's dismissals | (deferred — see R4) | **that client only** |

**Overlays never merge upward automatically.** Promotion from overlay to baseline is a deliberate
human act, because a learned pattern is **verbatim customer drawing text** — the live example,
`ユニットNo.`, is a title-block field lifted from a real sheet. Automatic promotion would ship one
customer's drawing content to every other customer as a "rule".

---

## Schema

```json
{
  "schema_version": 1,
  "bundle_version": "2026.08.1",
  "tier": "baseline",
  "client_id": null,
  "generated_at": "2026-08-07T00:00:00Z",
  "source_digest": "sha256:…",

  "rules": [
    {
      "pattern": "ユニットNo.",
      "category": "title_block",
      "match_mode": "normalized",
      "evidence_count": 3,
      "approved_by": "lead-auditor-id",
      "approved_at": "2026-08-07T00:00:00Z"
    }
  ],

  "tolerance_keywords": ["指示外公差", "機械加工公差"],
  "surface_roughness_patterns": ["\\d+\\.?\\d*S"],
  "upper_left_anchors": ["コードNo", "ユニットNo"]
}
```

### Field notes

| Field | Why it exists |
| :--- | :--- |
| `schema_version` | Distinct from `bundle_version`. One is the **shape**, the other is the **content**. Conflating them is how a format change becomes indistinguishable from a rule change. |
| `bundle_version` | What an edge pins to. Two edges on the same version **must** behave identically — that is the determinism guarantee this format exists to provide. |
| `tier` / `client_id` | `client_id` is `null` for `baseline` and required for `overlay`. A loader must **reject** an overlay with no client — otherwise a client-scoped rule silently becomes global, which is the exact failure the tiering prevents. |
| `source_digest` | sha256 of the authoring markdown. Makes "this bundle was built from that vault state" checkable rather than assumed — the same discipline as the eval corpus's payload digests. |
| `match_mode` | `exact` \| `normalized` \| `prefix`, per `LearnedDismissal` (landed 2026-08-07). **`normalized` at ≥3 characters, `exact` below.** A one-character pattern must never be widened; the vault currently holds the bare digit `8`. |
| `evidence_count` | The N that cleared the threshold. Carried so an auditor can see *why* a rule exists without consulting the server. |
| `approved_by` / `approved_at` | Null in a `baseline` (vendor-authored). Required in an `overlay`, because the lead-auditor gate is what separates a rule from an accident. |

---

## Resolution order

```
1. installer baseline        (always present, cannot fail)
2. per-client overlay        (if present for this client_id)
3. → merged rule set
```

**Overlay wins on conflict**, scoped to its client. Three properties that must hold:

- **The baseline alone is sufficient.** An edge with no overlay, no server and no network resolves
  a complete, working rule set. Absence of an overlay is **normal operation, not an error.**
- **Resolution is deterministic given `(baseline_version, overlay_version)`.** No clock, no
  network state, no ordering by filesystem enumeration.
- **An overlay for client A is never loaded for client B.** Asserted by test, not by convention.

---

## The minimized feedback record

The **only** shape permitted to leave a customer's network, per
[[ADR-005 Local-Only Processing with Cloud Licensing]]'s 2026-08-07 amendment.

```json
{
  "pattern": "ユニットNo.",
  "category": "title_block",
  "count": 3,
  "client_id": "opaque-client-identifier"
}
```

**Built in R3 even though nothing transmits it**, because retrofitting minimization onto a shipped
full-payload API means breaking a contract someone already depends on.

### What is dropped at the edge, and why

`AuditFeedbackDocument` carries far more. Everything below is stripped **before** the record is
constructed — not filtered at the transport layer, where a future refactor could route around it:

| Dropped field | Why |
| :--- | :--- |
| `drawing_id`, `session_id` | Identifies which drawing and which audit. Not needed to learn a pattern. |
| `coordinates` | Geometry. Explicitly forbidden by the amended ADR-005. |
| `human_comment` | **The sharpest edge.** Unbounded free text a person types — it can contain project names, customer details, anything. |
| `finding_snapshot` | Model training features. Useful later, but out of scope for rule extraction, so it does not travel today. |
| `client_name` | Replaced by an **opaque** `client_id`. The vendor needs to partition; it does not need the customer's name in the payload. |

### The residual, stated rather than hidden

**`pattern` is still verbatim drawing text.** A part number, a material spec or a supplier code
can travel in it. Minimization reduces exposure by an order of magnitude; **it does not eliminate
it**, and any claim made to a customer must say so. This is why the amended ADR-005 promises *"no
drawing, image, geometry or coordinate"* rather than *"nothing derived from your drawings"* — the
narrower sentence is the one that stays true.

---

## Compatibility rules

- **Additive changes** (new optional field) do **not** bump `schema_version`. An older edge
  ignores unknown fields.
- **Removing or re-meaning a field** bumps `schema_version`, and a loader **must refuse** a
  bundle whose `schema_version` it does not know — loudly. Silently ignoring an unknown schema is
  how an edge ends up running with half a rule set and no error.
- **A bundle is immutable once distributed.** Corrections ship as a new `bundle_version`, so
  "which rules were active" is answerable after the fact.
- **The empty bundle is valid** — `rules: []` means *no learned rules*, which is different from
  *no bundle*. The distinction matters: the first is a state, the second is a failure.

---

## Related

- [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] — the decisions
- [[Standards Knowledge — Staged Plan]] — R3 builds this
- [[ADR-005 Local-Only Processing with Cloud Licensing]] — the amended egress claim
- [[Gotcha - A Short Structured Value Suppresses Its Own Zone]] — why `match_mode` has a length
  floor: a short string is not an identifier
