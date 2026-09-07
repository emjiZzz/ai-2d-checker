"""
The `tolerance` zone must cover its table and stop there.

`tolerance` is a SAFE zone: it is never compared, it exists only so `views` can subtract it
(see VIEWS_EXCLUDED_ZONES). That makes over-growth silent and expensive — anything the box
swallows is dropped from the drawing_views comparison and never checked, with no finding to
show that it happened.

It grew on the isotropic CLUSTER_RADIUS with line geometry included, so the flood-fill hopped
along the sheet frame and the table's own rules. On both drawings of the M7452A1N01 pair it
blew out to BOTH caps exactly (0.95w x 0.30h — the signature of runaway growth, not a
detection) and reached ~150 units above the table, swallowing the `22.7±0.02` dimension, the
`6-6.6キリ11ザグリ深6.5` callout and the section marks. Now: wide-X/tight-Y radius, text only.
"""
from types import SimpleNamespace

from services.backend.infrastructure.audit.bom.zone_detector import detect_zones_by_content

SHEET_W, SHEET_H = 1000.0, 800.0


def _text(x: float, y: float, t: str = "X"):
    return SimpleNamespace(
        entity_type="text", layer="0", properties={"text": t}, geometry={"insert": [x, y]}
    )


def _line(x1: float, y1: float, x2: float, y2: float):
    return SimpleNamespace(
        entity_type="line", layer="0", properties={},
        geometry={"start": [x1, y1], "end": [x2, y2]},
    )


def _sheet():
    """A tolerance table in the bottom strip, the sheet frame, and drawing content above it."""
    entities = [
        # Sheet frame — the rules the flood-fill used to walk to the far corners.
        _line(0.0, 0.0, SHEET_W, 0.0),
        _line(0.0, SHEET_H, SHEET_W, SHEET_H),
        _line(0.0, 0.0, 0.0, SHEET_H),
        _line(SHEET_W, 0.0, SHEET_W, SHEET_H),
    ]
    # Tolerance table: anchored header plus a grid of cell values, x 40..600, y 20..90.
    entities.append(_text(40.0, 90.0, "Tolerances unless otherwise specified on the drawings"))
    entities.append(_text(40.0, 80.0, "roughness range"))
    for col in range(8):
        for row in range(6):
            entities.append(_text(40.0 + col * 80.0, 20.0 + row * 12.0, "0.05"))
        # Ruled column dividers running the full height of the table.
        entities.append(_line(40.0 + col * 80.0, 20.0, 40.0 + col * 80.0, 90.0))
    return entities


def _tolerance_box(entities):
    return detect_zones_by_content(entities).get("tolerance")


def test_tolerance_box_covers_its_own_table():
    bbox = _tolerance_box(_sheet())
    assert bbox is not None
    assert bbox[0] <= 40.0 and bbox[2] >= 600.0, f"table columns not covered: {bbox}"
    assert bbox[1] <= 20.0 and bbox[3] >= 90.0, f"table rows not covered: {bbox}"


def test_tolerance_box_does_not_reach_drawing_content_above_the_table():
    # A dimension 100 units clear of the top of the table. Swallowing it removes it from the
    # drawing_views pool entirely — the `22.7±0.02` case.
    entities = _sheet() + [_text(300.0, 190.0, "22.7")]
    bbox = _tolerance_box(entities)

    assert bbox is not None
    assert bbox[3] < 190.0, (
        f"tolerance box top {bbox[3]} reaches the dimension at y=190 — content above the "
        f"table is being silently dropped from drawing_views"
    )


def test_tolerance_box_does_not_blow_out_to_both_caps():
    # Growing to exactly 0.95w x 0.30h on a sheet whose table is a fraction of that is the
    # runaway-flood-fill signature, not a detection.
    bbox = _tolerance_box(_sheet())
    assert bbox is not None
    width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    assert width < 0.95 * SHEET_W, f"width pinned at the cap: {width}"
    assert height < 0.30 * SHEET_H, f"height pinned at the cap: {height}"


def test_tolerance_box_ignores_the_sheet_frame():
    # The frame alone must not drag the box to the sheet corners.
    bbox = _tolerance_box(_sheet())
    assert bbox is not None
    assert bbox[3] < SHEET_H * 0.5, f"box climbed the frame to {bbox[3]}"
