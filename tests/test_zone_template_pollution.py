"""Regression: a zone-template save must not persist non-zone keys.

The zones *response* object (schemas.py::DrawingZonesResponse) carries metadata like
"drawing_id" and "render_bounds" alongside the real zones. A save path that serialized that
object wholesale leaked those keys into the stored template — observed in the field as a
template applying 9 "zones" including 'drawing_id' and 'render_bounds', neither of which any
comparison consumes. Nothing broke, but the stored set was corrupt. The upsert request now
strips anything outside VALID_ZONE_KEYS; this pins that.
"""
from services.backend.api.routers.zone_templates import ZoneTemplateUpsertRequest
from services.backend.domain.models.zone_template import VALID_ZONE_KEYS


def _frac() -> dict:
    return {"xMin": 0.1, "xMax": 0.4, "yMin": 0.7, "yMax": 0.9}


def test_upsert_strips_non_zone_keys():
    req = ZoneTemplateUpsertRequest(
        name="polluted",
        zones={
            "bom": _frac(),
            "title": _frac(),
            "drawing_id": _frac(),      # not a zone — metadata leaked from the response object
            "render_bounds": _frac(),   # ditto
        },
    )
    assert set(req.zones) == {"bom", "title"}
    assert "drawing_id" not in req.zones
    assert "render_bounds" not in req.zones


def test_upsert_keeps_all_valid_zone_keys():
    req = ZoneTemplateUpsertRequest(zones={k: _frac() for k in VALID_ZONE_KEYS})
    assert set(req.zones) == set(VALID_ZONE_KEYS)


def test_valid_zone_keys_excludes_response_metadata():
    # Guards against someone widening the whitelist to the whole response shape.
    assert "drawing_id" not in VALID_ZONE_KEYS
    assert "render_bounds" not in VALID_ZONE_KEYS
