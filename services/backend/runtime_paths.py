"""Where the application's own files live, whether running from source or frozen.

## Why this exists

Two modules resolved the project root by counting `..` from `__file__`:

    services/backend/config.py                    -> parents[2] / ".env"
    .../infrastructure/storage/path_resolver.py   -> parents[4] / "storage"

That is correct from a source checkout and **wrong the moment the backend is frozen**. PyInstaller
unpacks a onefile build into a temporary directory and sets `__file__` inside it, so:

* `.env` is looked for in the temp dir, is not there, and every setting silently falls back to its
  default -- including `MONGO_URI`, which would point at localhost instead of Atlas;
* 🔴 `storage/` resolves into the temp dir too, which the OS **deletes when the process exits**.
  Uploaded drawings, renderings and the eval corpus would be written to a directory that is
  removed on shutdown, and nothing would report an error.

The second one is why this is a module rather than an inline `if` in each file. Both must agree on
one answer; two copies of a path rule that disagree is how the metadata says a drawing exists and
the file does not, which this project has already paid for once.

## The rule

**Frozen: the directory containing the executable.** That is stable, writable in the deployment
layout the other KMTI servers use (`...\Desktop\<System>\dist\`), and predictable to an operator
who wants to find the logs.

**From source: the repository root**, exactly as before, so development behaviour is unchanged.

⚠ `sys.executable` and NOT `sys._MEIPASS`. `_MEIPASS` is the temp unpack directory -- correct for
reading bundled read-only resources, and the wrong answer for anything the app writes.
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
