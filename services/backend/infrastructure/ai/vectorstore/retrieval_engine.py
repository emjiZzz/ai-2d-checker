from typing import List, Dict, Any
from ....logger import logger
from .embedding_provider import EmbeddingProvider
from .lancedb_manager import LanceDBManager

class RetrievalEngine:
    """
    Performs vector similarity search against the local vector database.
    Wires the local LanceDBManager index for live semantic matching.
    """
    
    def __init__(self):
        self.embedding_provider = EmbeddingProvider()
        self.db_manager = LanceDBManager()
        
    def query(self, search_text: str, top_k: int = 3, collection_name: str = "standards_reference") -> List[Dict[str, Any]]:
        """
        Embeds the query text and retrieves the K closest semantic matches from vector persistence.
        """
        logger.info(f"Performing local semantic search for: '{search_text[:35]}...'")
        
        # 1. Embed query search text (creates a 384-dim normalized vector)
        query_vector = self.embedding_provider.embed_texts([search_text])[0]
        
        # 2. Query underlying local database index
        results = self.db_manager.query_similarity(
            collection_name=collection_name,
            query_vector=query_vector,
            top_k=top_k
        )
        
        return results
