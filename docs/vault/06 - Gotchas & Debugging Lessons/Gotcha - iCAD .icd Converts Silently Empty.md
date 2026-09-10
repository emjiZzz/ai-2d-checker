---
tags: [gotcha, ingestion, icad, dxf, tooling, corpus]
related: [Gotcha - A Standard That Ingested Nothing Reported Success, Gotcha - The Two Sides
  of a Comparison Come From Different Exporters, Gotcha - 3D DXF Ingestion Was Built and Removed]
date: 2026-09-10
---

# Gotcha - iCAD .icd Converts Silently Empty

## What happened

iCAD SX `.icd` is the native format of the CAD the drawings are authored in, and one file
carries both a 3D model and 2D drawing content. Only the 2D half is extracted: it is what
the comparison engine reads, and the 3D half needs `ICD2STP.exe`, which answers exit 102
(batch-STEP licence not active) on this install. Bringing the 2D half in means converting to
DXF with the vendor translator, `%ICADDIR%\TR2\DXFDWG\bin\TR2_DExp.exe`, licensed off
`192.168.200.110`.

Until 2026-09-10 `.icd` was routed to `ThreeDPipeline` alongside STEP and IGES, so it never
reached `dxf_parser` at all. That path fails all the way down and reports success: ICD2STP
returns 102, gmsh cannot parse the binary, and the pipeline substitutes a 1x1x1 placeholder
box. A 6 MB assembly and a 440 KB drawing both produced byte-identical 1.6 KB glTF cubes
tagged `acad_version: 3D_STANDARD_BREP`, `face_count: 12`. The fallback box is still there
for the other 3D formats and is its own defect.

On a first production sample -- 27 drawings, 68 MB, pulled from four customer folders
under `Z:\PROJECTS\` -- the translator reported success on all 27 and `ezdxf` opened all
27. Fifteen of them contained **zero entities**.

The translator does not distinguish the two cases. Log output for a 6 MB file that
converted to nothing:

```
09251 図面変換を開始します。       name:...\p03.icd
09271 変換図面を登録しました。     name:...\p03.dxf   size:697593byte
09291 正常終了しました。
```

and for a good one, the same three codes, same exit 0, `size:2883754byte`. The only
signal is the size, and ~697 KB is simply what an R2000 DXF weighs with its tables and no
content. Nothing in stderr, `-msg 0` included.

Had this gone straight into ingestion, 56% of the corpus would have arrived as valid
blank drawings and every comparison over them would have reported clean.

## What was ruled out

- **Library misconfiguration.** The sample batch `TR2_DExpB.bat.txt` sets drawing, parts
  and symbol folders, and the manual warns that a command-line run resolves against
  whatever iCAD itself has configured. Re-run with the exact library set from
  `ETC/ICENV.INI` (`MDL00`, `LIB00`-`LIB08` including `sysmmf\システムフォルダ`): still
  zero entities on all six retried.
- **A missing flag.** `MAN/dxf_dwg_trans.pdf` section 6-1-2 documents the complete option
  set: `-d`, `-dwg|-dxf|-dxb [version]`, `-rn`, `-i`, `-o`, `-prm`, `-msg`, `-rp|-nrp`,
  `-RN`. There is no view-sheet selector and no 3D option.
- **The file header.** The `.icd` preamble decodes far enough to read a version word and
  byte order, and neither separates the two groups: empty and populated files appear on
  both V7 and V8, and the `DRW` section is a 76-412 byte header in every file regardless.

The likeliest remaining explanation is that those files carry no 2D drawing content --
several are named `Assy.icd` / `assy.icd` -- but that is **not confirmed**, and it does not
fit cleanly: some of the empty ones sit in folders named `製作図`. `ICD2PS.exe` would
settle it and was not made to run. Recorded as measured-but-unexplained rather than
guessed.

## Why there is no native .icd parser

Asked and answered, so it does not get re-litigated. The container preamble is readable:
sections `MOD0`/`MOD1`, `DRW0`/`DRW1`, `RES0`/`RES1`, each `tag(4) + length(4)`, closed by
the matching `1` tag, with the drawing name at offset 16. Byte order varies by
generation -- the length field reads `00 00 00 40` on older files and `40 00 00 00` on
current ones, both meaning 64.

Past that it stops. Better than 99% of every file sits after `RES1` in a region with no
recovered structure, and the coordinates in it decode to nothing. Tested against ground
truth taken from each file's own DXF export, on 63 distinctive non-integer coordinates:

| Encoding | Hits |
| :--- | ---: |
| float64, big and little endian | 0/63 |
| float32, big and little endian | 0/63 |
| scaled int32 and int64, x10^3 through x10^8 | 0/63 |
| IBM hex64, VAX D_float, VAX G_float | 0/63 |

Nor is it compression hiding them: entropy is 2.5-5.2 bits/byte across the corpus with no
zlib or raw-deflate stream anywhere. Matching round values like `1.0` looks like a hit and
is not -- an early pass read 21/25 that way and every one was coincidence. Filter to
distinctive values before believing any probe of this kind.

Against that, the translator emits R2000 DXF in exact millimetres, `Kyowa_A3` measuring
420.0 x 297.0. It is the supported seam and it is on the network already.

## What the converted drawings actually look like

The 12 with content flattened to 148,897 entities: `LINE` 103428, `ELLIPSE` 24589, `ARC`
9470, `SPLINE` 7377, `CIRCLE` 2323, `DIMENSION` 520, `LWPOLYLINE` 367, `HATCH` 186,
`TEXT` 169, `LEADER` 64, `MTEXT` 404. Blocks nest two deep.

Three things that differ from the DXFs already in the corpus:

- **These are not sheets.** Extents ran 9 x 19 mm to 70407 x 122685 mm, and exactly one
  landed on a paper size. They are model-space at drawing scale, so the sheet-fraction
  zone templates do not transfer to them.
  See [[Gotcha - One Template Looked Like Several in Fraction Space]].
- **`plain_text()` does not clean iCAD MTEXT.** Every string arrives wrapped in inline
  codes and `ezdxf.tools.text.plain_text` returns them verbatim. Strip
  `\\[fF][^;]*;|\\[AWTHQC][-0-9.]*;` first, and treat `\P` as a newline rather than
  deleting it. Related but not the same defect as
  [[Gotcha - AutoCAD Control Escape Codes]].
- **A third of text is one character.** 30.9% of MTEXT reduces to a single character after
  stripping, because Japanese title blocks position characters per cell. Full sentences do
  survive whole, so this is cell-structured text specifically, not global fragmentation.

## Guarded by

- `tests/test_icd_ingestion.py` -- five cases: the entity count resolves blocks (a raw
  modelspace count reads 1 where the truth is 21, which would classify every real drawing
  as empty), an empty conversion counts zero, `.icd` is not in the 3D format tuple, a
  populated .icd extracts through `dxf_parser`, and an empty one fails the job instead of
  ingesting blank. The three behavioural cases were watched failing against the pre-fix
  pipeline before being believed. The translator is stubbed, so no licence is needed and the
  tests run anywhere.
- `tests/test_drawing_format_consistency.py` -- the accepted-format list is hand-mirrored in
  `DrawingIngestionService.ALLOWED_EXTENSIONS` and `apps/desktop/src/config/drawingFormats.ts`,
  and this fails if either side moves alone, if a format claims both the 2D and 3D sets, or
  if any other frontend module inlines the list again.

Still unguarded: that a real `.icd` converts at all. Every test above stubs the translator,
because a fixture would have to be committed and licensing makes that an owner's call. The
conversion itself is only ever exercised by hand.

## Traps for the next person

- **Exit 0 from `TR2_DExp` means nothing.** Count entities, and count them with blocks
  resolved: a whole title block arrives as one `INSERT` that expands to a few hundred, so
  a modelspace count reads 1 where the truth is 233.
- **`-o` takes a directory.** A filename gets `09276 図面登録先パスの指定に誤りがあります`.
- **Default output is DWG,** not DXF. `-dxf` is required; `-dxf 2018` and similar are
  available up to 2019.
- **Use `-RN listfile` for anything real.** KUSAKABE alone holds ~2350 `.icd` at depth 4;
  passing those as arguments hits the command-line length limit.
- **Redirect `IUSRHOME`.** The shipped wrapper runs `rmdir %IUSRHOME%\TR2_DB /S /Q`, which
  without redirection deletes inside the live iCAD install.
- **`09904 ilg. BATCHMODE` at startup is benign** and fires once per run whether or not
  everything converts.

## Still unmeasured

Whether the geometry is *faithful*, not merely present. Extents matching ISO paper sizes on
the templates is a sanity check, not a fidelity measurement, and nothing has compared a
converted sheet against what iCAD itself renders. Until that is done, a conversion that
silently drops or displaces entities would look exactly like a conversion that worked --
which is the same shape as the defect this note is about.

Return to [[00 - Map of Content (MOC)]].
