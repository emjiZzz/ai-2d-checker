"""`sandboxed_path` — the join-and-validate helper the file-serving endpoints use.

Three defects motivated it, and each has a test here:

1. ``get_storage_root() / drawing.file_path`` **silently discards the storage root** when the DB
   value is absolute. The sandbox does not fail in that case; it stops existing.
2. Callers ran ``validate_sandboxed_path(p)`` for its exception and then used ``p`` — computing
   the canonical path and throwing it away.
3. The guard raised a bare ``ValueError`` on a NUL byte, surfacing as 500 rather than the 400 its
   contract promises, and rejected legitimate filenames containing two dots via a substring test.
"""
from pathlib import Path

import pytest
from fastapi import HTTPException, status

from services.backend.core.security import sandboxed_path, validate_sandboxed_path
from services.backend.infrastructure.storage.path_resolver import (
    bootstrap_storage,
    get_storage_root,
)


@pytest.fixture(autouse=True)
def _storage():
    bootstrap_storage()


def test_relative_parts_join_under_the_storage_root():
    assert sandboxed_path("reports", "report_abc.pdf") == (
        get_storage_root() / "reports" / "report_abc.pdf"
    ).resolve()


def test_absolute_part_is_rejected_rather_than_silently_replacing_the_root():
    """The defect this helper exists for.

    `Path("/a") / "/etc/passwd"` is `/etc/passwd` — pathlib drops the left operand entirely. A
    plain join therefore reads whatever absolute path a DB row names, with no error anywhere.
    """
    absolute = str(Path(Path(get_storage_root()).anchor) / "etc" / "passwd")

    # Demonstrate the pathlib behaviour being defended against, so this test explains itself.
    assert Path(get_storage_root()) / absolute == Path(absolute)

    with pytest.raises(HTTPException) as exc:
        sandboxed_path(absolute)
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST


def test_traversal_component_in_a_route_parameter_is_rejected():
    """`sandboxed_path("temp", f"model_{id}.gltf")` with a hostile `id`."""
    with pytest.raises(HTTPException) as exc:
        sandboxed_path("temp", f"model_{'../../etc/passwd'}.gltf")
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST


def test_nul_byte_is_a_400_not_a_500():
    """`Path.resolve()` raises a bare ValueError on an embedded NUL.

    That escaped the guard uncaught and became a 500 from the error middleware — a rejected path
    that looks like a server fault, which is both a worse signal and a worse log line.
    """
    with pytest.raises(HTTPException) as exc:
        validate_sandboxed_path(str(get_storage_root() / "uploads" / "evil\x00.dxf"))
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST


def test_a_filename_containing_two_dots_is_not_traversal():
    """The old check was `".." in str(path)` — a substring, so `rev..2.dxf` was rejected.

    Revision suffixes like this are ordinary in CAD filenames, so the false rejection was
    reachable by normal use while adding no security: `.resolve()` had already normalised any
    real traversal before the check ever ran.
    """
    ok = sandboxed_path("uploads", "rev..2.dxf")
    assert ok.name == "rev..2.dxf"
    assert ok.parent == (get_storage_root() / "uploads").resolve()


def test_symlink_escape_is_still_caught(tmp_path):
    """The containment check is the load-bearing layer and must keep doing the real work."""
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    link = get_storage_root() / "uploads" / "escape_link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation requires privilege on this platform")

    try:
        with pytest.raises(HTTPException) as exc:
            validate_sandboxed_path(link)
        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    finally:
        link.unlink(missing_ok=True)


def test_returns_the_canonical_path_so_callers_have_no_reason_to_discard_it():
    result = sandboxed_path("uploads", "drawing.dxf")
    assert result.is_absolute()
    assert result == result.resolve()
