import os
import uuid
import aiofiles
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from ...domain.models.standard_document import StandardDocument
from ...domain.models.standard_chunk import StandardChunk
from ...infrastructure.audit.standards_loader import StandardsLoader
from ...infrastructure.storage.path_resolver import get_storage_root
from ...core.security import validate_sandboxed_path
from ...logger import logger, correlation_id_var
from ..dependencies import get_auth_token
from ..schemas import StandardResponse, StandardDocumentResponse

router = APIRouter()


@router.post(
    "/standards/upload",
    response_model=StandardResponse[StandardDocumentResponse],
    summary="Upload and ingest a new Engineering Standard document",
    dependencies=[Depends(get_auth_token)]
)
async def upload_standard(
    file: UploadFile = File(..., description="PDF, TXT, or Markdown standard document"),
    name: str = Form(..., description="Unique title identifier of the standard"),
    scope: str = Form("client_specific", description="Scope of standard: 'universal' or 'client_specific'"),
    client_name: str | None = Form(None, description="Associated client name if scope is client_specific"),
    category: str | None = Form(None, description="Optional category label (e.g. Dimensions)"),
    description: str | None = Form(None, description="Optional detail context summary")
):
    """
    Saves the uploaded engineering standard file, verifies limits,
    processes text sections, chunks contents, and persists data inside MongoDB Beanie collections.
    """
    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext not in ("pdf", "txt", "md", "xlsx", "xls"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported format: Standards must be PDF, TXT, Excel, or Markdown (.md, .txt, .xlsx, .xls)."
        )

    # 1. Enforce sandbox boundary temp file writes
    temp_dir = Path(get_storage_root()) / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    unique_id = uuid.uuid4().hex
    temp_file_path = temp_dir / f"std_upload_{unique_id}.{ext}"
    validate_sandboxed_path(temp_file_path)

    try:
        # Write to temporary sandboxed file
        async with aiofiles.open(temp_file_path, "wb") as f_out:
            while chunk := await file.read(65536):
                await f_out.write(chunk)

        # Ingest, hash, chunk, and save in database
        doc, is_duplicate = await StandardsLoader.ingest_standard(
            src_file_path=temp_file_path,
            name=name,
            scope=scope,
            client_name=client_name,
            category=category,
            description=description
        )

        return StandardResponse(
            success=True,
            data=StandardDocumentResponse(
                id=str(doc.id),
                name=doc.name,
                file_path=doc.file_path,
                standard_hash=doc.standard_hash,
                file_size_bytes=doc.file_size_bytes,
                format=doc.format,
                scope=doc.scope,
                client_name=doc.client_name,
                category=doc.category,
                description=doc.description,
                metadata=doc.metadata,
                created_at=doc.created_at
            )
        )

    except Exception as e:
        corr_id = correlation_id_var.get()
        logger.exception(f"[{corr_id}] Failed standard document ingestion: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ingestion process failed. Reference: {corr_id}"
        )
    finally:
        # Clean temporary file
        if temp_file_path.exists():
            try:
                temp_file_path.unlink()
            except Exception as clean_err:
                logger.warning(f"Failed to delete standard upload temp file: {str(clean_err)}")


@router.get(
    "/standards",
    response_model=StandardResponse[list[StandardDocumentResponse]],
    summary="List all registered engineering standards documents",
    dependencies=[Depends(get_auth_token)]
)
async def list_standards():
    """
    Fetches all registered standards from the local MongoDB registry.
    """
    docs = await StandardDocument.find_all().to_list()
    res = [
        StandardDocumentResponse(
            id=str(d.id),
            name=d.name,
            file_path=d.file_path,
            standard_hash=d.standard_hash,
            file_size_bytes=d.file_size_bytes,
            format=d.format,
            scope=d.scope,
            client_name=d.client_name,
            category=d.category,
            description=d.description,
            metadata=d.metadata,
            created_at=d.created_at
        )
        for d in docs
    ]
    return StandardResponse(success=True, data=res)


@router.get(
    "/standards/{id}",
    response_model=StandardResponse[StandardDocumentResponse],
    summary="Retrieve details of a registered standard",
    dependencies=[Depends(get_auth_token)]
)
async def get_standard(id: str):
    doc = await StandardDocument.get(id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Standard document not found for ID: {id}"
        )
    return StandardResponse(
        success=True,
        data=StandardDocumentResponse(
            id=str(doc.id),
            name=doc.name,
            file_path=doc.file_path,
            standard_hash=doc.standard_hash,
            file_size_bytes=doc.file_size_bytes,
            format=doc.format,
            scope=doc.scope,
            client_name=doc.client_name,
            category=doc.category,
            description=doc.description,
            metadata=doc.metadata,
            created_at=doc.created_at
        )
    )


@router.delete(
    "/standards/{id}",
    response_model=StandardResponse[dict],
    summary="Delete a registered engineering standard and its chunks",
    dependencies=[Depends(get_auth_token)]
)
async def delete_standard(id: str):
    """
    Permanently removes a StandardDocument and all associated StandardChunk records
    from MongoDB. The source file on disk is also removed if it exists.
    """
    doc = await StandardDocument.get(id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Standard document not found for ID: {id}"
        )

    # Remove all associated text chunks from the vector store
    chunks = await StandardChunk.find(StandardChunk.standard_id == id).to_list()
    for chunk in chunks:
        await chunk.delete()

    # Remove source file from disk if it exists
    try:
        file_path = get_storage_root() / doc.file_path
        if file_path.exists():
            file_path.unlink()
    except Exception as e:
        logger.warning(f"Could not remove standard source file: {str(e)}")

    await doc.delete()
    return StandardResponse(
        success=True,
        data={"message": f"Standard '{doc.name}' and all its chunks have been permanently removed."}
    )


@router.post(
    "/admin/standards/reindex",
    response_model=StandardResponse[dict],
    summary="Re-embed all existing standard chunks into the local semantic vector index",
    dependencies=[Depends(get_auth_token)]
)
async def reindex_standards():
    """
    Iterates all StandardChunk records in MongoDB and writes their text embeddings
    to the local LanceDB JSON vector index in batches.
    """
    from ...infrastructure.ai.vectorstore.embedding_provider import EmbeddingProvider
    from ...infrastructure.ai.vectorstore.lancedb_manager import LanceDBManager

    all_chunks = await StandardChunk.find_all().to_list()
    if not all_chunks:
        return StandardResponse(success=True, data={"reindexed": 0, "message": "No standard chunks found in database."})

    provider = EmbeddingProvider()
    db_manager = LanceDBManager()

    batch_size = 50
    total_written = 0
    errors = 0

    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        try:
            texts = [c.content for c in batch]
            vectors = provider.embed_texts(texts)
            records = [
                {
                    "vector": v,
                    "text": t,
                    "metadata": {
                        "standard_id": str(c.standard_id),
                        "standard_hash": getattr(c, "standard_hash", ""),
                        "section_header": c.section_header or "General",
                        "chunk_index": c.chunk_index,
                        "page_number": (c.metadata or {}).get("page_number", 1)
                    }
                }
                for v, t, c in zip(vectors, texts, batch)
            ]
            db_manager.write_embeddings("standards_reference", records)
            total_written += len(records)
            logger.info(f"Reindex: wrote batch {i // batch_size + 1} ({len(records)} vectors).")
        except Exception as batch_err:
            logger.warning(f"Reindex batch {i // batch_size + 1} failed: {batch_err}")
            errors += 1

    return StandardResponse(
        success=True,
        data={
            "reindexed": total_written,
            "errors": errors,
            "message": f"Successfully re-indexed {total_written} standard chunks into the semantic vector store."
        }
    )
