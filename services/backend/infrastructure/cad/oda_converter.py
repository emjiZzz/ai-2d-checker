import os
import asyncio
import time
from pathlib import Path
from ...config import settings
from ...logger import logger
from ...core.security import validate_sandboxed_path

class ODAConverter:
    def __init__(self, converter_path: str = settings.ODA_CONVERTER_PATH):
        self.converter_path = Path(converter_path)

    def _verify_executable(self) -> None:
        """
        Verify the ODA File Converter executable exists.
        """
        if not self.converter_path.exists() or not self.converter_path.is_file():
            logger.error(f"ODA File Converter executable not found at specified path: {self.converter_path}")
            raise FileNotFoundError(
                f"ODA File Converter executable was not found at: {self.converter_path}. "
                "Please configure ODA_CONVERTER_PATH in your .env settings."
            )

    async def convert_dwg_to_dxf(self, dwg_path: Path, dxf_output_dir: Path) -> Path:
        """
        Asynchronously invokes the ODA File Converter CLI to safely convert
        a sandboxed DWG file into DXF format.
        """
        # 1. Enforce strict sandbox path traversals protection
        validate_sandboxed_path(dwg_path)
        validate_sandboxed_path(dxf_output_dir)

        self._verify_executable()

        if not dwg_path.exists() or not dwg_path.is_file():
            raise FileNotFoundError(f"Input DWG drawing file not found: {dwg_path}")

        # Ensure output directory exists within the sandbox
        dxf_output_dir.mkdir(parents=True, exist_ok=True)

        input_dir = dwg_path.parent
        file_name = dwg_path.name
        dxf_filename = dwg_path.stem + ".dxf"
        expected_dxf_path = dxf_output_dir / dxf_filename

        # Clean up any pre-existing converted file in the target location
        if expected_dxf_path.exists():
            try:
                expected_dxf_path.unlink()
            except Exception as e:
                logger.warning(f"Could not purge pre-existing DXF file at {expected_dxf_path}: {str(e)}")

        # Configure command: ODAFileConverter input_dir output_dir version format recurse audit [filter]
        # Using ACAD2018 format and DXF output type
        args = [
            str(input_dir),
            str(dxf_output_dir),
            "ACAD2018",
            "DXF",
            "0",
            "1",
            file_name
        ]

        logger.info(
            f"Invoking secure ODA subprocess: '{self.converter_path}' with args {args[2:]} "
            f"for file '{file_name}'"
        )
        
        start_time = time.time()
        try:
            # Safe process spawn wrapper
            proc = await asyncio.create_subprocess_exec(
                str(self.converter_path),
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Wait for execution with a 60-second limit to avoid process lock leaks
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
            
            elapsed = time.time() - start_time
            logger.info(f"ODA subprocess exited with code {proc.returncode} in {elapsed:.4f}s")

            if proc.returncode != 0:
                err_text = stderr.decode(errors="replace").strip()
                out_text = stdout.decode(errors="replace").strip()
                logger.error(f"ODA Converter Error (code {proc.returncode}): {err_text} | Out: {out_text}")
                raise RuntimeError(
                    f"ODA File Converter failed with exit code {proc.returncode}. Error details: {err_text}"
                )

            # Verify that the converter actually outputted the file
            # ODA File Converter outputs the DXF inside output_dir with same name structure
            # Note: ODA File Converter sometimes outputs DXF with lowercase/uppercase extensions.
            # Let's perform a robust search in output_dir.
            actual_dxf_path = None
            for p in dxf_output_dir.iterdir():
                if p.is_file() and p.stem.lower() == dwg_path.stem.lower() and p.suffix.lower() == ".dxf":
                    actual_dxf_path = p
                    break

            if not actual_dxf_path or not actual_dxf_path.exists():
                logger.error(
                    f"ODA subprocess completed successfully but no expected DXF was generated. "
                    f"Checked location: {dxf_output_dir}"
                )
                raise RuntimeError("ODA File Converter failed to output a DXF drawing.")

            # Validate that the generated path resides strictly inside the sandbox
            validate_sandboxed_path(actual_dxf_path)
            logger.info(f"Successfully generated converted DXF sandbox file: {actual_dxf_path}")
            return actual_dxf_path

        except asyncio.TimeoutError:
            logger.error("ODA Conversion process timed out (exceeded 60s limit).")
            raise RuntimeError("ODA File Converter execution timed out.")
        except Exception as e:
            logger.error(f"Critical error occurred during ODA conversion execution: {str(e)}")
            raise
