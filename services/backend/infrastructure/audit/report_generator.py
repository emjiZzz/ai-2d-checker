import re
from pathlib import Path

from ...core.security import validate_sandboxed_path
from ...domain.models.audit_session import AuditSession
from ...domain.models.audit_violation import AuditViolation
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.standard_document import StandardDocument
from ...infrastructure.storage.path_resolver import get_storage_root
from ...logger import logger
from .pdf_exporter import PDFComplianceExporter
from .xlsx_exporter import XLSXComplianceExporter


class ReportGenerator:
    """
    Coordinates and compiles enterprise engineering audit reports (PDF & Excel)
    from MongoDB session documents and writes them to sandboxed paths.
    """
    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """
        Hardens filenames to block path traversal, dot-dot attacks, or illegal symbols.
        """
        clean = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)
        # Prevent dot-dot or sequence exploits
        while ".." in clean:
            clean = clean.replace("..", ".")
        return clean.strip("_")

    async def generate_reports(self, session_id: str) -> dict[str, Path]:
        """
        Generates and saves sandboxed XLSX and PDF compliance logs.
        Returns:
            paths: Dict containing keys 'pdf' and 'xlsx' mapped to absolute Path locations.
        """
        logger.info(f"Initiating report compilation process for Session ID: {session_id}")
        
        # 1. Fetch matching models from MongoDB Beanie store
        session = await AuditSession.get(session_id)
        if not session:
            raise FileNotFoundError(f"Auditing session not found: {session_id}")
            
        drawing = await DrawingDocument.get(session.drawing_id)
        standard = await StandardDocument.get(session.standard_id)
        violations = await AuditViolation.find(AuditViolation.audit_session_id == session_id).to_list()
        
        logger.info(f"Retrieved {len(violations)} infractions for compilation from session {session_id}.")
        
        # 2. Establish sandboxed export target directories
        storage_root = get_storage_root()
        export_dir = storage_root / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        
        validate_sandboxed_path(export_dir)
        
        # Sanitize baseline name
        base_name = self._sanitize_filename(drawing.file_name if drawing else f"session_{session_id}")
        base_name_without_ext = Path(base_name).stem
        
        pdf_filename = f"AI_Audit_Report_{base_name_without_ext}_{session_id[:8]}.pdf"
        xlsx_filename = f"AI_Technical_Sheet_{base_name_without_ext}_{session_id[:8]}.xlsx"
        
        pdf_path = export_dir / pdf_filename
        xlsx_path = export_dir / xlsx_filename
        
        # Canonical sandbox checks
        validate_sandboxed_path(pdf_path)
        validate_sandboxed_path(xlsx_path)
        
        # 3. Trigger individual layout compilers
        PDFComplianceExporter.generate_pdf(pdf_path, session, drawing, standard, violations)
        XLSXComplianceExporter.generate_xlsx(xlsx_path, session, drawing, standard, violations)
        
        return {
            "pdf": pdf_path,
            "xlsx": xlsx_path
        }
