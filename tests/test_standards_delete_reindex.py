"""Deleting a standard must rebuild the search index, not just the database rows.

The delete endpoint removed the `StandardDocument`, its `StandardChunk`s and the source file,
and left the lexical index untouched. Retrieval therefore kept returning the deleted standard's
text — searchable content from a document the user had explicitly removed, with no error and no
way to tell from the UI.

It survived because of a stale comment. The line above the chunk deletion read
*"(MongoDB; there is no vector index)"*, which was true when R0 deleted the fake index and
stopped being true when R1 built a real one. Nobody maintaining delete had a reason to look.

**Rule: a comment asserting the absence of a thing ages exactly as badly as one asserting its
presence** — and this repo has now paid for both. See
`Gotcha - A Guard Clause Named an Exception the Library Stopped Raising` for the same shape.

The endpoint needs Mongo, which this suite does not have, so what is pinned here is the wiring:
delete must call the same rebuild ingest calls, and the two must stay the same function.
"""

import ast
import inspect
from pathlib import Path

from services.backend.api.routers import standards as standards_router
from services.backend.infrastructure.audit import standards_loader

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTER_SRC = REPO_ROOT / "services" / "backend" / "api" / "routers" / "standards.py"


def _function_source(module_src: str, name: str) -> str:
    tree = ast.parse(module_src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(module_src, node) or ""
    raise AssertionError(f"{name} not found — was it renamed?")


def test_delete_rebuilds_the_search_index():
    src = _function_source(ROUTER_SRC.read_text(encoding="utf-8"), "delete_standard")
    assert "rebuild_standards_index" in src, (
        "delete_standard does not rebuild the lexical index. Deleting a standard would leave "
        "its text searchable, so retrieval serves content the user removed."
    )


def test_delete_and_ingest_rebuild_through_the_same_function():
    """Two rebuild implementations would be free to drift; one cannot."""
    router_src = ROUTER_SRC.read_text(encoding="utf-8")
    loader_src = inspect.getsource(standards_loader)

    assert "rebuild_standards_index" in loader_src, "ingest path no longer rebuilds"
    assert standards_router.rebuild_standards_index is standards_loader.rebuild_standards_index


def test_the_stale_comment_is_gone():
    """The comment that caused this is pinned so it cannot come back verbatim."""
    src = ROUTER_SRC.read_text(encoding="utf-8")
    assert "there is no vector index" not in src or "used to read" in src, (
        "'there is no vector index' is asserted as current fact again; a real index has existed "
        "since R1 and that claim is what stopped delete from maintaining it."
    )


def test_rebuild_failure_is_non_fatal_and_logged():
    """A failed rebuild must not fail the delete: Mongo is already the source of truth."""
    src = _function_source(ROUTER_SRC.read_text(encoding="utf-8"), "delete_standard")
    assert "except" in src.split("rebuild_standards_index")[1], "rebuild is unguarded"
    assert "logger.error" in src or "logger.warning" in src, "a silent failure is the defect"
