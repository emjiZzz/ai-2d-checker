import traceback
from pathlib import Path
from typing import Any
from ...logger import logger

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
        
        # Fallback: compute bounds manually from extracted entities if Matplotlib failed (e.g. missing block definitions)
        if "render_bounds" not in metadata and entities:
            logger.info("Computing fallback render_bounds from extracted entities.")
            min_x = float("inf")
            min_y = float("inf")
            max_x = float("-inf")
            max_y = float("-inf")
            has_valid_point = False
            for e in entities:
                if "geometry" in e and "points" in e["geometry"]:
                    for pt in e["geometry"]["points"]:
                        min_x = min(min_x, pt[0])
                        min_y = min(min_y, pt[1])
                        max_x = max(max_x, pt[0])
                        max_y = max(max_y, pt[1])
                        has_valid_point = True
            
            if has_valid_point and min_x < max_x and min_y < max_y:
                metadata["render_bounds"] = [min_x, min_y, max_x, max_y]
                metadata["render_aspect"] = (max_x - min_x) / (max_y - min_y)
                logger.info(f"Fallback render_bounds computed: {metadata['render_bounds']}")
        # Ensure figure resources are cleaned up
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
        except Exception:
            pass
