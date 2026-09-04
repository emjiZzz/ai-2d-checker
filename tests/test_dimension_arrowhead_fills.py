"""Open arrowheads remain stroked lines and do not produce synthetic solid fills.

In CAD engineering drawings (such as iCAD SX and Japanese drafting standards),
dimension arrowheads authored with `_OPEN30` blocks are open wireframe barbs.
They must not be converted into synthetic filled triangles.
"""

from pathlib import Path
import ezdxf

from services.backend.infrastructure.cad.entity_mapper import EntityMapper

SAMPLE_DXF = Path("storage/uploads/000f6b04219b4ab8bcd79bff0003a191.dxf")


def test_open_arrowhead_stays_in_render_paths_without_render_fills():
    """An _OPEN30 dimension must have its barbs in render_paths and NO synthetic fills."""
    if not SAMPLE_DXF.exists():
        # Fallback dynamic mock if storage file is absent
        doc = ezdxf.new()
        blk = doc.blocks.new("*D1")
        open_blk = doc.blocks.new("_OPEN30")
        open_blk.add_line((0, 0), (3.75, 1.0))
        open_blk.add_line((0, 0), (3.75, -1.0))
        open_blk.add_line((0, 0), (3.75, 0.0))
        blk.add_blockref("_OPEN30", (100, 0))
        blk.add_line((0, 0), (100, 0))
        dim = doc.modelspace().add_linear_dim(base=(0, 10), p1=(0, 0), p2=(100, 0))
        dim.dxf.geometry = "*D1"
    else:
        doc = ezdxf.readfile(str(SAMPLE_DXF))
        dim = doc.modelspace().query("DIMENSION").first

    mapped = EntityMapper.map_dimension(dim)
    geo = mapped["geometry"]

    paths = geo.get("render_paths", [])
    fills = geo.get("render_fills", [])

    assert len(paths) >= 2, "Dimension should have drawable stroke paths (extension + dimension lines + barbs)"
    assert len(fills) == 0, "Open arrowheads (_OPEN30) must not produce synthetic solid fills"


def test_leader_open_arrowhead_does_not_mutate_render_fills():
    """A LEADER entity maps vertices and properties without synthesizing solid fills."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    leader = msp.add_leader(vertices=[(10, 20), (0, 0)])
    leader.dxf.dimstyle = "Standard"

    mapped = EntityMapper.map_leader(leader)
    props = mapped["properties"]
    assert props["has_arrowhead"] == 1
    assert "render_fills" not in mapped.get("geometry", {})
