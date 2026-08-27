"""Guards for the vector-sheet export route.

The renderer itself is covered by `test_vector_pdf_export.py`; this file is about the route's
refusals. Each one exists because the alternative is a PDF that looks fine:

* a non-DXF drawing reaches the same room and the same report button, and has no DXF to render;
* a drawing still extracting has no entities, so it would render as a correct-looking page with
  an empty text layer and nothing anywhere would say the text was missing;
* a renderer crash must not return a truncated PDF, which opens in some viewers and not others
  and therefore reads as the reader's problem.

Route functions are called directly, matching `test_drawings_router_error_handling.py`.
"""

from pathlib import Path

import pytest
from fastapi import HTTPException

from services.backend.api.routers import export
from services.backend.api.routers.export import (
    MarkerPayload,
    VectorSheetRequest,
    export_vector_sheet,
)

pytestmark = pytest.mark.asyncio

PDF_BYTES = b"%PDF-1.4\n%stub\n"


class _Drawing:
    def __init__(self, fmt="dxf", file_path="uploads/sheet.dxf", file_name="M745221N01.dxf"):
        self.format = fmt
        self.file_path = file_path
        self.file_name = file_name


class _Entity:
    def __init__(self, text="SS400"):
        self.entity_type = "text"
        self.properties = {"text": text, "height": 5.0, "attachment_point": 7}
        self.geometry = {"location": [10.0, 20.0]}


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Route dependencies stubbed; returns a dict recording what the renderer was handed."""
    source = tmp_path / "sheet.dxf"
    source.write_bytes(b"dxf")
    seen: dict = {}

    async def fake_get_or_404(model, id, detail, projection=None):
        return seen.get("drawing", _Drawing())

    async def fake_load_entities(drawing_id):
        return seen.get("entities", [_Entity()])

    def fake_render(path, *, entities, markers, page, text_source=None):
        seen.update(path=path, entities=entities, markers=markers, page=page,
                    text_source=text_source)
        return PDF_BYTES

    monkeypatch.setattr(export, "get_or_404", fake_get_or_404)
    monkeypatch.setattr(export, "load_entities", fake_load_entities)
    monkeypatch.setattr(export, "sandboxed_path", lambda p: source)
    monkeypatch.setattr(export, "render_vector_sheet", fake_render)
    seen["source"] = source
    return seen


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


async def test_a_non_dxf_drawing_is_refused(wired):
    """PDF- and STEP-sourced drawings reach the same room and the same report button."""
    wired["drawing"] = _Drawing(fmt="pdf")
    with pytest.raises(HTTPException) as err:
        await export_vector_sheet("d1", VectorSheetRequest())
    assert err.value.status_code == 422
    assert "pdf" in err.value.detail


async def test_a_drawing_with_no_stored_file_is_refused(wired):
    wired["drawing"] = _Drawing(file_path="")
    with pytest.raises(HTTPException) as err:
        await export_vector_sheet("d1", VectorSheetRequest())
    assert err.value.status_code == 422


async def test_a_missing_source_file_is_refused(wired, monkeypatch, tmp_path):
    monkeypatch.setattr(export, "sandboxed_path", lambda p: tmp_path / "gone.dxf")
    with pytest.raises(HTTPException) as err:
        await export_vector_sheet("d1", VectorSheetRequest())
    assert err.value.status_code == 422


async def test_a_drawing_still_extracting_is_a_conflict_not_a_blank_page(wired):
    """409, never a 200 with an empty text layer.

    An un-extracted drawing still renders perfectly good geometry — the DXF is right there. The
    only thing missing would be every searchable string, which no viewer reports.
    """
    wired["entities"] = []
    with pytest.raises(HTTPException) as err:
        await export_vector_sheet("d1", VectorSheetRequest())
    assert err.value.status_code == 409


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


async def test_returns_a_pdf_with_a_download_name(wired):
    response = await export_vector_sheet("d1", VectorSheetRequest())
    assert response.body == PDF_BYTES
    assert response.media_type == "application/pdf"
    assert "M745221N01-sheet.pdf" in response.headers["content-disposition"]


async def test_the_stored_entities_are_rendered_not_a_fresh_parse(wired):
    """The report must describe the extraction the ENGINEER saw.

    36 of 55 stored drawings are at a stale `EXTRACTION_SCHEMA_VERSION`. Letting the renderer
    re-parse would give those a text layer their own canvas never had, and the report would
    quietly disagree with the review it documents.
    """
    await export_vector_sheet("d1", VectorSheetRequest())
    assert wired["entities"] == [
        {"entity_type": "text",
         "properties": {"text": "SS400", "height": 5.0, "attachment_point": 7},
         "geometry": {"location": [10.0, 20.0]}}
    ]


async def test_markers_reach_the_renderer_in_cad_coordinates(wired):
    request = VectorSheetRequest(
        markers=[MarkerPayload(x=12.5, y=34.5, status="CHANGED", label="125 -> 130")]
    )
    await export_vector_sheet("d1", request)
    (marker,) = wired["markers"]
    assert (marker.x, marker.y, marker.status, marker.label) == (
        12.5, 34.5, "CHANGED", "125 -> 130")


async def test_page_size_defaults_to_a4_landscape(wired):
    await export_vector_sheet("d1", VectorSheetRequest())
    assert (wired["page"].width_mm, wired["page"].height_mm) == (297.0, 210.0)


async def test_a_custom_page_size_is_passed_through(wired):
    await export_vector_sheet(
        "d1",
        VectorSheetRequest(page_width_mm=420.0, page_height_mm=297.0, margin_mm=5.0),
    )
    assert (wired["page"].width_mm, wired["page"].margin_mm) == (420.0, 5.0)


async def test_a_half_specified_page_falls_back_to_the_default(wired):
    """Width without height is not a page. Silently using it would print at the wrong aspect."""
    await export_vector_sheet("d1", VectorSheetRequest(page_width_mm=420.0))
    assert wired["page"].width_mm == 297.0


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


async def test_a_renderer_crash_is_a_500_that_leaks_nothing(wired, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("matplotlib blew up with /secret/path/detail")

    monkeypatch.setattr(export, "render_vector_sheet", boom)
    with pytest.raises(HTTPException) as err:
        await export_vector_sheet("d1", VectorSheetRequest())
    assert err.value.status_code == 500
    assert "secret" not in err.value.detail


async def test_an_http_exception_from_the_renderer_passes_through(wired, monkeypatch):
    """`render_vector_sheet` sandboxes its path and raises 400 on an escape.

    Rewrapping that as a 500 would report a rejected path as a server fault — the exact
    contract violation `validate_sandboxed_path` was fixed for.
    """
    def refuse(*args, **kwargs):
        raise HTTPException(status_code=400, detail="Access Denied: Path escapes the sandbox.")

    monkeypatch.setattr(export, "render_vector_sheet", refuse)
    with pytest.raises(HTTPException) as err:
        await export_vector_sheet("d1", VectorSheetRequest())
    assert err.value.status_code == 400


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.filterwarnings("ignore")
async def test_the_route_is_authenticated():
    """This repo has shipped an auth dependency that was a no-op stub returning a fixed token.

    Asserted on the route object rather than on the source, so deleting the dependency fails
    here even if the decorator still mentions it.
    """
    from services.backend.api.dependencies import get_auth_token

    route = next(
        r for r in export.router.routes
        if getattr(r, "path", "") == "/export/drawings/{drawing_id}/vector-sheet"
    )
    assert get_auth_token in [d.call for d in route.dependant.dependencies]


async def test_the_report_asks_for_the_visible_text_layer(wired):
    """The route requests `TextSource.LAYER`, which is where the export's speed comes from.

    Measured on the six densest sheets in `storage/uploads`: **3.4x to 8.0x** end-to-end, and a
    change in how the export SCALES rather than a constant — ezdxf spends ~44 ms per string
    against the layer's 2.18 ms, and an assembly is a lot of strings.

    Pinned because it is a REQUEST that silently degrades: `_resolve_text_source` downgrades it
    to `OUTLINES` for a drawing whose extraction cannot place every string, so a report that
    quietly stopped asking would look identical and just be slow again.
    """
    from services.backend.infrastructure.rendering.vector_pdf_exporter import TextSource

    await export_vector_sheet("d1", VectorSheetRequest())
    assert wired["text_source"] is TextSource.LAYER
