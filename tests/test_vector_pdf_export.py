"""Guards for the vector report page.

Every test here pins a defect that produced a plausible-looking PDF rather than an error:
a file that opens, looks perfect at 1000%, prints beautifully, and is missing the one property
it was built for. That is the failure mode of this whole pipeline — see
`docs/vault/06 - Gotchas .../Gotcha - The Vector PDF Had No Text at All.md`, where four separate
displacements each did exactly that.

The fixture is built with `ezdxf` rather than read from `storage/uploads`, which is gitignored.
That limits what these can claim: a document written by the same library that renders it cannot
expose a disagreement between two of its own fields (the lesson from
`Gotcha - The Dimension Text Was Anchored to the Line It Had to Avoid`). These test our
pipeline — page size, vector-ness, that the text layer exists and is searchable and invisible —
not ezdxf's fidelity to a real CAD package. `tools/render_audit.py` is what measures that.
"""

from pathlib import Path

import ezdxf
import pytest

from services.backend.infrastructure.rendering.text_placement import (
    REPORT_FONT_CANDIDATES,
    resolve_report_font,
)
from services.backend.infrastructure.rendering.vector_pdf_exporter import (
    MARKER_EDGE,
    MARKER_INK,
    PageSpec,
    SheetMarker,
    render_vector_sheet,
)
from services.backend.infrastructure.storage import path_resolver

fitz = pytest.importorskip("fitz", reason="PyMuPDF is an optional dependency")
pytest.importorskip("matplotlib", reason="matplotlib is an optional dependency")

LATIN = "SS400"
DRAWING_NO = "M745221N01"
JAPANESE = "指示なき角部は糸面取りのこと"


@pytest.fixture(scope="module", autouse=True)
def storage_root(tmp_path_factory):
    """A throwaway storage root, because the exporter sandboxes its input path.

    `DXFParser.parse_file` and (since this module) the geometry pass both run the DXF through
    `validate_sandboxed_path`, so a fixture written to pytest's own tmp dir is REJECTED rather
    than rendered. Redirecting the root is how the guard gets exercised instead of bypassed.
    """
    root = tmp_path_factory.mktemp("storage")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(path_resolver, "get_storage_root", lambda: root)
        yield root


@pytest.fixture(scope="module")
def sheet_dxf(storage_root) -> Path:
    """A minimal sheet: some geometry, Latin text, a drawing number, and a Japanese note."""
    doc = ezdxf.new("R2010", setup=True)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (400, 0), (400, 280), (0, 280), (0, 0)], close=True)
    msp.add_circle((200, 140), radius=40)
    msp.add_text(LATIN, height=8).set_placement((20, 250))
    msp.add_text(DRAWING_NO, height=8).set_placement((260, 20))
    msp.add_text(JAPANESE, height=8).set_placement((20, 60))
    path = storage_root / "sheet.dxf"
    doc.saveas(path)
    return path


@pytest.fixture(scope="module")
def rendered(sheet_dxf) -> bytes:
    return render_vector_sheet(sheet_dxf)


@pytest.fixture(scope="module")
def page(rendered):
    with fitz.open(stream=rendered, filetype="pdf") as doc:
        yield doc[0]


# ---------------------------------------------------------------------------
# The claim the whole module exists for
# ---------------------------------------------------------------------------


def test_cad_text_is_extractable(page):
    """`ezdxf + MatplotlibBackend` alone yields zero characters — every glyph is a path.

    `MatplotlibBackend` implements `draw_filled_paths` and no `draw_text`, and the frontend
    converts text to outlines upstream of every backend, so this is not fixable by choosing a
    different one. If this assertion ever reads 0 again, the text layer stopped being written
    and nothing else in the PDF will look wrong.
    """
    assert len(page.get_text().strip()) > 0


@pytest.mark.parametrize("needle", [LATIN, DRAWING_NO, JAPANESE])
def test_text_is_searchable(page, needle):
    """`Ctrl + F` is the acceptance criterion, so search rather than substring-match.

    Extraction can succeed while search fails: a Type 3 font drops every codepoint above 255
    from the text layer, so `get_text()` returns the Latin and `search_for` finds no Japanese.
    """
    assert page.search_for(needle), f"{needle!r} is not findable in the text layer"


def test_the_text_layer_is_invisible(page):
    """Render mode 3. Without it the layer double-strikes ezdxf's own glyphs in a second font."""
    contents = b"".join(page.read_contents() for _ in [0])
    assert b"3 Tr" in contents, "no invisible-text operator in the content stream"


# ---------------------------------------------------------------------------
# 100% vector
# ---------------------------------------------------------------------------


def test_there_is_no_raster_image(page):
    """The point of the exercise. A raster page also opens fine and also prints."""
    assert page.get_images() == []


def test_geometry_is_vector_paths(page):
    assert len(page.get_drawings()) > 4


# ---------------------------------------------------------------------------
# Ink: black sheet, coloured marks
# ---------------------------------------------------------------------------


def _ink_colours(page_obj) -> set[tuple[float, ...]]:
    """Every stroke and fill colour used on the page, rounded."""
    found = set()
    for op in page_obj.get_drawings():
        for key in ("color", "fill"):
            value = op.get(key)
            if value:
                found.add(tuple(round(channel, 2) for channel in value))
    return found


def _is_monochrome(colour: tuple[float, ...]) -> bool:
    return max(colour) < 0.05 or min(colour) > 0.95   # black, or the white paper


def test_the_drawing_prints_black(page):
    """ezdxf otherwise honours each entity's ACI colour, which is tuned for a CAD SCREEN.

    This corpus draws in yellow, cyan, orange and red. Those are legible on the dark canvas and
    washed out on white paper — and a printed report is the one place the sheet is guaranteed to
    be on white. Nothing errors when this regresses; the page just prints faint.
    """
    assert all(_is_monochrome(c) for c in _ink_colours(page)), (
        f"non-monochrome ink on an unmarked sheet: "
        f"{[c for c in _ink_colours(page) if not _is_monochrome(c)]}"
    )


def test_only_the_markers_carry_colour(sheet_dxf):
    """Colour means exactly one thing in this document: a reviewer flagged it.

    So the marks must survive the black policy — they are painted after it, in PyMuPDF — and
    they must be the ONLY thing that does.
    """
    marked = render_vector_sheet(
        sheet_dxf,
        markers=[SheetMarker(200.0, 140.0, "CHANGED"), SheetMarker(100.0, 100.0, "MATCHED")],
    )
    with fitz.open(stream=marked, filetype="pdf") as doc:
        coloured = {c for c in _ink_colours(doc[0]) if not _is_monochrome(c)}

    # One colour per mark: the dot's fill and the tick's stroke, both straight from
    # `MARKER_INK`. The rim that briefly added a second is gone — the canvas never had one.
    expected = {MARKER_INK["CHANGED"], MARKER_INK["MATCHED"]}
    for want in expected:
        assert any(
            all(abs(a - b) < 0.02 for a, b in zip(want, got)) for got in coloured
        ), f"marker ink {want} is not on the page"
    assert len(coloured) == len(expected), f"unexpected colour on the sheet: {coloured}"


# ---------------------------------------------------------------------------
# Page geometry
# ---------------------------------------------------------------------------


def test_the_page_is_a4_landscape(page):
    """`MatplotlibBackend.finalize()` REPLACES the figure size with the drawing's aspect ratio.

    Measured on M745221N01: a figure asked for at 11.69x8.27in came back 6.788x4.8. The page
    size has to be re-asserted after `draw_layout`, and nothing warns if it is not — the PDF is
    simply a different size than requested.
    """
    assert page.rect.width == pytest.approx(841.89, abs=1.0)
    assert page.rect.height == pytest.approx(595.28, abs=1.0)


def test_a_custom_page_spec_is_honoured(sheet_dxf):
    """A3, for the plotter. `PageSpec` is the only place paper size is decided."""
    a3 = PageSpec(width_mm=420.0, height_mm=297.0, margin_mm=5.0)
    with fitz.open(stream=render_vector_sheet(sheet_dxf, page=a3), filetype="pdf") as doc:
        assert doc[0].rect.width == pytest.approx(420.0 / 25.4 * 72.0, abs=1.0)


def test_the_drawing_is_cropped_to_its_ink(page):
    """Matplotlib's autoscale carries 5% margins per side, and `set_aspect(..., 'datalim')` --
    which ezdxf's `finalize()` switches on -- satisfies equal aspect by widening the view rather
    than shrinking the box, discarding the crop with only a warning on stderr.

    The sheet border should therefore reach close to the content box, not float inside it.
    """
    ops = [d["rect"] for d in page.get_drawings()]
    ink_width = max(o.x1 for o in ops) - min(o.x0 for o in ops)
    # 3 mm margins on a 297 mm page leave 291 mm of content; allow generous slack for the
    # letterboxing that preserving aspect legitimately introduces.
    assert ink_width > page.rect.width * 0.75


# ---------------------------------------------------------------------------
# Review markers
# ---------------------------------------------------------------------------


def test_markers_add_vector_badges_and_searchable_labels(sheet_dxf, page):
    before = len(page.get_drawings())
    marked = render_vector_sheet(
        sheet_dxf,
        markers=[SheetMarker(200.0, 140.0, "CHANGED", "125 -> 130"),
                 SheetMarker(100.0, 100.0, "MATCHED")],
    )
    with fitz.open(stream=marked, filetype="pdf") as doc:
        assert len(doc[0].get_drawings()) > before
        assert doc[0].get_images() == [], "a marker must not introduce a raster"
        assert doc[0].search_for("125 -> 130")


def test_an_unknown_status_still_paints(sheet_dxf):
    """A status the report does not know must not be silently dropped from the drawing.

    `MARKER_STYLES` is the union of the engine's and a human's vocabularies precisely because a
    filter that knows five of seven hides the other two.
    """
    with fitz.open(
        stream=render_vector_sheet(sheet_dxf, markers=[SheetMarker(200.0, 140.0, "WAT")]),
        filetype="pdf",
    ) as doc:
        assert len(doc[0].get_drawings()) > 4


def test_every_marker_status_has_both_a_mark_and_a_label_ink():
    assert set(MARKER_INK) == set(MARKER_EDGE)


def _luminance(rgb):
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _marker_ops(sheet_dxf, status):
    """Just the drawing ops painted in this status's ink, isolated from the sheet's own linework."""
    ink = MARKER_INK[status]
    pdf = render_vector_sheet(sheet_dxf, markers=[SheetMarker(200.0, 140.0, status)])
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        return [
            op for op in doc[0].get_drawings()
            if any(
                op.get(key) and all(abs(a - b) < 0.02 for a, b in zip(ink, op[key]))
                for key in ("color", "fill")
            )
        ]


def test_matched_is_a_stroked_tick_and_every_other_status_is_a_filled_dot(sheet_dxf):
    """The report draws what `renderEntities.ts` draws, and it does not draw the same thing twice.

    The canvas branches on MATCHED: a stroked tick for it, a flat translucent dot for everything
    else. A report that drew a dot for MATCHED would be a sheet with no checkmarks on it,
    which is the one thing the mark is called after — and it would look correct in every test
    that only counts drawings.
    """
    tick = _marker_ops(sheet_dxf, "MATCHED")
    dot = _marker_ops(sheet_dxf, "CHANGED")

    assert any(op["type"] == "s" for op in tick), "MATCHED is not stroked — no tick on the sheet"
    assert not any(op["type"] in ("f", "fs") for op in tick), "MATCHED must not be filled"
    assert any(op["type"] == "f" for op in dot), "CHANGED is not filled — no dot on the sheet"
    assert not any(op["type"] in ("s", "fs") for op in dot), (
        "the dot must have no outline; `renderEntities.ts` rejected the stroke explicitly"
    )


def test_the_badge_is_translucent_so_the_marked_content_still_reads():
    """A highlighter is translucent; paint is not, and paint hides what it points at.

    Opaque neon buried the very title-block fields the badges were flagging. This pins the wash
    itself — an opacity of 1.0 would look fine in isolation and silently re-hide the content.
    """
    from services.backend.infrastructure.rendering import vector_pdf_exporter as exporter

    assert 0.2 < exporter._BADGE_FILL_OPACITY < 0.8, (
        "below ~0.2 the hue stops registering, above ~0.8 it is paint again"
    )
    # Every channel must move toward white, or nothing is showing through.
    for fill in MARKER_INK.values():
        for raw, seen in zip(fill, exporter.composited_badge_fill(fill)):
            assert seen >= raw
        assert _luminance(exporter.composited_badge_fill(fill)) > _luminance(fill)


def test_the_marker_label_is_dark_enough_to_read_on_paper():
    """`MARKER_EDGE` no longer rims anything — it is the LABEL ink, and labels sit on white.

    The mark itself is neon by an explicit call, and hue is all it carries. A label carries words,
    so it cannot follow: `#39ff14` text on white paper is the one piece of marker output nobody
    could read.
    """
    for status, edge in MARKER_EDGE.items():
        assert _luminance(edge) < 0.55, f"{status} label ink is too light to read on white paper"


def test_the_highlight_fill_is_actually_neon():
    """The fill has to be conspicuous or the badge is just a grey dot.

    Pins the intent, not the specific hexes — those are pinned against `markerStyles.ts` by
    `tests/test_report_style_consistency.py`. Here: every status except the deliberately muted
    NOT_A_FINDING must be strongly saturated, which is what "neon" means numerically.
    """
    for status, (r, g, b) in MARKER_INK.items():
        if status == "NOT_A_FINDING":
            continue
        assert max(r, g, b) > 0.9, f"{status} fill is not bright enough to read as a highlight"
        assert max(r, g, b) - min(r, g, b) > 0.4, f"{status} fill is washed out, not neon"


# ---------------------------------------------------------------------------
# Where the strings come from
# ---------------------------------------------------------------------------


def test_supplied_entities_are_used_instead_of_reparsing(sheet_dxf):
    """The report must describe the extraction the ENGINEER saw, not a fresh one.

    36 of 55 stored drawings are at a stale `EXTRACTION_SCHEMA_VERSION`; re-parsing here would
    give those a text layer their own canvas never had, and the report would quietly disagree
    with the review it documents. Passing `entities` is how a caller pins that.
    """
    only_one = [{
        "entity_type": "text",
        "properties": {"text": "ONLYTHIS", "height": 8.0, "attachment_point": 7},
        "geometry": {"location": [20.0, 250.0]},
    }]
    with fitz.open(
        stream=render_vector_sheet(sheet_dxf, entities=only_one), filetype="pdf"
    ) as doc:
        assert doc[0].search_for("ONLYTHIS")
        assert not doc[0].search_for(JAPANESE), "re-parsed the DXF instead of using `entities`"


def test_empty_entities_still_produces_a_drawing(sheet_dxf):
    """An empty text layer is a report with no searchable text, NOT a blank page.

    Distinguishable on purpose: a caller that fetched no entities should still get the geometry,
    because a blank page-1 reads as a rendering glitch rather than as a missing query.
    """
    with fitz.open(stream=render_vector_sheet(sheet_dxf, entities=[]), filetype="pdf") as doc:
        assert len(doc[0].get_drawings()) > 4
        assert doc[0].get_images() == []


# ---------------------------------------------------------------------------
# Threading
# ---------------------------------------------------------------------------


def test_the_exporter_never_touches_pyplot():
    """`pyplot` is a global state machine and this module is built for a request path.

    `dxf_background_renderer` uses it and is safe only because the ingestion queue has a single
    serial consumer — see `Gotcha - The Background Queue Was Not a Background Thread`. A second,
    concurrent user of that global is the bug this asserts against, and it would show up as
    corrupted output under load rather than as an exception.
    """
    import ast

    module = ast.parse(
        Path("services/backend/infrastructure/rendering/vector_pdf_exporter.py")
        .read_text(encoding="utf-8")
    )
    imported: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported += [f"{node.module or ''}.{alias.name}" for alias in node.names]

    # Parsed, not grepped — and `ast.walk` so that an import nested inside a function body is
    # seen too, which is how this module imports everything optional. A substring check over the
    # source would fail on the module's own docstring explaining why it avoids pyplot.
    assert not [name for name in imported if "pyplot" in name]


# ---------------------------------------------------------------------------
# Typeface
# ---------------------------------------------------------------------------


def test_the_mincho_order_runs_lightest_and_narrowest_first():
    """The ORDER is load-bearing, and these are not interchangeable members of one family.

    Widths at equal cap height for `M745206N01`, relative to MS Gothic: Light 1.196x,
    Regular 1.283x, MS Mincho widest. Two separate things ride on this order:

    * MS Mincho last, because it re-creates the title-block collisions `CAD_TEXT_FIT_SCALE`
      exists to prevent — and that presents as a scale bug, not a font bug.
    * Light before Regular, because Regular's vertical stems read as bold at the 9.5 mm
      title-block sizes. Light is also narrower, so it cannot introduce a collision Regular
      did not already have.
    """
    names = [Path(c).name.lower() for c in REPORT_FONT_CANDIDATES]
    assert names.index("yuminl.ttf") < names.index("yumin.ttf") < names.index("msmincho.ttf")


@pytest.mark.parametrize("face", [Path(c).name for c in REPORT_FONT_CANDIDATES])
def test_cap_height_ratio_is_typographically_possible_for_every_report_face(face):
    """No face may report a cap height outside the band real fonts occupy.

    This is the guard that would have caught the defect below, and it is written against the
    CLASS rather than the instance: any future change to `REPORT_FONT_CANDIDATES` is checked
    the moment it lands, without anyone having to know which faces are half-width.

    Cap height is ~0.66-0.78 em across every face in this list. A number outside that band is
    not a font with unusual proportions, it is a measurement error — and it lands as a text
    layer scaled by exactly that error, which is invisible at `render_mode=3`.
    """
    from services.backend.infrastructure.rendering.text_placement import cap_height_ratio

    ezdxf_fonts = pytest.importorskip("ezdxf.fonts.fonts")
    if not ezdxf_fonts.font_manager.has_font(face):
        pytest.skip(f"{face} is not installed on this machine")

    assert 0.6 <= cap_height_ratio(face) <= 0.85


def test_cap_height_is_not_measured_by_forcing_m_to_half_width():
    """`M` is 0.5 em in MS Gothic and 0.939 em in Yu Mincho, and only one of those is assumed.

    Until 2026-08-25 `cap_height_ratio` computed `text_width("MMMM") / 2`, which is exact for a
    half-width-Latin face and defines the answer into existence for any other: it returns
    whatever value makes `M` half-width. On `yuminl.ttf` that gave 0.3890 against a true
    0.7305, so the report's invisible text layer was written at 1.92x the size of the
    glyphs it sits over — measured end-to-end as a width ratio of 1.920 against ezdxf's own ink,
    and 1.026 once fixed. It also pushed strings past the page rect, where `TextWriter` dropped
    six of them from the layer entirely.

    Nothing looked wrong on the page, because an invisible layer cannot look wrong. The only
    symptom was a selection rectangle twice the width of its text.

    The two MS faces are asserted UNCHANGED to the sixth decimal: they are half-width, so the
    old estimate was right for them, and `tools/render_audit.py` calls this with `msgothic.ttc`
    and has committed baselines that must not move.
    """
    from services.backend.infrastructure.rendering.text_placement import cap_height_ratio

    ezdxf_fonts = pytest.importorskip("ezdxf.fonts.fonts")
    for face, expected in (("msgothic.ttc", 0.761719), ("MSMINCHO.TTF", 0.667969)):
        if ezdxf_fonts.font_manager.has_font(face):
            assert cap_height_ratio(face) == pytest.approx(expected, abs=1e-6), (
                f"{face} is half-width Latin; its ratio is pinned by render_audit's baselines"
            )

    if not ezdxf_fonts.font_manager.has_font("yuminl.ttf"):
        pytest.skip("Yu Mincho Light is not installed on this machine")

    ratio = cap_height_ratio("yuminl.ttf")
    assert ratio == pytest.approx(0.7305, abs=5e-4)
    # The specific wrong answer, named so a regression is recognisable rather than merely red.
    assert ratio != pytest.approx(0.3890, abs=5e-4)


def test_the_report_face_is_not_the_ingestion_faces():
    """The export renders Mincho to match the canvas; ingestion must stay on MS Gothic.

    Not a style preference: the ingestion raster produces `render_bounds`, which every zone
    template stores its boxes as fractions of and `zone_signature` derives a sheet's identity
    from. Changing the face there moves all of them at once. The two are separated on purpose,
    so a change to one must not quietly become a change to the other.
    """
    from services.backend.infrastructure.rendering.dxf_render_setup import (
        JAPANESE_FONT_CANDIDATES,
    )

    assert Path(REPORT_FONT_CANDIDATES[0]).name != Path(JAPANESE_FONT_CANDIDATES[0]).name


def test_the_text_layer_uses_the_report_face(page):
    """The invisible layer must be set in the SAME face the geometry pass drew.

    Only the text layer shows up in `get_fonts()` — ezdxf's glyphs are paths and embed nothing —
    so this asserts the half that is assertable. A mismatch here is a highlight rectangle that
    does not line up with the glyphs it selects.
    """
    resolved, path = resolve_report_font()
    if not resolved:
        pytest.skip("no report font installed on this machine")
    stem = Path(path).stem.replace("-", " ").lower()
    embedded = " ".join(f[3] for f in page.get_fonts()).lower()
    assert "mincho" in embedded or stem[:4] in embedded, (
        f"text layer embeds {embedded!r}, expected the report face {resolved!r}"
    )


# ---------------------------------------------------------------------------
# Lineweight
# ---------------------------------------------------------------------------


def _sheet_with_lineweights(root: Path, name: str, lwdisplay: int) -> Path:
    """A sheet carrying real pen weights, and a `$LWDISPLAY` flag saying whether to show them."""
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$LWDISPLAY"] = lwdisplay
    msp = doc.modelspace()
    # 1.00 mm frame, 0.50 mm and 0.25 mm detail — the three weights this corpus actually uses.
    msp.add_lwpolyline([(0, 0), (400, 0), (400, 280), (0, 280), (0, 0)],
                       close=True, dxfattribs={"lineweight": 100})
    msp.add_line((20, 20), (380, 20), dxfattribs={"lineweight": 50})
    msp.add_line((20, 40), (380, 40), dxfattribs={"lineweight": 25})
    path = root / name
    doc.saveas(path)
    return path


def _stroke_widths(pdf_bytes: bytes) -> set[float]:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return {
            round(op["width"], 3)
            for op in doc[0].get_drawings()
            if op.get("width") is not None and op.get("type") in ("s", "fs")
        }


def test_lwdisplay_off_draws_hairlines(storage_root):
    """`$LWDISPLAY` is 0 across this corpus, and ezdxf ignores it entirely.

    Lineweight is a *plotting* property, and the flag is the drawing's own statement about
    whether to show it. A CAD viewer, a plot preview and `renderEntities.ts` all draw hairlines;
    ezdxf's `addons/drawing` has no reference to `$LWDISPLAY` anywhere and applies
    `LineweightPolicy.ABSOLUTE` unconditionally, which put the DXF's real 0.25/0.50/1.00 mm pen
    weights on the report — measured as 0.72 pt and 1.00 pt strokes against a canvas drawing
    every one of them as a hairline.
    """
    pdf = render_vector_sheet(_sheet_with_lineweights(storage_root, "lw_off.dxf", 0))
    widths = _stroke_widths(pdf)
    assert widths, "no strokes on the page at all"
    assert max(widths) <= 0.6, f"expected hairlines, got {sorted(widths)} pt"


def test_lwdisplay_on_honours_the_pen_weights(storage_root):
    """The hairline is conditional, not hardcoded.

    A drawing that asks for its lineweights gets them — otherwise this would be a blanket
    override dressed up as honouring a flag, and a sheet whose weights carry meaning would print
    flat with nothing to show it.
    """
    pdf = render_vector_sheet(_sheet_with_lineweights(storage_root, "lw_on.dxf", 1))
    widths = _stroke_widths(pdf)
    assert max(widths) > 0.6, f"pen weights were flattened anyway: {sorted(widths)} pt"


def test_min_lineweight_is_converted_as_points_not_thirtieths_of_an_inch(storage_root):
    """`Configuration.min_lineweight` documents itself as 1/300 inch. It is NOT, here.

    Measured through `MatplotlibBackend`, the value passes straight through as PDF points
    (0.25 -> 0.25 pt, 1.0 -> 1.0, 2.0 -> 2.0). Trusting the docstring produced 1.535 pt strokes
    for a 0.13 mm hairline — twice as thick as the weights it replaced, which reads as the
    setting having had no effect rather than as the wrong unit.
    """
    from services.backend.infrastructure.rendering import vector_pdf_exporter as exporter

    pdf = render_vector_sheet(_sheet_with_lineweights(storage_root, "lw_unit.dxf", 0))
    expected_pt = exporter._HAIRLINE_MM * 72.0 / 25.4
    assert min(_stroke_widths(pdf)) == pytest.approx(expected_pt, abs=0.02)


def _sheet_with_a_dimension(root: Path, name: str) -> Path:
    """A part line with a linear dimension measuring it."""
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$LWDISPLAY"] = 0
    msp = doc.modelspace()
    msp.add_line((20, 20), (380, 20), dxfattribs={"lineweight": 50})
    msp.add_lwpolyline([(0, 0), (400, 0), (400, 280), (0, 280), (0, 0)],
                       close=True, dxfattribs={"lineweight": 100})
    msp.add_linear_dim(base=(20, 60), p1=(20, 20), p2=(380, 20)).render()
    path = root / name
    doc.saveas(path)
    return path


def test_dimensions_are_drawn_thinner_than_the_part(storage_root):
    """A dimension must not print as loudly as the thing it measures.

    Until 2026-08-25 it did: `_lineweight_settings` used `lineweight_scaling: 0.0`, which
    collapses every stroke onto `min_lineweight`, so the sheet had exactly one width and no
    depth. ISO 128 puts dimension and witness lines on the thin pen.

    This is also the guard for a failure that looks like the feature is merely off. A
    DIMENSION renders through `draw_composite_entity`, which re-resolves properties for each
    virtual child, so an override keyed on `entity.dxftype()` alone thins the DIMENSION and then
    resets every line it is made of. The first implementation did exactly that and produced one
    width, as before. Asserting "two widths exist and the thin one is in the majority of the
    dimension's own strokes" is what distinguishes a working override from an inert one.
    """
    from services.backend.infrastructure.rendering import vector_pdf_exporter as exporter

    widths = _stroke_widths(render_vector_sheet(_sheet_with_a_dimension(storage_root, "dim.dxf")))
    part_pt = exporter._HAIRLINE_MM * 72.0 / 25.4
    dim_pt = exporter._DIMENSION_HAIRLINE_MM * 72.0 / 25.4

    assert len(widths) >= 2, (
        f"only one stroke width on a sheet with a dimension ({sorted(widths)} pt) — the pen "
        "override is inert, most likely reset on the dimension's virtual children"
    )
    assert min(widths) == pytest.approx(dim_pt, abs=0.02), (
        f"thinnest stroke {min(widths)} pt is not the dimension pen ({dim_pt:.4f} pt)"
    )
    assert max(widths) == pytest.approx(part_pt, abs=0.02), (
        f"thickest stroke {max(widths)} pt is not the part pen ({part_pt:.4f} pt)"
    )
    assert dim_pt < part_pt


def test_the_part_pen_is_unchanged_by_the_dimension_split(storage_root):
    """Thinning dimensions must not have moved the part's own width.

    The switch away from `lineweight_scaling: 0.0` re-routed every stroke on the sheet, so this
    pins the half that was supposed to stay still: 0.13 mm x 72/25.4 = 0.3685 pt, the same
    stroke the old collapse produced. A sheet with no annotation on it must be byte-for-byte the
    drawing it was before.
    """
    from services.backend.infrastructure.rendering import vector_pdf_exporter as exporter

    widths = _stroke_widths(render_vector_sheet(
        _sheet_with_lineweights(storage_root, "lw_part_only.dxf", 0)))
    assert len(widths) == 1, f"a sheet with no annotation should have one pen, got {widths}"
    assert widths.pop() == pytest.approx(exporter._HAIRLINE_MM * 72.0 / 25.4, abs=0.001)


# ---------------------------------------------------------------------------
# The text layer as the VISIBLE copy (`TextSource.LAYER`)
#
# Everything above this line tests the layer while it is invisible, where being in the wrong
# place or the wrong colour costs nothing you can see. These pin the two defects that were
# waiting in it -- both found by rasterising the page and looking at it, neither detectable by
# any assertion about the text itself.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rotated_dxf(storage_root) -> Path:
    """Two identical-width strings from ONE insert point, rotated +90 and -90.

    Same length on purpose: it makes the assertion a pure comparison between the two, with no
    dependency on the anchor fractions, the fit scale, or the page transform.
    """
    doc = ezdxf.new("R2010", setup=True)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (400, 0), (400, 280), (0, 280), (0, 0)], close=True)
    msp.add_text("AAA", height=8, dxfattribs={"rotation": 90}).set_placement((200, 140))
    msp.add_text("BBB", height=8, dxfattribs={"rotation": -90}).set_placement((200, 140))
    path = storage_root / "rotated.dxf"
    doc.saveas(path)
    return path


def _spans(pdf: bytes) -> list[dict]:
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        return [span
                for block in doc[0].get_text("dict")["blocks"]
                for line in block.get("lines", [])
                for span in line["spans"]]


def test_the_visible_text_layer_is_black(sheet_dxf):
    """White is `TextWriter.write_text`'s default colour, and it is not a colour paper shows.

    The layer spent its whole life at render mode 3, so its colour was never painted and never
    asserted. Made visible without stating the ink, the page extracts 2600 characters, answers
    every `search_for`, counts the right number of spans -- and is blank.
    """
    from services.backend.infrastructure.rendering.vector_pdf_exporter import TextSource

    spans = _spans(render_vector_sheet(sheet_dxf, text_source=TextSource.LAYER))
    assert spans, "no text on the page at all"
    white = [s for s in spans if s["color"] == 0xFFFFFF]
    assert not white, f"{len(white)} of {len(spans)} spans are white on white paper"


def test_a_rotated_string_turns_the_way_cad_turns(rotated_dxf):
    """+90 deg must read bottom-to-top, which on a y-down page means UP from the insert point.

    `morph` applies its matrix in the opposite sense to the one the operand order suggests, so
    the natural-looking rotation matrix turns every string by MINUS its rotation. The result is
    a string at a plausible angle, displaced by its own length -- measured at |d| median 6.9
    drawing units against 0.10 for unrotated strings, on a sheet with 72 rotated ones.

    Asserted as a comparison between the two strings rather than against a coordinate: with the
    sign wrong they simply swap, and nothing about the page size or the anchor model matters.
    """
    from services.backend.infrastructure.rendering.vector_pdf_exporter import TextSource

    spans = _spans(render_vector_sheet(rotated_dxf, text_source=TextSource.LAYER))
    up = next(s for s in spans if "A" in s["text"])
    down = next(s for s in spans if "B" in s["text"])

    up_y = (up["bbox"][1] + up["bbox"][3]) / 2
    down_y = (down["bbox"][1] + down["bbox"][3]) / 2
    assert up_y < down_y, (
        f"the +90 deg string sits at y={up_y:.1f} and the -90 deg one at y={down_y:.1f}; "
        "PDF y grows downward, so the rotation is inverted"
    )


def test_layer_is_refused_when_a_dimension_cannot_place_its_text():
    """A stale extraction must not get the visible layer -- silently, and without failing.

    `render_text_point` arrived at `EXTRACTION_SCHEMA_VERSION` 3. Below it `_text_items` falls
    back to the midpoint of the dimension LINE, which is harmless under drawn glyphs and is the
    wrong place for the visible value. The request degrades rather than raising, because a
    slower correct page beats a fast wrong one and beats an error.
    """
    from services.backend.infrastructure.rendering.vector_pdf_exporter import (
        TextSource,
        _resolve_text_source,
    )

    fresh = [{"entity_type": "dimension", "properties": {"render_text": "40"},
              "geometry": {"render_text_point": [1.0, 2.0], "text_point": [9.0, 9.0]}}]
    stale = [{"entity_type": "dimension", "properties": {"render_text": "40"},
              "geometry": {"text_point": [9.0, 9.0]}}]

    assert _resolve_text_source(TextSource.LAYER, fresh) is TextSource.LAYER
    assert _resolve_text_source(TextSource.LAYER, stale) is TextSource.OUTLINES
    # A request for OUTLINES is never upgraded, whatever the payload can do.
    assert _resolve_text_source(TextSource.OUTLINES, fresh) is TextSource.OUTLINES


def test_outlines_remains_the_default(sheet_dxf):
    """The visible layer is opt-in. Nothing that has not asked for it changes."""
    contents = b""
    with fitz.open(stream=render_vector_sheet(sheet_dxf), filetype="pdf") as doc:
        contents = doc[0].read_contents()
    assert b"3 Tr" in contents, "the default export stopped writing an invisible layer"


# ---------------------------------------------------------------------------
# Strings the layer cannot reproduce, which ezdxf must keep drawing
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def toleranced_dxf(storage_root) -> Path:
    r"""A sheet whose one dimension carries an asymmetric tolerance.

    ezdxf composes `dimtp`/`dimtm` into a STACKED FRACTION at render time — the MTEXT comes out
    as `200{\H0.50x;\S+0.10^ -0.20;}` — so the tolerance exists in neither the DXF's `text`
    attribute nor anything extraction can store. That is the whole reason for the deferral.
    """
    doc = ezdxf.new("R2010", setup=True)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (400, 0), (400, 280), (0, 280), (0, 0)], close=True)
    msp.add_text(LATIN, height=8).set_placement((20, 250))
    dim = msp.add_linear_dim(base=(0, 150), p1=(100, 100), p2=(300, 100),
                             override={"dimtol": 1, "dimtp": 0.1, "dimtm": 0.2, "dimtxt": 8})
    dim.render()
    path = storage_root / "toleranced.dxf"
    doc.saveas(path)
    return path


def test_a_tolerance_is_deferred_to_ezdxf_under_layer(toleranced_dxf):
    """The stacked fraction is drawn by ezdxf, and its handle comes back so it can be skipped."""
    from services.backend.infrastructure.rendering.vector_pdf_exporter import (
        TextSource,
        _render_geometry,
        A4_LANDSCAPE,
    )

    *_, deferred = _render_geometry(toleranced_dxf, A4_LANDSCAPE, TextSource.LAYER)
    assert deferred, "the toleranced dimension was left to a text layer that cannot draw it"


def test_outlines_defers_nothing_because_ezdxf_draws_everything(toleranced_dxf):
    """The deferral set is meaningful only under `LAYER`; `OUTLINES` has nothing to skip."""
    from services.backend.infrastructure.rendering.vector_pdf_exporter import (
        TextSource,
        _render_geometry,
        A4_LANDSCAPE,
    )

    *_, deferred = _render_geometry(toleranced_dxf, A4_LANDSCAPE, TextSource.OUTLINES)
    assert deferred == frozenset()


def test_a_deferred_string_is_not_also_written_by_the_layer(toleranced_dxf):
    """The double-strike guard, which is the failure mode this pairing exists to avoid.

    Both halves drawn is every character struck twice in two typefaces; neither is a value
    missing from the sheet. `_text_items` must drop exactly the handles `_render_geometry`
    reports and no others.
    """
    from services.backend.infrastructure.cad.dxf_parser import DXFParser
    from services.backend.infrastructure.rendering.vector_pdf_exporter import (
        TextSource,
        _render_geometry,
        _text_items,
        A4_LANDSCAPE,
    )

    entities = DXFParser().parse_file(toleranced_dxf)[0]
    *_, deferred = _render_geometry(toleranced_dxf, A4_LANDSCAPE, TextSource.LAYER)

    kept = _text_items(entities, skip_handles=deferred)
    everything = _text_items(entities)
    assert len(kept) < len(everything), "nothing was skipped, so the tolerance is struck twice"

    dropped = {e["properties"]["handle"] for e in entities
               if (e.get("properties") or {}).get("handle") in deferred}
    assert dropped, "the deferred handles do not correspond to any extracted entity"
    # …and only those: every other string survives.
    assert len(everything) - len(kept) <= len(dropped)


def test_the_unreproducible_codes_are_the_raw_mtext_ones(toleranced_dxf):
    """These are matched against RAW MTEXT, which only exists at render time.

    `strip_mtext` runs during extraction, so a stored string never carries them — a check
    written against `properties.text` would match nothing and defer nothing, silently.
    """
    from services.backend.infrastructure.rendering.vector_pdf_exporter import (
        _UNREPRODUCIBLE_MTEXT,
    )
    from services.backend.infrastructure.utils.text import strip_mtext

    for code in _UNREPRODUCIBLE_MTEXT:
        assert code.startswith("\\") and len(code) == 2, f"{code!r} is not an MTEXT inline code"
        assert code not in strip_mtext(f"{code}sample", convert_symbols=False), (
            f"{code!r} survives extraction, so this set could have been checked there"
        )
