"""The report's paper and palette are declared twice. This is what stops the copies drifting.

Page 1 is now generated in Python (`vector_pdf_exporter.py`) and pages 2+ are still generated in
TypeScript (`complianceChecklistSheet.ts`, driven by `useComplianceReportExport.ts`). Two
languages, one document — and no runtime type sharing between them, exactly like the comparison
taxonomy in `test_taxonomy_consistency.py`.

So the duplication is deliberate, and **unpinned deliberate duplication is just duplication**.
Two things have to agree or the report is wrong in ways nobody will notice:

* **Paper size.** Page 1 at A4 and page 2 at something else produces a PDF that prints with
  alternating page sizes. Every viewer renders it happily.
* **Marker colour.** `markerStyles.ts` already records what this costs: the engine's markers and
  the manual ones drifted to different colours for the same word, both rendered fine, and it was
  invisible until an engineer looked at one drawing carrying both kinds.

⚠ This asserts on the values a *human* would compare, not on file bytes. It parses the TS source
rather than importing it, so a rename on either side fails loudly here rather than silently
letting the two copies diverge.
"""

import re
from pathlib import Path

import pytest

from services.backend.infrastructure.rendering.text_placement import CAD_TEXT_FIT_SCALE
from services.backend.infrastructure.rendering.vector_pdf_exporter import (
    A4_LANDSCAPE,
    MARKER_EDGE,
    MARKER_INK,
)

REVIEW = Path("apps/desktop/src/components/review")
MARKER_STYLES_TS = REVIEW / "markerStyles.ts"
PAGE_GEOMETRY_TS = REVIEW / "reportPageGeometry.ts"
RENDER_ENTITIES_TS = REVIEW / "renderEntities.ts"

pytestmark = pytest.mark.skipif(
    not MARKER_STYLES_TS.exists() or not PAGE_GEOMETRY_TS.exists(),
    reason="desktop app sources not present in this checkout",
)


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _parse_marker_styles() -> dict[str, dict[str, str]]:
    """`MARKER_STYLES` from the TS source: status -> {field: value}."""
    source = MARKER_STYLES_TS.read_text(encoding="utf-8")
    body = source.split("export const MARKER_STYLES", 1)[1]
    body = body.split("};", 1)[0]

    styles: dict[str, dict[str, str]] = {}
    for status, fields in re.findall(r"(\w+):\s*\{([^}]*)\}", body):
        styles[status] = dict(re.findall(r"(\w+):\s*'([^']*)'", fields))
    return styles


def _parse_mm(name: str) -> float:
    """A `REPORT_*_MM` numeric literal out of `reportPageGeometry.ts`."""
    source = PAGE_GEOMETRY_TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name}\s*=\s*(?:Object\.freeze\()?([^;]+)", source)
    assert match, f"{name} not found in {PAGE_GEOMETRY_TS}"
    return match.group(1)


def test_the_two_sides_know_the_same_statuses():
    """A status one side can draw and the other cannot is a row with no mark, or the reverse."""
    assert set(_parse_marker_styles()) == set(MARKER_INK)


def test_the_mark_matches_the_canvas_column_of_marker_styles():
    """The mark itself is `color` — the same ink the review canvas paints.

    ⚠ This assertion was inverted on 2026-08-25, by an explicit owner's call, and the reasoning it
    replaced is kept because it was half right. It read *"Page 1 must use `uiLight`, NOT `color` …
    `#39ff14` and `#00ffff` on white paper are close to invisible"* — true of neon as a **stroke**
    on white, and `markerInkFor(type, 'print')` still says exactly that. The report deliberately
    diverges from that surface so the printed mark is the one the engineer saw on screen.

    ⚠ **So `markerInkFor(..., 'print')` and this constant now disagree on purpose.** If they are
    ever reconciled, reconcile them toward whichever surface the owner picks — do not assume this
    one drifted.
    """
    for status, fields in _parse_marker_styles().items():
        assert MARKER_INK[status] == pytest.approx(_hex_to_rgb(fields["color"]), abs=1 / 255), (
            f"{status}: the mark has drifted from markerStyles.ts color ({fields['color']})"
        )


def test_report_label_ink_matches_the_light_theme_column_of_marker_styles():
    """The label beside a mark is `uiLight` — that table's own answer for a light background.

    The mark can be neon because hue is all it carries. A label carries words, and neon words on
    white paper are unreadable, so the two take different columns of the same table.
    """
    for status, fields in _parse_marker_styles().items():
        assert MARKER_EDGE[status] == pytest.approx(_hex_to_rgb(fields["uiLight"]), abs=1 / 255), (
            f"{status}: label ink has drifted from markerStyles.ts uiLight ({fields['uiLight']})"
        )


def test_page_size_matches_the_checklist_sheets():
    """Page 1 and pages 2+ are bound into one PDF and must be the same paper."""
    page_mm = _parse_mm("REPORT_PAGE_MM")
    assert f"width: {A4_LANDSCAPE.width_mm:g}" in page_mm
    assert f"height: {A4_LANDSCAPE.height_mm:g}" in page_mm


def test_margin_matches_the_checklist_sheets():
    assert float(_parse_mm("REPORT_MARGIN_MM")) == A4_LANDSCAPE.margin_mm


def test_text_fit_scale_matches_the_canvas():
    """Both renderers must shrink CAD text by the same factor, or they draw different sheets.

    The corpus is drawn in `txt.shx` + the `extfont2` BigFont, which ezdxf cannot rasterise at
    all — `configure_cad_fonts` redirects both to MS Gothic, whose glyphs are wider than the
    stick font the title block was laid out for. At full height the labels overflow their cells:
    on M745206N01, `材料個数` runs 291.92 → 306.48 while `Material Weight(kg)` starts at 304.87.

    ⚠ **That overlap is in the source data as rendered, not in either renderer** — ezdxf's ink
    and the canvas model agree on it to within 0.2 units. The canvas has compensated with 0.80
    since the vector path landed; the PDF applies the same factor. If one side changes it alone
    the report stops matching the sheet the engineer reviewed, and nothing else would say so.
    """
    source = RENDER_ENTITIES_TS.read_text(encoding="utf-8")
    match = re.search(r"capHeightPx\s*\*\s*([0-9.]+)\s*\)", source)
    assert match, f"the text fit scale is no longer a literal in {RENDER_ENTITIES_TS}"
    assert float(match.group(1)) == CAD_TEXT_FIT_SCALE
