"""The radius/diameter leader check in `tools/render_audit.py`.

Built to answer one question a screenshot kept getting wrong: *does a radial callout's pointer
arrive?* The census cannot answer it -- a dimension that draws one of its four paths still counts
as `drawn` -- so 490/518 stays green while a leader is missing.

The load-bearing test here is `test_a_one_arrow_callout_is_never_reported_short`. The first
version of this harness flagged anything reaching under 95% of the way to the centre and reported
36 of 92 radial dimensions SHORT across the corpus. That threshold came from a single sheet,
and sweeping `storage/uploads` refuted it: a one-arrow callout's leader length is set by where the
CAD put its text, so the rule condemned every one of them. Only the two-arrow form carries an
invariant. A checker that cries wolf is how a real regression gets waved through.
"""

import math

import ezdxf
import pytest

from tools.render_audit import (
    _ARROWS_AT_BOTH_ENDS,
    _DIM_KIND_DIAMETER,
    _DIM_KIND_MASK,
    _DIM_KIND_RADIUS,
    _radial_geometry,
    radial_leader_rows,
)

CIRCLE_CENTRE = (10.0, 20.0)
CIRCLE_RADIUS = 25.0


@pytest.fixture
def doc_with_radial_dims():
    """A document carrying one diameter and one radius callout, each rendered to a real block."""
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_circle(CIRCLE_CENTRE, radius=CIRCLE_RADIUS)
    msp.add_diameter_dim(
        center=CIRCLE_CENTRE, radius=CIRCLE_RADIUS, angle=45, dimstyle="EZ_RADIUS"
    ).render()
    msp.add_radius_dim(
        center=(80.0, 20.0), radius=15.0, angle=30, dimstyle="EZ_RADIUS"
    ).render()
    msp.add_linear_dim(base=(0, -10), p1=(0, 0), p2=(40, 0)).render()
    return doc


def _row(rows, kind):
    matches = [r for r in rows if r["kind"] == kind]
    assert len(matches) == 1, f"expected exactly one {kind} row, got {len(matches)}"
    return matches[0]


def test_both_radial_kinds_are_found_and_a_linear_dimension_is_not(doc_with_radial_dims):
    rows = radial_leader_rows(doc_with_radial_dims)
    assert sorted(r["kind"] for r in rows) == ["diameter", "radius"]


def test_the_implied_length_is_the_radius_for_both_kinds(doc_with_radial_dims):
    """A diameter callout's `defpoint`/`defpoint4` are the two ENDS of the diameter.

    Its centre is therefore their midpoint, and the implied leader is the radius -- not the
    measurement. On M745221N01 the two sheets author the same ⌀125 as a diameter dimension
    (`actual_measurement` 125.0) and a radius one (62.5); both imply the same 62.50 here, which
    is what makes the two comparable at all.
    """
    rows = radial_leader_rows(doc_with_radial_dims)
    assert _row(rows, "diameter")["implied"] == pytest.approx(CIRCLE_RADIUS)
    assert _row(rows, "radius")["implied"] == pytest.approx(15.0)


def test_the_centre_of_a_diameter_callout_is_the_midpoint_of_its_defpoints(doc_with_radial_dims):
    for dim in doc_with_radial_dims.modelspace():
        if dim.dxftype() != "DIMENSION":
            continue
        if (int(dim.dxf.dimtype) & _DIM_KIND_MASK) != _DIM_KIND_DIAMETER:
            continue
        centre, arc = _radial_geometry(dim)
        assert math.dist(centre, CIRCLE_CENTRE) == pytest.approx(0.0, abs=1e-6)
        assert math.dist(centre, arc) == pytest.approx(CIRCLE_RADIUS)
        return
    pytest.fail("the fixture carried no diameter dimension")


def test_a_linear_dimension_has_no_radial_geometry(doc_with_radial_dims):
    linear = [
        d for d in doc_with_radial_dims.modelspace()
        if d.dxftype() == "DIMENSION"
        and (int(d.dxf.dimtype) & _DIM_KIND_MASK) not in (_DIM_KIND_DIAMETER, _DIM_KIND_RADIUS)
    ]
    assert linear, "the fixture carried no linear dimension"
    assert all(_radial_geometry(d) is None for d in linear)


def test_a_one_arrow_callout_is_never_reported_short(doc_with_radial_dims):
    """The negative result this harness exists to hold on to.

    A one-arrow callout's leader runs as far as its text placement asks and no further, including
    reach 0.0 when it points away from the centre with the value outside the circle. Measured
    across `storage/uploads`: 84 of the 92 radial dimensions are this form, spanning 0.000 to
    1.742 of the radius, on 12 distinct drawings. None of them is a defect.
    """
    rows = radial_leader_rows(doc_with_radial_dims)
    one_arrow = [r for r in rows if r["arrowheads"] < _ARROWS_AT_BOTH_ENDS]
    assert one_arrow, "the fixture produced no one-arrow callout"
    assert not any(r["short"] for r in one_arrow)


def test_the_dimtype_flag_bits_are_masked_off():
    """`dimtype` carries flags above the kind: 32 = block owned, 128 = user-positioned text.

    M745221N01 stores 163 and 164 -- diameter and radius with both flags set. Comparing the raw
    value against 3 and 4 finds neither, which would make this whole check silently report zero
    rows on the very sheet it was built for.
    """
    assert 163 & _DIM_KIND_MASK == _DIM_KIND_DIAMETER
    assert 164 & _DIM_KIND_MASK == _DIM_KIND_RADIUS
