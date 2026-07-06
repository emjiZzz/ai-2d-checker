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
    assert len(vectors[0]) == 384 # Using standard MiniLM normalized 384 dims
    # Check that it is normalized (norm of vector should be close to 1.0)
    import numpy as np
    assert np.allclose(np.linalg.norm(vectors[0]), 1.0)

def test_retrieval_engine_query(tmp_path, monkeypatch):
    """Verify similarity search returns grounded context semantically."""
    # Temporarily redirect STORAGE_ROOT to tmp_path sandbox so we write cleanly
    class MockSettings:
        STORAGE_ROOT = str(tmp_path)
    monkeypatch.setattr("services.backend.infrastructure.ai.vectorstore.vector_persistence.settings", MockSettings())
    
    from services.backend.infrastructure.ai.vectorstore.lancedb_manager import LanceDBManager
    db_manager = LanceDBManager()
    provider = EmbeddingProvider()
    
    # 1. Seed vector database with some actual standard grounding clauses
    clauses = [
        "All holes must have a specified tolerance.",
        "Electrical cables must have a continuous protective sheath of rubber.",
        "Structural columns must withstand structural wind loads of 50kN/m2."
    ]
    vectors = provider.embed_texts(clauses)
    records = []
    for text, vec in zip(clauses, vectors):
        records.append({
            "vector": vec,
            "text": text,
            "metadata": {"source": "ISO 286", "standard_id": "iso-286"}
        })
        
    db_manager.write_embeddings("standards_reference", records)
    
    # 2. Query retrieval engine semantically
    engine = RetrievalEngine()
    
    # Query: "Tolerance limits on circular holes"
    results = engine.query("Tolerance limits on circular holes", top_k=1)
    
    assert len(results) == 1
    assert "tolerance" in results[0]["text"]
    assert results[0]["metadata"]["source"] == "ISO 286"
    assert results[0]["distance"] < 0.6  # Cosine distance should be highly aligned
