"""The frozen server carries its own CA roots, rather than trusting the host's store.

A PyInstaller build has no site-packages, so `ssl` falls back to whatever certificates the machine
happens to have. That is not a constant: the same executable connected to Atlas on the build
machine and failed on a fresh Windows Server on 2026-09-07 with

    [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer
    certificate

Atlas is TLS-only, so the backend fell through to its local fallback, found no Mongo there either,
and started in disconnected mode -- a server that looks healthy in the banner and cannot read or
write anything.

The failure is invisible on any machine whose certificate store happens to be complete, which is
every developer machine, so it needs a test rather than a memory.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "tools" / "draftcheck_server.spec"
SERVER_MAIN = REPO / "services" / "backend" / "server_main.py"


def test_the_spec_collects_certifi():
    """`cacert.pem` is package DATA, so collecting only code leaves the build with no roots."""
    source = SPEC.read_text(encoding="utf-8")
    collected = [
        line for line in source.splitlines() if "for package in (" in line and "collect_all" not in line
    ]
    assert collected, "the spec no longer collects packages in a loop; check this test still applies"
    assert any("certifi" in line for line in collected), (
        "certifi is not collected, so the frozen build ships no CA bundle and TLS depends on "
        "whatever certificates the target machine happens to have."
    )


def test_the_bundle_is_installed_before_anything_connects():
    """Ordering is the property: a TLS context created earlier would not see the variable."""
    tree = ast.parse(SERVER_MAIN.read_text(encoding="utf-8"))
    main = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    calls = [
        node.func.id
        for node in ast.walk(main)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert "_install_ca_bundle" in calls, "main() no longer installs the CA bundle"

    # Before uvicorn.run, which is where the app and every client it builds come to life.
    # Scoped to main()'s own body: the module docstring names `uvicorn.run` too, and comparing
    # raw file offsets matched that instead -- the test failed against correct code.
    body = SERVER_MAIN.read_text(encoding="utf-8")[main.body[0].col_offset :]
    start = body.index("def main(")
    within = body[start:]
    assert within.index("_install_ca_bundle()") < within.index("uvicorn.run(")


def test_it_points_at_a_bundle_that_exists():
    from services.backend.server_main import _install_ca_bundle

    saved = {k: os.environ.get(k) for k in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")}
    try:
        for k in saved:
            os.environ.pop(k, None)
        _install_ca_bundle()
        bundle = os.environ.get("SSL_CERT_FILE")
        assert bundle, "no SSL_CERT_FILE was set"
        assert os.path.exists(bundle), f"SSL_CERT_FILE points at a file that is not there: {bundle}"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_an_operators_own_bundle_wins():
    """A site pointing these at a corporate CA must not be overridden by the shipped roots."""
    from services.backend.server_main import _install_ca_bundle

    saved = os.environ.get("SSL_CERT_FILE")
    try:
        os.environ["SSL_CERT_FILE"] = "C:/corp/ca.pem"
        _install_ca_bundle()
        assert os.environ["SSL_CERT_FILE"] == "C:/corp/ca.pem"
    finally:
        if saved is None:
            os.environ.pop("SSL_CERT_FILE", None)
        else:
            os.environ["SSL_CERT_FILE"] = saved
