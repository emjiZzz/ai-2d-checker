---
title: Rooms and Upload Surfaces
type: frontend
tags: [frontend, rooms, upload, pagination, accessibility]
status: active
verified-against: 2026-09-09, commit 3b2b8d4 (`RoomsView` pagination, `UploadZone` interaction)
related: [Workspace Store Slices & the Ingestion Resume Path, CanvasRenderer & Entity Drawing]
---

# 🖥️ Rooms and Upload Surfaces

The two surfaces an engineer meets before any comparison exists: the room grid, and the two
drop slots inside a room. Both were reworked on 2026-09-08.

## RoomsView: fixed pages, not infinite scroll

The grid paged itself by `IntersectionObserver` — a sentinel div at the bottom raised
`displayLimit` by 24 each time it scrolled into view. It now uses fixed pages:

```
ROOMS_ON_FIRST_PAGE = 11   // page 1 also carries the Create New card, so the grid stays 3 rows
ROOMS_PER_PAGE      = 12   // every page after
```

Both constants are exported, because `RoomsView.test.tsx` asserts the row budget against them
rather than against a literal that could drift from the layout.

Three behaviours are worth keeping when this is touched again:

- **The page is clamped, not preserved.** Filtering or searching can shorten the list under the
  current page; an effect pulls `currentPage` back to `totalPages`, and a new search resets to
  page 1. Without that, narrowing a search from page 4 lands on an empty grid that looks like
  "no rooms" rather than "no rooms *here*".
- **Arrow keys page the grid**, and the handler stands down while `isCreating` or `deletingRoom`
  is set, so Left/Right inside a modal do not move the grid behind it.
- **The range label is computed from the same two constants**, so "showing 12-23 of 40" cannot
  disagree with what is rendered.

> [!WARNING] In flight as of 2026-09-09, and not landed.
> The working tree removes the Previous/Next buttons and keeps only the arrow-key path. Four
> tests in `RoomsView.test.tsx` still query those controls by title and fail against it. Whoever
> finishes that change decides which is the real interface — if the keyboard is the only way to
> page, the tests move to it, and the pagination becomes invisible to anyone who does not know
> the keys.

## UploadZone: one explicit control, and a picker that agrees with the validator

Drag-and-drop is gone. The zone was `role="button"` over its whole area, with
`onDragEnter/Over/Leave/Drop`, a drag-active border treatment, and a click anywhere to open the
file picker. It is now `role="region"` with an inner Browse control that carries the button role,
its own `aria-label`, and Enter/Space handling. `e2e/ingestion.spec.ts` asks for that button by
name instead of matching the old "Drag & drop or" copy.

The accept list narrowed with it, from `.pdf,.dwg,.dxf` to `.dxf` in the 2D workspace (the 3D
workspace keeps its own STEP/IGES/SolidWorks list). That is the more useful half of the change:
`createUploadSlice` has always rejected everything but DXF with *"Unsupported format. Only DXF
files (.dxf) are currently supported"*, so the old picker advertised two formats that the
validator immediately refused. A file dialog that offers `.pdf` and then fails the upload reads
as a broken app; the two lists now say the same thing. See
[[ADR-011 Vector as the Only Render Path]] for why DXF is the only input.
