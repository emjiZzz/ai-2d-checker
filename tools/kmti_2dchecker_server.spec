# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the LAN backend server.

Build from the repo root:

    services/backend/.venv/Scripts/python.exe -m PyInstaller tools/kmti_2dchecker_server.spec --noconfirm

Produces `dist/KMTI_2DChecker_Server.exe` -- a console application, matching how
`KMTI_iCAD_Server.exe` and `KMTI_FMS_Server.exe` are deployed on 192.168.200.105.

## Why onedir and not onefile

`--onefile` unpacks the whole bundle to a temp directory on every launch. For a stack this size
that is a multi-second startup and a large temp write each time, and the temp directory is exactly
the trap `services/backend/runtime_paths.py` documents. `onedir` starts fast, and the layout
matches the `dist\\` folder the other two servers already use.

## The collect_all calls, and why each is here

PyInstaller finds imports by static analysis. These four defeat it in different ways:

* **ezdxf** loads font metrics and resources from package DATA at run time, and resolves some
  entity handlers dynamically -- neither is visible as an `import`.
* **matplotlib** ships `mpl-data` (fonts, style sheets) and picks a backend by name at run time.
  The vector PDF export needs it; nothing else does.
* **fitz** (PyMuPDF) is a C extension with its own bundled binaries.
* **uvicorn** resolves its protocol, loop and lifespan implementations from strings, so
  `uvicorn.protocols.*` and friends look unused to the analyser and get dropped.

⚠ **`.env` and `storage/` are deliberately NOT bundled.** They belong beside the executable on the
server, not inside it -- `.env` holds the Atlas password and must stay editable by an operator, and
`storage/` is the shared drawing corpus that has to survive replacing the exe. `runtime_paths.app_root()`
resolves both to the executable's own directory when frozen.
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []

for package in ("ezdxf", "matplotlib", "fitz", "uvicorn"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Beanie/Motor build their model registry through Pydantic at import time; the ODM's own
# submodules are reached dynamically often enough that the analyser misses some.
for package in ("beanie", "motor", "pymongo", "encodings"):
    hiddenimports += collect_submodules(package)

# The app's own routers are imported through `api.v1` by name; keeping the whole package explicit
# means a new router does not silently drop out of the build.
hiddenimports += collect_submodules("services.backend")

a = Analysis(
    ["../services/backend/server_main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Excluded on purpose: these are development-only and pull in large trees.
    # ⚠ Do NOT add sklearn/scipy here without checking -- the learned model imports them, and a
    # missing one surfaces at request time as a 500 rather than at build time.
    excludes=["tkinter", "pytest", "IPython", "notebook", "PyInstaller"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KMTI_2DChecker_Server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX mangles some native extensions; not worth the risk on one server.
    console=True,       # Terminal application, like the other two KMTI servers.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KMTI_2DChecker_Server",
)
