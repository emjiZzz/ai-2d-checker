import os
import traceback
from pathlib import Path
from ...logger import logger

class SolidWorksConverter:
    """
    Silent background COM integration module for SolidWorks.
    Automates conversion of native .sldprt / .sldasm formats into standard STEP files.
    """

    @staticmethod
    def convert_to_step(file_path: Path) -> Path:
        """
        Launches local SolidWorks app via COM interface and silent-saves STEP companion.
        """
        logger.info(f"SolidWorks Ingestion: Initiating COM conversion for: {file_path.name}")
        
        # win32com and pythoncom imports are kept local to avoid dependency issues on non-Windows systems
        try:
            import win32com.client
            import pythoncom
        except ImportError:
            logger.error("SolidWorks Ingestion Error: pywin32 library is not installed in the Python environment.")
            raise RuntimeError("pywin32 dependencies are missing on the local machine.")

        pythoncom.CoInitialize()
        sw_app = None
        doc = None
        try:
            # 1. Connect to active SolidWorks app or launch new headless application
            logger.info("Accessing local SldWorks.Application COM wrapper...")
            try:
                sw_app = win32com.client.GetActiveObject("SldWorks.Application")
                logger.info("COM: Swapp connected to active SolidWorks session.")
            except Exception:
                sw_app = win32com.client.Dispatch("SldWorks.Application")
                logger.info("COM: Launched new background SldWorks app session.")

            sw_app.Visible = False  # Keep application headless and silent
            
            # Determine SW Doc Types (Part = 1, Assembly = 2)
            ext = file_path.suffix.lower()
            doc_type = 1 if ext == ".sldprt" else 2
            
            # 2. Open document silently
            errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            
            logger.info(f"Opening native document {file_path.name} via COM OpenDoc6...")
            doc = sw_app.OpenDoc6(
                str(file_path),
                doc_type,
                1,  # swOpenDocOptions_Silent
                "",
                errors,
                warnings
            )
            
            if not doc:
                raise RuntimeError(
                    f"SolidWorks failed to open target CAD file (Code: {errors.value})."
                )

            # 3. Export to temporary STEP companion
            temp_step_path = file_path.with_suffix(".step")
            logger.info(f"Exporting to temporary STEP format: {temp_step_path.name}")
            
            save_errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            save_warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            
            # SaveAs4 parameters: FilePath, Version (0=current), Options (2=swSaveAsSilent), Errors, Warnings
            success = doc.SaveAs4(
                str(temp_step_path),
                0,
                2,
                save_errors,
                save_warnings
            )
            
            # Force close active document
            sw_app.CloseDoc(doc.Title)
            
            if not success or not temp_step_path.exists():
                raise RuntimeError(
                    f"SolidWorks export failed (Code: {save_errors.value})."
                )
                
            logger.info("SolidWorks Ingestion: Successfully completed background STEP conversion.")
            return temp_step_path
            
        except Exception as e:
            logger.error(f"SolidWorks COM pipeline conversion crashed: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        finally:
            pythoncom.CoUninitialize()
