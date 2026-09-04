"""The backend's layer direction, enforced instead of reviewed.

`.claude/agents/architect-reviewer.md` lists layer inversion — `domain/` importing from
`infrastructure/` — as a violation to flag, and schema leakage — `api/schemas.py` models
used as internal domain objects — as another. Neither was enforced by anything: CI's ruff and
mypy gates are `continue-on-error`, so the only thing standing between the rule and its breach
was whether a reviewer happened to look.

They had both been breached, and had been for months:

* `domain/services/drawing_ingestion_service.py` imported the processing queue, the storage path
  resolver and the comparison cache manager — and `fastapi` besides. Moved to
  `infrastructure/ingestion/` on 2026-08-14; see that package's `__init__.py` for why relocating
  beat inverting three imports and leaving a web framework in the domain layer.
* `domain/contracts.py` re-exported seven Pydantic models from `api/schemas.py` as "canonical
  domain data contracts". It had zero importers — dead code whose only live effect was the
  `domain -> api` edge itself. Deleted the same day.

This test is deliberately structural rather than a `grep`: it resolves relative imports to
their real targets, which is what the original violations were written as. A substring search
for "infrastructure" over `domain/` matches half a dozen prose comments and misses nothing that
matters; `from ..cad.processing_queue import ...` is invisible to it entirely.
"""
import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "services" / "backend"
DOMAIN = BACKEND / "domain"

#: Package prefixes `domain/` may not depend on, and why each one matters.
FORBIDDEN_PREFIXES = {
    "services.backend.infrastructure": "layer inversion — domain must not depend on infrastructure",
    "services.backend.api": "schema leakage — api models must not become domain objects",
}

#: Third-party packages that make a module an adapter rather than a domain rule. Beanie and
#: Pydantic are deliberately absent: this codebase's domain models ARE Beanie Documents, which
#: is a settled trade-off, not an accident to re-litigate here.
FORBIDDEN_THIRD_PARTY = {"fastapi", "starlette"}


def _module_path(file: Path) -> list[str]:
    """Dotted package parts of the module *containing* `file`, rooted at `services`."""
    rel = file.relative_to(BACKEND.parents[1])
    return list(rel.parts[:-1])


def _resolve(file: Path, node: ast.ImportFrom) -> str:
    """Absolute dotted target of an ImportFrom, relative or not.

    `from ...config import settings` inside `services/backend/domain/models/foo.py` resolves to
    `services.backend.config`: level 1 is the containing package, and each extra level climbs one
    more. Getting this wrong is how a checker like this quietly passes on everything.
    """
    if not node.level:
        return node.module or ""
    parts = _module_path(file)
    base = parts[: len(parts) - (node.level - 1)]
    return ".".join([*base, node.module]) if node.module else ".".join(base)


def _domain_files() -> list[Path]:
    return sorted(p for p in DOMAIN.rglob("*.py") if "__pycache__" not in p.parts)


def _imports(file: Path) -> list[str]:
    tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            targets.append(_resolve(file, node))
        elif isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
    return targets


def test_the_domain_package_still_has_files():
    """A checker that silently walks an empty tree passes forever. Pin that it found something."""
    files = _domain_files()
    assert len(files) >= 10, f"Expected the domain package to hold real modules, found {files}"


@pytest.mark.parametrize("file", _domain_files(), ids=lambda p: p.name)
def test_domain_module_does_not_import_outward(file: Path):
    """No module under `domain/` may import `infrastructure/`, `api/`, or a web framework.

    `ast.walk` reaches imports nested inside functions on purpose: two of the three original
    infrastructure imports were deferred inside method bodies, where a module-header review does
    not see them.
    """
    for target in _imports(file):
        for prefix, reason in FORBIDDEN_PREFIXES.items():
            assert not (target == prefix or target.startswith(prefix + ".")), (
                f"{file.relative_to(BACKEND)} imports {target} — {reason}"
            )
        root = target.split(".")[0]
        assert root not in FORBIDDEN_THIRD_PARTY, (
            f"{file.relative_to(BACKEND)} imports {target} — a web framework in the domain layer "
            f"means this module is an adapter and belongs under infrastructure/"
        )


def test_the_checker_catches_the_violation_it_was_written_for():
    """Guards the checker itself, against the real pre-move import.

    `domain/services/drawing_ingestion_service.py` carried
    `from ...infrastructure.cad.processing_queue import processing_queue`. A checker that only
    understood absolute imports would pass on it, so the test that matters is that this exact
    line still resolves into a forbidden prefix.
    """
    src = "from ...infrastructure.cad.processing_queue import processing_queue\n"
    node = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom))
    offender = DOMAIN / "services" / "drawing_ingestion_service.py"

    resolved = _resolve(offender, node)

    assert resolved == "services.backend.infrastructure.cad.processing_queue"
    assert any(resolved.startswith(p + ".") for p in FORBIDDEN_PREFIXES)


def test_relative_levels_are_counted_from_the_containing_package():
    """Off-by-one here is the difference between a real checker and one that passes on anything.

    Level 1 is the containing package, so from `domain/models/x.py` a single dot is
    `domain.models`, two dots is `domain`, three is `services.backend`.
    """
    fake = DOMAIN / "models" / "x.py"

    def resolve(src: str) -> str:
        node = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom))
        return _resolve(fake, node)

    assert resolve("from .sibling import a") == "services.backend.domain.models.sibling"
    assert resolve("from ..other import b") == "services.backend.domain.other"
    assert resolve("from ...config import settings") == "services.backend.config"


def test_the_deleted_contracts_shim_has_not_come_back():
    """`domain/contracts.py` was a dead re-export of `api/schemas.py`. Its whole cost was the
    edge it created, so the useful assertion is that the file stays gone."""
    assert not (DOMAIN / "contracts.py").exists(), (
        "domain/contracts.py re-exported api/schemas.py Pydantic models as domain contracts. "
        "If domain-side contracts are needed, define them in domain/ rather than re-exporting "
        "the wire schema."
    )
