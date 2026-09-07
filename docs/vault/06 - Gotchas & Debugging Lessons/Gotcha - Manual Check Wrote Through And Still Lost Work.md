# Gotcha - Manual Check Wrote Through And Still Lost Work

> Found 2026-08-20, reviewing whether Manual Check was ready for prototype testing. It was not,
> and every reason was invisible from the screen.

Manual Check was designed around one good idea, stated in its own docstrings and honoured
everywhere: **every marking is written through to the server the moment it is made**, because a
session on a dense sheet is an hour of work and a submit-shaped API loses all of it to one closed
laptop. `M745230A01` carries 68 addressable rows. The design is right.

The implementation then swallowed every write failure, which makes write-through worth nothing.
Three separate paths, each with its own way of looking fine.

## 1. The recording path caught its own failure and dropped it

`SelectionMenu.write` ended in `.catch(() => {})`, under a comment reading *"The store logs and
surfaces a failure; the menu's job is only not to swallow it."*

The store logged. Nothing surfaced. `recordStamp` did `console.error` and re-threw, and no
component rendered it. So a failed `POST /markings` — a stopped backend, a dropped connection, a
422 — produced **no UI at all**: the menu closed, the entity stayed unmarked, and the result was
indistinguishable from a mis-click.

**A comment asserting that someone else handles the error is a claim, and it was false.** Follow
it to the handler before trusting it. This is the same lesson as
[[Gotcha - A Verdict Mapping That Contradicted Its Own Comment]] — a comment describing behaviour
16 lines away that the code did not have.

## 2. The retraction path told the UI one thing and the database another

`retractManualMarking` dropped the row from the local list only on success — but caught its
failure, logged it, and returned. So a failed `DELETE` left the engineer looking at a panel that
agreed the marking was gone and a database in which it was still **live**.

That is not a display bug. `eval_corpus.py from-manual-check` reads the database and filters on
`retracted_at`, so a retraction the server never applied is converted into a **corpus finding the
engineer explicitly withdrew** — committed, attributed to them, and indistinguishable from a
judgement they actually made.

The traffic makes it worse: **31 of the 38 markings** in the session that produced
`M745204N01` are retractions (see [[Gotcha - Two Ground-Truth Stores That Never Met]]).
Retracting is not an edge case here, it is the main verb.

## 3. Submit reported success unconditionally

`ManualMarkingList.submit` was `await submitManualSession(); setSubmitted(true)`, and the store
swallowed. A submit that never reached the database rendered **"Check submitted"** and the
engineer walked away from a session still marked `in_progress`.

## The one that had never run at all

While fixing (1), the 404 self-heal underneath it — the branch that clears a dead `manualSessionId`
so the open effect can reopen, *"without this the app dead-ends"* — turned out to contain **two
literal backspace bytes (0x08)** where word-boundary escapes were meant to be. The regex therefore
matched only a message containing a backspace character, i.e. never, and the repair had not run
once since it was written.

It was invisible three ways over: the file renders normally in an editor, the Read tool showed it
as ordinary, and `tsc` and the linter are both perfectly happy with a valid regex. Only
`cat -A`, and then reading the raw bytes, showed it.

⚠ **It reproduced itself during the fix.** Writing the replacement through a heredoc mangled the
escapes again, in the same file, the same way — which is near-certainly how the original arrived.
The comment there is now deliberately escape-free, and says so.

**A repo-wide scan found these two bytes and no others**, so this is a one-file problem, not a
systemic one. The scan is worth repeating if it ever recurs:

```bash
python -c "import os;[print(p) for r,d,f in os.walk('.') if '.git' not in r and 'node_modules' not in r for n in f if n.endswith(('.ts','.tsx','.py')) for p in [os.path.join(r,n)] if b'\x08' in open(p,'rb').read()]"
```

## What the shape has in common

None of these raise. Each produces a screen a reasonable person would accept. That is the
category of defect this codebase keeps paying for — the same family as the zone overlay that
mirrors plausibly, and the sweep that measured F1 0.68 against the eval's 0.92 for four days
without anything failing.

**For a tool whose entire output is the records it keeps, "the write failed" is the most
important thing it can ever have to say.** All three paths now report through one `markingError`
field, which the panel renders separately from the session-open error — deliberately separate,
because the open error says *"your markings are safe, this pane could not read them"* and a
write error says *"what you just did was not recorded"*, and one banner cannot say both.

## Fixed alongside, same review

- **A submitted session accepted new and edited markings.** `submit` is the moment a pass becomes
  the record `from-manual-check` converts; appending after it rewrites what a label was derived
  from, after the derivation. Now 409.
- **`submit` was not idempotent** — a double click moved `submitted_at` to the retry and re-ran
  `_recount` over a closed session.
- **The session resume was a read-then-insert race with no unique index.** Now a *partial* unique
  index on `(room_id, ref_drawing_id, rev_drawing_id, annotator)` filtered to
  `status: "in_progress"`, with `DuplicateKeyError` handled by re-reading the winner. ⚠ The
  partial filter is required, not tidy: a pair legitimately accumulates many *submitted* sessions,
  and a plain unique index would reject the second honest check of a drawing. ⚠ Beanie builds
  indexes at `init_beanie`, so this fails loudly at startup against a collection that already
  holds duplicates — run `tools/merge_duplicate_check_sessions.py` on **every** environment first,
  Atlas included, since these collections are not in `sync_manager.SYNC_COLLECTIONS`.
- **`resetWorkspace` cleared nine comparison fields and no manual ones.** `leaveRoom` calls it, so
  room A's markings rendered on room B's canvas, and `findMarkingForEntity` — which matches on
  handle and side, not on drawing — silently refused to let the engineer mark B's colliding
  entities.
- **`retract_marking` called `ManualCheckSession.get()` directly**, reintroducing the 500-instead-of-404
  failure `get_or_404` exists to prevent and documents at length.
- **`list_markings` filtered retracted rows in Python** after fetching them all, leaving the
  `(session_id, retracted_at)` compound index unused on the panel's read — transferring roughly
  five times what it returned.
- **`"unknown"` could reach committed ground truth.** It is the router's fallback when a check is
  opened with no `X-Session-Token`, and `from-manual-check` only tested the annotator for
  *emptiness*, which `"unknown"` passes. Now refused by name, via `require_named_annotator`.
- **`tools/export_manual_labels.py` deleted.** It read `ref_handle`/`rev_handle` off raw Mongo
  documents, but those fields exist only on the API's `MarkingResponse`; the handle branch could
  never fire, so every finding silently degraded to a text-index lookup or was dropped. Fully
  superseded by `from-manual-check`.

## Accepted, not fixed

**`StampMarkingModal` was dead code and is deleted.** `openStamp` had five call sites and every
one passed `null`, so `pendingStamp` was permanently null, the modal never rendered, and
`commitStamp` was unreachable. It was the only UI that collected `notes`, `is_bulk` and
`text_was_edited`.

Deleted rather than revived (owner's call, 2026-08-20), so the consequence is now explicit rather
than looking like data nobody filled in:

- `text_was_edited`, `is_bulk` and `notes` on a marking are **structurally always** `false` /
  `false` / `""`;
- therefore `ExpectedFinding.is_bulk` is always `false` and the eval manifest's `bulk_count` is
  always `0` — **neither is a measurement**;
- there is no revision path at all. `PATCH /ground-truth/markings/{id}` has no caller;
  retract-and-remark is the only correction.

⚠ The bridge's `[category:zone]` tag is unaffected — it prepends to the *finding's* notes, not the
marking's.

## Still unmeasured: REMOVED

Every address in `tests/fixtures/eval/labels/M745204N01.json` is `REV-`. There is not one `REF-`.

REMOVED anchors on `ref_address`, and reference-side handle coverage is **0.8–13%** against 92% on
a re-traced revision sheet. `address_resolver.resolve` returns UNRESOLVED for a stored-but-absent
handle rather than falling through to text, and tiers 3–4 refuse ties. So deletions — half of what
recall means — have never been carried through the bridge end to end, and nothing has measured how
often they convert. That is the next thing to find out, and it needs a session with REMOVED
markings in it rather than a code change.

## Related

- [[Gotcha - Two Ground-Truth Stores That Never Met]] — the bridge this review was checking
- [[Gotcha - A Verdict Mapping That Contradicted Its Own Comment]] — the same "comment asserts what
  the code does not do" shape
- [[Gotcha - Comparison Cache Invalidation]] — the archetype: a plausible answer served instead of
  a correct one
