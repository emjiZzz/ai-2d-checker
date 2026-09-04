from typing import Any

from ....logger import logger


class GraphBuilder:
    """
    Builds the localized Engineering Knowledge Graph relationships.
    Connects CAD geometries, historical annotations, standards, and revision nodes.
    """
    
    def __init__(self):
        self.nodes = {}
        self.edges = []
        
    def add_node(self, node_id: str, label: str, properties: dict[str, Any]):
        """Registers a node representing a standard clause, geometry pattern, or violation."""
        logger.debug(f"Adding knowledge graph node: {node_id} ({label})")
        self.nodes[node_id] = {
            "id": node_id,
            "label": label,
            "properties": properties
        }
        
    def add_edge(self, source_id: str, target_id: str, relationship_type: str):
        """Creates a directional edge linking nodes (e.g. [ShaftGeometry] -- Cites --> [ISO 286])."""
        logger.debug(f"Adding knowledge edge: {source_id} --({relationship_type})--> {target_id}")
        self.edges.append({
            "source": source_id,
            "target": target_id,
            "relationship": relationship_type
        })
        
    def query_related_context(self, source_node_id: str) -> list[dict[str, Any]]:
        """Returns adjacent nodes, allowing quick navigation between standard clauses and similar historic violations."""
        results = []
        for edge in self.edges:
            if edge["source"] == source_node_id:
                results.append({
                    "target_node": self.nodes.get(edge["target"]),
                    "relationship": edge["relationship"]
                })
        return results
