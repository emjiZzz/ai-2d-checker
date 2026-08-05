---
title: Gotcha - BOM Refer-To-Table Deferral Row
type: gotcha
tags: [gotcha, bom, extraction, comparison]
status: resolved
date: 2026-07-30
---

# The BOM showed no results though a row was plainly on the sheet

Reported as "BOM no results? There's a value in there!". The BOM zone on the KEMCO pair
contains the header row plus exactly one data row: an item number `1` next to `表ニヨル`
(表による = "as per the table") — a **pointer** saying the materials live in a separate table
(here the shim table). `extract_bom_table` returned `[]`, so `build_bom_table` emitted only a
header and the BOM comparison was blank.

## Root cause

`extract_bom_table` drops any row group with `< 4` cells (to reject sub-totals and header
fragments). The `1 表ニヨル` deferral row has only **two** cells, so it was filtered out.

## Fix

A fallback in `extract_bom_table`: when no real (≥4-cell) rows are found, scan the BOM texts
directly for a deferral marker (`表ニヨル` / `表による` / `別表` …) and, if present, emit one row
carrying the marker (`CODE` for parts drawings, `TITLE` for assembly). Detected from the raw
texts rather than the row grouping on purpose — the two cells can fall inside the header row's
y-threshold and merge into it, then be discarded as a label row. Fallback only, so an ordinary
populated BOM is untouched.

The row now compares MATCHED (both drawings defer identically), and the **actual materials**
are compared in the shim-table zone — see [[Gotcha - Optional Zones and the Shim Table]].

## Guarded by / cache

`tests/test_extraction_logic.py::test_extract_bom_captures_refer_to_table_deferral_row`.
Cache **v21→v22**.
