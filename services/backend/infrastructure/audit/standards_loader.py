import os
import hashlib
import shutil
from pathlib import Path
from typing import Optional, Tuple
from ...logger import logger
from ...config import settings
from ...core.security import validate_sandboxed_path
from ...domain.models.standard_document import StandardDocument
from ...domain.models.standard_chunk import StandardChunk
from .standards_parser import StandardsParser

class StandardsLoader:
    """
    Ingests and registers new engineering standards.
    Handles traversal protection, file hashing, duplicate bypass, parsing,
    and bulk saving of StandardDocuments and StandardChunks in MongoDB.
    """

    @staticmethod
    def calculate_file_hash(file_path: Path) -> str:
        """
        Computes the SHA-256 hash checksum of a local file.
        """
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()

    @staticmethod
    async def ingest_standard(
        src_file_path: Path,
        name: str,
        scope: str = "client_specific",
        client_name: Optional[str] = None,
        category: Optional[str] = None,
        description: Optional[str] = None,
        max_size_mb: int = 50
    ) -> Tuple[StandardDocument, bool]:
        """
        Validates, duplicates, parses, and persists a standard file.
        Returns:
            document: Saved StandardDocument instance.
            is_duplicate: True if the standard already existed in the system.
            """
        # 1. Traversal and bounds checking
        validate_sandboxed_path(src_file_path)

        if not src_file_path.exists() or not src_file_path.is_file():
            raise FileNotFoundError(f"Engineering standard file does not exist: {src_file_path}")

        # Validate size bounds
        file_size_bytes = src_file_path.stat().st_size
        max_size_bytes = max_size_mb * 1024 * 1024
        if file_size_bytes > max_size_bytes:
            raise ValueError(f"Engineering standard file size exceeds maximum limit of {max_size_mb}MB.")

        # Validate format
        ext = src_file_path.suffix.lower().lstrip(".")
        if ext not in ("pdf", "txt", "md", "xlsx", "xls"):
            raise ValueError(f"Unsupported format: .{ext}. Standards must be PDF, TXT, Excel, or Markdown.")

        # Compute secure hash
        standard_hash = StandardsLoader.calculate_file_hash(src_file_path)

        # 2. Check for duplicate standard documents in Database
        existing = await StandardDocument.find_one(StandardDocument.standard_hash == standard_hash)
        if existing:
            logger.info(f"Engineering standard duplicate detected (bypassing parsing): {name}")
            return existing, True

        # Ensure standards sandbox directory exists
        standards_dir = Path(settings.STORAGE_ROOT) / "standards"
        standards_dir.mkdir(parents=True, exist_ok=True)

        # Move to standards storage sandbox
        dest_filename = f"{standard_hash}.{ext}"
        dest_path = standards_dir / dest_filename
        
        # Avoid redundant copies
        if not dest_path.exists():
            shutil.copy2(src_file_path, dest_path)

        relative_path = os.path.relpath(dest_path, settings.STORAGE_ROOT)

        # 3. Parse and chunk document contents
        chunks, parsed_meta = StandardsParser.parse_file(dest_path)

        if not chunks:
            # If no chunks were extracted, insert a fallback general chunk to avoid empty standards
            chunks = [{
                "content": f"Engineering Standard Document: {name}",
                "section_header": "General",
                "metadata": {"fallback": True}
            }]

        # 4. Save metadata document in MongoDB
        doc = StandardDocument(
            name=name,
            file_path=relative_path,
            standard_hash=standard_hash,
            file_size_bytes=file_size_bytes,
            format=ext,
            scope=scope,
            client_name=client_name,
            category=category,
            description=description,
            metadata=parsed_meta
        )
        await doc.save()

        # 5. Bulk ingest StandardChunks in MongoDB
        db_chunks = []
        for idx, chunk in enumerate(chunks):
            db_chunks.append(
                StandardChunk(
                    standard_id=str(doc.id),
                    standard_hash=standard_hash,
                    chunk_index=idx,
                    content=chunk["content"],
                    section_header=chunk["section_header"],
                    metadata=chunk["metadata"]
                )
            )

        if db_chunks:
            await StandardChunk.insert_many(db_chunks)

        logger.info(f"Ingested standard standard document '{name}' with {len(db_chunks)} parsed chunks successfully.")
        return doc, False
