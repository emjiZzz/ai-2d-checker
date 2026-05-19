import pytest
from unittest.mock import MagicMock

# Target Domain Services
from services.backend.infrastructure.ai.explainability.violation_reasoner import ViolationReasoner
from services.backend.infrastructure.ai.explainability.remediation_engine import RemediationEngine
from services.backend.infrastructure.ai.explainability.confidence_interpreter import ConfidenceInterpreter
from services.backend.infrastructure.ai.explainability.standards_reference_mapper import StandardsReferenceMapper
from services.backend.infrastructure.ai.geometry.geometry_search_engine import GeometrySearchEngine
from services.backend.infrastructure.ai.geometry.vector_geometry_index import VectorGeometryIndex

class MockViolation:
    def __init__(self, _id, category, description):
        self.id = _id
        self.category = category
        self.description = description

class MockEntity:
    def __init__(self, _id):
        self.id = _id

def test_violation_reasoner():
    """Verify reasoning generation provides context based on category."""
    viol = MockViolation("v1", "missing_dimensions", "Line missing dim")
    explanation = ViolationReasoner.generate_explanation(viol)
    
    assert "Machining constraints" in explanation["detailed_reasoning"]
    assert explanation["summary"] == "Line missing dim"

def test_remediation_engine():
    """Verify step-by-step suggestions are ordered and actionable."""
    viol = MockViolation("v2", "unauthorized_layer", "Line on TEMP layer")
    steps = RemediationEngine.suggest_fixes(viol)
    
    assert len(steps) == 2
    assert steps[0]["step"] == 1
    assert "approved production layer" in steps[1]["action"]

def test_confidence_interpreter():
    """Verify float scores map correctly to visual labels."""
    high = ConfidenceInterpreter.interpret(0.98)
    medium = ConfidenceInterpreter.interpret(0.75)
    low = ConfidenceInterpreter.interpret(0.4)
    
    assert high["level"] == "High"
    assert medium["level"] == "Medium"
    assert low["level"] == "Low"

def test_standards_reference_mapper():
    """Verify semantic mapping to ISO standards."""
    viol = MockViolation("v3", "scale_ratio", "Invalid scale 1:11")
    reference = StandardsReferenceMapper.map_to_standard(viol)
    
    assert reference["standard_name"] == "ISO 5455"
    assert "Scales for engineering drawings" in reference["clause"]

def test_geometry_vector_index():
    """Verify index creation and spatial querying mock logic."""
    engine = GeometrySearchEngine()
    ent1 = MockEntity("e1")
    ent2 = MockEntity("e2")
    
    # Should build index cleanly
    engine.index.build_index([ent1, ent2])
    
    # Check underlying dict populates
    assert "e1" in engine.index._index
    
    # Clustering mock check
    clusters = engine.detect_repeated_symbols([ent1, ent2])
    assert "pattern_1" in clusters
