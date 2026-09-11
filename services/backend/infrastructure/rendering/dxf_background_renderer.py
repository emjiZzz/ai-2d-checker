import traceback
from pathlib import Path
from typing import Any
from ...logger import logger

# Every geometry key a coordinate can arrive under, for the fallback below. Single points
# ("start") and lists of them ("points") both appear, so the fallback sniffs the shape rather
# than keeping two lists that can drift apart.
_BOUNDS_POINT_KEYS = (
    "points", "vertices", "start", "end", "center", "location", "insert",
    "def_point", "text_point", "control_points", "fit_points",
)

def render_dxf_background(dxf_path: Path, drawing_id: str, metadata: dict[str, Any], entities: list[dict[str, Any]]) -> None:
    try:
        import matplotlib
        matplotlib.use('Agg') # Headless background thread safe execution
        import matplotlib.pyplot as plt
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

        from .dxf_render_setup import (
            configure_cad_fonts,
            load_and_transcode,
            select_render_layout,
        )

        logger.info(f"Generating high-fidelity CAD layout background for drawing {drawing_id}...")

        # --- Step 1: Configure ezdxf font manager (MUST happen before readfile) ---
        # Shared with tools/render_audit.py, which measures text placement against this exact
        # configuration -- see dxf_render_setup for why each step is load-bearing.
        jp_font_filename = configure_cad_fonts(configure_matplotlib=True)

        # --- Steps 2 & 3: Load with byte-preserving encoding, recover CJK text, and repoint
        # every SHX text style at the TTF. Shared with the render-fidelity harness.
        doc = load_and_transcode(dxf_path, jp_font_filename)

        # --- Step 4: Select best layout to render (Paper Space preferred over Model Space,
        # but ONLY if it contains a viewport) ---
        layout_to_render = select_render_layout(doc)

        # Record WHICH layout this raster depicts. The extractor walks every layout in the
        # file and stores them all, so without this the vector renderer has no way to show the
        # same sheet: it drew 'ICADSX Layout' (426 entities) and 'Model' (86) superimposed,
        # which put a second copy of the section labels and other model-space annotation on
        # top of the real drawing, projected to plausible-but-wrong positions. The raster and
        # the vectors have to agree on what "the drawing" is, and this is that agreement.
        metadata["render_layout"] = layout_to_render.name

        # --- Brighten dark colors for visibility on dark UI background ---
        # AutoCAD Color 5 (Blue) and Color 8 (Dark Gray) are nearly invisible on a dark canvas.
        for layer in doc.layers:
            if layer.color == 5:
                layer.color = 4  # Change Blue to Cyan
            elif layer.color == 8:
                layer.color = 9  # Change Dark Gray to Light Gray
        
        for entity in doc.entitydb.values():
            if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'color'):
                if entity.dxf.color == 5:
                    entity.dxf.color = 4
                elif entity.dxf.color == 8:
                    entity.dxf.color = 9

        fig = plt.figure(figsize=(24, 18), dpi=350)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        ax.set_aspect('equal', 'box')
        
        from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
        ctx = RenderContext(doc)
        ctx.set_current_layout(layout_to_render)
        
        # Configure ezdxf to NOT draw a background rectangle so it remains completely transparent
        # Also swap Black lines to White so they are visible on the dark React canvas grid
        config = Configuration(
            background_policy=BackgroundPolicy.OFF,
            color_policy=ColorPolicy.COLOR_SWAP_BW
        )
        
        # Keep figure transparent to let the frontend React grid show through perfectly
        fig.patch.set_alpha(0.0)
        ax.patch.set_alpha(0.0)
        
        backend = MatplotlibBackend(ax)
        # Render the selected layout (with automatic viewport projection!)
        Frontend(ctx, backend, config=config).draw_layout(layout_to_render, finalize=True)
        
        # These are NOT tight bounds, whatever this comment used to claim. `get_xlim()` returns
        # the AUTOSCALED limits, which carry Matplotlib's default `axes.xmargin`/`axes.ymargin`
        # of 5% per side — and `set_aspect('equal', 'box')` above then expands whichever axis is
        # short of the figure's ratio. So `render_bounds` is systematically ~10% larger than the
        # drawing, more on one axis.
        #
        # Do NOT "fix" that by tightening it here. Zone templates store their boxes as fractions
        # of `render_bounds`, `zone_signature` derives a sheet's template identity from it, and
        # every stored `CadPoint` carries a snapshot of it for drift detection; re-deriving it
        # would silently invalidate all three across every drawing already ingested. A consumer
        # that needs the drawing's real extent must measure it — the PDF export does, in
        # `apps/desktop/src/components/review/exportFit.ts`, because fitting a page to these
        # bounds prints a margin nobody asked for.
        xmin, xmax = ax.get_xlim()
        ymin, ymax = ax.get_ylim()
        
        metadata["render_bounds"] = [float(xmin), float(ymin), float(xmax), float(ymax)]
        
        # Adjust figure size dynamically to match rendering aspect ratio exactly with zero padding
        dx = xmax - xmin
        dy = ymax - ymin
        aspect = dx / dy if dy > 0 else 1.333
        fig.set_size_inches(24.0, 24.0 / aspect)
        
        # Save rendering to safe destination path inside storage directory
        from services.backend.infrastructure.storage.path_resolver import get_storage_root
        render_dir = get_storage_root() / "renderings"
        render_dir.mkdir(parents=True, exist_ok=True)
        output_png_path = render_dir / f"{drawing_id}.png"
        
        fig.savefig(
            str(output_png_path),
            dpi=350,
            transparent=True,
            facecolor='none',
            edgecolor='none'
        )
        plt.close(fig)
        logger.info(f"High-fidelity CAD background rendering successfully saved to: {output_png_path}")
    except Exception as render_e:
        logger.error(f"High-fidelity rendering generation failed: {str(render_e)}\n{traceback.format_exc()}")
        
        # Fallback bounds, when the render failed. This read only `geometry["points"]` until
        # 2026-09-10, which on a DWG meant 59 polylines out of 1,231 entities: the stored
        # `render_bounds` was the extent of those polylines, the canvas normalised to it, and
        # the pane silently disagreed with its neighbour instead of erroring. Every key a
        # point can arrive under has to be read, or this produces a plausible wrong answer.
        #
        # These bounds are not the same measurement as the success path's. That one is
        # matplotlib's autoscale over a paper-space layout, so viewport-projected model
        # geometry lands in paper coordinates; this is the raw extent of extracted entities in
        # their own spaces. Treat a drawing carrying `render_aspect` as one to re-extract once
        # the render is fixed, not as one that is merely 10% loose.
        if "render_bounds" not in metadata and entities:
            logger.warning(
                "Falling back to entity-derived render_bounds -- these are NOT in the same "
                "frame as a rendered sheet's. Re-extract this drawing once the render works."
            )
            xs: list[float] = []
            ys: list[float] = []
            for e in entities:
                geometry = e.get("geometry") or {}
                for key in _BOUNDS_POINT_KEYS:
                    value = geometry.get(key)
                    if not isinstance(value, (list, tuple)) or not value:
                        continue
                    # A single point, or a list of them.
                    points = value if isinstance(value[0], (list, tuple)) else [value]
                    for pt in points:
                        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                            xs.append(float(pt[0]))
                            ys.append(float(pt[1]))

            if xs and min(xs) < max(xs) and min(ys) < max(ys):
                metadata["render_bounds"] = [min(xs), min(ys), max(xs), max(ys)]
                metadata["render_aspect"] = (max(xs) - min(xs)) / (max(ys) - min(ys))
                logger.info(f"Fallback render_bounds computed: {metadata['render_bounds']}")
        # Ensure figure resources are cleaned up
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
        except Exception:
            pass
