from typing import Any
from ....logger import logger
from .embedding_provider import EmbeddingProvider
from .lancedb_manager import LanceDBManager


class StandardsVectorIndexer:
    """
    Dedicated service for generating vector embeddings and persisting
    standards chunks into the local LanceDB vector store.
    Encapsulates LanceDB schemas and embedding provider interactions.
    """

    @staticmethod
    def index_standard_chunks(
        doc_id: str,
        standard_hash: str,
        name: str,
        chunks: list[dict[str, Any]],
        table_name: str = "standards_reference"
    ) -> bool:
        """
        Computes dense vector embeddings for standard text chunks and
        persists them to LanceDB.
        
        Returns:
            bool: True if indexing succeeded, False if a non-fatal error occurred.
        """
        if not chunks:
            return False

        try:
            provider = EmbeddingProvider()
            db_manager = LanceDBManager()

            texts = [c.get("content", "") for c in chunks]
            vectors = provider.embed_texts(texts)

            vector_records = []
            for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
                meta = chunk.get("metadata")
                page_num = meta.get("page_number", 1) if isinstance(meta, dict) else 1

                vector_records.append({
                    "vector": vec,
                    "text": chunk.get("content", ""),
                    "metadata": {
                        "standard_id": str(doc_id),
                        "standard_hash": standard_hash,
                        "section_header": chunk.get("section_header"),
                        "chunk_index": i,
                        "page_number": page_num
                    }
                })

            db_manager.write_embeddings(table_name, vector_records)
            logger.info(f"StandardsVectorIndexer: Wrote {len(vector_records)} semantic embeddings for standard '{name}'.")
            return True

        except Exception as vec_err:
            logger.warning(f"StandardsVectorIndexer: Embedding indexing failed for '{name}' (non-fatal): {vec_err}")
            return False
