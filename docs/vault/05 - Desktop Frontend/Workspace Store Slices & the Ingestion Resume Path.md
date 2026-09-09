---
title: Workspace Store Slices & the Ingestion Resume Path
type: frontend
tags: [frontend, zustand, state, ingestion, upload, rooms]
status: active
verified-against: 2026-09-09, commit bddcad8 (`GET /drawings/{id}/job` and `applyOrResumeDrawing`)
related: [CanvasRenderer & Entity Drawing, Rooms and Upload Surfaces, 00 - AI Maturity Status]
---

# 🖥️ Workspace Store Slices & the Ingestion Resume Path

`useWorkspaceStore` is one Zustand store assembled from eight slices in
`src/stores/workspace/slices/`, with every shape declared in `workspace/types.ts`.
`workspaceStore.ts` itself holds no logic: it spreads the slices, re-exports the types the old
flat store exported so existing imports keep working, and owns the two IndexedDB functions.

| Slice | Owns |
| :--- | :--- |
| `createComparisonSlice` | running a comparison and its violations |
| `createUploadSlice` | both drawing slots: validation, upload, extraction jobs, the queue |
| `createAuditSlice` | audit session state and verdicts |
| `createClientSlice` | the selected client (7 lines; it exists so the field has an owner) |
| `createUndoSlice` | undo entries for zone-box edits |
| `createNavSlice` | which workspace surface is showing |
| `createAnnotationsSlice` | annotations and layer visibility |
| `createManualCheckSlice` | manual-check sessions and ground-truth markings |

## Persistence is per room, and deliberately partial

`saveWorkspaceState(roomId)` writes a hand-listed subset to IndexedDB under `workspace-<roomId>`
— both drawings, both upload states, both job ids, violations, pan/zoom, active layers. It is a
list rather than the whole state because the store also holds things that must not survive a room
switch. `loadWorkspaceState` clears the undo history *before* the swap, since an undo entry names
drawing ids and zone keys from the room being left and replaying one after the swap writes a box
onto an unrelated drawing.

## What the upload slice refuses, and why the pair guard deletes

Validation runs in the client before anything is sent: extension (`.dxf`, or the 3D formats when
the 3D workspace is showing), a 10 GB ceiling, and a two-byte read for the `MZ` header so an
executable renamed to `.dxf` is rejected without reaching the server.

The guard worth knowing about is `applyCompletedDrawing`. A room's two slots must hold two
revisions of **one** drawing; `isDrawingPairMismatch` compares the extracted drawing numbers, and
on a mismatch the slice deletes the drawing that was just ingested rather than the one already in
the room. Without it an unrelated file ingests cleanly and produces a full comparison in which
every value differs — confident, complete, and meaningless. Deleting the newer side is safe
because the rejected upload is the user's own mistake and the slot it targeted is unambiguous.

## The resume path, landed 2026-09-08

Reopening a room used to mount whatever the room named, with no reference to extraction state:
`if (oldDoc) ws.setOldDrawing(oldDoc)`. A drawing that was still being extracted was handed to
the canvas as though it were finished, and because nothing resumed job polling the room stayed
that way until the app was reloaded.

`applyOrResumeDrawing` in `roomStore.ts` now branches on `doc.status`:

- `completed` — mount it, progress 100, clear the job id.
- `queued` or `processing` — mount the UploadZone in its processing state instead of the drawing,
  then ask `GET /api/v1/drawings/{id}/job` for the latest `ExtractionJob` and either apply it,
  fail the slot with the job's error, or adopt the job id so the existing polling takes over.
- `failed` — fail the slot with a retry prompt.

The route returns the newest job for a drawing, or `null`, and is the only way the client can
learn about a job it did not start itself. Both halves are pinned:
`tests/test_drawing_job_endpoint.py::test_get_drawing_job_returns_latest_job` and, on the client,
`roomStore.openRoom.test.ts` — *resumes in-flight ingestion when re-entering a room with an
ingesting drawing* and *immediately mounts drawing when re-entering a room with a completed
drawing*.

> [!WARNING] The resume path writes store state directly, and lint says so.
> `applyOrResumeDrawing` calls `useWorkspaceStore.setState(...)` at four places rather than going
> through a named slice action, which is exactly what the `no-restricted-syntax` rule in
> `eslint.config.js` exists to prevent — the rule names the fix in its own message: add an action
> in `src/stores/workspace/slices/*`. Measured 2026-09-09: `npx eslint src/stores/roomStore.ts`
> reports 10 of these, 4 of them in this function. It is part of the standing backlog `CLAUDE.md`
> describes, not a new failure, and it is the cheapest thing to fix in this file: the slice
> already exports `setUploadFailure`, `applyCompletedDrawing` and `clearUpload`, so only the
> processing branch has no action to call.
