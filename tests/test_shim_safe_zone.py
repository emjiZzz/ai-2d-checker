"""
The `shim` zone must cover its own table, because nothing inside it is ever compared.

`shim` (シム表) is a SAFE zone like `tolerance`: assembly-thickness reference data, detected
and subtracted from `views`, never diffed as its own category. So a row the box fails to
reach does not merely land in the wrong zone — it falls through to the `drawing_views` pool
and is compared and marked, which is what a live review reported: `総厚サ 6mm` shown as
`[REMOVED] drawing views` on a table that is identical on both sides.

The cause was a cap smaller than the thing it capped. On M745227N01's reference the drawn
シム表 is 337.5 units tall on an 891-unit sheet (37.9%) and its anchor cluster spans 345.9
(38.8%), against `ZONE_MAX_LIMITS["shim"]` of 0.35. The box was clamped to exactly 311.8,
`_clamp_bbox` shrinks symmetrically, and the bottom row finished 35.8 units *below the bottom
edge of its own zone*.

No published number moves when this breaks. `M745227N01` is the only corpus pair carrying a
shim table and it is one of the six the runner skips for having no labels, so both baselines
are byte-identical either way. These tests are the only guard.
"""
from types import SimpleNamespace

from services.backend.infrastructure.audit.bom.zone_detector import (
    ZONE_MAX_LIMITS,
    detect_zones_by_content,
)

# The sheet and the table are the real measured geometry of M745227N01's reference, not a
# scaled model of it — the defect is a ratio between two of these numbers, and rescaling is
# exactly how you lose it.
SHEET_W, SHEET_H = 1260.0, 891.0

# 337.5 drawn / 891.0 sheet. The anchor cluster including the title row is 345.9 / 891.0.
REAL_TABLE_FRACTION = 337.5 / 891.0
REAL_CLUSTER_FRACTION = 345.9 / 891.0


def _text(x: float, y: float, t: str = "X"):
    return SimpleNamespace(
        entity_type="text", layer="0", properties={"text": t}, geometry={"insert": [x, y]}
    )


def _line(x1: float, y1: float, x2: float, y2: float):
    return SimpleNamespace(
        entity_type="line", layer="0", properties={},
        geometry={"start": [x1, y1], "end": [x2, y2]},
    )


# The drawn table, and the cell positions inside it, as measured on that sheet.
TABLE_X0, TABLE_X1 = 746.7, 986.7
TABLE_Y0, TABLE_Y1 = 292.4, 629.9

# The title sits above the top rule, the way the draughtsman draws it.
TITLE_ROW = (874.6, 657.0, "シム表")

# Row baselines, measured. The vertical axis is the one the defect lives on, so these are the
# real numbers: note the 75-unit step from the last body row (423.6) down to `設計組厚サ`,
# wider than the 44.55 growth radius, which is why the rules above are load-bearing.
ROW_YS = [609.9, 573.6, 536.1, 498.6, 461.1, 423.6, 348.6, 311.1]
BOTTOM_ROW_Y = 311.1  # `総厚サ 6mm` — the row the cap used to cut out of its own zone

# Column baselines, laid out across the measured table width at the growth radius. The real
# sheet carries a No./t/材質/一組分個数 grid here; the exact x's do not matter to this defect,
# only that the table is populated rather than a single column.
COL_XS = [766.7, 806.7, 846.7, 886.7, 926.7, 966.7]

CELL_TEXT = {609.9: "材質", 348.6: "設計組厚サ 5mm", 311.1: "総厚サ  6mm"}


def _sheet():
    """The sheet frame, the fully ruled シム表, and its cells at their measured positions."""
    entities = [
        _line(0.0, 0.0, SHEET_W, 0.0),
        _line(0.0, SHEET_H, SHEET_W, SHEET_H),
        _line(0.0, 0.0, 0.0, SHEET_H),
        _line(SHEET_W, 0.0, SHEET_W, SHEET_H),
    ]
    entities.append(_text(*TITLE_ROW))
    for y in ROW_YS:
        for x in COL_XS:
            entities.append(_text(x, y, CELL_TEXT.get(y, "SPCC")))

    # The table's own rules. `shim` grows with line geometry included (`exclude_lines` is
    # False for it) and this table is fully ruled on both sides of the real pair — the rules
    # are how the box reaches its lower rows at all, since the 75-unit gap between the last
    # body row and `設計組厚サ` is wider than the 44.55 growth radius.
    #
    # Drawn one segment per cell, which is how they arrive in the real DXF. It matters:
    # `_expand_bbox` tests a line's ENDPOINTS, not whether it passes through the box, so a
    # full-width rule contributes only its two far-apart ends and the box never catches it.
    columns = (TABLE_X0, 786.7, 826.7, 866.7, 906.7, 946.7, TABLE_X1)
    rows = (TABLE_Y0, 330.0, 367.5, 405.0, 442.5, 480.0, 517.5, 555.0, 592.5, TABLE_Y1)
    for y in rows:
        for x0, x1 in zip(columns, columns[1:]):
            entities.append(_line(x0, y, x1, y))
    for x in columns:
        for y0, y1 in zip(rows, rows[1:]):
            entities.append(_line(x, y0, x, y1))
    return entities


def _shim_box(entities):
    return detect_zones_by_content(entities).get("shim")


def test_the_height_cap_can_contain_a_real_shim_table():
    """A cap smaller than the table it caps is a silent truncation, not a limit."""
    _, max_h_frac = ZONE_MAX_LIMITS["shim"]
    assert max_h_frac > REAL_CLUSTER_FRACTION, (
        f"shim height cap {max_h_frac} is below the measured anchor cluster "
        f"{REAL_CLUSTER_FRACTION:.4f} of M745227N01's reference — the box will be clamped and "
        f"_clamp_bbox will shrink it symmetrically, dropping the bottom row out of its own zone"
    )


def test_shim_box_covers_its_own_bottom_row():
    """`総厚サ` is the row that was reported compared as a drawing dimension."""
    bbox = _shim_box(_sheet())

    assert bbox is not None, "shim zone not detected at all"
    assert bbox[1] <= TABLE_Y0, (
        f"shim box bottom {bbox[1]:.1f} is above the table's bottom row at y={TABLE_Y0} — that "
        f"row falls through to the drawing_views pool and gets compared, and shim is a SAFE "
        f"zone whose rows must never be compared"
    )
    assert bbox[3] >= TABLE_Y1, f"shim box top {bbox[3]:.1f} does not reach the header row"


def test_shim_box_covers_every_row_of_the_table():
    entities = _sheet()
    bbox = _shim_box(entities)
    assert bbox is not None

    uncovered = [
        (e.geometry["insert"], e.properties["text"])
        for e in entities
        if e.entity_type == "text"
        and TABLE_X0 <= e.geometry["insert"][0] <= TABLE_X1
        and TABLE_Y0 <= e.geometry["insert"][1] <= TABLE_Y1
        and not (
            bbox[0] <= e.geometry["insert"][0] <= bbox[2]
            and bbox[1] <= e.geometry["insert"][1] <= bbox[3]
        )
    ]
    assert not uncovered, f"shim rows outside their own zone box {bbox}: {uncovered}"


def test_a_title_field_inside_an_overreaching_tolerance_box_is_owned_by_title():
    """The safety property the orchestrator's safe-zone net rests on.

    That net drops any finding whose owning zone is `shim` or `tolerance`. It uses ownership
    rather than a bare box test because a box is not a claim: on M745227N01 the revision's
    detected `tolerance` box over-reaches into the title block and 7 real `title_block`
    findings sit inside it. `title` outranks `tolerance` in ZONE_PRECEDENCE, so they are
    claimed by `title` and survive. A naive "inside the tolerance box?" test would delete all
    seven — silently, which is the direction this system cannot detect.
    """
    from services.backend.infrastructure.audit.bom.zone_ownership import owner_of

    # The measured shape of the problem: a tolerance box covering the bottom strip, with the
    # title block inside it.
    regions = {
        "tolerance": (20.6, 5.6, 407.7, 59.2),
        "title": (196.0, 10.0, 407.7, 50.0),
    }
    # `津田`, `ZHR`, `1/3`, `2026/07/03` — real title-block fields, all inside both boxes.
    for x, y in ((232.3, 36.0), (246.8, 36.0), (261.2, 36.0), (282.0, 36.0)):
        assert owner_of(x, y, regions) == "title", (
            f"({x}, {y}) is claimed by {owner_of(x, y, regions)!r} rather than `title` — the "
            f"safe-zone net would drop a real title_block finding"
        )


def test_shim_box_does_not_swallow_drawing_content_clear_of_the_table():
    """The other direction: over-growth on a SAFE zone is a silent false negative.

    Anything the box covers is dropped from drawing_views with no finding to show for it, so
    raising the cap must not turn the box into a net over the drawing.
    """
    dim_y = TABLE_Y0 - 120.0
    entities = _sheet() + [_text(820.0, dim_y, "22.7")]
    bbox = _shim_box(entities)

    assert bbox is not None
    assert bbox[1] > dim_y, (
        f"shim box bottom {bbox[1]:.1f} reaches the dimension at y={dim_y} — content well "
        f"clear of the table is being silently dropped from drawing_views"
    )
