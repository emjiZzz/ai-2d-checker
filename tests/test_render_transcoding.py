"""Guards on the shared render preamble's byte-recovery pass.

`load_and_transcode` re-decodes latin-1 bytes as cp932 to recover Shift-JIS text. It used to
apply that to `INSERT.dxf.name` as well, which is a pointer into the block table rather than
text: the reference was renamed and the BLOCK record was not, so any block whose name carried
CJK bytes lost its referent and `Frontend.draw_layout` raised DXFStructureError. On this corpus
that killed the render for three DWGs, and the caller's except-branch then stored bounds
measured from a fraction of the entities -- a wrong number rather than an error.

See `docs/vault/06 - Gotchas & Debugging Lessons/Gotcha - Transcoding an INSERT Name Unlinks
Its Block.md`.
"""

from pathlib import Path

import ezdxf
import pytest

from services.backend.infrastructure.rendering.dxf_render_setup import load_and_transcode

# "ﾌﾞ" (halfwidth katakana FU + voiced mark) as UTF-8 on disk. These files are read latin-1 to
# preserve the bytes, so this is what the recovery pass has to turn back into text. Taken from
# the block name "1A1ﾌﾞﾋﾝ" in M745228N01R1A.dwg.
CJK_BYTES = "\uff8c\uff9e".encode("utf-8")
MARKER = "ZZCJKZZ"


def _save_with_raw_cjk(doc, path: Path) -> Path:
    """Write `doc`, replacing the ASCII marker with raw CJK bytes.

    ezdxf re-encodes on save, so a CJK string handed to it round-trips to something already
    decoded. Patching bytes afterwards is the only way to reproduce what a real translator
    writes. DXF group values carry no length prefix, so substitution is safe.
    """
    # The corpus is Shift-JIS. The recovery pass tries the document codepage before UTF-8, and
    # cp1252 (ezdxf's default when unset) decodes these bytes successfully into garbage -- so a
    # fixture that leaves the codepage alone silently exercises a different path.
    doc.encoding = "cp932"
    doc.saveas(str(path))
    path.write_bytes(path.read_bytes().replace(MARKER.encode("ascii"), CJK_BYTES))
    return path


def _dxf_with_cjk_block_name(tmp_path: Path) -> Path:
    doc = ezdxf.new("R12")
    block = doc.blocks.new(name=MARKER)
    block.add_line((0, 0), (10, 10))
    doc.modelspace().add_blockref(MARKER, (0, 0))
    return _save_with_raw_cjk(doc, tmp_path / "cjk_block.dxf")


def test_transcoding_leaves_every_insert_resolvable_to_a_block(tmp_path):
    doc = load_and_transcode(_dxf_with_cjk_block_name(tmp_path), None)

    defined = {b.name for b in doc.blocks}
    referenced = {
        e.dxf.name for layout in doc.layouts for e in layout if e.dxftype() == "INSERT"
    }

    dangling = referenced - defined
    assert not dangling, (
        f"INSERT names with no block definition: {dangling!r}. Transcoding a block reference "
        f"unlinks it from its definition; block names are identifiers, not text."
    )


def test_the_rendering_frontend_accepts_the_transcoded_document(tmp_path):
    """The end state the test above exists to protect: the layout actually draws."""
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    doc = load_and_transcode(_dxf_with_cjk_block_name(tmp_path), None)
    layout = doc.modelspace()

    fig = plt.figure()
    try:
        ax = fig.add_axes([0, 0, 1, 1])
        ctx = RenderContext(doc)
        ctx.set_current_layout(layout)
        # Raised DXFStructureError before the fix.
        Frontend(ctx, MatplotlibBackend(ax)).draw_layout(layout, finalize=True)
    finally:
        plt.close(fig)


def test_text_is_still_transcoded(tmp_path):
    """The rename removal must not have disabled the recovery this function exists for."""
    doc = ezdxf.new("R12")
    doc.modelspace().add_text(MARKER)
    path = _save_with_raw_cjk(doc, tmp_path / "cjk_text.dxf")

    loaded = load_and_transcode(path, None)
    texts = [e.dxf.text for e in loaded.modelspace() if e.dxftype() == "TEXT"]
    assert texts == ["\uff8c\uff9e"], texts
