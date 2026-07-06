
from ....logger import logger
from ..embeddings.local_embedding_model import LocalEmbeddingModel


class EmbeddingProvider:
    """
    Acts as the interface for generating vector embeddings from text/geometry chunks.
    Automatically routes to the local, offline embedding model.
    """
    
    def __init__(self):
        self._model = LocalEmbeddingModel()
        
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generates dense vector embeddings for semantic search.
        """
        logger.debug(f"Generating embeddings for {len(texts)} chunks.")
        return self._model.encode(texts)
