"""The report's drawing page, as real vectors with real selectable text.

## What this produces

One PDF page per call: the sheet's CAD geometry as mathematical vector paths, a **searchable
text layer** over it, and the review markers as vector badges. No raster anywhere — measured on
`M745221N01`: 714 vector operations, 0 images, 1612 extractable characters, ~0.5 MB.

⚠ **There are two copies of every string on the page and `TextSource` decides which one you can
see.** Read that enum before changing anything here: it is also the export's single largest
cost, at 90-98% of the time a sheet takes.

The report's page 1 has until now been a 304 dpi PNG of the canvas
(`useComplianceReportExport.ts`). That prints acceptably and cannot be searched, copied, or
zoomed past its capture resolution.

## Why the text layer is written by hand

**ezdxf's drawing add-on renders every string as filled glyph outlines, in every backend.**
`MatplotlibBackend` implements `draw_filled_paths` and has no `draw_text`; the frontend converts
text to paths upstream of the backend, so `TextPolicy` offers `FILLING`, `OUTLINE` (also paths)
and `IGNORE` and nothing else. A PDF made that way contains **zero** extractable characters, and
nothing reports it — the file opens, looks perfect at 1000%, and prints beautifully.

So the glyphs come from ezdxf and the text layer is written separately, from the **extracted
entities** -- by default in PDF text render mode 3, invisible, over ezdxf's own glyphs. That is
deliberate beyond necessity: the strings a reader can select are then the same `ExtractedEntity`
data the canvas draws and the checklist quotes, so the report cannot disagree with itself about
what the sheet says.

⚠ **An invisible layer cannot be observed to be wrong**, and it was wrong in two ways for its
whole life -- white, and rotating every string backwards -- neither of which any assertion about
the text can see. See `Gotcha - Making the Text Layer Visible Showed What Being Invisible Had
Hidden`. If you touch this layer, rasterise a page and look at it under `TextSource.LAYER`.

Placement is not modelled here — it comes from `text_placement.py`, which `tools/render_audit.py`
measures against ezdxf's own `Recorder` output every time the renderer changes.

See `docs/vault/06 - Gotchas .../Gotcha - The Vector PDF Had No Text at All.md` for the four
displacements this file exists to avoid, each of which is silent.

## Threading

⚠ **This does not touch `pyplot`.** `dxf_background_renderer` does, and is safe only because the
ingestion queue has a single serial consumer — see
`Gotcha - The Background Queue Was Not a Background Thread`. This module is built to be called
from a request path, so it drives the OO `Figure` API and holds a lock only around the two global
registrations it genuinely cannot avoid (ezdxf's font manager, matplotlib's font cache).

`pdf.fonttype` is **not** set, and that is not an oversight: it governs how matplotlib embeds
`Text` artists, and this module draws none — every glyph on the page is a path from ezdxf, and
every character in the text layer is written by PyMuPDF.
"""

from __future__ import annotations

import io
import math
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from ...logger import logger
from .text_placement import (
    CAD_TEXT_FIT_SCALE,
    CANVAS_FONT,
    anchor_fractions_of,
    cap_height_ratio,
    clean_cad_text,
    resolve_report_font,
)

MM_PER_INCH = 25.4
PT_PER_INCH = 72.0


@dataclass(frozen=True)
class PageSpec:
    """The paper, in millimetres.

    Mirrors `REPORT_PAGE_MM` / `REPORT_MARGIN_MM` in
    `apps/desktop/src/components/review/reportPageGeometry.ts`, because the checklist pages this
    sheet is bound with are still generated there and two page sizes would not bind.
    Pinned by `tests/test_report_style_consistency.py`.
    """

    width_mm: float = 297.0
    height_mm: float = 210.0
    margin_mm: float = 3.0

    @property
    def size_inches(self) -> tuple[float, float]:
        return (self.width_mm / MM_PER_INCH, self.height_mm / MM_PER_INCH)

    @property
    def content_fractions(self) -> tuple[float, float, float, float]:
        """(left, bottom, width, height) of the printable box, as figure fractions."""
        fx = self.margin_mm / self.width_mm
        fy = self.margin_mm / self.height_mm
        return (fx, fy, 1.0 - 2 * fx, 1.0 - 2 * fy)


A4_LANDSCAPE = PageSpec()


class TextSource(StrEnum):
    """Which of the two copies of the sheet's text is the one you can see.

    There have always been two. ezdxf tessellates every string into filled glyph outlines, and
    this module writes the same strings again from `ExtractedEntity` as a selectable layer. Only
    one may be visible: both, and every character is double-struck in two typefaces; neither, and
    the sheet has no text at all. That is why this is one enum and not two booleans.

    ## `OUTLINES` — ezdxf draws, our layer is invisible

    What the report has always done, and the safe answer. The visible glyphs are ezdxf's own, so
    they are correct by construction; the invisible layer only has to land close enough to select.

    ⚠ **It costs 90-98% of the export.** Measured 2026-08-25: on the largest sheet in the corpus
    `draw_layout` takes **21.4 s**, of which all 2263 entities of geometry are **2.2 s** and the
    373 strings are the other **19.2 s** — about **52 ms per string**, near enough linear. A
    small sheet is 9.9 s and a dense one 28.1 s, so an assembly with a thousand strings is a
    minute and one with two thousand is two.

    ## `LAYER` — ezdxf skips text, our layer is the page

    `TextPolicy.IGNORE` plus render mode 0. **10x on the largest sheet**, and it changes the
    SCALING rather than the constant: text stops being the cost, so a big assembly becomes a
    geometry problem, and geometry is cheap. The text also becomes real text rather than paths.

    ⚠ **It shows the placement model's errors instead of hiding them.** Measured by
    `tools/text_layer_audit.py`: `|dx|` median 0.094 drawing units and 97% of widths within ±20%
    — so ~3% of strings would be visibly off, and the wrapped-MTEXT line split (a guess) and
    rotated text (untested, no rotated strings in the corpus) stop being invisible gaps.

    🔴 **And it is only safe on a drawing extracted at the current
    `EXTRACTION_SCHEMA_VERSION`.** `render_text_point` — the dimension text anchor — arrived in
    v3. Below that, `_text_items` falls back to `text_point`, the midpoint of the dimension LINE,
    which today is harmless because ezdxf draws the real text over it. Make this layer visible on
    a stale drawing and every dimension value moves to the wrong place. Measured 2026-08-25:
    **38 of 65 stored drawings are stale, 20 of them at v2.** `_resolve_text_source` is what
    stops that reaching a page; `tools/extraction_status.py` lists them and `/reextract` fixes
    one without losing its id, room slot or audit history.
    """

    OUTLINES = "outlines"
    LAYER = "layer"


#: Status -> the badge's NEON FILL, as 0-1 RGB. `markerStyles.ts`'s **`color`** column.
#:
#: ⚠ **These are deliberately the high-chroma canvas values, and they are used as a FILL, never
#: as a stroke.** That distinction is the entire reason this works, and reversing it re-creates
#: the defect the previous palette existed to avoid.
#:
#: Until 2026-08-25 the badge was drawn the other way round: `uiLight` ink on a white fill,
#: chosen because `#39ff14` and `#00ffff` are close to invisible *as a line* on white paper.
#: That reasoning was right about the colours and wrong about the outcome — on a printed sheet
#: the badges disappeared into the linework, because a thin dark ring reads as part of a
#: technical drawing. Marks a reviewer made have to be findable at arm's length.
#:
#: Neon on white is a **highlighter**, not a pen. Filled, `#39ff14` is the most conspicuous thing
#: on an otherwise black-and-white sheet; stroked, it is the least. So the fill carries the neon
#: and `MARKER_EDGE` carries a dark outline and glyph over it, which is also what keeps the badge
#: legible for a reader who cannot separate the hues.
#: Pinned by `tests/test_report_style_consistency.py`.
MARKER_INK: dict[str, tuple[float, float, float]] = {
    "MISMATCHED": (0xFF / 255, 0x28 / 255, 0x50 / 255),
    "CHANGED": (0xFF / 255, 0x96 / 255, 0x00 / 255),
    "ADDED": (0x00 / 255, 0xFF / 255, 0xFF / 255),
    "MATCHED": (0x39 / 255, 0xFF / 255, 0x14 / 255),
    "CONFLICT": (0xC0 / 255, 0x84 / 255, 0xFC / 255),
    "REMOVED": (0xFF / 255, 0x28 / 255, 0x50 / 255),
    "NOT_A_FINDING": (0xA1 / 255, 0xA1 / 255, 0xAA / 255),
}

#: Status -> the outline and glyph drawn ON the neon fill. `markerStyles.ts`'s `uiLight` column.
#:
#: The same table's answer for "this status, on a light background", so the report still reads
#: two columns out of `markerStyles.ts` rather than inventing a palette. It is what makes the
#: glyph legible against its own highlight: `#39ff14` at 0.87 luminance cannot carry a white ✓.
MARKER_EDGE: dict[str, tuple[float, float, float]] = {
    "MISMATCHED": (0xB9 / 255, 0x1C / 255, 0x1C / 255),
    "CHANGED": (0xC2 / 255, 0x41 / 255, 0x0C / 255),
    "ADDED": (0x1D / 255, 0x4E / 255, 0xD8 / 255),
    "MATCHED": (0x04 / 255, 0x78 / 255, 0x57 / 255),
    "CONFLICT": (0x7E / 255, 0x22 / 255, 0xCE / 255),
    "REMOVED": (0xB9 / 255, 0x1C / 255, 0x1C / 255),
    "NOT_A_FINDING": (0x71 / 255, 0x71 / 255, 0x7A / 255),
}

# `MARKER_GLYPH` was deleted on 2026-08-25 along with the glyph it drew. The report matches the
# canvas now, and the canvas puts no symbol inside a mark: a flat dot, or a tick for MATCHED. The
# dict had become data with no reader, mirrored by hand from `markerStyles.ts` and kept honest by
# a test — which is a maintenance cost paid for nothing. `markerStyles.ts` still carries `glyph`
# and the CHECKLIST pages still draw it; that side is TypeScript end to end and never read this.

_FALLBACK_STATUS = "MISMATCHED"

#: Badge radius in points. ~2.5 mm — large enough to read on A4, small enough not to bury the
#: geometry it is pointing at.
_BADGE_RADIUS_PT = 7.0

#: Hairline width in mm, used when the drawing asks for lineweights NOT to be displayed.
#:
#: 0.13 mm is the ISO thin line and the thinnest stroke a 600 dpi laser still holds cleanly.
#: See `_lineweight_settings` for why this is reached at all on this corpus.
_HAIRLINE_MM = 0.13

#: Dimensions, leaders and their extension lines are drawn at this instead — **thinner than the
#: part itself**, which is what ISO 128 asks for and what a CAD viewer shows.
#:
#: Until 2026-08-25 there was one width for the whole sheet, because `_lineweight_settings`
#: collapsed every stroke onto `min_lineweight` and nothing could differ from anything else. The
#: part outline and the dimension witness lines printed at the same 0.369 pt, so the drawing had
#: no depth: the measurement furniture read as loudly as the thing being measured.
#:
#: 0.09 mm is the next ISO step down and still holds at 600 dpi (0.255 pt). Below this the line
#: starts dropping out on a laser, and a dimension you cannot see is worse than a heavy one.
_DIMENSION_HAIRLINE_MM = 0.09

#: The same relationship expressed as a ratio, for the `$LWDISPLAY` path where the drawing's own
#: pen weights are honoured and there is no fixed width to substitute.
_DIMENSION_WEIGHT_RATIO = _DIMENSION_HAIRLINE_MM / _HAIRLINE_MM

#: DXF types whose ink is *annotation* rather than *part*, and which therefore take the thin pen.
#:
#: ⚠ Only the top-level type is listed. A DIMENSION carries its lines, arrowheads and text in an
#: anonymous geometry block, and ezdxf resolves the properties **once, from the DIMENSION** before
#: drawing that block -- so overriding here reaches the whole assembly. Verified by measuring the
#: stroke widths in the output PDF, not by reading the ezdxf source: `tests/test_vector_pdf_export
#: .py::test_dimensions_are_drawn_thinner_than_the_part` fails if that resolution order changes.
_ANNOTATION_TYPES = frozenset({
    "DIMENSION", "ARC_DIMENSION", "LARGE_RADIAL_DIMENSION", "LEADER", "MULTILEADER", "MLEADER",
})

#: ⚠ `Configuration.min_lineweight` documents itself as "in 1/300 inch". Through
#: `MatplotlibBackend` it is **not** — measured, the value passes through 1:1 as PDF POINTS
#: (min_lineweight 0.25 -> 0.25 pt strokes, 1.0 -> 1.0, 2.0 -> 2.0). Trusting the docstring
#: makes a 0.13 mm hairline come out at 1.535 pt, i.e. twice as thick as the weights it was
#: meant to replace — which reads as the setting having no effect rather than the wrong unit.
_LINEWEIGHT_PT_PER_MM = 72.0 / 25.4

#: MTEXT inline codes the text layer cannot reproduce, so ezdxf must draw those strings itself
#: even when it is drawing nothing else. Code -> why it cannot be reproduced.
#:
#: The test is against the **raw MTEXT at render time**, which is the only place these survive:
#: `strip_mtext` runs at extraction, so by the time a string reaches `_text_items` the evidence
#: is gone. That is also why this lives here and not in the extracted entity.
#:
#: ## `\S` — the stacked fraction, i.e. the dimension tolerance
#:
#: `40` over a stacked `-0.1`/`-0.2`. ezdxf composes it at render time out of the DIMENSION's
#: `DimStyleOverride` (`dimtol`/`dimtp`/`dimtm`), so it is in neither the DXF's `text` attribute
#: nor the extracted entity — `strip_mtext` drops the whole group and `render_text` is bare `40`.
#: Measured across `storage/uploads`: **46 of 724 dimensions on 14 of 57 sheets.**
#:
#: ⛔ **Two ways of reproducing it ourselves were measured and rejected.** `MTextExplode` returns
#: each piece as a placed TEXT and looks like the answer, but it is a DIFFERENT layout engine from
#: the drawing frontend and disagrees with it by up to **5.1 drawing units** over these seven
#: strings, consistently laying the stack narrower. Re-deriving the stack from `dimtp`/`dimtm` is
#: the same mistake one layer down: a second opinion about ezdxf's own composition rule, correct
#: until ezdxf changes and silently wrong after.
#:
#: ## `\L` `\O` `\K` — underline, overline, strikethrough
#:
#: Two defects at once, and deferring fixes both. The layer draws no rule under a string at all;
#: and `strip_mtext` removes the BACKSLASH but not the letter, so `\LA-A\l` is stored as
#: `LA-Al` and the stray `L` prints. Measured: **11 strings on 7 of 57 sheets**, all of them the
#: section-view designation. 🔴 The `strip_mtext` half is NOT fixed by this — `properties.text`
#: is what the comparison engine pools and the checklist quotes, and it still carries the stray
#: letter there. Fixing that changes comparison input and needs a `COMPARISON_CACHE_VERSION`
#: bump and a re-extraction; this only stops it reaching the page.
#:
#: ## `\P` — the paragraph break
#:
#: `strip_mtext` turns it into a SPACE, so a two-line label arrives as one line and the layer has
#: nothing to split on. **8 strings on 4 sheets**, the same section-view labels.
#:
#: ⚠ Deferring a string trades searchability for fidelity: ezdxf draws paths, so a deferred
#: string is on the page and correct but not selectable. That is the right way round, and the
#: cost is bounded by how rare these are — 7 of 484 strings on the densest sheet.
_UNREPRODUCIBLE_MTEXT: dict[str, str] = {
    r"\S": "stacked fraction (dimension tolerance)",
    r"\L": "underline",
    r"\O": "overline",
    r"\K": "strikethrough",
    r"\P": "paragraph break",
}

#: The text layer's ink. Black, to match `ColorPolicy.BLACK` in the geometry pass, so a sheet
#: looks the same whichever of the two copies of its text is the visible one.
#:
#: Stated rather than defaulted: `TextWriter.write_text` defaults to WHITE. See the note at its
#: call site. Pinned by `tests/test_vector_pdf_export.py::test_the_visible_text_layer_is_black`.
_TEXT_INK = (0.0, 0.0, 0.0)

#: Below this a highlight rectangle is not a usable selection target, and the string is dropped
#: from the text layer rather than written somewhere a reader cannot click.
_MIN_FONT_PT = 0.3

#: ezdxf's font manager scan and matplotlib's font cache are process-global and not thread-safe.
#: The registration is idempotent, so it is done once behind this lock rather than per call.
_FONT_LOCK = threading.Lock()
_font_state: dict[str, Any] = {}


@dataclass(frozen=True)
class SheetMarker:
    """One review mark, in the drawing's own coordinate frame.

    `x`/`y` are paper-space CAD coordinates — the frame `ExtractedEntity.geometry` is stored in
    and the frame `EntityAddress.point` records a click in. NOT canvas pixels, and not
    `render_bounds` fractions: those are Y-down, and this is Y-up.
    See `apps/desktop/src/utils/zoneFractions.ts` for the only place that conversion belongs.
    """

    x: float
    y: float
    status: str = _FALLBACK_STATUS
    label: str = ""


@dataclass(frozen=True)
class _TextItem:
    """A string to place, resolved to its baseline origin inputs."""

    text: str
    x: float
    y: float
    height: float
    rotation: float
    anchor_fx: float
    anchor_fy: float
    width_factor: float


def _configure_fonts_once() -> str | None:
    """Register the CJK font with ezdxf (and matplotlib) exactly once per process."""
    with _FONT_LOCK:
        if "jp_font" not in _font_state:
            from .dxf_render_setup import configure_cad_fonts

            _font_state["jp_font"] = configure_cad_fonts(configure_matplotlib=True)
        return _font_state["jp_font"]


def _text_items(entities: Sequence[dict[str, Any]],
                skip_handles: frozenset[str] = frozenset()) -> list[_TextItem]:
    """Every string on the sheet, with what is needed to put it back where ezdxf drew it.

    `skip_handles` are the entities ezdxf drew itself — see `_UNREPRODUCIBLE_MTEXT`. They come
    back from `_render_geometry`, which is the only thing that knows: the decision is made once,
    while rendering, and consumed here. Recomputing it from the extracted entities instead would
    put the same rule in two places, and the failure mode of the two disagreeing is a string
    drawn twice in two typefaces, or not at all.
    """
    items: list[_TextItem] = []
    for entity in entities:
        props = entity.get("properties") or {}
        if props.get("handle") in skip_handles:
            continue
        geo = entity.get("geometry") or {}
        width_factor = float(props.get("width_factor") or 1.0) or 1.0
        entity_type = entity.get("entity_type")

        if entity_type == "text":
            text = clean_cad_text(str(props.get("text") or "")).strip()
            # The INSERT POINT, in `renderEntities`' own field order -- never `properties.bbox`,
            # which is the declared MTEXT wrapping column and not the rendered extent. Anchoring
            # on the bbox put 25.6% of this sheet's strings on blank paper.
            point = geo.get("location") or geo.get("insert")
            if not text or not point:
                continue
            fx, fy = anchor_fractions_of(props.get("attachment_point", 7))
            height = float(props.get("height") or 2.5) * CAD_TEXT_FIT_SCALE
            for index, line in enumerate(text.split("\n")):
                if line.strip():
                    items.append(_TextItem(
                        line, float(point[0]), float(point[1]) - index * height * 1.6,
                        height, float(props.get("rotation") or 0.0), fx, fy, width_factor))

        elif entity_type == "dimension":
            text = clean_cad_text(str(props.get("render_text") or props.get("text") or "")).strip()
            # `render_text_point` is where the CAD put the string; `text_point` is the midpoint of
            # the dimension LINE. See `Gotcha - The Dimension Text Was Anchored to the Line It
            # Had to Avoid` -- they coincide on ezdxf-authored files and differ on iCAD SX.
            point = geo.get("render_text_point") or geo.get("text_point")
            if not text or not point:
                continue
            items.append(_TextItem(
                text, float(point[0]), float(point[1]),
                float(props.get("text_height") or 2.5) * CAD_TEXT_FIT_SCALE,
                float(props.get("text_rotation") or 0.0), 0.5, 0.5, width_factor))

    return items


def _unplaceable_strings(entities: Sequence[dict[str, Any]]) -> tuple[int, int]:
    """(strings this payload cannot place, strings it has). Placement, not schema version.

    A string is *unplaceable* when the payload carries its text but not the anchor `_text_items`
    needs to put it where the CAD did. Under `TextSource.OUTLINES` that costs nothing visible —
    ezdxf draws the glyph anyway and only the invisible copy is missing, so the string is on the
    page but cannot be selected. Under `LAYER` the same shortfall is the string **not being on
    the page at all**, or being on it in the wrong place.

    ⚠ **A DIMENSION needs `render_text_point` specifically, not merely some point.** `text_point`
    is the midpoint of the dimension LINE and `_text_items` falls back to it, which is right when
    it is a fallback under drawn glyphs and wrong when it is the anchor of the visible value —
    see `Gotcha - The Dimension Text Was Anchored to the Line It Had to Avoid`. That field
    arrived at `EXTRACTION_SCHEMA_VERSION` 3, which is why this is worth checking at all.

    Asking the payload beats asking the stamp in both directions: a sheet with no dimension text
    is safe at any version, and a v7 extraction of a DXF that never recorded a text midpoint is
    not safe despite its stamp.
    """
    unplaceable = total = 0
    for entity in entities:
        props = entity.get("properties") or {}
        geo = entity.get("geometry") or {}
        entity_type = entity.get("entity_type")

        if entity_type == "text":
            text = clean_cad_text(str(props.get("text") or "")).strip()
            anchor = geo.get("location") or geo.get("insert")
        elif entity_type == "dimension":
            text = clean_cad_text(str(props.get("render_text") or props.get("text") or "")).strip()
            anchor = geo.get("render_text_point")
        else:
            continue

        if not text:
            continue
        total += 1
        if not anchor:
            unplaceable += 1
    return unplaceable, total


def _resolve_text_source(requested: TextSource,
                         entities: Sequence[dict[str, Any]]) -> TextSource:
    """`requested`, downgraded to `OUTLINES` unless this payload can carry the whole page's text.

    The downgrade is all-or-nothing because `TextPolicy` is: ezdxf draws every string in the
    layout or none of them, so there is no rendering both the placeable strings from our layer
    and the rest from ezdxf. One string this payload cannot place is therefore one string missing
    from a report a reviewer signs, and the 10x is not worth that trade.

    Recoverable rather than fatal, and loudly: `tools/extraction_status.py` lists the stale
    drawings and `POST /drawings/{id}/reextract` fixes one without losing its id, room slot or
    audit history.
    """
    if requested is not TextSource.LAYER:
        return requested

    unplaceable, total = _unplaceable_strings(entities)
    if unplaceable:
        logger.warning(
            "Text layer cannot be the visible copy: %d of %d strings have no anchor. "
            "Falling back to ezdxf outlines (slower). Re-extract this drawing to fix.",
            unplaceable, total,
        )
        return TextSource.OUTLINES
    return TextSource.LAYER


def _is_full_width(char: str) -> bool:
    """Full-width in MS Gothic: kana, CJK ideographs, and the fullwidth forms."""
    code = ord(char)
    return (0x3000 <= code <= 0x30FF or 0x3400 <= code <= 0x4DBF
            or 0x4E00 <= code <= 0x9FFF or 0xFF00 <= code <= 0xFF60)


def _script_runs(text: str) -> list[tuple[str, bool]]:
    """`text` split into maximal (run, is_full_width) stretches.

    Each run is written with the font whose ADVANCES match it. PyMuPDF writes every glyph from
    `msgothic.ttc` at 0.5 em -- right for that font's half-width Latin, exactly half of right for
    full-width CJK (measured: 0.588 width ratio against ezdxf's ink on every Japanese string) --
    while its built-in CID font gets full-width right and carries proportional Latin.
    """
    runs: list[tuple[str, bool]] = []
    for char in text:
        wide = _is_full_width(char)
        if runs and runs[-1][1] == wide:
            runs[-1] = (runs[-1][0] + char, wide)
        else:
            runs.append((char, wide))
    return runs


def _lineweight_settings(doc: Any) -> dict[str, Any]:
    """Honour `$LWDISPLAY`, which ezdxf's drawing add-on ignores.

    Lineweight is a *plotting* property — how thick the pen is on paper — and `$LWDISPLAY` is the
    drawing's own statement about whether it should be shown at all. **It is 0 across this
    corpus**, so a CAD viewer, a plot preview and `renderEntities.ts` all draw hairlines;
    `renderEntities` says so directly ("the hairline case, and the only one this corpus
    exercises since `$LWDISPLAY` is 0").

    ezdxf has **no reference to `$LWDISPLAY` anywhere in `addons/drawing`**. It applies
    `LineweightPolicy.ABSOLUTE` unconditionally, so the report came out carrying the DXF's real
    0.25 / 0.50 / 1.00 mm pen weights — measured as 0.72 pt and 1.00 pt strokes — against a canvas
    drawing every one of them as a hairline. Same sheet, visibly heavier on paper.

    `renderEntities.ts` had already chosen this side of the argument for the canvas and left a
    warning saying so: *"Matching the live CAD viewer beats matching the bitmap here, because the
    bitmap is only a stand-in for it."* The report is not a stand-in for anything, and it is the
    copy that gets printed and signed.

    ⚠ When `$LWDISPLAY` IS set, the weights are honoured — this returns ezdxf's own defaults and
    the drawing gets the pen widths it asked for.
    """
    if doc.header.get("$LWDISPLAY", 0):
        return {}

    # ⚠ **NOT `lineweight_scaling: 0.0`**, which is what this returned until 2026-08-25.
    #
    # That is `LineweightPolicy`'s own recipe for a constant width, and it works by collapsing
    # every stroke onto `min_lineweight`: the backend computes
    # `max(properties.lineweight * scaling, min_lineweight)`, so at scaling 0 the left term is
    # always 0 and **every per-entity lineweight is discarded before it is read**. One width for
    # the whole sheet, and no override can change that — `_pen_override` would be silently inert.
    #
    # Scaling by points-per-mm instead makes `properties.lineweight` mean exactly what it holds
    # (millimetres) and lets the floor sit under the thinnest pen rather than on top of every pen.
    # `_pen_override` then assigns the width per entity.
    #
    # Inert for part geometry by construction: 0.13 mm x 72/25.4 = 0.3685 pt, the same stroke the
    # collapse produced.
    return {
        "lineweight_scaling": _LINEWEIGHT_PT_PER_MM,
        "min_lineweight": _DIMENSION_HAIRLINE_MM * _LINEWEIGHT_PT_PER_MM,
    }


def _annotation_aware_frontend(frontend_class: Any,
                               deferred_text: set[str] | None = None) -> Any:
    """`Frontend` that knows whether the entity it is drawing came out of a DIMENSION.

    ⚠ **Testing `entity.dxftype()` alone does not work, and fails in the direction that looks
    like the feature is simply off.** A DIMENSION keeps its lines, arrowheads and text in an
    anonymous block, and `draw_composite_entity` renders them through
    `draw_entities(entity.virtual_entities(...))` — which **re-resolves properties per child**,
    so the override is called again for each one as a plain `LINE` or `SOLID`. The first attempt
    at this thinned the 12 DIMENSION entities and then immediately reset every line they are made
    of back to the part pen, and the output PDF came out with exactly one stroke width, as
    before. Measured, not assumed: `get_drawings()` reported `0.3685 pt x391` and nothing else.

    Neither is the child's origin recoverable inside the override. `entity.dxf.owner` is unset on
    a virtual entity and `properties.handle` — which is how `render_audit.record_ground_truth`
    attributes recordings — is **not yet populated** at override time; it is filled further down
    the pipeline. Both were measured before settling on this.

    So the state is tracked where it is actually known: around the composite call itself.
    """
    class AnnotationAwareFrontend(frontend_class):  # type: ignore[misc, valid-type]
        in_annotation = False
        composite_handle: str | None = None

        def draw_composite_entity(self, entity: Any, properties: Any) -> None:
            # The handle is tracked here for the same reason `in_annotation` is: this is the one
            # place a child's parent is known. A DIMENSION's text is an MTEXT inside its
            # anonymous block, and by the time it reaches `draw_mtext_entity` nothing on it says
            # which dimension it belongs to.
            previous_handle = self.composite_handle
            self.composite_handle = getattr(entity.dxf, "handle", None)
            previous = self.in_annotation
            if entity.dxftype() in _ANNOTATION_TYPES:
                self.in_annotation = True
            try:
                super().draw_composite_entity(entity, properties)
            finally:
                self.in_annotation = previous
                self.composite_handle = previous_handle

        def _layer_covers(self, entity: Any, raw: str) -> bool:
            """True when the text layer will draw this string, so ezdxf must not.

            ⚠ **The two halves of that sentence have to stay one decision.** Both drawn is every
            character double-struck in two typefaces; neither is a string missing from the sheet.
            This method is the decision, and the handle it records is how `_text_items` learns
            the other half of it.
            """
            if deferred_text is None:
                return False                        # TextSource.OUTLINES: ezdxf draws it all
            if any(code in raw for code in _UNREPRODUCIBLE_MTEXT):
                handle = self.composite_handle or getattr(entity.dxf, "handle", None)
                if handle:
                    deferred_text.add(handle)
                return False
            return True

        def draw_mtext_entity(self, entity: Any, properties: Any) -> None:
            if self._layer_covers(entity, getattr(entity, "text", "") or ""):
                return
            super().draw_mtext_entity(entity, properties)

        def draw_text_entity(self, entity: Any, properties: Any) -> None:
            if self._layer_covers(entity, getattr(entity.dxf, "text", "") or ""):
                return
            super().draw_text_entity(entity, properties)

    return AnnotationAwareFrontend


def _pen_override(frontend: Any, hairline: bool):
    """A property-override that gives annotation ink a thinner pen than the part it measures.

    `push_property_override_function` is the documented seam for this; the alternative was a
    second render pass, which for a paper-space sheet means re-deriving the VIEWPORT transform
    and getting a second chance to get it wrong.

    `hairline` follows `_lineweight_settings`: when the drawing says not to display lineweights
    every stroke is *assigned* a width, and when it does say to, the drawing's own weights are
    kept and annotation is scaled down relative to them.
    """
    def override(entity: Any, properties: Any) -> None:
        thin = entity.dxftype() in _ANNOTATION_TYPES or frontend.in_annotation
        if hairline:
            properties.lineweight = _DIMENSION_HAIRLINE_MM if thin else _HAIRLINE_MM
        elif thin:
            properties.lineweight = float(properties.lineweight) * _DIMENSION_WEIGHT_RATIO

    return override


def _shrink_text_to_fit(doc: Any) -> int:
    """Scale every string down by `CAD_TEXT_FIT_SCALE`, the way the canvas does at draw time.

    ezdxf's `Configuration` has no text-scale knob, so the height is changed on the document
    itself before rendering. `dxf_background_renderer` already mutates a loaded document this way
    for its colour swap, so this is the established shape rather than a new one.

    Walks `entitydb` rather than the layout, because a DIMENSION keeps its drawable text in an
    anonymous geometry block — the layout iteration would miss exactly the strings that sit
    tightest against their dimension lines.

    ⚠ MTEXT scales through `char_height` and keeps its column `width`, so a string that ezdxf
    was wrapping gets *closer* to the canvas's single line, not further from it.
    """
    scaled = 0
    for entity in doc.entitydb.values():
        dxftype = entity.dxftype() if hasattr(entity, "dxftype") else ""
        attribute = {"TEXT": "height", "ATTRIB": "height", "ATTDEF": "height",
                     "MTEXT": "char_height"}.get(dxftype)
        if not attribute:
            continue
        try:
            current = float(getattr(entity.dxf, attribute))
        except (AttributeError, TypeError, ValueError):
            continue
        if current > 0:
            setattr(entity.dxf, attribute, current * CAD_TEXT_FIT_SCALE)
            scaled += 1
    return scaled


def _render_geometry(
    dxf_path: Path, page: PageSpec, text_source: TextSource = TextSource.OUTLINES,
) -> tuple[bytes, Any, float, float, frozenset[str]]:
    """The vector geometry pass.

    Returns (pdf_bytes, transData, dpi, page_height_pt, handles_ezdxf_drew_the_text_for).

    ⚠ Drawing the text is **90-98% of this function's cost**, not a detail. See `TextSource`.

    Under `LAYER` this still draws a handful of strings — the ones `_UNREPRODUCIBLE_MTEXT`
    names — and the last element of the tuple says which, so `_text_items` can skip exactly
    those and no others.
    """
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import (
        BackgroundPolicy,
        ColorPolicy,
        Configuration,
        TextPolicy,
    )
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from .dxf_render_setup import load_and_transcode, select_render_layout

    # `configure_cad_fonts` must still run -- it scans C:\Windows\Fonts into ezdxf's font
    # manager, which is what lets the name below resolve at all. Its GLOBAL substitution is then
    # bypassed: `load_and_transcode` takes the face as a parameter and writes it onto this
    # document's own text styles, so the export can render Mincho without changing the face the
    # ingestion raster uses. That separation is not cosmetic -- the raster feeds `render_bounds`,
    # and every zone template stores its boxes as fractions of it.
    fallback_font = _configure_fonts_once()
    report_font, _ = resolve_report_font()
    doc = load_and_transcode(dxf_path, report_font or fallback_font)
    _shrink_text_to_fit(doc)
    layout = select_render_layout(doc)

    # OO API, never `pyplot` -- see the threading note in the module docstring.
    figure = Figure(figsize=page.size_inches)
    FigureCanvasAgg(figure)
    axes = figure.add_axes(page.content_fractions)
    axes.set_axis_off()
    axes.set_aspect("equal", "box")

    context = RenderContext(doc)
    context.set_current_layout(layout)
    # The sheet prints BLACK, and only the review marks carry colour.
    #
    # ezdxf otherwise honours each entity's ACI colour, which is tuned for a CAD screen: this
    # corpus draws in yellow, cyan, orange and red. On a dark canvas those are legible and
    # meaningful; on white paper they are washed out to the point of being hard to read, and a
    # printed report is the one place the sheet is guaranteed to be on white.
    #
    # Colour then means exactly one thing in this document — a marker's status. Anything coloured
    # is something a reviewer flagged. `_draw_markers` paints after this pass, in PyMuPDF, so it
    # is untouched by the policy.
    #
    # ⚠ NOT `MONOCHROME_LIGHT_BG`, which maps to grey in [0%, 70%] and would print the thin
    # construction linework at a grey no laser holds cleanly.
    pen = _lineweight_settings(doc)
    deferred: set[str] | None = None if text_source is TextSource.OUTLINES else set()
    frontend = _annotation_aware_frontend(Frontend, deferred)(
        context, MatplotlibBackend(axes),
        config=Configuration(
            background_policy=BackgroundPolicy.OFF,
            color_policy=ColorPolicy.BLACK,
            # Always FILLING. Which strings are actually drawn is decided per entity by the
            # frontend below, because `TextPolicy` has no setting between "all" and "none" and
            # this sheet needs a handful of strings from ezdxf and the rest from the layer.
            text_policy=TextPolicy.FILLING,
            **pen,
        ),
    )
    # Dimensions and leaders take a thinner pen than the part they measure. Pushed rather than
    # baked into the config because a `Configuration` has one lineweight rule for the whole sheet.
    frontend.push_property_override_function(_pen_override(frontend, hairline=bool(pen)))
    frontend.draw_layout(layout, finalize=True)

    # `MatplotlibBackend.finalize()` REPLACES the figure size with the drawing's aspect ratio --
    # 11.69x8.27in becomes 6.788x4.8 -- re-homes the axes at [0,0,1,1], and switches the aspect
    # to `adjustable='datalim'`. All three have to be re-asserted or the "A4 page with a margin"
    # is none of those things.
    #
    # ⚠ The aspect one is the quiet one. Left at 'datalim', matplotlib satisfies equal aspect by
    # WIDENING the view limits instead of shrinking the axes box, so the crop below is discarded
    # with only a warning on stderr ("Ignoring fixed x limits ...") and the sheet prints with the
    # dead space still around it.
    figure.set_size_inches(*page.size_inches)
    axes.set_position(page.content_fractions)
    axes.set_aspect("equal", "box")

    # Crop to the ink. `dataLim` is the true extent of what was drawn; the autoscaled view limits
    # carry matplotlib's 5%-per-side margins, which is the dead space `exportFit.ts` exists to
    # strip out of the current report. Neither is `render_bounds`, and none of this touches it.
    bounds = axes.dataLim
    if bounds.width > 0 and bounds.height > 0:
        axes.set_xlim(bounds.x0, bounds.x1)
        axes.set_ylim(bounds.y0, bounds.y1)

    # `set_aspect('equal','box')` defers the box adjustment to draw time. Read `transData` before
    # this and it is stale by the sheet's aspect ratio -- measured 1.4135 -- which scales every
    # glyph in the text layer by exactly that, silently.
    figure.canvas.draw()

    buffer = io.BytesIO()
    figure.savefig(buffer, format="pdf")
    return (buffer.getvalue(), axes.transData, float(figure.dpi),
            page.height_mm / MM_PER_INCH * PT_PER_INCH, frozenset(deferred or ()))


def _write_text_layer(page_obj: Any, items: Sequence[_TextItem], to_pdf, pt_per_unit: float,
                      fitz: Any, font_path: str | None, font_name: str | None = None,
                      visible: bool = False) -> int:
    """Overlay `items` as selectable text. Returns how many were written.

    `visible=False` writes render mode 3 -- an invisible layer over glyphs ezdxf drew.
    `visible=True` writes render mode 0, making THIS the text on the page. See `TextSource`.
    """
    from ezdxf.fonts import fonts as ezdxf_fonts

    # The SAME face the geometry pass rendered, or the invisible rects drift from the glyphs
    # they are meant to select. `CANVAS_FONT` is deliberately NOT used here: it is the harness's
    # reference face and moving it would move `tools/render_audit.py`'s baselines.
    face = font_name or CANVAS_FONT
    metrics = ezdxf_fonts.make_font(face, cap_height=1.0)
    cap_ratio = cap_height_ratio(face)
    font_wide = fitz.Font("japan")
    font_narrow = fitz.Font(fontfile=font_path) if font_path else font_wide

    written = 0
    for item in items:
        font_size = item.height / cap_ratio * pt_per_unit
        if font_size < _MIN_FONT_PT:
            continue

        radians = math.radians(item.rotation)
        ux, uy = math.cos(radians), math.sin(radians)      # advance direction
        vx, vy = -uy, ux                                   # toward the ascenders
        width = metrics.text_width(item.text) * item.height * item.width_factor

        # Insert point -> baseline origin, undoing the attachment-point offset along the string's
        # own axes. `anchor_fy` is a fraction of CAP height, which is what ezdxf anchors on.
        ox = item.x - width * item.anchor_fx * ux - item.height * item.anchor_fy * vx
        oy = item.y - width * item.anchor_fx * uy - item.height * item.anchor_fy * vy

        # `width_factor` scales glyph ADVANCES, so it rides the text matrix. It cannot ride the
        # glyph positions: `TextWriter` re-lays a run out from its own advances and ignores
        # per-glyph points (measured: a uniform 2.54 pt step where 6.01 was asked for).
        matrix = fitz.Matrix(item.width_factor, 0, 0, 1, 0, 0)
        if abs(item.rotation) > 1e-6:
            # ⚠ `Matrix(ux, -uy, uy, ux)` -- the form this reads as -- rotates the string the
            # WRONG WAY, by -rotation. Measured with `TextWriter.append` at a known point: asked
            # for +90 deg it lays the glyphs DOWN the page, where CAD's counter-clockwise +90
            # must read bottom-to-top. `morph` applies its matrix in the opposite sense to the
            # one the operand order suggests, so the transpose is what expresses the rotation.
            #
            # The cost of getting it backwards is a string rotated to a plausible angle and
            # displaced by its own length -- measured at |d| median 6.9 drawing units over this
            # corpus's 72 rotated strings, against 0.10 for unrotated ones. It went unnoticed
            # because it is invisible under `TextSource.OUTLINES` (a selection rect in the wrong
            # place) and because `tools/text_layer_audit.py` SKIPS every rotated string.
            matrix = matrix * fitz.Matrix(ux, uy, -uy, ux, 0, 0)

        advance = 0.0
        for run, wide in _script_runs(item.text):
            px, py = to_pdf(ox + advance * ux, oy + advance * uy)
            origin = fitz.Point(px, py)
            writer = fitz.TextWriter(page_obj.rect)
            writer.append(origin, run, font=font_wide if wide else font_narrow,
                          fontsize=font_size)
            # ⚠ `color` is NOT optional, and its default is WHITE.
            #
            # This layer was invisible for its whole life (render mode 3), so the colour was
            # never painted and never checked. Turning it visible without this line produces a
            # page whose text extracts, searches and counts perfectly -- 2609 characters, every
            # `search_for` hit -- and shows nothing at all, because white ink on white paper is
            # not a rendering failure any assertion about the TEXT can see. Caught by
            # rasterising the page and looking at it.
            writer.write_text(page_obj, render_mode=0 if visible else 3,
                              color=_TEXT_INK, morph=(origin, matrix))
            advance += metrics.text_width(run) * item.height * item.width_factor
        written += 1

    return written


#: How opaque the neon dot is over the drawing beneath it. **`renderEntities.ts`'s own 0.55.**
#:
#: The canvas settled this and wrote down what it rejected on the way: *"The stroke gave it a hard
#: border that ink does not have; the gradient that replaced the stroke read as blur. What is
#: wanted is neither — one flat colour at partial opacity, so the mark sits over the value without
#: hiding it and without drawing an edge."* The report now paints the same mark.
#:
#: ⚠ This report briefly had a rimmed, glyphed badge at 0.45 — legible, and not what the app
#: draws. Owner's call on 2026-08-25 was to match the canvas, so the rim and the glyph came off
#: and the opacity moved to the canvas's number. Do not reintroduce the rim without moving
#: `renderEntities.ts` with it; that divergence is the thing this constant exists to prevent.
_BADGE_FILL_OPACITY = 0.55

#: MATCHED is a stroked tick on the canvas, not a dot, and the report follows.
#:
#: ⚠ **The proportions are `renderEntities.ts`'s, the SIZES are `MARK_PAINT.print`'s**, and mixing
#: them that way is deliberate rather than sloppy. The vertex ratios below are copied from the
#: canvas so the tick has the same shape; the stroke/rise/shift ratios come from the app's own
#: *print* row, which was derived by measuring against this sheet — "at the report's A4 capture
#: the drawing's own linework is a 0.42 mm hairline and its title-block text is about 2.5 mm
#: tall". The canvas ratio would put a 0.5x stroke on the tick, three times the weight of the
#: drawing under it. Colour is the canvas's; weight is paper's.
_TICK_STROKE_RATIO = 0.60 / 3.2
_TICK_RISE_RATIO = 1.8 / 3.2
_TICK_SHIFT_RATIO = 5.0 / 3.2

#: Half-width of the tick in points. The dot's own radius, scaled back so the two marks read as
#: the same size on the page rather than the tick reading as the louder status.
_TICK_SIZE_PT = 7.0 * 0.8

#: The one status the canvas draws as a tick rather than a dot.
_TICK_STATUS = "MATCHED"

def composited_badge_fill(fill: tuple[float, float, float]) -> tuple[float, float, float]:
    """The colour the eye actually meets: the neon at `_BADGE_FILL_OPACITY` over white paper.

    ⚠ **This is what any contrast decision has to be made against, not `MARKER_INK`.** A
    translucent wash over white is always LIGHTER than the ink that made it — `#ff2850` composites
    to luminance 0.71 against its own 0.35 — so reading contrast off the raw value answers a
    question about a badge that is not on the page. Getting this backwards puts a white glyph on a
    pale pink disc.

    White is the right ground to assume: the sheet is white, and where the dot does sit over
    linework it sits over a 0.13 mm hairline covering a few percent of it.
    """
    return tuple(1.0 - _BADGE_FILL_OPACITY * (1.0 - channel) for channel in fill)  # type: ignore[return-value]


def _draw_markers(page_obj: Any, markers: Sequence[SheetMarker], to_pdf, fitz: Any) -> None:
    """Paint the review marks as vector badges at their CAD coordinates."""
    for marker in markers:
        ink = MARKER_INK.get(marker.status) or MARKER_INK[_FALLBACK_STATUS]
        px, py = to_pdf(marker.x, marker.y)

        shape = page_obj.new_shape()
        if marker.status == _TICK_STATUS:
            # The canvas's own tick, vertex for vertex. Shifted right and lifted off the value so
            # the thing being confirmed stays readable underneath — the mark's coordinate is the
            # entity's bounding-box CENTRE, which on one line of text is the middle of the glyphs.
            size = _TICK_SIZE_PT
            cx = px + size * _TICK_SHIFT_RATIO
            cy = py - size * _TICK_RISE_RATIO
            shape.draw_polyline([
                fitz.Point(cx - size * 0.8, cy - size * 0.1),
                fitz.Point(cx - size * 0.1, cy + size * 0.6),
                fitz.Point(cx + size * 0.9, cy - size * 0.7),
            ])
            # Round cap and join, as on the canvas: a tick with mitred ends reads as an arrow.
            shape.finish(color=ink, width=size * _TICK_STROKE_RATIO, closePath=False,
                         lineCap=1, lineJoin=1)
        else:
            # A plain translucent dot. No outline, no gradient, no glyph — `renderEntities.ts`
            # tried the first two and rejected both, and the third was never on the canvas.
            shape.draw_circle(fitz.Point(px, py), _BADGE_RADIUS_PT)
            shape.finish(fill=ink, width=0, color=None, fill_opacity=_BADGE_FILL_OPACITY)
        shape.commit()

        if marker.label:
            # The label sits on the WHITE SHEET, not on the mark, so it takes the dark ink from
            # `MARKER_EDGE`. In neon it would be the one piece of marker text nobody can read —
            # and unlike the mark itself, a label carries meaning that hue cannot.
            edge = MARKER_EDGE.get(marker.status) or MARKER_EDGE[_FALLBACK_STATUS]
            page_obj.insert_text(
                fitz.Point(px + _BADGE_RADIUS_PT * 1.35, py + _BADGE_RADIUS_PT * 0.40),
                marker.label, fontname="helv", fontsize=_BADGE_RADIUS_PT * 0.95, color=edge,
            )


def render_vector_sheet(
    dxf_path: Path,
    *,
    entities: Sequence[dict[str, Any]] | None = None,
    markers: Sequence[SheetMarker] = (),
    page: PageSpec = A4_LANDSCAPE,
    text_source: TextSource = TextSource.OUTLINES,
) -> bytes:
    """One drawing, as a single-page vector PDF with a searchable text layer.

    `entities` should be the drawing's **stored** `ExtractedEntity` payload — the same records
    the canvas drew and the checklist quotes. Passing `None` re-parses the DXF, which is right
    for an offline or tooling caller and wrong for the report: a drawing at a stale
    `EXTRACTION_SCHEMA_VERSION` would then get a text layer its own canvas never had.

    `markers` are in paper-space CAD coordinates, Y-up. See `SheetMarker`.

    `text_source` decides which of the two copies of the text is visible, and is the export's
    single largest cost — see `TextSource`. It is a REQUEST: `_resolve_text_source` downgrades
    it to `OUTLINES` for a payload that cannot place every string, so asking for `LAYER` is
    always safe and sometimes slow.
    """
    import fitz

    from ...core.security import validate_sandboxed_path
    from .dxf_render_setup import JAPANESE_FONT_CANDIDATES

    # Validate ONCE, up front, covering both passes.
    #
    # `DXFParser.parse_file` sandboxes its own argument, so the `entities is None` path was
    # already guarded — but `load_and_transcode` below is not, so a caller who supplied
    # `entities` could have had arbitrary DXF geometry rendered onto the page. Two passes over
    # one file that disagree about whether the file is allowed is the hole, not either pass.
    dxf_path = validate_sandboxed_path(dxf_path)

    if entities is None:
        from ..cad.dxf_parser import DXFParser

        entities = DXFParser().parse_file(dxf_path)[0]

    # Resolved BEFORE the geometry pass, because that pass is where the choice is spent, and
    # re-deciding afterwards would mean re-rendering.
    source = _resolve_text_source(text_source, entities)

    geometry_pdf, transform, dpi, page_height_pt, drawn = _render_geometry(
        dxf_path, page, source)
    # AFTER the render, because only the render knows which strings it could not leave to us.
    items = _text_items(entities, skip_handles=drawn)
    points_per_px = PT_PER_INCH / dpi

    def to_pdf(x: float, y: float) -> tuple[float, float]:
        px, py = transform.transform((x, y))
        return px * points_per_px, page_height_pt - py * points_per_px   # y-up -> y-down

    origin_px = transform.transform((0.0, 0.0))
    pt_per_unit = (transform.transform((100.0, 0.0))[0] - origin_px[0]) / 100.0 * points_per_px

    document = fitz.open(stream=geometry_pdf, filetype="pdf")
    try:
        page_obj = document[0]
        report_font, report_font_path = resolve_report_font()
        font_path = report_font_path or next(
            (c for c in JAPANESE_FONT_CANDIDATES if Path(c).exists()), None)
        written = _write_text_layer(
            page_obj, items, to_pdf, pt_per_unit, fitz, font_path, report_font,
            visible=source is TextSource.LAYER)
        _draw_markers(page_obj, markers, to_pdf, fitz)

        # Embedding msgothic.ttc whole costs ~9 MB; subsetting brings the page to ~0.5 MB and is
        # measurably innocent of the advance-width defect above (checked with and without).
        document.subset_fonts(verbose=False)
        out = document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()

    logger.info(
        "Vector sheet rendered: %s -- %d strings searchable (%s), %d drawn by ezdxf, "
        "%d markers, %.2f MB",
        dxf_path.name, written, source.value, len(drawn), len(markers), len(out) / 1e6,
    )
    return out
