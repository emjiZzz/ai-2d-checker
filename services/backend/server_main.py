"""Console entry point for the packaged backend server.

Frozen by `tools/draftcheck_server.spec` into `DraftCheck_Server.exe` and run on the LAN
server, matching how `KMTI_iCAD_Server.exe` and `KMTI_FMS_Server.exe` are deployed:

    C:\\Users\\Administrator\\Desktop\\DraftCheck\\dist\\DraftCheck_Server.exe

## Why a script rather than `-m uvicorn`

PyInstaller freezes a *script*, not a module invocation. `python -m uvicorn services.backend.main:app`
has no frozen equivalent, so the ASGI app is imported here and handed to `uvicorn.run` directly.

The app object is passed, never the `"module:attr"` string. Uvicorn resolves a string by
importing it, which works from a checkout and fails inside a bundle where the import graph is not
on disk in the same shape. Passing the object also rules out `--reload` and multiple workers, both
of which re-import by string -- neither is wanted for this deployment anyway.

## What it prints

Deliberately noisy at startup. This is a terminal application an operator watches, exactly like the
other two KMTI servers, and the three facts that determine whether it is working -- bind address,
storage root, database -- are the ones nobody can discover from a stack trace later.
"""

from __future__ import annotations

import sys


def _install_ca_bundle() -> None:
    """Make `certifi`'s roots the process default, when they are available.

    Silent when certifi is absent: running from source on a machine with a working certificate
    store is a legitimate configuration, and failing to start over it would be worse than the
    problem. The frozen build carries certifi -- see `tools/draftcheck_server.spec`.
    """
    import os

    try:
        import certifi
    except ImportError:
        return

    bundle = certifi.where()
    if not os.path.exists(bundle):
        return
    os.environ.setdefault("SSL_CERT_FILE", bundle)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle)


def main() -> int:
    import uvicorn

    # ABSOLUTE imports, not relative. PyInstaller executes this file as `__main__`, which has
    # no parent package, so `from .config import ...` dies with "attempted relative import with no
    # known parent package" -- at startup, before anything is logged. Verified by running the
    # frozen exe; the build itself completes happily either way.
    from services.backend.config import settings
    from services.backend.infrastructure.storage.path_resolver import get_storage_root
    from services.backend.runtime_paths import app_root, is_frozen

    # Point OpenSSL at the bundled CA roots before anything opens a TLS connection.
    #
    # A frozen build has no site-packages, so `ssl` falls back to the host's certificate store.
    # That store is not a constant: this worked on the build machine and failed on a fresh
    # Windows Server with `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`,
    # against Atlas, which is TLS-only. The backend then ran in disconnected mode with no
    # database -- a startup that looks successful and can do nothing.
    #
    # Set for the whole process rather than passed to the Mongo client alone, because every
    # outbound TLS call has the same dependency: Atlas, the Gemini API, licence checks.
    # `setdefault`, so an operator who points these at a corporate CA bundle keeps that.
    _install_ca_bundle()

    host = settings.HOST
    port = settings.PORT

    # A frozen build defaults to 127.0.0.1 like everything else, which on a LAN server means
    # "reachable by nobody". Said plainly at startup rather than left to be discovered from a
    # workstation that cannot connect.
    binding_note = (
        "  LAN clients CANNOT reach 127.0.0.1 -- set SIDECAR_HOST=0.0.0.0 in .env to serve them."
        if host in ("127.0.0.1", "localhost", "::1")
        else "  Serving all interfaces."
    )

    mongo = settings.MONGO_URI
    # Never print the connection string: it carries the Atlas password.
    mongo_display = mongo.split("@")[-1].split("/")[0] if "@" in mongo else mongo

    print("=" * 62)
    print("  DraftCheck -- Backend Server")
    print("=" * 62)
    print(f"  Mode        : {'FROZEN' if is_frozen() else 'source'}")
    print(f"  App root    : {app_root()}")
    print(f"  Storage     : {get_storage_root()}")
    print(f"  Database    : {mongo_display}")
    print(f"  Listening   : http://{host}:{port}")
    print(binding_note)
    print(f"  Health      : http://{host}:{port}/health")
    print("=" * 62)
    print()

    from services.backend.main import app

    uvicorn.run(app, host=host, port=port, log_level=settings.LOG_LEVEL.lower())
    return 0


if __name__ == "__main__":
    sys.exit(main())
