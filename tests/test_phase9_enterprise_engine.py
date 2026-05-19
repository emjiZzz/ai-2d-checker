import pytest
from pathlib import Path
from unittest.mock import MagicMock

# Target Domain Engines
from services.backend.infrastructure.ai.vectorstore.lancedb_manager import LanceDBManager
from services.backend.infrastructure.ai.reasoning.drawing_similarity_engine import DrawingSimilarityEngine
from services.backend.infrastructure.ai.knowledge_graph.graph_builder import GraphBuilder
from services.backend.infrastructure.ai.embeddings.local_embedding_model import LocalEmbeddingModel

@pytest.fixture(autouse=True)
def mock_persistence_paths(monkeypatch):
    """Enforces sandboxed path validation for testing."""
    class MockSettings:
        STORAGE_ROOT = "/mock/storage"
    monkeypatch.setattr("services.backend.config.settings", MockSettings())
    
    # Mock validation function
    monkeypatch.setattr(
        "services.backend.infrastructure.ai.vectorstore.vector_persistence.VectorPersistence.validate_sandbox_path",
        lambda path: True
    )
    monkeypatch.setattr(
        "services.backend.infrastructure.ai.vectorstore.vector_persistence.VectorPersistence.get_secure_db_path",
        lambda: Path("/mock/storage/vector/memory_db")
    )

def test_lancedb_writing():
    """Verify that writing records to local collections passes constraints."""
    manager = LanceDBManager()
    
    # Commit vector list
    records = [{"id": "v1", "vector": [0.1, 0.2]}]
    status = manager.write_embeddings("standards_coll", records)
    
    assert status is True

def test_drawing_similarity():
    """Verify calculations for systemic drafting anomalies and similarity distances."""
    engine = DrawingSimilarityEngine()
    
    dist = engine.calculate_drawing_distance({}, {})
    assert dist == 0.85
    
    anomalies = engine.find_systemic_drafting_errors([{"id": "audit1"}, {"id": "audit2"}])
    assert len(anomalies) == 1
    assert anomalies[0]["category"] == "missing_chamfer_annotations"

def test_graph_relationship_traversal():
    """Verify nodes and directed dependency edges correctly map relationship queries."""
    graph = GraphBuilder()
    
    graph.add_node("n1", "Geometry", {"layer": "0"})
    graph.add_node("n2", "Standard", {"clause": "ISO 286"})
    graph.add_edge("n1", "n2", "CITES")
    
    relations = graph.query_related_context("n1")
    assert len(relations) == 1
    assert relations[0]["relationship"] == "CITES"
    assert relations[0]["target_node"]["properties"]["clause"] == "ISO 286"

def test_onnx_local_embedding():
    """Verify embedding encoding works cleanly under lazy quantized/ONNX mode."""
    model = LocalEmbeddingModel()
    vectors = model.encode(["test query"])
    
    assert len(vectors) == 1
    assert model.onnx_available is True
