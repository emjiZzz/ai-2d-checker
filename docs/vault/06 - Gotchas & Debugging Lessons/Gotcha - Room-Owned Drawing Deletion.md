---
title: Gotcha - Room-Owned Drawing Deletion
type: gotcha
tags: [gotcha, rooms, drawings, lifecycle, frontend, backend, ingestion]
status: resolved
date: 2026-08-03
---

# 🔥 Gotcha — Delete-on-Replace Cannot Ride the Room Sync PATCH

## 🧭 Context

The Library was removed in favour of **room-owned drawings**: dedup is gone (every upload is
its own `DrawingDocument`, always re-parsed), replacing a slot hard-deletes the drawing it
displaced, and deleting a room hard-deletes both its drawings + entities + files + caches. The
question that bites is *where the replace-delete runs*.

## ⚠️ The Trap

The obvious home for "replacing a slot deletes the old drawing" is the room PATCH endpoint
(`rooms.py::update_room`): diff the incoming `active_old_drawing_id` / `active_new_drawing_id`
against the stored ones and purge whatever changed. **This deletes the wrong room's data.**

## 🔍 Root Cause

`AuditWorkspace.tsx` reverse-syncs the workspace's live drawings onto the active room via a
`useEffect` keyed on `oldDrawing?.id`, `newDrawing?.id`, and `activeRoom`. Any time those
drift out of agreement, it PATCHes the room.

`roomStore.ts::openRoom` opens with a fast-path restore **before** it fetches the room:

```ts
openRoom: async (roomId) => {
  if (currentRoom) await saveWorkspaceState(currentRoom.id);
  await loadWorkspaceState(roomId);   // ← sets oldDrawing/newDrawing from IndexedDB (room B)
  ...
  set({ activeRoom: roomData });      // ← activeRoom only flips to B much later
}
```

Between those two lines, `oldDrawing`/`newDrawing` already hold **room B's** ids while
`activeRoom` is still **room A**. The sync effect sees the mismatch and fires
`updateRoom(A, { active_old_drawing_id: B.oldId, ... })`. Under a diff-delete PATCH, that call
purges **room A's real drawings** — swapping between rooms silently destroys them.

## 💥 Why it is nasty

- It is a **cross-room race** that only surfaces on room switching, never in a single-room test.
- It is a **hard delete** — irreversible, no soft-delete safety net on the drawings.
- The sync effect was built for *soft* state persistence; the transient A-holds-B's-ids window
  is harmless there and has always existed. Wiring destructive semantics into the PATCH is what
  turns a benign transient into data loss.

## 🛠️ The Fix — put deletion at the two moments of genuine intent

1. **Replace-delete lives in the upload path**, not the PATCH.
   `createUploadSlice.ts::uploadDrawingFile` captures the slot's prior id **before** the
   `set({ oldDrawing: null })` reset, and after the new upload succeeds deletes it (best-effort):

   ```ts
   const previousDrawingId = (isOld ? get().oldDrawing : get().newDrawing)?.id ?? null;
   // ...after the new drawing is persisted:
   if (previousDrawingId && previousDrawingId !== drawing.id) {
     deleteDrawing(previousDrawingId).catch(/* log only */);
   }
   ```

   Unambiguous user intent, the exact slot id, no cross-room ambiguity, and only after the
   replacement is safely in (a failed upload never loses the existing drawing).

2. **Room-delete purge lives in the backend** `rooms.py::delete_room`, which knows both slot ids
   at delete time and calls the shared `DrawingIngestionService.purge_drawing` for each.

3. **`clearUpload` stays non-destructive.** It is a shared reset primitive fired by
   `createNavSlice`, `createAuditSlice`, `roomStore.openRoom`'s restore (`else ws.clearUpload(...)`),
   and the DELETE_TAB veto. Wiring deletion into it would nuke drawings during ordinary
   navigation — the same class of bug as the PATCH, from a different direction.

> [!IMPORTANT]
> Never move drawing deletion into `update_room` or `clearUpload`. The room PATCH and the reset
> primitive both fire transiently with a mismatched (room, drawings) pair. Deletion belongs only
> where the user's intent is explicit: a completed replacement upload, or an explicit room delete.

## 🧨 Secondary trap — unique on-disk filenames

Dropping dedup means the file name can no longer be `{file_hash}.{ext}`: two uploads of the same
bytes would otherwise write the same path, and purging one drawing's file would orphan the
other's on disk. `process_ingestion` now names uploads `{uuid4().hex}.{ext}` so **each drawing
owns exactly one file**. `file_hash` is still stored (metadata + OCR cache key) but never names
the file.

## 🧪 Guards

- `apps/desktop/src/stores/__tests__/createUploadSlice.test.ts` — uploading over an occupied slot
  calls `deleteDrawing(previousId)`; an empty slot deletes nothing.
- `tests/test_rooms.py::test_delete_room_purges_both_owned_drawings` — room delete hard-deletes
  both slots; the Room record stays soft-deleted.
- `tests/test_drawing_ingestion_service.py` — re-upload yields a **new distinct** drawing (no
  dedup); `purge_drawing` removes record + file + job + caches.

## 🔗 Related Notes
- See [[Gotcha - Zod Strips Unknown Room Fields]] — the other Room-lifecycle sharp edge.
- See [[Gotcha - Re-test and the Four Caches]] and [[Gotcha - Comparison Cache Invalidation]] —
  what `purge_drawing`'s cache clear does and does not cover.
- Return to [[00 - Map of Content (MOC)]]
