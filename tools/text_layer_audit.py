"""Does the report's invisible text layer land on the glyphs it is meant to select?

`tools/render_audit.py` measures the CANVAS against ezdxf. This measures the **exported PDF**
against ezdxf, which is a different question with a different oracle, and it is the acceptance
metric for `vector_pdf_exporter.render_vector_sheet`.

⚠ **The oracle is the whole difficulty, and getting it wrong is the reason this file exists.**
`render_audit.record_ground_truth` records ezdxf's ink in the CANVAS configuration — MS Gothic,
full DXF height. The report renders Yu Mincho Light at `CAD_TEXT_FIT_SCALE`, so measured against
that oracle it is wrong in two directions at once (0.8464 on width), and the two errors partly
cancel into a number that looks fine. The figures in
`docs/vault/06 - .../Gotcha - The Vector PDF Had No Text at All.md` were quoted from that stale
oracle for two weeks, across a fit-scale change and a font change, and the re-measurement that
replaced them found the invisible layer was being written at 1.92x size (Displacement 8).

So this records the ink by mirroring `_render_geometry`'s document preparation exactly — the
report face through `load_and_transcode`, then `_shrink_text_to_fit` — and swapping
`MatplotlibBackend` for `Recorder`. "Where ezdxf put the glyphs" is then measured on the same
document the sheet was rendered from, and a change to the face or the fit scale moves the oracle
with the page instead of leaving it behind.

Healthy at 2026-08-25 on the two dense sheets: **width ratio median 1.026 / 1.027, 97% within
+/-20%, |dx| median 0.094 / 0.095 drawing units, 0 strings missing, 0 raster images.**

Measured in `TextSource.LAYER`, which is what the report requests. It used to measure `OUTLINES`
-- where the layer is invisible, so every number it reported was about a page nobody looks at and
a mode the product no longer ships. The figures are unchanged by the switch, which is the point:
placement is the same either way, and only the deferred strings differ.

⚠ **Read the width ratio expecting ~1.026, not 1.000.** A PDF text rect is an ADVANCE box and
ezdxf's is an INK box, so the rect is wider by the side bearings. The model's widths themselves
are exact — PyMuPDF's advances match ezdxf's at 1.0000 on Latin, CJK and U+3000-padded strings.
A ratio near **1.9** means `cap_height_ratio` has regressed; near **0.5**, the two-font split in
`_script_runs`.

Usage, from the repo root:

    services/backend/.venv/Scripts/python.exe tools/text_layer_audit.py [DXF ...]
    services/backend/.venv/Scripts/python.exe tools/text_layer_audit.py --sweep storage/uploads

Each sheet costs about four ezdxf renders (~45 s), so `--sweep` takes a `--limit`.
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "tools"))

PT_PER_INCH = 72.0

#: Strings shorter than this are skipped: they repeat dozens of times on a sheet and a search
#: cannot be attributed to one entity with any confidence.
_MIN_CHARS = 3


def record_export_ink(dxf_path: Path) -> tuple[dict[str, tuple], dict[str, list]]:
    """Ezdxf's own ink box per handle, in the configuration the REPORT renders.

    Mirrors `_render_geometry`'s document preparation. Any divergence here is a silent
    measurement error, not a test failure -- keep the two in step.
    """
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.recorder import Recorder

    from services.backend.infrastructure.rendering import vector_pdf_exporter as exporter
    from services.backend.infrastructure.rendering.dxf_render_setup import (
        load_and_transcode,
        select_render_layout,
    )
    from services.backend.infrastructure.rendering.text_placement import resolve_report_font

    fallback = exporter._configure_fonts_once()
    report_font, _ = resolve_report_font()
    doc = load_and_transcode(dxf_path, report_font or fallback)
    exporter._shrink_text_to_fit(doc)

    layout = select_render_layout(doc)
    context = RenderContext(doc)
    context.set_current_layout(layout)
    backend = Recorder()
    Frontend(context, backend, config=Configuration(
        background_policy=BackgroundPolicy.OFF, color_policy=ColorPolicy.BLACK,
    )).draw_layout(layout, finalize=True)

    boxes: dict[str, list[float]] = {}
    records: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
    for record, props in backend.player().recordings():
        handle = props.handle
        if not handle:
            continue
        bbox = record.bbox()
        if not bbox.has_data:
            continue
        lo, hi = bbox.extmin, bbox.extmax
        records[handle].append((lo.x, lo.y, hi.x, hi.y))
        current = boxes.get(handle)
        if current is None:
            boxes[handle] = [lo.x, lo.y, hi.x, hi.y]
        else:
            current[0] = min(current[0], lo.x)
            current[1] = min(current[1], lo.y)
            current[2] = max(current[2], hi.x)
            current[3] = max(current[3], hi.y)
    return {h: tuple(b) for h, b in boxes.items()}, dict(records)


def audit_sheet(dxf_path: Path) -> dict[str, Any] | None:
    """Measure one drawing. Returns None if it yielded too few comparable strings to score."""
    import fitz
    import render_audit

    from services.backend.infrastructure.cad.dxf_parser import DXFParser
    from services.backend.infrastructure.rendering import vector_pdf_exporter as exporter

    entities = DXFParser().parse_file(dxf_path)[0]
    ink, ink_records = record_export_ink(dxf_path)

    # The exporter's OWN transform, so this compares through the same mapping the layer was
    # written with rather than a ratio regressed back out of the page.
    # `TextSource.LAYER`, because that is what the report requests -- an acceptance metric
    # taken in a mode the product does not use is the defect this tool exists to catch, one
    # level up. `deferred` are the strings ezdxf draws itself (`_UNREPRODUCIBLE_MTEXT`); they
    # are legitimately absent from the layer, and counting them as missing would put a
    # permanent non-zero in the one column whose expected value is 0.
    _, transform, dpi, page_height, deferred = exporter._render_geometry(
        dxf_path, exporter.A4_LANDSCAPE, exporter.TextSource.LAYER)
    points_per_px = PT_PER_INCH / dpi

    def to_pdf(x: float, y: float) -> tuple[float, float]:
        px, py = transform.transform((x, y))
        return px * points_per_px, page_height - py * points_per_px

    pt_per_unit = abs(to_pdf(1.0, 0.0)[0] - to_pdf(0.0, 0.0)[0])

    sheet = exporter.render_vector_sheet(
        dxf_path, text_source=exporter.TextSource.LAYER)
    page = fitz.open(stream=sheet, filetype="pdf")[0]

    rows: list[dict[str, float]] = []
    missing: list[str] = []
    for entity in entities:
        if entity["entity_type"] != "text":
            continue
        props = entity["properties"]
        handle = props.get("handle")
        text = render_audit.clean_cad_text((props.get("text") or "").strip())
        if not handle or handle not in ink or len(text) < _MIN_CHARS or "\n" in text:
            continue
        if handle in deferred:
            continue
        if abs(float(props.get("rotation") or 0.0)) > 1e-6:
            continue

        # A wrapped MTEXT emits one record per LINE; merge so one string is scored as one box.
        clustered = render_audit.cluster_text_records(ink_records.get(handle, []))
        box = clustered[0] if len(clustered) == 1 else ink[handle]

        hits = page.search_for(text)
        if not hits:
            missing.append(text)
            continue

        expected_width = (box[2] - box[0]) * pt_per_unit
        if expected_width <= 1:
            continue
        left, top = to_pdf(box[0], box[3])
        right, bottom = to_pdf(box[2], box[1])

        # `hits[0]` is the first instance ANYWHERE on the sheet and this corpus repeats short
        # strings dozens of times, which reports an unrelated copy's distance as placement error.
        centre_x, centre_y = (left + right) / 2.0, (top + bottom) / 2.0
        hit = min(hits, key=lambda r: (r.x0 + r.x1 - 2 * centre_x) ** 2
                  + (r.y0 + r.y1 - 2 * centre_y) ** 2)

        # `_script_runs` writes a mixed Latin/CJK string as SEPARATE runs and `search_for` then
        # returns one quad per run -- scoring 'Kusakabe Electric 株 Machinery Co.,Ltd.' as its
        # first fragment alone, a width ratio of 0.058. Union the fragments in this string's box.
        expected = fitz.Rect(min(left, right), min(top, bottom),
                             max(left, right), max(top, bottom))
        pad = max(expected.height, 1.0)
        probe = fitz.Rect(expected.x0 - pad, expected.y0 - pad,
                          expected.x1 + pad, expected.y1 + pad)
        fragments = [r for r in hits if r.intersects(probe)]
        if fragments:
            for fragment in fragments[1:]:
                fragments[0] = fragments[0] | fragment
            hit = fragments[0]

        rows.append({
            "ratio": hit.width / expected_width,
            "dx": abs(hit.x0 - left) / pt_per_unit,
            "dy": abs(hit.y0 - top) / pt_per_unit,
            "text": text,
        })

    if not rows:
        return None

    def pct(values: list[float], fraction: float) -> float:
        ordered = sorted(values)
        return ordered[min(int(fraction * len(ordered)), len(ordered) - 1)]

    ratios = [r["ratio"] for r in rows]
    return {
        "name": dxf_path.name,
        "n": len(rows),
        "missing": len(missing),
        "ratio_median": st.median(ratios),
        "ratio_p10": pct(ratios, 0.10),
        "ratio_p90": pct(ratios, 0.90),
        "within10": 100.0 * sum(1 for r in ratios if 0.9 <= r <= 1.1) / len(rows),
        "within20": 100.0 * sum(1 for r in ratios if 0.8 <= r <= 1.2) / len(rows),
        "dx_median": st.median([r["dx"] for r in rows]),
        "dy_median": st.median([r["dy"] for r in rows]),
        "chars": len(page.get_text("text")),
        "images": len(page.get_images(full=True)),
        "size_mb": len(sheet) / 1e6,
        "worst": sorted(rows, key=lambda r: abs(r["ratio"] - 1.0), reverse=True)[:5],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dxf", nargs="*", type=Path, help="drawings to audit")
    parser.add_argument("--sweep", type=Path, help="audit every .dxf in this directory")
    parser.add_argument("--limit", type=int, default=6, help="cap on --sweep (default 6)")
    parser.add_argument("--verbose", action="store_true", help="show the worst strings per sheet")
    args = parser.parse_args()

    targets = list(args.dxf)
    if args.sweep:
        targets.extend(sorted(args.sweep.glob("*.dxf"))[:args.limit])
    if not targets:
        parser.error("give at least one DXF, or --sweep a directory")

    results = []
    for target in targets:
        if not target.exists():
            print(f"  !! no such DXF: {target}")
            continue
        result = audit_sheet(target)
        if result is None:
            print(f"  -- {target.name}: no comparable strings, skipped")
            continue
        results.append(result)
        if args.verbose:
            print(f"\n{result['name']}  worst by width ratio:")
            for row in result["worst"]:
                print(f"    {row['ratio']:6.3f}  dx {row['dx']:6.3f}  {row['text'][:40]!r}")

    if not results:
        return 1

    print("\n" + "=" * 108)
    print("  %-34s %5s %5s %7s %6s %6s %6s %6s %6s %5s" % (
        "sheet", "n", "miss", "ratio", "w10", "w20", "|dx|", "|dy|", "chars", "img"))
    print("-" * 108)
    for r in results:
        print("  %-34s %5d %5d %7.3f %5.0f%% %5.0f%% %6.3f %6.3f %6d %5d" % (
            r["name"][:34], r["n"], r["missing"], r["ratio_median"], r["within10"],
            r["within20"], r["dx_median"], r["dy_median"], r["chars"], r["images"]))

    # The two that must never drift: a string written but unfindable is the defect this whole
    # pipeline is prone to, and a raster image means page 1 stopped being vector at all.
    total_missing = sum(r["missing"] for r in results)
    total_images = sum(r["images"] for r in results)
    print("-" * 108)
    print("  strings missing from the layer: %d (expected 0)   raster images: %d (expected 0)"
          % (total_missing, total_images))
    return 0 if total_missing == 0 and total_images == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
