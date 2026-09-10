"""Convert iCAD SX .icd drawings to DXF with the vendor translator.

An .icd holds both a 3D model and 2D drawing content. This converts the 2D half, which is
what the comparison engine reads; the 3D half needs `ICD2STP.exe`, which answers exit 102
(batch-STEP licence not active) on the current install.

A conversion that reports success can still be empty, so callers must count what came out.
See `06 - .../Gotcha - iCAD .icd Converts Silently Empty.md`.
"""

import asyncio
import os
import subprocess
import tempfile
import time
from pathlib import Path

import ezdxf

from ...config import settings
from ...core.security import validate_sandboxed_path
from ...logger import logger


class ICDConverter:
    def __init__(self, icad_dir: str = settings.ICAD_DIR):
        self.icad_dir = Path(icad_dir)
        self.converter_path = self.icad_dir / "TR2" / "DXFDWG" / "bin" / "TR2_DExp.exe"

    def _verify_executable(self) -> None:
        if not self.converter_path.exists() or not self.converter_path.is_file():
            logger.error(f"iCAD DXF translator not found at: {self.converter_path}")
            raise FileNotFoundError(
                f"iCAD SX DXF translator was not found at: {self.converter_path}. "
                "Please configure ICAD_DIR in your .env settings."
            )

    def _environment(self, usrhome: Path) -> dict[str, str]:
        """The library set from the install's own ETC/ICENV.INI, plus an isolated home.

        IUSRHOME is redirected at a scratch directory because the vendor's sample wrapper
        runs `rmdir %IUSRHOME%\\TR2_DB /S /Q`, which would delete inside the live install.
        """
        env = dict(os.environ)
        env.update(
            {
                "ICADDIR": str(self.icad_dir),
                "IUSRHOME": str(usrhome),
                "BATCHMODE": "1",
                "MDL00": str(self.icad_dir / "parts" / "部品フォルダ１"),
                "LIB00": str(self.icad_dir),
                "LIB01": str(self.icad_dir / "mmf" / "図面フォルダ"),
                "LIB02": str(self.icad_dir / "parts" / "部品フォルダ２"),
                "LIB05": str(self.icad_dir / "parts" / "部品フォルダ３"),
                "LIB08": str(self.icad_dir / "sysmmf" / "システムフォルダ"),
                "ILOGFN": str(usrhome / "cmdlog"),
                "IMACDN": str(self.icad_dir / "macro"),
                "IMSGIDX": str(self.icad_dir / "msg" / "msgidx_J"),
                "IMSGF0": str(self.icad_dir / "msg" / "sdsmsg_J"),
                "IMSGF1": str(self.icad_dir / "msg" / "usrmsg1"),
                "KGSV": str(self.icad_dir / "kgs"),
                "RESFILE": str(usrhome / "res00"),
                "ROLFILE": str(usrhome / "rol00"),
            }
        )
        return env

    async def convert_icd_to_dxf(
        self, icd_path: Path, dxf_output_dir: Path, validate_sandbox: bool = True
    ) -> Path:
        """Asynchronously convert an .icd into DXF.

        Returns the DXF path. Whether it holds any geometry is the caller's question --
        `count_drawing_entities` answers it.

        `validate_sandbox` is the default because an uploaded path is user-supplied and must
        stay inside the storage root. Only `tools/icd_to_dxf.py` turns it off, to seed a
        corpus from the drawing share, where the paths come from an operator's command line
        and never from HTTP.
        """
        if validate_sandbox:
            validate_sandboxed_path(icd_path)
            validate_sandboxed_path(dxf_output_dir)

        self._verify_executable()

        if not icd_path.exists() or not icd_path.is_file():
            raise FileNotFoundError(f"Input iCAD drawing file not found: {icd_path}")

        dxf_output_dir.mkdir(parents=True, exist_ok=True)
        expected_dxf_path = dxf_output_dir / f"{icd_path.stem}.dxf"
        if expected_dxf_path.exists():
            try:
                expected_dxf_path.unlink()
            except Exception as e:
                logger.warning(f"Could not purge pre-existing DXF at {expected_dxf_path}: {e}")

        start_time = time.time()

        def run_subprocess():
            # A list file rather than arguments: the translator is also driven over whole
            # corpora by tools/icd_to_dxf.py, where the argument form hits the command-line
            # length limit. Odd lines are inputs, even lines output names; an empty even
            # line keeps the source name. See MAN/dxf_dwg_trans.pdf section 6-1-2.
            with tempfile.TemporaryDirectory(prefix="icd2dxf_") as tmp:
                usrhome = Path(tmp)
                listing = usrhome / "drawlist.txt"
                listing.write_text(f"{icd_path}\n\n", encoding="cp932", errors="replace")
                kwargs = {
                    "stdout": subprocess.PIPE,
                    "stderr": subprocess.PIPE,
                    "timeout": 120.0,
                    "env": self._environment(usrhome),
                    "cwd": str(dxf_output_dir),
                }
                if os.name == "nt":
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                return subprocess.run(
                    [
                        str(self.converter_path),
                        "-RN", str(listing),
                        "-dxf", settings.ICAD_DXF_VERSION,
                        "-o", str(dxf_output_dir),
                        "-msg", "0",
                    ],
                    **kwargs,
                )

        try:
            result = await asyncio.to_thread(run_subprocess)
        except subprocess.TimeoutExpired as te:
            raise TimeoutError(
                f"iCAD DXF translator timed out converting {icd_path.name}."
            ) from te

        elapsed = time.time() - start_time
        logger.info(
            f"iCAD translator exited with code {result.returncode} in {elapsed:.4f}s "
            f"for '{icd_path.name}'"
        )

        # The translator answers 0 and logs `09271 registered` whether or not the drawing
        # had any 2D content, so the exit code is checked for process failure only.
        if not expected_dxf_path.exists():
            err_text = result.stderr.decode("cp932", errors="replace").strip()
            out_text = result.stdout.decode("cp932", errors="replace").strip()
            logger.error(
                f"iCAD translator produced no DXF (code {result.returncode}): "
                f"{err_text} | Out: {out_text}"
            )
            raise RuntimeError(
                f"iCAD SX DXF translation produced no output for {icd_path.name} "
                f"(exit code {result.returncode})."
            )

        return expected_dxf_path


def count_drawing_entities(dxf_path: Path) -> int:
    """Entities in modelspace with blocks resolved.

    Counting modelspace directly undercounts badly: an iCAD title block arrives as a single
    INSERT that expands to a few hundred entities, so a raw count reads 1 where the truth is
    233. Shared with tools/icd_to_dxf.py so the tool and the pipeline cannot hold different
    opinions about whether a conversion was empty.
    """
    doc = ezdxf.readfile(dxf_path)
    total = 0
    stack = list(doc.modelspace())
    while stack:
        e = stack.pop()
        if e.dxftype() == "INSERT":
            try:
                stack.extend(e.virtual_entities())
            except Exception:
                total += 1
        else:
            total += 1
    return total
