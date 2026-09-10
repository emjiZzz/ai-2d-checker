"""Bulk-convert iCAD SX .icd drawings to DXF, for seeding a corpus outside the upload path.

The conversion itself lives in `infrastructure/cad/icd_converter.py`, which the ingestion
pipeline also uses -- the two must not hold different opinions about the translator's
environment or about what counts as an empty result.

A conversion that reports success can still be empty, so every output is counted. See
`06 - .../Gotcha - iCAD .icd Converts Silently Empty.md`.

    python tools/icd_to_dxf.py <src dir or file> --out <dir>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.backend.infrastructure.cad.icd_converter import (  # noqa: E402
    ICDConverter,
    count_drawing_entities,
)


@dataclass
class Result:
    source: Path
    output: Path | None
    entities: int
    error: str = ""

    @property
    def status(self) -> str:
        if self.error:
            return "failed"
        return "converted" if self.entities else "empty"


async def convert(sources: list[Path], out_dir: Path) -> list[Result]:
    converter = ICDConverter()
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[Result] = []
    for i, src in enumerate(sources, 1):
        try:
            # Sandbox validation off: these paths name the drawing share, not the storage
            # root, and reach this process from an operator's argv rather than from HTTP.
            dxf = await converter.convert_icd_to_dxf(src, out_dir, validate_sandbox=False)
            results.append(Result(src, dxf, count_drawing_entities(dxf)))
        except Exception as exc:
            results.append(Result(src, None, 0, f"{type(exc).__name__}: {exc}"))
        print(f"  {i}/{len(sources)}", end="\r", flush=True)
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path, help="an .icd file, or a directory to walk")
    ap.add_argument("--out", type=Path, required=True, help="destination directory")
    ap.add_argument(
        "--keep-empty",
        action="store_true",
        help="keep the zero-entity DXFs an .icd with no 2D drawing produces",
    )
    args = ap.parse_args()

    sources = (
        sorted(args.source.rglob("*.icd")) if args.source.is_dir() else [args.source]
    )
    if not sources:
        print("no .icd files found", file=sys.stderr)
        return 1

    print(f"converting {len(sources)} drawing(s) -> {args.out}")
    results = asyncio.run(convert(sources, args.out))

    converted = [r for r in results if r.status == "converted"]
    empty = [r for r in results if r.status == "empty"]
    failed = [r for r in results if r.status == "failed"]

    if not args.keep_empty:
        for r in empty:
            if r.output:
                r.output.unlink(missing_ok=True)

    print(
        f"\nconverted {len(converted)}   "
        f"empty (no 2D drawing) {len(empty)}   failed {len(failed)}"
    )
    for r in empty:
        print(f"  EMPTY  {r.source}")
    for r in failed:
        print(f"  FAILED {r.source}: {r.error}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
