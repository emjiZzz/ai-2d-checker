import asyncio
import hashlib
import os
import shutil
from pathlib import Path

from ...core.security import validate_sandboxed_path
from ...domain.models.standard_chunk import StandardChunk
from ...domain.models.standard_document import StandardDocument
from ...logger import logger
from ..retrieval.encoder import EncoderError
from ..retrieval.service import rebuild_standards_index
from ..storage.path_resolver import get_storage_root
from .standards_parser import (
    SUPPORTED_STANDARD_FORMATS,
    StandardIngestError,
    StandardsParser,
)


def standards_storage_dir() -> Path:
    """Where ingested standards are kept, as a path the sandbox guard will accept.

    Derived from `get_storage_root()` and **not** from `settings.STORAGE_ROOT`, which defaults to
    the relative `"./storage"` and therefore resolves against the backend's working directory.
    Those two disagreed, and the disagreement was a live 400 on every upload:

        Path Traversal Attempt Blocked: Resolved path
        '...\\services\\backend\\storage\\standards\\<hash>.xls'
        escapes storage root boundary '...\\ai-2d-checker\\storage'

    The loader wrote under one root while `validate_sandboxed_path` — whose docstring calls
    `get_storage_root()` *"the single source of truth ... regardless of the process working
    directory"* — enforced the other. Nothing caught it because no upload had ever reached this
    far: the endpoint 405'd, and before that `.xls` was rejected earlier in the chain.

    Exposed as a function purely so the invariant is assertable: the directory this returns must
    survive `validate_sandboxed_path`. See `test_standards_ingest_guards.py`.
    """
    return get_storage_root() / "standards"


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
        client_name: str | None = None,
        category: str | None = None,
        description: str | None = None,
        max_size_mb: int = 50
    ) -> tuple[StandardDocument, bool]:
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

        # Validate format against the parser's own list rather than a second copy of it.
        ext = src_file_path.suffix.lower().lstrip(".")
        if ext not in SUPPORTED_STANDARD_FORMATS:
            raise StandardIngestError(
                f"Unsupported format '.{ext}'. Standards must be one of: "
                f"{', '.join('.' + f for f in SUPPORTED_STANDARD_FORMATS)}."
            )

        # Compute secure hash off-thread to avoid blocking event loop
        standard_hash = await asyncio.to_thread(StandardsLoader.calculate_file_hash, src_file_path)

        # 2. Check for duplicate standard documents in Database
        existing = await StandardDocument.find_one(StandardDocument.standard_hash == standard_hash)
        if existing:
            logger.info(f"Engineering standard duplicate detected (bypassing parsing): {name}")
            return existing, True

        # Ensure standards sandbox directory exists
        standards_dir = standards_storage_dir()
        standards_dir.mkdir(parents=True, exist_ok=True)

        # Move to standards storage sandbox
        dest_filename = f"{standard_hash}.{ext}"
        dest_path = standards_dir / dest_filename
        
        # Avoid redundant copies off-thread
        created_dest = not dest_path.exists()
        if created_dest:
            await asyncio.to_thread(shutil.copy2, src_file_path, dest_path)

        # Relative to the SAME root the readers resolve against. Taking it against
        # settings.STORAGE_ROOT stored a path that only resolved correctly when the backend's
        # working directory happened to match — so a document row could point at nothing.
        relative_path = os.path.relpath(dest_path, get_storage_root())

        # 3. Parse and chunk document contents off-thread to prevent event loop stalls on heavy PDFs
        try:
            chunks, parsed_meta = await asyncio.to_thread(StandardsParser.parse_file, dest_path)
        except Exception:
            # Do not leave an unreferenced file in the standards sandbox when no StandardDocument
            # will be saved for it. Only remove what this call created — an existing file may
            # belong to a document whose row was deleted while the blob was kept.
            if created_dest:
                dest_path.unlink(missing_ok=True)
            raise

        if not chunks:
            # **This used to succeed.** A parse yielding nothing substituted one chunk holding
            # only the title the uploader typed, saved it, and returned 200. The standard then
            # appeared in the list, reported a chunk, and contained none of its own content —
            # for a scanned PDF, the most likely failure of all, and permanently, because
            # re-uploading hits the duplicate-hash bypass.
            #
            # That is the same shape as the SHA-256 embeddings this project already paid for:
            # returning something plausible instead of failing. An empty parse is now an error,
            # and it names the cause the uploader can act on.
            if created_dest:
                dest_path.unlink(missing_ok=True)
            if ext == "pdf":
                reason = (
                    "No text could be extracted. This is usually a scanned PDF with no text "
                    "layer — the parser reads embedded text, it does not run OCR. Run OCR over "
                    "it first, or supply the content as .xlsx, .md or .txt."
                )
            elif ext == "xlsx":
                reason = (
                    "No text was found in any cell of any sheet. Content that exists only "
                    "inside embedded images is not read."
                )
            else:
                reason = "No text content could be extracted from this file."
            raise StandardIngestError(f"'{name}' was not ingested. {reason}")

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

        # R1 (ADR-008): rebuild the lexical retrieval index over the new corpus.
        #
        # Whole-corpus rebuild, not an append: TF-IDF's idf is a property of the corpus, so
        # adding chunks changes the weighting of every n-gram they contain. Appending would
        # leave new and old chunks ranked under different weights — an error that produces
        # plausible orderings and no symptom.
        #
        # Off-thread because fitting a vocabulary is genuinely CPU-bound. The step this
        # replaces was called inline and got away with it only because its "embedding" was a
        # random number generator (R0 deleted it). Guarded by test_standards_loader_async.py.
        #
        # A failed rebuild must not fail the upload: the chunks are already committed to Mongo
        # above, which is the source of truth, and the index is a derived artifact that startup
        # or the next upload will rebuild. `query()` reports MISSING rather than pretending to
        # have searched, so a missing index is visible instead of silent.
        try:
            result = await rebuild_standards_index()
            logger.info(
                f"[retrieval] standards index: {result.n_records} record(s), "
                f"built={result.built}{f' ({result.reason})' if result.reason else ''}"
            )
        except (OSError, ValueError, EncoderError) as index_err:
            logger.error(
                f"[retrieval] Failed to rebuild the standards index after ingesting "
                f"'{name}': {index_err}. The chunks are saved; the index is stale until the "
                f"next rebuild."
            )

        logger.info(f"Ingested standard standard document '{name}' with {len(db_chunks)} parsed chunks successfully.")
        return doc, False
