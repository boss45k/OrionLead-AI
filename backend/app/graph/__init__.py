"""
Relationship Graph Engine
=========================
Builds an in-memory entity graph that links Companies, People, Emails,
Domains, LinkedIn profiles, and Technologies.

Strong connections between entities boost confidence scores and help
resolve duplicates intelligently.

Usage
-----
    from app.graph import get_entity_graph

    graph = get_entity_graph()
    graph.add_lead(lead_dict)
    confidence = graph.score_lead(lead_dict)
"""

from app.graph.entity_graph       import EntityGraph, get_entity_graph
from app.graph.relationship_mapper import RelationshipMapper
from app.graph.confidence_engine   import ConfidenceEngine

__all__ = [
    "EntityGraph",
    "get_entity_graph",
    "RelationshipMapper",
    "ConfidenceEngine",
]
