---
title: Gotcha - Zod Strips Unknown Room Fields
type: gotcha
tags: [gotcha, frontend, zod, schemas, rooms, api]
status: resolved
date: 2026-07-28
---

# 🔥 Gotcha — Zod Silently Strips Any Room Field Missing From `RoomSchema`

## ⚠️ The Problem

Add a field to the backend `Room` document, thread it through `RoomResponse` and
`UpdateRoomRequest`, map it in `_to_response`, add it to the TypeScript `Room` interface —
and it still never reaches the app.

## 🔍 Root Cause

`apps/desktop/src/services/fetchUtils.ts::parseAndValidate` calls `schema.parse(data)`, and
`RoomSchema` in `apps/desktop/src/schemas/apiSchemas.ts` is a `z.object`. **Zod object parse
strips keys the schema does not declare.** The TypeScript interface is compile-time only and
does nothing to stop it.

Every consumer is affected at once, because `parseAndValidate` sits on both room paths:
`roomStore.openRoom` and `roomStore.updateRoom`.

## 💥 Why it is nasty

The failure is not an error — it is an omission. For the zone-review gate this presented as:

1. User clicks **Done**; optimistic local state opens the gate; the panel appears. Looks fine.
2. The PATCH succeeds and the server stores the value correctly.
3. The response comes back through `parseAndValidate`, which drops the field.
4. `activeRoom` is replaced with the stripped object, the derived gate flips false, and the
   panel vanishes on the next sync.

Every symptom points at React state management. Nothing points at the schema.

## 🛠️ The Fix

Declare the field in `RoomSchema` too:

```ts
zones_confirmed_for: z.string().nullable().optional(),
```

> [!IMPORTANT]
> **Adding a field to the `Room` document is a FIVE-file change, not four:**
> 1. `services/backend/domain/models/room.py`
> 2. `services/backend/api/schemas.py` — `RoomResponse` **and** `UpdateRoomRequest`
> 3. `services/backend/api/routers/rooms.py` — `_to_response`
> 4. `apps/desktop/src/stores/roomStore.ts` — the `Room` interface
> 5. **`apps/desktop/src/schemas/apiSchemas.ts` — `RoomSchema`** ← the one that is easy to miss

The same applies to any other `z.object` schema in `apiSchemas.ts`, not just rooms.

## 🧪 Guard

A store-level test that mocks a room response containing the new field and asserts it
survives onto `activeRoom` is worth more than any component test, because it is the only
layer where the stripping happens.

## 🔗 Related Notes
- See [[Gotcha - Zone Detection Accuracy & Stability]]
- Return to [[00 - Map of Content (MOC)]]
