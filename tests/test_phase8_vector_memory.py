import pytest
from pathlib import Path
from unittest.mock import MagicMock

from services.backend.infrastructure.ai.vectorstore.vector_persistence import VectorPersistence
from services.backend.infrastructure.ai.vectorstore.embedding_provider import EmbeddingProvider
from services.backend.infrastructure.ai.vectorstore.retrieval_engine import RetrievalEngine

def test_vector_persistence_sandbox(monkeypatch):
    """Verify that vector DB shards cannot be read or written outside the storage sandbox."""
    
    mock_base = str(Path("/mock/storage").resolve())
    
    class MockSettings:
        STORAGE_ROOT = mock_base
    monkeypatch.setattr("services.backend.infrastructure.ai.vectorstore.vector_persistence.settings", MockSettings())
    
    valid_path = str(Path("/mock/storage/vector/memory_db/shard1").resolve())
    assert VectorPersistence.validate_sandbox_path(valid_path) is True
    
    # Path traversal attack
    invalid_path = str(Path("/mock/storage/../../etc/passwd").resolve())
    assert VectorPersistence.validate_sandbox_path(invalid_path) is False

def test_embedding_generation():
    """Verify the embedding provider wraps the local model and returns vectors."""
    provider = EmbeddingProvider()
    vectors = provider.embed_texts(["Engineering Standard 101"])
    
    assert len(vectors) == 1
    assert len(vectors[0]) == 3 # Using mock length 3
    assert vectors[0] == [0.1, 0.2, 0.3]

def test_retrieval_engine_query():
    """Verify similarity search returns grounded context."""
    engine = RetrievalEngine()
    results = engine.query("Tolerance limits")
    
    assert len(results) == 1
    assert "tolerance" in results[0]["text"]
    assert results[0]["metadata"]["source"] == "ISO 286"
