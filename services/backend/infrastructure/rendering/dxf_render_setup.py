"""Shared preamble for anything that renders a DXF through ezdxf's drawing add-on.

Four steps have to happen, in this order, before `Frontend.draw_layout` produces text that
matches what a CAD viewer shows. They were previously inline in `render_dxf_background`, which
made them unavailable to any second consumer -- and the second consumer that needed them most
was the render-fidelity harness (`tools/render_audit.py`), whose whole job is measuring text
placement against this exact configuration. A harness that configured fonts differently from the
renderer it audits would report differences that only exist in the harness.

The steps, and why each is load-bearing:

1. `configure_cad_fonts()` -- register Windows fonts with ezdxf's font manager and map the SHX
   names this corpus uses (`txt` + `extfont2` bigfont) onto MS Gothic. ezdxf cannot rasterise
   BigFont SHX glyphs at all, so without this every CJK string measures and draws as nothing or
   as tofu. **Must run before `readfile`.**
2. `load_and_transcode()` -- read as latin-1 to preserve the raw bytes, then re-decode as cp932
   to recover real Shift-JIS. See `dxf_parser.transcode_value` for the same trick on the
   extraction side; the two must agree or the raster and the vectors show different strings.
3. Text-style override, folded into step 2 -- point every SHX style at the TTF.
4. `select_render_layout()` -- pick the paper-space layout that actually contains a viewport,
   else model space. The extractor walks *every* layout, so this is the only record of which one
   "the drawing" means; see the `render_layout` metadata note in `dxf_background_renderer`.
"""

from pathlib import Path
from typing import Any

from ...logger import logger

JAPANESE_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msgothic.ttc",   # MS Gothic - best AutoCAD compatibility
    r"C:\Windows\Fonts\YuGothR.ttc",    # Yu Gothic Regular
    r"C:\Windows\Fonts\meiryo.ttc",     # Meiryo
    r"C:\Windows\Fonts\MSMINCHO.TTF",   # MS Mincho
]

# SHX font names seen on this corpus. `txt` is the stock stick font and `extfont2` is the
# BigFont carrying the CJK glyphs; ezdxf supports neither, so both are redirected to the TTF.
SHX_NAMES_TO_OVERRIDE = [
    "TXT", "TXT.SHX", "EXTFONT2", "EXTFONT2.SHX",
    "GOTHICJ", "GOTHICJ.SHX", "ROMANS", "ROMANS.SHX",
    "SIMPLEX", "SIMPLEX.SHX", "CHINESET", "CHINESET.SHX",
]


def configure_cad_fonts(configure_matplotlib: bool = True) -> str | None:
    """Register a CJK-capable TTF with ezdxf (and optionally matplotlib).

    Returns the font *filename* (e.g. ``msgothic.ttc``) for use in style overrides, or None if
    no candidate font exists on this machine. Must be called before `ezdxf.readfile`.

    `configure_matplotlib=False` is for consumers that never touch pyplot -- the recorder
    backend, for instance -- so they do not pay for the matplotlib import.
    """
    from ezdxf.fonts import fonts as ezdxf_fonts

    jp_font_path = next((c for c in JAPANESE_FONT_CANDIDATES if Path(c).exists()), None)
    if not jp_font_path:
        logger.warning("No Japanese font found. CJK characters may render as boxes.")
        return None

    logger.info(f"Japanese font found: {jp_font_path}")
    ezdxf_fonts.font_manager.scan_folder(Path(r"C:\Windows\Fonts"))
    jp_font_filename = Path(jp_font_path).name
    ezdxf_fonts.font_manager._fallback_font_name = jp_font_filename

    for shx_name in SHX_NAMES_TO_OVERRIDE:
        ezdxf_fonts.SHX_FONTS[shx_name] = jp_font_filename

    if configure_matplotlib:
        import matplotlib
        import matplotlib.font_manager as mpl_fm

        mpl_fm.fontManager.addfont(jp_font_path)
        jp_font_name = mpl_fm.FontProperties(fname=jp_font_path).get_name()
        matplotlib.rcParams["font.sans-serif"] = [jp_font_name, "DejaVu Sans", "sans-serif"]
        matplotlib.rcParams["font.family"] = "sans-serif"
        matplotlib.rcParams["axes.unicode_minus"] = False
        logger.info(f"Japanese font '{jp_font_name}' registered for ezdxf + matplotlib rendering.")

    return jp_font_filename


def _make_transcoder(doc: Any):
    """Byte-preserving latin-1 -> cp932 re-decode, matching the extraction side."""
    doc_encoding = getattr(doc, "encoding", "cp932") or "cp932"
    if doc_encoding.lower() in ("ansi_932", "cp932", "ms932", "shift_jis", "sjis"):
        doc_encoding = "cp932"

    def transcode_str(s: str) -> str:
        if not s:
            return ""
        decoded = s
        try:
            b = s.encode("latin1")
            for enc in (doc_encoding, "cp932", "utf-8", "latin-1"):
                if not enc:
                    continue
                try:
                    decoded = b.decode(enc)
                    break
                except Exception:
                    continue
        except Exception:
            pass

        # Replace all CP932 decoded multiplication signs with standard x.
        #
        # U+FF97 is halfwidth katakana RA and U+30E9 is fullwidth katakana RA: a DXF written
        # with "6x145" in the wrong codepage surfaces as one of those, so this recovers the
        # multiplication sign. It is lossy in the other direction -- a legitimate katakana RA
        # in a Japanese word becomes "x" -- but the raster path has always behaved this way and
        # `cleanCadText` in the frontend mirrors it, so changing it here alone would make the
        # two disagree. Left as-is deliberately.
        #
        # (The original spelled U+30E9 twice, once escaped and once literal. Same character.)
        decoded = decoded.replace("\uff97", "x")
        decoded = decoded.replace("\u30e9", "x")
        decoded = decoded.replace("\u00d7", "x")
        return decoded

    return transcode_str


def load_and_transcode(dxf_path: Path, jp_font_filename: str | None) -> Any:
    """Read a DXF preserving raw bytes, recover CJK text, and repoint SHX styles at the TTF.

    Raises ValueError if the file cannot be read either way.
    """
    import ezdxf

    try:
        doc = ezdxf.readfile(str(dxf_path), encoding="latin-1")
        logger.info(
            f"DXF loaded with latin-1. Header codepage: {doc.header.get('$DWGCODEPAGE')}"
        )
    except Exception as read_err:
        logger.warning(f"Latin-1 load failed: {read_err}")
        try:
            doc = ezdxf.readfile(str(dxf_path))
        except Exception as e:
            raise ValueError(f"Unable to read DXF file: {e}") from e

    transcode_str = _make_transcoder(doc)

    for layout in doc.layouts:
        for entity in layout:
            dxftype = entity.dxftype()
            if dxftype in ("TEXT", "MTEXT"):
                if hasattr(entity, "text"):
                    entity.text = transcode_str(entity.text)
                if hasattr(entity.dxf, "text"):
                    entity.dxf.text = transcode_str(entity.dxf.text)
            elif dxftype == "DIMENSION":
                if hasattr(entity.dxf, "text"):
                    entity.dxf.text = transcode_str(entity.dxf.text)
            elif dxftype == "INSERT":
                if hasattr(entity.dxf, "name"):
                    entity.dxf.name = transcode_str(entity.dxf.name)

    for block in doc.blocks:
        for entity in block:
            dxftype = entity.dxftype()
            if dxftype in ("TEXT", "MTEXT"):
                if hasattr(entity, "text"):
                    entity.text = transcode_str(entity.text)
                if hasattr(entity.dxf, "text"):
                    entity.dxf.text = transcode_str(entity.dxf.text)

    if jp_font_filename:
        for style in doc.styles:
            font = style.dxf.get("font", "")
            bigfont = style.dxf.get("bigfont", "")
            if font.upper().endswith(".SHX") or bigfont:
                style.dxf.font = jp_font_filename
                style.dxf.bigfont = ""
                logger.info(
                    f"Overriding DXF style {style.dxf.get('name', '?')!r}: "
                    f"{font!r}+{bigfont!r} -> {jp_font_filename}"
                )

    return doc


def select_render_layout(doc: Any) -> Any:
    """The one layout that means "the drawing".

    Paper space wins, but only if it holds a viewport looking into model space -- id 1 is the
    paper-space background itself and does not count. Otherwise model space.
    """
    for pl in (l for l in doc.layouts if l.name.lower() != "model" and len(l) > 0):
        if any(e.dxftype() == "VIEWPORT" and e.dxf.id != 1 for e in pl):
            logger.info(f"Rendering Paper Space layout (contains viewport): {pl.name}")
            return pl

    logger.info("No valid Paper Space layouts with viewports found. Defaulting to Model Space.")
    return doc.modelspace()
