from services.backend.infrastructure.ai.knowledge_graph.graph_builder import GraphBuilder


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
