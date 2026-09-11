"""The accepted-format list is hand-mirrored in Python and TypeScript, so pin it.

`DrawingIngestionService.ALLOWED_EXTENSIONS` decides what the upload route accepts;
`apps/desktop/src/config/drawingFormats.ts` decides what the client offers and which
workspace it opens. No runtime type-sharing exists across the two languages, so the only
thing stopping them drifting is this test -- the same arrangement as
`tests/test_taxonomy_consistency.py`.

Drift here is silent in the expensive direction. A format the backend accepts and the client
rejects is merely annoying; a format on the wrong side of the 2D/3D split opens the 3D
workspace and fetches a glTF the backend never generated, with no error anywhere. `.icd` sat
on the 3D side while its 2D content was the only half the comparison engine could read.
"""

import re
from pathlib import Path

from services.backend.infrastructure.ingestion.drawing_ingestion_service import (
    DrawingIngestionService,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FORMATS_TS = REPO_ROOT / "apps" / "desktop" / "src" / "config" / "drawingFormats.ts"


def _ts_list(name: str) -> set[str]:
    source = FORMATS_TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name}[^=]*=\s*\[(.*?)\]", source, re.S)
    assert match, f"{name} not found in {FORMATS_TS.name}"
    return set(re.findall(r'"([a-z0-9]+)"', match.group(1)))


def test_the_two_languages_accept_the_same_formats():
    backend = set(DrawingIngestionService.ALLOWED_EXTENSIONS)
    frontend = _ts_list("DRAWING_FORMATS") | _ts_list("MODEL_3D_FORMATS")
    assert backend == frontend, (
        f"backend-only: {sorted(backend - frontend)}, frontend-only: {sorted(frontend - backend)}"
    )


def test_the_two_dimensional_and_three_dimensional_sets_do_not_overlap():
    drawings = _ts_list("DRAWING_FORMATS")
    models = _ts_list("MODEL_3D_FORMATS")
    assert not (drawings & models), f"a format claims both sides: {sorted(drawings & models)}"


def test_icd_is_a_drawing_format_not_a_3d_model_format():
    """An .icd holds both, but only its 2D half is extracted -- see
    `infrastructure/cad/icd_converter.py`. Classified 3D, it reaches a pipeline that yields a
    placeholder cube and never reaches `dxf_parser`."""
    assert "icd" in _ts_list("DRAWING_FORMATS")
    assert "icd" not in _ts_list("MODEL_3D_FORMATS")


def test_no_other_module_hardcodes_the_3d_format_list():
    """Four copies of this list existed and `.icd` moving sides left three of them wrong."""
    src = REPO_ROOT / "apps" / "desktop" / "src"
    offenders = []
    for path in src.rglob("*.ts*"):
        if path == FORMATS_TS:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'"sldprt"\s*,\s*"sldasm"', text):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert not offenders, (
        f"these inline the format list instead of importing drawingFormats.ts: {offenders}"
    )
