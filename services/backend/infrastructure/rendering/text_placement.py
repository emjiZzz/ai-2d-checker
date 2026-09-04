"""Where a CAD string lands, and how wide it is — the one model, for everyone who needs it.

Three consumers ask the same questions about a DXF string and must not answer them differently:

* `tools/render_audit.py`, which measures the canvas's text placement against ezdxf's own
  `Recorder` output and is the reason any of this is known to be right.
* `vector_pdf_exporter.py`, which writes an invisible, searchable text layer over ezdxf's vector
  geometry — a layer that is *only* useful if it lands on the glyphs.
* `apps/desktop/src/components/review/renderEntities.ts`, which cannot import Python and
  therefore mirrors these rules by hand. That mirror is the drift risk; the harness above is
  what pins it.

This module was extracted from `render_audit.py` on 2026-08-25 rather than restated, because the
alternative was production code importing a harness out of `tools/`. It was proven inert first:
`tools/render_audit.py --json` is byte-identical across the move.

**What deliberately did NOT move**: `anchor_reference` and the `RENDERER_APPLIES_*` flags. Those
encode *what the canvas is modelled as doing* — a drift surface the harness exists to interrogate,
not a fact about DXF. They stay with the harness and consume `ANCHOR_FRACTIONS` and `quadrant`
from here.

The three facts, and why each is load-bearing:

1. **Cap height is not em.** ezdxf scales glyphs so the DXF `height` lands on the CAP height;
   every text API in the world sizes by the EM square. The ratio is ~0.7617 for MS Gothic and it
   **cannot be hand-picked**: Latin caps sit at ~0.72 em in that font and CJK ideographs fill
   ~1.0 em, while one DXF `height` governs both. Guessing 0.72 inflates Japanese by 1.39x.
2. **The insert point is not the corner.** MTEXT's `attachment_point` says which corner or edge
   midpoint of the text box the insert point coincides with. Assuming bottom-left puts a
   right-aligned string out by its full width and a centred one by half.
3. **`%%c` is one glyph, not four characters.** Measure the substituted string or a diameter
   callout reads 1.56x too wide.
"""

from __future__ import annotations

from typing import Any

#: The font the canvas asks for first (see `renderEntities.ts`), what Windows resolves in
#: practice, and what `configure_cad_fonts` substitutes for this corpus's SHX styles. Anything
#: measuring "what the canvas will do" has to measure it in this font.
CANVAS_FONT = "msgothic.ttc"

#: The face the REPORT draws CAD text in, in the canvas's own preference order.
#:
#: Mirrors `CAD_FONT_STACK` in `renderEntities.ts`, which is a **Mincho** stack — so the printed
#: sheet and the screen show the same typeface. The ingestion raster deliberately keeps MS Gothic
#: (`JAPANESE_FONT_CANDIDATES` in `dxf_render_setup.py`): its output feeds `render_bounds`, which
#: every zone template stores fractions of, so changing the face there is a template-invalidation
#: event rather than a rendering change. This constant exists so the export can differ from it
#: without touching it.
#:
#: **The order is load-bearing.** Widths at equal cap height, relative to MS Gothic — and note
#: they are string-dependent, because MS Gothic's Latin is half-width while Mincho's is
#: proportional, so a lowercase label and an all-caps drawing number do not scale alike:
#:
#: | face | `Material Weight(kg)` | `M745206N01` |
#: | :--- | :--- | :--- |
#: | `yuminl.ttf` (Light) | — | **1.196x** |
#: | `yumin.ttf` (Regular) | 1.001x | 1.283x |
#: | `MSMINCHO.TTF` | 1.140x | — |
#:
#: MS Mincho last of the Minchos: it is the widest and re-creates the title-block collisions
#: `CAD_TEXT_FIT_SCALE` exists to prevent, which presents as a scale bug rather than a font bug.
#:
#: **Light before Regular, and this is a deliberate divergence from the canvas.** `CAD_FONT_STACK`
#: asks for `"Yu Mincho"`, which resolves to Regular. Regular's vertical stems are heavy — invisible
#: on 3 mm labels and obvious on the 9.5 mm title-block values, which an engineer reading a printed
#: sheet flagged as too bold. The underlying cause is unfixable by font choice: `txt.shx` is a
#: **monoline stroke** font and every TTF substitute is a **filled outline** font, so weight grows
#: with size in a way the original never did. Light is the same family, one step back toward the
#: stick font, and narrower — so it cannot introduce a collision Regular did not already have.
REPORT_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\yuminl.ttf",     # Yu Mincho Light — lightest stems, still the canvas family
    r"C:\Windows\Fonts\yumin.ttf",      # Yu Mincho Regular — exactly what CAD_FONT_STACK resolves
    r"C:\Windows\Fonts\MSMINCHO.TTF",   # MS Mincho — next in that stack, and the widest
    r"C:\Windows\Fonts\msgothic.ttc",   # last resort: the face the ingestion raster uses
)


def resolve_report_font() -> tuple[str, str] | tuple[None, None]:
    """(filename, full path) of the first report font present, or (None, None).

    The filename is what `load_and_transcode` writes into `style.dxf.font` and what ezdxf's font
    manager resolves; the path is what PyMuPDF needs to embed a subset.
    """
    from pathlib import Path as _Path

    for candidate in REPORT_FONT_CANDIDATES:
        if _Path(candidate).exists():
            return _Path(candidate).name, candidate
    return None, None


#: Every CAD string is drawn at this fraction of the height the DXF asks for.
#:
#: **This is not a fudge, it is a substitution artefact.** The corpus is drawn in `txt.shx` plus
#: the `extfont2` BigFont, and ezdxf cannot rasterise SHX glyphs at all -- `configure_cad_fonts`
#: redirects both to MS Gothic, whose glyphs are wider than the stick font the title block was
#: laid out for. At full height the labels overflow their own cells: on `M745206N01`,
#: `材料個数` measures 291.92 -> 306.48 while `Material Weight(kg)` starts at 304.87, so the two
#: collide by ~1.6 units. **That overlap is in the source data as rendered, not in either
#: renderer** -- ezdxf's own ink and the canvas model agree on it to within 0.2 units.
#:
#: `renderEntities.ts` has compensated with this same 0.80 since the vector canvas landed
#: ("Scaled (0.80x) so text fits comfortably within table cells without unwanted line breaks or
#: column collisions"). The PDF has to apply it too or it disagrees with the sheet the engineer
#: reviewed -- which is the one thing a compliance report may not do.
#:
#: Mirrored by hand from `renderEntities.ts`, because no runtime type sharing exists between
#: the two languages. Pinned by `tests/test_report_style_consistency.py`.
CAD_TEXT_FIT_SCALE = 0.80

#: `attachment_point` -> (x fraction of the text box, y fraction) that the insert point sits on.
#: 1-3 top, 4-6 middle, 7-9 bottom; left / centre / right across.
ANCHOR_FRACTIONS: dict[int, tuple[float, float]] = {
    1: (0.0, 1.0), 2: (0.5, 1.0), 3: (1.0, 1.0),
    4: (0.0, 0.5), 5: (0.5, 0.5), 6: (1.0, 0.5),
    7: (0.0, 0.0), 8: (0.5, 0.0), 9: (1.0, 0.0),
}

#: The escape -> glyph substitutions `cleanCadText` makes before anything measures a string.
#: Without these "%%c145" measures as six glyphs against ezdxf's rendered "⌀145".
_CAD_TEXT_SUBSTITUTIONS = (("%%c", "⌀"), ("%%C", "⌀"), ("%%d", "°"), ("%%D", "°"),
                           ("%%p", "±"), ("%%P", "±"))


def clean_cad_text(text: str) -> str:
    """Mirror of `cleanCadText` in `renderEntities.ts`, for the substitutions that change width."""
    for escape, glyph in _CAD_TEXT_SUBSTITUTIONS:
        text = text.replace(escape, glyph)
    return text


def cap_height_ratio(font_name: str = CANVAS_FONT) -> float:
    """Cap height as a fraction of the em square.

    ezdxf scales glyphs so the DXF `height` lands on the CAP height; CSS `font: Npx` and every
    PDF text API set the EM size. Before the fix the canvas passed the DXF height straight to
    `font-size`, drawing every string at this fraction of its correct size -- measured as a flat
    0.7617 across the sheet. `renderEntities.ts` now divides by the same ratio, measured
    in-browser from `TextMetrics.actualBoundingBoxAscent`.

    Read straight out of the measurements ezdxf itself scaled the glyphs by, because that is the
    number the caller actually needs: `_write_text_layer` converts a DXF height into a PyMuPDF
    `fontsize` for a run whose ADVANCES come from this same font object, so any other source of
    "cap height" makes the size and the spacing disagree.

    **This replaced a `text_width("MMMM") / 2` estimate on 2026-08-25, which was exact for
    MS Gothic and 1.88x wrong for Yu Mincho.** That estimate hard-coded its own assumption in a
    comment -- *"Latin glyphs in MS Gothic are exactly half-width, so `MMMM` is 2 em"* -- and it
    holds only for a half-width-Latin face. `M` is 0.5000 em in `msgothic.ttc` and **0.9390 em**
    in `yuminl.ttf`, whose Latin is proportional; this module's own `REPORT_FONT_CANDIDATES`
    docstring says so two screens up. Forcing `M` back to half-width returned **0.3890** against
    a true 0.7305, so every string in the report's invisible layer was written at **1.92x** its
    correct size -- measured end-to-end as a width ratio of **1.920** before this fix and
    **1.026** after, by `tools/text_layer_audit.py`. Nothing looked wrong, because the layer is
    `render_mode=3`: the defect is only visible as a selection rectangle twice the width of the
    glyphs it selects, and as six strings pushed past the page rect and dropped outright.

    **Inert for every face where the old assumption was true**, which is why the harness
    baselines do not move: `msgothic.ttc` returns 0.761719 and `MSMINCHO.TTF` 0.667969, both
    bit-identical to the estimate, because MS CJK faces really do set `M` at exactly 0.5 em.
    `tools/render_audit.py` calls this with the default and is untouched.
    """
    from ezdxf.fonts import fonts

    font = fonts.make_font(font_name, cap_height=1.0)
    renderer = getattr(font, "glyph_cache", None)
    measurements = getattr(renderer, "font_measurements", None)
    units_per_em = 0.0
    try:
        units_per_em = float(renderer.font["head"].unitsPerEm)     # type: ignore[union-attr]
    except (AttributeError, KeyError, TypeError, ValueError):
        units_per_em = 0.0

    if measurements is not None and units_per_em > 0:
        cap_height = float(getattr(measurements, "cap_height", 0.0) or 0.0)
        if cap_height > 0:
            return cap_height / units_per_em

    # ezdxf moved its font internals. Fall back to the half-width estimate rather than crash the
    # export, but say so: it is silently wrong by ~1.9x on any proportional-Latin face, and a
    # wrong number here prints a page that looks perfect.
    #
    # Imported here, not at module scope: this module is the shared placement model and is pulled
    # in by `tools/render_audit.py`, so its only module-level import stays `typing`.
    from ...logger import logger

    logger.warning(
        "cap_height_ratio: ezdxf font measurements unavailable for %s; falling back to the "
        "half-width estimate, which is only valid for a half-width-Latin face.", font_name,
    )
    em_in_cap_units = font.text_width("MMMM") / 2.0
    return 1.0 / em_in_cap_units if em_in_cap_units else 1.0


def quadrant(rotation: float) -> int | None:
    """0/90/180/270 as 0-3, or None for an off-axis rotation."""
    normalized = round(((rotation % 360.0) + 360.0) % 360.0, 3)
    for index, angle in enumerate((0.0, 90.0, 180.0, 270.0)):
        if abs(normalized - angle) < 1.0 or abs(normalized - angle - 360.0) < 1.0:
            return index
    return None


def anchor_fractions_of(attachment_point: Any) -> tuple[float, float]:
    """`ANCHOR_FRACTIONS` for a value off an entity, defaulting to bottom-left for junk.

    7 (bottom-left) is the default because it is DXF's own for a plain TEXT with no MTEXT
    attachment, not because it is a safe guess -- see fact 2 in the module docstring.
    """
    try:
        return ANCHOR_FRACTIONS.get(int(attachment_point), (0.0, 0.0))
    except (TypeError, ValueError):
        return (0.0, 0.0)
