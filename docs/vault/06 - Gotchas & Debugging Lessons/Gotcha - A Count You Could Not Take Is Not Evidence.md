---
tags: [gotcha, backend, hitl, auto-doc, error-handling, testing, client-isolation]
status: fixed
cache-version: n/a — vault rules are read at runtime, not baked into a comparison cache entry
date: 2026-08-10
---

# Gotcha — A Count You Could Not Take Is Not Evidence

> [!WARNING] Six lines of `auto_doc.py` could write **customer A's verbatim drawing text into
> customer B's rule file**, and could promote a **single** dismissal to a permanent rule on any
> database error. Both wrote into the one vault directory that is a runtime input, in the
> false-negative direction.

## What happened

`AutoDocEngine.process_feedback_event` promotes a pattern to a permanent learned rule once it has
been dismissed N≥3 times. The count:

```python
try:
    dismiss_count = await AuditFeedbackDocument.find(
        getattr(AuditFeedbackDocument, "entity_text") == target_text,
        getattr(AuditFeedbackDocument, "human_corrected_status") == "dismissed"
    ).count()
except Exception:
    # Fallback count for unit testing outside live DB connection
    dismiss_count = getattr(feedback, "_mock_dismiss_count", 3)

if dismiss_count >= 3:
    client_label = feedback.client_name or "General"
    ...  # writes Learned_Rules_{client_label}.md
```

**Three defects, all of the same family — the count is not counting what the write assumes.**

1. **No `client_name` clause, but the rule is filed under `feedback.client_name`.** A pattern
   dismissed **once at each of three different clients** reaches the threshold and lands in
   whichever client's file happened to trip it. `pattern` is verbatim drawing text, so this is
   customer A's part numbers appearing in customer B's rules — the exact contamination the
   two-tier overlay was designed to prevent, and that tier was retired by
   [[ADR-009 Retiring the Standards Knowledge Track]]. **Nothing else prevents it.**

2. **The error fallback equals the threshold.** `except Exception → 3`, against `if >= 3`. Any DB
   hiccup — a dropped connection, a timeout, a typo in a field name — promotes the *current single*
   dismissal to a permanent rule. And the value arrives from `getattr(feedback, ...)`: **test
   scaffolding hanging off the production data object**, reachable on the live path.

3. **Retracted dismissals counted.** Found while fixing the other two. `retracted_at` means a human
   said *"I clicked that by mistake"*; `trainer.py:106` already skips those rows, and the model's own
   docstring says *"Non-null rows never train."* This counter did not skip them — so three
   taken-back clicks could write a rule, and a vault rule is far more durable than a training row.

## Why it matters more than its size

`docs/vault/08 - Client Domain & CAD Rules/` is **the only directory in this vault that is a
runtime input.** It feeds `get_learned_dismissal_rules()` → `safe_filter` → the zone pools. A wrong
rule there does not produce a wrong finding; it produces **no finding** — the false-negative
direction, in the system whose headline gap is that false negatives have never been measured
([[00 - AI Agent Navigation & System Gap Analysis]]).

That is also why it left no symptom. A suppressed finding looks exactly like a drawing with nothing
wrong on it.

## Why it survived: the test passed *because of* the bug

The one test covering the write half constructed a feedback document with no database. The
`.find(...)` therefore raised, the `except` branch substituted `3`, the threshold was met, the file
was written, and the test **passed** — asserting the rule note existed.

It was a real test of a real property, and it was **green precisely because the fallback was
broken.** Removing the defect broke it. Nothing about a passing suite pointed at any of this.

> **Rule: if a test can only pass through an error handler, the error handler is part of the
> feature and nobody decided that.** A test with no database should be *given* a count, not allowed
> to trip an exception and inherit whatever the `except` block believes.

## Why the filter is now a plain dict

The fix could have added one clause to the Beanie expression. It builds a dict instead:

```python
def build_dismissal_filter(target_text, client_name) -> Dict[str, Any]:
    return {
        "entity_text": target_text,
        "human_corrected_status": "dismissed",
        "client_name": client_name,
        "retracted_at": None,
    }
```

Beanie's class-level comparison operators require `init_beanie`, and this suite has no MongoDB and
no `mongomock`. A filter built from them **cannot be inspected offline** — so no test could ever
have asserted that the client clause was present, which is how its absence survived. A dict can be
asserted on directly, with no database and no mocking.

`client_name=None` is matched **as `None`**, not omitted: an unattributed dismissal files under
`General`, so it must be promoted by other unattributed dismissals. Dropping the key for null
clients would have restored the sheet-wide count for exactly the rows that carry no client.

## The rules

- **A count you could not take is no information — never evidence.** An unavailable measurement
  must fail towards *not acting*. The same shape appears in
  [[ADR-005 Local-Only Processing with Cloud Licensing]]: a failed licence check must count as "no
  information", never as a negative result. Here it is the mirror — never as a positive one.
- **A fallback constant must never equal the threshold it is compared against.** If it does, the
  error path silently becomes the success path.
- **Test hooks do not live on production data objects.** `_mock_dismiss_count` was reachable from
  the live path by construction. Stub the *function*, not the document.
- **When two code paths read the same corpus, they must agree on which rows count.** `trainer.py`
  skipped retracted rows and `auto_doc.py` did not. Fourth time this project has paid for "two
  callers, one contract, no shared definition" — compare
  [[Gotcha - The Sweep Never Got the Zone Template Seam]].

## How it was verified

The eval cannot see any of this: `tools/eval.py` calls `generate_deterministic_candidates`
directly and never loads vault rules, so no corpus number moves in either direction. Claiming a
byte-identical baseline as evidence here would be [[Gotcha - Title Block QTY Reads the Upper-Left Table]]'s
mistake — citing a counter that is blind to the defect by construction.

Verified by **mutation instead**: each of the three defects was re-introduced into the fixed code
and the suite was re-run. All three were caught — client clause dropped, retracted clause dropped,
fallback restored. `tests/test_audit_feedback.py` went 3 → 11 tests.

## See also

- [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]] — the same module
  family and the same lesson from the other side: there, a broad `except` hid a write that had
  never run; here, a broad `except` *invented* a reason to write. The outer handler in
  `process_feedback_event` now logs the exception type and a traceback, because the caller collapses
  it to `auto_documented: false` — which is also the normal answer below the threshold.
- [[ADR-009 Retiring the Standards Knowledge Track]] — retired the overlay tier that was going to
  fix this, and re-homed it here as the highest-severity open item
- [[Gotcha - A Guard Test's Failure Path Had Never Run]] — code that only runs when something goes
  wrong is code nothing has ever run
- [[Gotcha - Null Snapshot Features Are Not Degraded Labels]] — the other place this corpus's
  shape is easy to misread
