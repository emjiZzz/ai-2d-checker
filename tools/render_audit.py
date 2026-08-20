#!/usr/bin/env python
"""Render-fidelity harness: what the vector canvas draws vs what ezdxf draws.

## Why this exists

The 2D review canvas can draw a sheet two ways: a downsampled PNG produced by ezdxf
(`renderMode: 'raster'`) or real vectors from the extracted entity payload
(`renderMode: 'vector'`). The raster is the ground truth -- it comes from ezdxf's own
`Frontend`, so it cannot be missing anything -- and the vector path is the one with bugs.

Judging the vector path by eye does not work. It has been tried twice, and both times a
confident diagnosis was wrong in a way that cost a full re-ingestion cycle:

  * The first switch to `'vector'` shipped green on 278 tests and silently deleted every
    dimension from the drawing, because nothing in any suite asks "does the sheet look right".
  * The follow-up fixed the count to a healthy 500/518 and the sheet was *still* wrong, because
    an entity count says nothing about whether the entity is in the right place or the right
    size. Two further defects (dimension text drawn horizontally, elliptical arcs swept
    backwards) were only found by rendering the vectors beside the raster.

See `docs/vault/06 - Gotchas & Debugging Lessons/Gotcha - A Blurry CAD Canvas and Its Four
Causes.md`, which records both rounds and ends by naming this harness as the thing that should
have been built first.

## What it reports

1. **Census** -- reproduces the canvas HUD's `drawn/total`, classifying every extracted entity
   through a port of the `renderEntities.ts` branch table. Answers "is anything missing".
   On M745221N01 the healthy number is 497/518: 518 minus 6 `layer` records and 12 `block`
   containers (never drawable) minus 3 clipped model-space entities. If this moves, geometry
   was lost.

2. **Text placement oracle** -- the reason to build this at all. Renders the same layout
   through `ezdxf.addons.drawing.Frontend` into a `Recorder` backend, which yields the exact
   placed ink box for every entity, keyed by handle. Then asks where the canvas renderer would
   put the same string under the rules it currently applies, and reports the delta.

   Three defects overlapped here -- one moved text, one narrowed it, one shrank it -- and they
   partly cancelled: `width_ratio` sat at a healthy-looking 0.954 while half the sheet was in
   the wrong place. That is why this is measured rather than eyeballed. Per string:

   * `dx`, `dy`     -- drawing units between the insert point and the point inside ezdxf's ink
                       box that the attachment point implies. Needs no width prediction, so it
                       is an exact test of the anchor. Was max 33.3 (a full string width) when
                       the renderer drew everything left/alphabetic.
   * `width_ratio`  -- predicted advance width / ezdxf's ink width. Tests that `\\W` is applied
                       and that the DXF **cap** height is not being passed to CSS `font-size`
                       as an **em** size. Settles just above 1.0; the excess is glyph side
                       bearing, which is the floor of an advance-vs-ink comparison.

   Both must converge on 0 and ~1.0. Rotated, wrapped and off-axis strings are excluded from
   the statistics and counted as their own defects -- their world-space box is not comparable
   to a single horizontal line.

## Usage

    services/backend/.venv/Scripts/python.exe tools/render_audit.py <dxf> [--top N] [--json OUT]

Run from the repo root; `pyproject.toml` sets `pythonpath = ["."]`. No backend, no MongoDB.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.backend.infrastructure.cad.dxf_parser import DXFParser  # noqa: E402
from services.backend.infrastructure.rendering.dxf_render_setup import (  # noqa: E402
    configure_cad_fonts,
    load_and_transcode,
    select_render_layout,
)
from services.backend.infrastructure.rendering.geometry_serializer import (  # noqa: E402
    GeometrySerializer,
)

# ---------------------------------------------------------------------------
# The renderEntities.ts branch table, ported.
#
# Deliberately declarative and deliberately shallow: this answers "would the canvas draw this,
# and from which geometry key", NOT "what pixels result". A faithful reimplementation of the
# renderer in Python would be a second renderer to keep in sync, which is a worse problem than
# the one being solved. Final acceptance is still the running app.
#
# Keep in step with `apps/desktop/src/components/review/renderEntities.ts`.
# ---------------------------------------------------------------------------

#: entity_type -> the geometry keys the renderer accepts, in the order it tries them.
BRANCH_TABLE: dict[str, tuple[str, ...]] = {
    "text": ("location", "insert"),
    "line": ("start",),            # also needs `end`; checked below
    "circle": ("center", "location"),
    "arc": ("center", "location"),
    "polyline": ("vertices", "points"),
    "ellipse": ("vertices", "points"),
    "spline": ("vertices", "points"),
    "leader": ("vertices", "points"),
    "multileader": ("vertices", "points"),
    "dimension": ("render_paths", "render_fills"),  # or a resolved measurement string
}

#: Extracted so the payload is addressable, never drawn. `layer` is a layer-table record and
#: `block` is an INSERT container whose children are exploded and drawn separately. Both are in
#: the serializer payload, so the HUD's denominator counts entities that can never be drawn.
NON_DRAWABLE_TYPES = frozenset({"layer", "block", "xref"})


#: Mirrors `SECTION_DESIGNATION_RE` / `LONE_LETTER_RE` in
#: `apps/desktop/src/components/review/sectionCallouts.ts`. Same letter both sides.
_SECTION_DESIGNATION_RE = re.compile(r"^([A-Za-z])\s*[-‐‑–—ー－]\s*\1$", re.IGNORECASE)
_LONE_LETTER_RE = re.compile(r"^[A-Za-z]$")
#: `viewport_transform.NO_VIEWPORT` — the projector never resolved this entity to a viewport,
#: i.e. it is native paper-space sheet furniture (frame, title block, border grid labels).
_NO_VIEWPORT = -1


def _canvas_text(entity: dict[str, Any]) -> str:
    """The string the canvas would paint, read in `renderEntities`' own field order."""
    geo = entity.get("geometry") or {}
    props = entity.get("properties") or {}
    raw = str(geo.get("text") or geo.get("content") or props.get("text") or "")
    # The `cleanCadText` subset that can affect a match: MTEXT braces and formatting codes.
    raw = re.sub(r"\\[A-Za-z][^;]*;", "", raw.replace("{", "").replace("}", ""))
    return unicodedata.normalize("NFKC", raw).strip()


#: Coincidence tolerance in projected paper units — see `COINCIDENT` in `sectionCallouts.ts`.
_COINCIDENT = 1.0
_APPARATUS_TYPES = {"leader", "polyline", "multileader"}
_MAX_APPARATUS_VERTICES = 3


def _through_viewport(ent: dict[str, Any]) -> bool:
    try:
        return int((ent.get("properties") or {}).get("viewport_index")) > _NO_VIEWPORT
    except (TypeError, ValueError):
        return False


def _line_ends(ent: dict[str, Any]) -> list[tuple[float, float]]:
    geo = ent.get("geometry") or {}
    out = []
    for key in ("start", "end"):
        p = geo.get(key)
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            out.append((float(p[0]), float(p[1])))
    return out


def _vertex_list(ent: dict[str, Any]) -> list[tuple[float, float]]:
    geo = ent.get("geometry") or {}
    raw = geo.get("vertices") or geo.get("points") or []
    return [
        (float(p[0]), float(p[1]))
        for p in raw
        if isinstance(p, (list, tuple)) and len(p) >= 2
    ]


def _cut_plane_lines(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The sheet's cut-plane lines: `CENTER` lines in the minority colour.

    Port of `findCutPlaneLines` in `sectionCallouts.ts` — see there for why colour rather than
    position, and for the corpus measurement behind it.
    """
    centre = [
        e
        for e in entities
        if (e.get("entity_type") or "").lower() == "line"
        and _through_viewport(e)
        and "CENTER" in str((e.get("properties") or {}).get("linetype", "")).upper()
    ]
    if len(centre) < 2:
        return []

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in centre:
        buckets[str((e.get("properties") or {}).get("color", "unknown"))].append(e)
    if len(buckets) < 2:
        return []

    counts = sorted((len(g) for g in buckets.values()), reverse=True)
    if counts[0] == counts[1]:
        return []

    return [e for g in buckets.values() if len(g) < counts[0] for e in g]


def section_callout_ids(entities: list[dict[str, Any]]) -> set[int]:
    """`id()`s of the section-view identifiers the canvas refuses to draw.

    Port of `findSectionCallouts` in `sectionCallouts.ts`; the two must agree or this harness
    stops reproducing the HUD's `drawn/total`, which is the only thing it is for. Both gates are
    reproduced: a lone letter qualifies only alongside a matching `X-X` designation, and only
    text projected through a viewport is eligible at all, so the sheet frame's grid labels —
    which are lone letters too — are never swept up.
    """
    candidates: list[tuple[dict[str, Any], str]] = []
    for ent in entities:
        if (ent.get("entity_type") or "").lower() != "text":
            continue
        props = ent.get("properties") or {}
        try:
            vp = int(props.get("viewport_index"))
        except (TypeError, ValueError):
            continue
        if vp <= _NO_VIEWPORT:
            continue
        text = _canvas_text(ent)
        if text:
            candidates.append((ent, text))

    letters = {
        m.group(1).upper()
        for _, text in candidates
        if (m := _SECTION_DESIGNATION_RE.match(text))
    }
    if not letters:
        return set()

    found = {
        id(ent)
        for ent, text in candidates
        if _SECTION_DESIGNATION_RE.match(text)
        or (_LONE_LETTER_RE.match(text) and text.upper() in letters)
    }

    cut_lines = _cut_plane_lines(entities)
    if not cut_lines:
        return found
    found.update(id(e) for e in cut_lines)

    vertices = [p for e in cut_lines for p in _line_ends(e)]
    for ent in entities:
        if (ent.get("entity_type") or "").lower() not in _APPARATUS_TYPES:
            continue
        if not _through_viewport(ent):
            continue
        verts = _vertex_list(ent)
        if not 2 <= len(verts) <= _MAX_APPARATUS_VERTICES:
            continue
        anchors = list(verts) + [
            ((verts[0][0] + verts[-1][0]) / 2, (verts[0][1] + verts[-1][1]) / 2)
        ]
        if any(math.dist(a, v) <= _COINCIDENT for a in anchors for v in vertices):
            found.add(id(ent))

    return found


def classify(entity: dict[str, Any]) -> str:
    """Which bucket this entity lands in when `renderEntities` walks the payload."""
    etype = (entity.get("entity_type") or "").lower()
    props = entity.get("properties") or {}
    geo = entity.get("geometry") or {}

    if etype in NON_DRAWABLE_TYPES:
        return "not-drawable"

    # Model-space geometry that fell outside every paper-space viewport window. CAD clips it and
    # the ezdxf raster never draws it, so the renderer skips it too -- correctly.
    if props.get("outside_viewport"):
        return "outside-viewport"

    if not geo:
        return "no-geometry"

    keys = BRANCH_TABLE.get(etype)
    if keys is None:
        return "no-branch"

    if etype == "line":
        return "drawn" if (geo.get("start") and geo.get("end")) else "empty-geometry"

    if etype == "dimension":
        has_paths = bool(geo.get("render_paths")) or bool(geo.get("render_fills"))
        raw = str(props.get("text") or "")
        has_text = bool(raw) and "<>" not in raw
        return "drawn" if (has_paths or has_text) else "empty-geometry"

    if etype in ("polyline", "ellipse", "spline", "leader", "multileader"):
        pts = next((geo[k] for k in keys if geo.get(k)), None)
        # `if (rawVertices.length < 2) return;`
        return "drawn" if pts and len(pts) >= 2 else "empty-geometry"

    return "drawn" if any(geo.get(k) for k in keys) else "empty-geometry"


# ---------------------------------------------------------------------------
# Ground truth: ezdxf's own placed ink, keyed by entity handle.
# ---------------------------------------------------------------------------


def _walk(entity: Any, depth: int = 0):
    """Every entity the extractor sees, INSERTs exploded -- mirrors `dxf_parser.process_entity`."""
    yield entity
    if entity.dxftype() == "INSERT" and depth < 6:
        try:
            for child in entity.virtual_entities():
                yield from _walk(child, depth + 1)
        except Exception:
            pass


def record_ground_truth(dxf_path: Path) -> tuple[dict[str, tuple[float, float, float, float]], dict[str, dict[str, Any]], str]:
    """Ink boxes and true text facts per entity handle, straight from ezdxf.

    Returns `(boxes, text_facts, layout_name)`.

    `boxes` is the authoritative placed ink extent of each entity: the `Recorder` backend
    captures every primitive the frontend emits, tagged with the source entity's handle --
    including glyph outlines, since TTF text is rendered as paths. Coordinates are the same
    paper space the extractor projects into (model-space geometry arrives here through the
    VIEWPORT, exactly as it does on the extraction side).

    `text_facts` carries what the DXF really says about each string, independent of what
    extraction managed to record. `rotation` in particular is read via `MText.get_rotation()`
    rather than `dxf.rotation`: MTEXT keeps its orientation in the `text_direction` vector, and
    `dxf.rotation` reads 0 for a string that is actually vertical. Without this the harness
    would compare a horizontal predicted box against a vertical measured one and report a
    meaningless ratio instead of naming the defect.
    """
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.recorder import Recorder

    jp_font_filename = configure_cad_fonts(configure_matplotlib=False)
    doc = load_and_transcode(dxf_path, jp_font_filename)
    layout = select_render_layout(doc)

    text_facts: dict[str, dict[str, Any]] = {}
    for top in doc.layouts:
        for entity in top:
            for ent in _walk(entity):
                if ent.dxftype() not in ("MTEXT", "TEXT", "ATTRIB", "ATTDEF"):
                    continue
                handle = getattr(ent.dxf, "handle", "") or ""
                if not handle or handle in text_facts:
                    continue
                if ent.dxftype() == "MTEXT":
                    try:
                        rotation = float(ent.get_rotation())
                    except Exception:
                        rotation = float(ent.dxf.get("rotation", 0.0) or 0.0)
                    column_width = float(ent.dxf.get("width", 0.0) or 0.0)
                else:
                    rotation = float(ent.dxf.get("rotation", 0.0) or 0.0)
                    column_width = 0.0
                text_facts[handle] = {
                    "true_rotation": round(rotation, 3),
                    "column_width": round(column_width, 4),
                }

    ctx = RenderContext(doc)
    ctx.set_current_layout(layout)
    backend = Recorder()
    config = Configuration(
        background_policy=BackgroundPolicy.OFF,
        color_policy=ColorPolicy.COLOR_SWAP_BW,
    )
    Frontend(ctx, backend, config=config).draw_layout(layout, finalize=True)

    boxes: dict[str, list[float]] = {}
    records: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
    for record, props in backend.player().recordings():
        handle = props.handle
        if not handle:
            continue
        bbox = record.bbox()
        if not bbox.has_data:
            continue
        lo, hi = bbox.extmin, bbox.extmax
        records[handle].append((lo.x, lo.y, hi.x, hi.y))
        cur = boxes.get(handle)
        if cur is None:
            boxes[handle] = [lo.x, lo.y, hi.x, hi.y]
        else:
            cur[0] = min(cur[0], lo.x)
            cur[1] = min(cur[1], lo.y)
            cur[2] = max(cur[2], hi.x)
            cur[3] = max(cur[3], hi.y)

    return (
        {h: (b[0], b[1], b[2], b[3]) for h, b in boxes.items()},
        dict(records),
        text_facts,
        layout.name,
    )


#: How far a no-handle string may sit from a candidate box, as a multiple of its text height,
#: before the match is rejected. A wrong match would report a small fake error, which is worse
#: than reporting the row as unmeasured.
PARENT_MATCH_TOLERANCE = 3.0


def cluster_text_records(
    boxes: list[tuple[float, float, float, float]],
) -> list[tuple[float, float, float, float]]:
    """Merge a parent INSERT's records into one box per rendered string.

    A wrapped MTEXT emits one record per LINE, so matching a string against a single record
    measures one line of it and reports the anchor as displaced by half the block. That is
    exactly what happened to the drawing title `ロールカセット 12"ミル`: ezdxf wraps it at its
    60.2-unit column and the oracle read `dy = -2.16` against the lower line alone.

    Merged on three conditions together, because no one of them is sufficient here:
      * similar box height -- the neighbouring `押エ板` sits at char height 6.55 against this
        string's 4.73 and their ink boxes overlap vertically by 0.6 units, so proximity alone
        would swallow it;
      * substantial horizontal overlap -- lines of one block share a column;
      * vertical centres within ~1.6 line heights.

    Zero-area records are the block's rule lines and are dropped, not clustered.
    """
    glyphs = [b for b in boxes if (b[2] - b[0]) > 1e-6 and (b[3] - b[1]) > 1e-6]
    merged: list[list[float]] = []

    for box in sorted(glyphs, key=lambda b: (-(b[3] - b[1]), b[0])):
        height = box[3] - box[1]
        for group in merged:
            group_height = group[3] - group[1]
            shorter = min(height, group_height)
            if shorter <= 0 or min(height, group_height) / max(height, group_height) < 0.75:
                continue
            overlap = min(box[2], group[2]) - max(box[0], group[0])
            if overlap < 0.5 * min(box[2] - box[0], group[2] - group[0]):
                continue
            if abs((box[1] + box[3]) / 2 - (group[1] + group[3]) / 2) > 1.6 * shorter:
                continue
            group[0] = min(group[0], box[0])
            group[1] = min(group[1], box[1])
            group[2] = max(group[2], box[2])
            group[3] = max(group[3], box[3])
            break
        else:
            merged.append(list(box))

    return [(g[0], g[1], g[2], g[3]) for g in merged]


def match_within_parent(
    insert: tuple[float, float],
    attachment_point: Any,
    rotation: float,
    height: float,
    candidates: list[tuple[float, float, float, float]],
    claimed: set[int],
) -> tuple[int, tuple[float, float, float, float]] | None:
    """Pick the ink box belonging to one child of an exploded INSERT.

    `virtual_entities()` copies carry no handle, so the 19 most prominent strings on this sheet
    -- the title-block values `45/221/24/0`, `M745221N01`, `FSRS2`, `押エ板`, the date, the
    material -- had nothing to join on and sat outside the oracle entirely. They are exactly the
    strings a reviewer looks at first, so "unmeasured" is not good enough.

    ezdxf tags an INSERT's children with the *parent's* handle, and emits one record per child,
    so the parent's record list is the candidate set. Matched on proximity to the anchor the
    attachment point implies, claiming each box so two strings cannot take the same one.
    Zero-area records are the block's rule lines, not glyphs.
    """
    best: tuple[float, int, tuple[float, float, float, float]] | None = None
    for index, box in enumerate(candidates):
        if index in claimed:
            continue
        if (box[2] - box[0]) <= 1e-6 or (box[3] - box[1]) <= 1e-6:
            continue
        reference = anchor_reference(box, attachment_point, rotation)
        if reference is None:
            continue
        distance = math.hypot(insert[0] - reference[0], insert[1] - reference[1])
        if best is None or distance < best[0]:
            best = (distance, index, box)

    if best is None or best[0] > max(height, 1e-6) * PARENT_MATCH_TOLERANCE:
        return None
    return best[1], best[2]


# ---------------------------------------------------------------------------
# Font metrics: the cap-height/em factor the canvas renderer is missing.
# ---------------------------------------------------------------------------

#: The canvas asks for these in order (see `renderEntities.ts`); the first is what Windows
#: resolves in practice and what the raster path substitutes for the SHX styles.
CANVAS_FONT = "msgothic.ttc"


def cap_height_ratio(font_name: str = CANVAS_FONT) -> float:
    """Cap height as a fraction of the em square.

    ezdxf scales glyphs so the DXF `height` lands on the CAP height; CSS `font: Npx` sets the EM
    size. Before the fix the canvas passed the DXF height straight to `font-size`, drawing every
    string at this fraction of its correct size -- measured as a flat 0.7617 across the sheet.
    `renderEntities.ts` now divides by the same ratio, measured in-browser from
    `TextMetrics.actualBoundingBoxAscent`.
    """
    from ezdxf.fonts import fonts

    # A font built at cap_height=1 measures widths in cap-height units. Latin glyphs in MS
    # Gothic are exactly half-width, so "MMMM" is 2 em; dividing gives em per cap unit.
    font = fonts.make_font(font_name, cap_height=1.0)
    em_in_cap_units = font.text_width("MMMM") / 2.0
    return 1.0 / em_in_cap_units if em_in_cap_units else 1.0


# ---------------------------------------------------------------------------
# What the canvas renderer is modelled as doing.
#
# This is the drift surface between the harness and `renderEntities.ts`, so it is declared
# rather than buried: flip a flag to False to re-measure the defect it corresponds to. With all
# three True the oracle is asking "given the renderer applies these rules, does the text land
# where ezdxf puts it" -- which is the question that has to stay answered.
# ---------------------------------------------------------------------------

RENDERER_APPLIES_ATTACHMENT_POINT = True   # ctx.textAlign / ctx.textBaseline from attachment_point
RENDERER_APPLIES_WIDTH_FACTOR = True       # \W and \T folded into a horizontal scale
RENDERER_APPLIES_CAP_HEIGHT = True         # font-size = height / (cap/em)


#: The escape -> glyph substitutions `cleanCadText` makes before the canvas measures anything.
#: Without these the harness measures "%%c145" as six glyphs against ezdxf's rendered "⌀145",
#: and reports a 1.56 width ratio for a string that is drawn correctly.
_CAD_TEXT_SUBSTITUTIONS = (("%%c", "⌀"), ("%%C", "⌀"), ("%%d", "°"), ("%%D", "°"),
                           ("%%p", "±"), ("%%P", "±"))


def clean_cad_text(text: str) -> str:
    """Mirror of `cleanCadText` in `renderEntities.ts`, for the substitutions that change width."""
    for escape, glyph in _CAD_TEXT_SUBSTITUTIONS:
        text = text.replace(escape, glyph)
    return text


def predicted_width(
    text: str,
    height: float,
    cap_ratio: float,
    width_factor: float | None,
    tracking: float | None,
    font_name: str = CANVAS_FONT,
) -> float:
    """Width of a string as the canvas renderer draws it, in drawing units."""
    from ezdxf.fonts import fonts

    if not text or height <= 0:
        return 0.0
    text = clean_cad_text(text)

    # With the cap-height fix the canvas em is `height / cap_ratio`, i.e. cap height == height,
    # which is exactly what ezdxf uses. Without it the em is `height`, so the cap height comes
    # out at `height * cap_ratio`.
    cap = height if RENDERER_APPLIES_CAP_HEIGHT else height * cap_ratio

    # `\W` only. `tracking` is accepted so callers can pass the whole property bag, but ezdxf
    # does not apply `\T` as a glyph scale and neither does the renderer -- measured: folding it
    # in made width_ratio equal the tracking factor across all 81 strings that carry one.
    _ = tracking
    scale = 1.0
    if RENDERER_APPLIES_WIDTH_FACTOR:
        try:
            v = float(width_factor)  # type: ignore[arg-type]
            if v > 0:
                scale = v
        except (TypeError, ValueError):
            pass

    return fonts.make_font(font_name, cap_height=cap, width_factor=scale).text_width(text)


#: attachment point -> (x fraction of the box, y fraction) that the anchor sits on.
#: 1-3 top, 4-6 middle, 7-9 bottom; left/centre/right across.
_ANCHOR_FRACTIONS: dict[int, tuple[float, float]] = {
    1: (0.0, 1.0), 2: (0.5, 1.0), 3: (1.0, 1.0),
    4: (0.0, 0.5), 5: (0.5, 0.5), 6: (1.0, 0.5),
    7: (0.0, 0.0), 8: (0.5, 0.0), 9: (1.0, 0.0),
}


#: Strings shorter than this are excluded from the width statistic.
#:
#: `ez_w` is the INK width of the rendered glyphs; the predicted width is the ADVANCE width,
#: which includes side bearings. Over a long string the difference amortises to noise, but for a
#: one-character cell like a fullwidth "１" the bearings are most of the advance and the ratio
#: reads 3.5 with nothing actually wrong. Measuring only longer strings keeps the statistic
#: about the width factor rather than about font side bearings.
MIN_CHARS_FOR_WIDTH_RATIO = 6


def _quadrant(rotation: float) -> int | None:
    """0/90/180/270 as 0-3, or None for an off-axis rotation."""
    normalized = round(((rotation % 360.0) + 360.0) % 360.0, 3)
    for index, angle in enumerate((0.0, 90.0, 180.0, 270.0)):
        if abs(normalized - angle) < 1.0 or abs(normalized - angle - 360.0) < 1.0:
            return index
    return None


def anchor_reference(
    box: tuple[float, float, float, float], attachment_point: Any, rotation: float = 0.0
) -> tuple[float, float] | None:
    """The point inside ezdxf's ink box that the insert point should coincide with.

    This is the whole anchor test, and it needs no width prediction: if the renderer honours the
    attachment point, the DXF insert point lands on the matching corner (or edge midpoint) of
    the rendered ink. Before the fix the renderer always used bottom-left, so a right-aligned
    string was out by its full width and a centred one by half.

    Rotation has to be undone first. A 90-degree string advances up the page, so its ink box's
    *height* is the text width -- comparing a "bottom-left" fraction against the world-space box
    would put the anchor on the wrong edge entirely. Off-axis rotations return None: the
    axis-aligned world box of a slanted string is not its text box, so there is nothing sound to
    compare and the row is excluded rather than reported as a large fake error.
    """
    quadrant = _quadrant(rotation)
    if quadrant is None:
        return None

    xmin, ymin, xmax, ymax = box
    width, height = xmax - xmin, ymax - ymin
    ap = int(attachment_point) if isinstance(attachment_point, (int, float)) else 7
    fx, fy = _ANCHOR_FRACTIONS.get(ap, (0.0, 0.0)) if RENDERER_APPLIES_ATTACHMENT_POINT else (0.0, 0.0)

    if quadrant == 0:      # text advances +X, grows +Y
        return (xmin + width * fx, ymin + height * fy)
    if quadrant == 1:      # advances +Y, grows -X
        return (xmax - width * fy, ymin + height * fx)
    if quadrant == 2:      # advances -X, grows -Y
        return (xmax - width * fx, ymax - height * fy)
    return (xmin + width * fy, ymax - height * fx)   # advances -Y, grows +X


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def census_of(payload_entities: list[dict[str, Any]]) -> dict[str, Any]:
    """The `drawn/total` census for one sheet's serializer payload.

    Split out of `build_report` so `--sweep` can take the census without paying for the text
    oracle, which renders the whole sheet through ezdxf's `Frontend` and dominates the runtime.

    One implementation on purpose: a sweep and a single-sheet run that each classified entities
    their own way could disagree about what was culled, and the sweep exists precisely to catch
    a change in that number.
    """
    # Needs the whole sheet, so it cannot live inside the per-entity `classify`. Only a verdict
    # that would otherwise be `drawn` is overridden, mirroring the renderer's own order: the
    # `outside_viewport` cull runs first, and a non-drawable record never reaches this at all.
    callouts = section_callout_ids(payload_entities)

    census: Counter = Counter()
    by_type: dict[str, Counter] = defaultdict(Counter)
    for ent in payload_entities:
        verdict = classify(ent)
        if verdict == "drawn" and id(ent) in callouts:
            verdict = "section-callout"
        census[verdict] += 1
        by_type[(ent.get("entity_type") or "?").lower()][verdict] += 1

    return {
        "drawn": census["drawn"],
        "total": len(payload_entities),
        "buckets": dict(census),
        "by_type": {k: dict(v) for k, v in sorted(by_type.items())},
    }


def build_report(dxf_path: Path) -> dict[str, Any]:
    entities, layers, counts, metadata = DXFParser().parse_file(dxf_path)

    # The serializer payload is what actually reaches the canvas: entities plus the layer-table
    # records, which is why the HUD denominator is larger than the entity count.
    payload_entities = entities + layers

    # Needs the whole sheet, so it cannot live inside the per-entity `classify`. Only a verdict
    # that would otherwise be `drawn` is overridden, mirroring the renderer's own order: the
    # `outside_viewport` cull runs first, and a non-drawable record never reaches this at all.
    census_block = census_of(payload_entities)

    truth, truth_records, text_facts, layout_name = record_ground_truth(dxf_path)
    cap_ratio = cap_height_ratio()

    rows: list[dict[str, Any]] = []
    unmatched = Counter()
    #: parent handle -> record indices already taken, so two children cannot claim one box.
    claimed_by_parent: dict[str, set[int]] = defaultdict(set)
    #: parent handle -> its records merged into one box per rendered string, computed once.
    clustered_parents: dict[str, list[tuple[float, float, float, float]]] = {}

    for ent in payload_entities:
        if (ent.get("entity_type") or "").lower() != "text":
            continue
        props = ent.get("properties") or {}
        handle = props.get("handle") or ""
        parent_handle = props.get("parent_handle") or ""
        text = props.get("text") or ""
        if not text:
            unmatched["empty-text"] += 1
            continue

        insert = (ent.get("geometry") or {}).get("insert") or [0.0, 0.0, 0.0]
        height = float(props.get("height") or 0.0)
        via_parent = False

        box = truth.get(handle) if handle else None
        if box is None:
            # No handle (an exploded INSERT child) or a handle ezdxf never drew. Fall back to
            # matching against the parent INSERT's records -- see `match_within_parent`.
            # Clustered so a wrapped string is one candidate rather than one per line --
            # see `cluster_text_records`.
            if parent_handle and parent_handle not in clustered_parents:
                clustered_parents[parent_handle] = cluster_text_records(
                    truth_records.get(parent_handle, [])
                )
            candidates = clustered_parents.get(parent_handle, [])
            hit = match_within_parent(
                (float(insert[0]), float(insert[1])),
                props.get("attachment_point"),
                float(props.get("rotation") or 0.0),
                height,
                candidates,
                claimed_by_parent[parent_handle],
            ) if candidates else None
            if hit is None:
                unmatched["no-handle" if not handle else "not-in-ground-truth"] += 1
                continue
            claimed_by_parent[parent_handle].add(hit[0])
            box = hit[1]
            via_parent = True
        our_w = predicted_width(
            text, height, cap_ratio, props.get("width_factor"), props.get("tracking")
        )
        if our_w <= 0:
            unmatched["unmeasurable"] += 1
            continue

        ez_xmin, ez_ymin, ez_xmax, ez_ymax = box
        ez_w = ez_xmax - ez_xmin
        ez_h = ez_ymax - ez_ymin

        facts = text_facts.get(handle, {})
        true_rotation = facts.get("true_rotation", 0.0)
        stored_rotation = float(props.get("rotation") or 0.0)
        # `dxf.rotation` is 0 for an MTEXT that is actually vertical -- the orientation lives in
        # `text_direction`. Where the two disagree, the renderer draws the string horizontally.
        rotation_lost = abs(true_rotation - stored_rotation) > 0.5

        reference = anchor_reference(box, props.get("attachment_point"), stored_rotation)
        off_axis = reference is None

        # Split the measured box into text-space extents. A 90-degree string advances up the
        # page, so its world-space HEIGHT is the text width -- reading the box axis-aligned
        # reports a vertical label as five lines of text one character wide, and its width
        # ratio as 4.6 with nothing wrong.
        quadrant = _quadrant(stored_rotation)
        along, across = (ez_h, ez_w) if quadrant in (1, 3) else (ez_w, ez_h)

        # ezdxf wrapped the string to its declared column width. The canvas draws one line
        # regardless (`cleanCadText` turns \P into a space), so a wrapped string runs
        # across whatever cell sits beside it.
        est_lines = (across / height) if height > 0 else 0.0
        wrapped = est_lines > 1.6 and not rotation_lost

        # A wrapped or off-axis string's measured box is not comparable to a single-line
        # prediction, so its numbers would be noise. Flagged as its own defect instead of being
        # averaged into the statistics.
        comparable = not rotation_lost and not wrapped and not off_axis
        ref_x, ref_y = reference if reference else (ez_xmin, ez_ymin)

        # dx/dy compare the insert point against the point inside ezdxf's ink box that the
        # renderer's anchor implies. Exact, and independent of any width prediction.
        rows.append({
            "handle": handle,
            "layer": ent.get("layer"),
            "text": text[:32],
            "attachment_point": props.get("attachment_point"),
            "matched_via_parent": via_parent,
            "stored_rotation": stored_rotation,
            "true_rotation": true_rotation,
            "rotation_lost": rotation_lost,
            "wrapped": wrapped,
            "off_axis": off_axis,
            "est_lines": round(est_lines, 2),
            "comparable": comparable,
            "width_factor": props.get("width_factor"),
            "tracking": props.get("tracking"),
            "height": height,
            "dx": round(float(insert[0]) - ref_x, 4),
            "dy": round(float(insert[1]) - ref_y, 4),
            "width_ratio": round(our_w / along, 4) if along > 1e-9 else None,
            "ez_size": [round(ez_w, 4), round(ez_h, 4)],
            "ez_box": [round(v, 4) for v in box],
        })

    rows.sort(key=lambda r: max(abs(r["dx"]), abs(r["dy"])), reverse=True)
    comparable_rows = [r for r in rows if r["comparable"]]

    def stats(key: str) -> dict[str, float] | None:
        vals = [abs(r[key]) for r in comparable_rows if r.get(key) is not None]
        if not vals:
            return None
        return {
            "median": round(statistics.median(vals), 4),
            "p90": round(sorted(vals)[int(len(vals) * 0.9)], 4),
            "max": round(max(vals), 4),
        }

    def ratio_stats(key: str) -> dict[str, float] | None:
        # Short strings are dominated by side bearings, not by the width factor -- see
        # MIN_CHARS_FOR_WIDTH_RATIO.
        vals = [
            r[key] for r in comparable_rows
            if r.get(key) is not None and len(r["text"]) >= MIN_CHARS_FOR_WIDTH_RATIO
        ]
        if not vals:
            return None
        return {
            "median": round(statistics.median(vals), 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
        }

    # Strings whose position depends on the attachment point being honoured. Bottom-left (7) is
    # the only value a left/alphabetic renderer gets right by accident, so this is exactly the
    # population that moved when the fix landed -- and the population that regresses if the
    # anchor handling is ever removed.
    anchor_dependent = sum(1 for r in rows if r["attachment_point"] not in (7, None))

    return {
        "dxf": str(dxf_path),
        "render_layout": layout_name,
        "extraction_counts": dict(counts),
        "census": census_block,
        "font": {"name": CANVAS_FONT, "cap_height_over_em": round(cap_ratio, 4)},
        "text_oracle": {
            "measured": len(rows),
            "comparable": len(comparable_rows),
            "matched_via_parent": sum(1 for r in rows if r["matched_via_parent"]),
            "unmatched": dict(unmatched),
            "attachment_points": dict(Counter(r["attachment_point"] for r in rows)),
            "anchor_dependent": anchor_dependent,
            "rotation_lost": sum(1 for r in rows if r["rotation_lost"]),
            "wrapped_but_drawn_on_one_line": sum(1 for r in rows if r["wrapped"]),
            "off_axis_rotation": sum(1 for r in rows if r["off_axis"]),
            "dx": stats("dx"),
            "dy": stats("dy"),
            "width_ratio": ratio_stats("width_ratio"),
            "rows": rows,
        },
        "metadata_keys": sorted(metadata.keys()),
    }


#: MTEXT attachment points. 7 (bottom-left) is the only one the canvas renderer draws correctly,
#: because it is the only one matching `textAlign: 'left'` + `textBaseline: 'alphabetic'`.
ATTACHMENT_NAMES = {
    1: "top-left", 2: "top-center", 3: "top-right",
    4: "middle-left", 5: "middle-center", 6: "middle-right",
    7: "bottom-left", 8: "bottom-center", 9: "bottom-right",
}


def print_report(report: dict[str, Any], top: int) -> None:
    census = report["census"]
    print(f"\nDXF     : {report['dxf']}")
    print(f"Layout  : {report['render_layout']}")
    print(f"Font    : {report['font']['name']}  cap/em = {report['font']['cap_height_over_em']}")

    print(f"\n=== CENSUS =====================================  {census['drawn']}/{census['total']} drawn")
    for bucket, n in sorted(census["buckets"].items(), key=lambda kv: -kv[1]):
        print(f"  {bucket:<18} {n:>5}")
    print("\n  by entity type:")
    for etype, buckets in census["by_type"].items():
        detail = "  ".join(f"{k}={v}" for k, v in sorted(buckets.items()))
        print(f"    {etype:<14} {detail}")

    oracle = report["text_oracle"]
    unmatched_total = sum(oracle["unmatched"].values())
    print(f"\n=== TEXT PLACEMENT ORACLE ======================  {oracle['measured']} measured, "
          f"{unmatched_total} unmatched")
    if oracle["unmatched"]:
        detail = "  ".join(f"{k}={v}" for k, v in sorted(oracle["unmatched"].items()))
        print(f"  unmatched: {detail}")
    print(f"  matched through a parent INSERT (title-block values): {oracle['matched_via_parent']}")

    honoured = "honoured" if RENDERER_APPLIES_ATTACHMENT_POINT else "IGNORED"
    print(f"\n  attachment points (renderer: {honoured}). 7 = bottom-left is the only value a")
    print("  left/alphabetic renderer gets right by accident:")
    for ap, n in sorted(oracle["attachment_points"].items(), key=lambda kv: -kv[1]):
        name = ATTACHMENT_NAMES.get(ap, "?")
        marker = "" if ap == 7 else "   <-- depends on the anchor fix"
        print(f"    {ap} {name:<15} {n:>4}{marker}")

    print("\n  counts:")
    print(f"    strings depending on the anchor fix {oracle['anchor_dependent']:>4}")
    print(f"    rotation lost (MTEXT text_direction){oracle['rotation_lost']:>4}")
    print(f"    wrapped by ezdxf, drawn on one line {oracle['wrapped_but_drawn_on_one_line']:>4}")
    print(f"    off-axis rotation (not measurable)  {oracle['off_axis_rotation']:>4}")

    print(f"\n  metrics over the {oracle['comparable']} comparable rows "
          f"(rotated/wrapped excluded -- their boxes are not comparable to a single horizontal line)")
    print("  target: dx/dy -> 0 (insert point on ezdxf's anchor), width_ratio -> 1.0")
    for key in ("dx", "dy"):
        st = oracle[key]
        if st:
            print(f"    |{key}|  median={st['median']:<9} p90={st['p90']:<9} max={st['max']}")
    st = oracle["width_ratio"]
    if st:
        print(f"    width_ratio   median={st['median']:<9} min={st['min']:<9} max={st['max']}"
              f"   (strings of >= {MIN_CHARS_FOR_WIDTH_RATIO} chars)")

    if top:
        print(f"\n  worst {top} by displacement:")
        print(f"    {'handle':<8} {'ap':<3} {'h':<6} {'dx':>9} {'dy':>9} {'w/w':>7} flags  text")
        for r in oracle["rows"][:top]:
            flags = ("R" if r["rotation_lost"] else "-") + ("W" if r["wrapped"] else "-")
            print(f"    {r['handle']:<8} {r['attachment_point']!s:<3} {r['height']:<6.2f} "
                  f"{r['dx']:>9.3f} {r['dy']:>9.3f} "
                  f"{r['width_ratio']!s:>7}  {flags}    {r['text']!r}")
        print("    flags: R = rotation lost, W = wrapped by ezdxf but drawn on one line")
    print()


#: What CLAUDE.md records for the section-callout cull across `storage/uploads`, so a drift is
#: visible in the output rather than needing a human to remember the figure. These are a
#: reference point, NOT a pass/fail gate: adding a drawing legitimately moves the denominator.
DOCUMENTED_CULL = {"drawings": 32, "cull_nothing": 23, "max_per_sheet": 10}


def sweep_cull(directory: Path) -> dict[str, Any]:
    """Census every DXF under `directory`, reporting how many entities each sheet culls.

    ## Why this exists

    CLAUDE.md mandates this sweep before landing any change to the section-callout rule, and
    quotes its result: *"23 of 32 drawings cull nothing, 9 cull 8-10 entities each, and the
    maximum on any sheet is 10. Re-run that sweep if you touch the rule -- a jump in those
    numbers is the failure mode, and it does not show up as a test failure."*

    Until now nothing produced those numbers. `main()` took a single DXF, so the documented
    pre-landing check had no producer -- the same shape as
    `Gotcha - A Checklist Item With No Producer Reported Clean`, one layer over.

    A sheet that fails to parse is **reported, not skipped silently**: a sweep that quietly
    drops the drawing which would have shown the regression is worse than no sweep.
    """
    rows: list[dict[str, Any]] = []
    failures: list[tuple[str, str]] = []

    for dxf_path in sorted(directory.glob("*.dxf")):
        try:
            entities, layers, _counts, _metadata = DXFParser().parse_file(dxf_path)
            block = census_of(entities + layers)
        except Exception as err:  # noqa: BLE001 - an unparseable sheet is a reportable row
            failures.append((dxf_path.name, f"{type(err).__name__}: {err}"))
            continue
        rows.append(
            {
                "file": dxf_path.name,
                "culled": block["buckets"].get("section-callout", 0),
                "drawn": block["drawn"],
                "total": block["total"],
            }
        )

    culls = [r["culled"] for r in rows]
    return {
        "directory": str(directory),
        "drawings": len(rows),
        "cull_nothing": sum(1 for c in culls if c == 0),
        "max_per_sheet": max(culls) if culls else 0,
        "histogram": {str(c): culls.count(c) for c in sorted(set(culls))},
        "rows": sorted(rows, key=lambda r: (-r["culled"], r["file"])),
        "failures": failures,
    }


def print_sweep(result: dict[str, Any], top: int) -> None:
    """The two headline numbers first, then the sheets that actually cull something."""
    print(f"\nSection-callout cull sweep -- {result['directory']}")
    print(f"  drawings censused    {result['drawings']}")

    if result["histogram"]:
        widest = max(result["histogram"].values())
        print("\n  entities culled per sheet:")
        for culled, count in sorted(result["histogram"].items(), key=lambda kv: int(kv[0])):
            bar = "#" * max(1, round(count * 28 / widest))
            print(f"    {culled:>3} culled   {bar:<28} {count}")

    doc = DOCUMENTED_CULL
    print("\n  against the figure recorded in CLAUDE.md:")
    for key, label in (
        ("drawings", "drawings swept"),
        ("cull_nothing", "sheets culling nothing"),
        ("max_per_sheet", "max cull on any sheet"),
    ):
        got, want = result[key], doc[key]
        verdict = "as documented" if got == want else f"DIFFERS (documented {want})"
        print(f"    {label:<24} {got:>4}   {verdict}")
    print(
        "\n  A difference is not automatically a defect -- adding a drawing moves the\n"
        "  denominator. A jump in the per-sheet maximum is the failure mode to look at."
    )

    culling = [r for r in result["rows"] if r["culled"]]
    if culling:
        print(f"\n  sheets that cull ({len(culling)}), worst first:")
        print(f"    {'culled':>6}  {'drawn/total':>12}  file")
        for row in culling[:top]:
            print(f"    {row['culled']:>6}  {row['drawn']:>5}/{row['total']:<6}  {row['file']}")

    if result["failures"]:
        print(f"\n  [!] {len(result['failures'])} sheet(s) could not be censused:")
        for name, err in result["failures"]:
            print(f"      {name}: {err}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "dxf", type=Path, nargs="?", help="Path to the DXF (must live under storage/)"
    )
    parser.add_argument(
        "--sweep",
        type=Path,
        default=None,
        metavar="DIR",
        help="Census every DXF in DIR and report the section-callout cull histogram. "
        "Skips the text oracle, so it is fast enough to run before landing.",
    )
    parser.add_argument("--top", type=int, default=15, help="Worst-N text rows to print")
    parser.add_argument("--json", type=Path, default=None, help="Write the full ledger here")
    args = parser.parse_args()

    if args.sweep is not None:
        sweep_dir = args.sweep if args.sweep.is_absolute() else (REPO_ROOT / args.sweep)
        if not sweep_dir.is_dir():
            print(f"No such directory: {sweep_dir}", file=sys.stderr)
            return 2
        result = sweep_cull(sweep_dir)
        print_sweep(result, args.top)
        if args.json is not None:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"Sweep written to {args.json}")
        return 0

    if args.dxf is None:
        parser.error("give a DXF path, or --sweep DIR")

    dxf_path = args.dxf if args.dxf.is_absolute() else (REPO_ROOT / args.dxf)
    if not dxf_path.exists():
        print(f"No such DXF: {dxf_path}", file=sys.stderr)
        return 2

    report = build_report(dxf_path)
    print_report(report, args.top)

    out = args.json
    if out is None:
        out_dir = REPO_ROOT / "storage" / "eval" / "render_audit"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{dxf_path.stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Ledger written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
