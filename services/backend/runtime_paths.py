r"""Where the application's own files live, whether running from source or frozen.

`config.py` and `path_resolver.py` each counted `..` from `__file__`, which is correct from a
checkout and wrong once frozen: PyInstaller unpacks into a temp directory and sets `__file__`
inside it. So `.env` was looked for there, was absent, and every setting silently fell back to
its default -- `MONGO_URI` included, pointing at localhost instead of Atlas. And `storage/`
resolved into the same temp directory, which the OS deletes on exit: uploads, renderings and the
eval corpus written to a directory that disappears at shutdown, with no error anywhere.

One module rather than an inline `if` in each file, because both must agree. Two copies of a path
rule that disagree is how the metadata says a drawing exists and the file does not, which this
project has already paid for once.

The rule: frozen resolves to the directory containing the executable, which is stable, writable
in the deployment layout the other KMTI servers use (`...\Desktop\<System>\dist\`) and findable
by an operator looking for logs. From source it is the repository root, so development is
unchanged. It uses `sys.executable`, never `sys._MEIPASS` -- that is the temp unpack directory,
right for reading bundled read-only resources and wrong for anything the app writes.
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """The directory holding `.env` and `storage/`.

    Frozen -> beside the executable. From source -> the repository root.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # services/backend/runtime_paths.py -> backend -> services -> <repo root>
    return Path(__file__).resolve().parents[2]


def bundled_resource_root() -> Path:
    """Where read-only files packaged INTO the executable were unpacked.

    Distinct from `app_root()` on purpose: this one is the temp directory and is destroyed on
    exit, so it is only ever correct for reading things PyInstaller bundled. Falls back to
    `app_root()` from source, where the two coincide.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else app_root()
