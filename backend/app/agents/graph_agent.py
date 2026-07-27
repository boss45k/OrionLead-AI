"""
Graph Agent
===========
Specialized agent that:
  1. Runs RelationshipMapper to infer identity relationships
  2. Registers the lead in the EntityGraph
  3. Computes graph_confidence via ConfidenceEngine

Returns graph_confidence (0.0-1.0) for use in the final scoring pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from app.graph import get_entity_graph, RelationshipMapper, ConfidenceEngine
    _graph_available = True
except ImportError:
    _graph_available = False

_mapper: Optional[Any] = None
_confidence: Optional[Any] = None


def _get_mapper():
    global _mapper
    if _mapper is None and _graph_available:
        _mapper = RelationshipMapper()
    return _mapper


def _get_confidence():
    global _confidence
    if _confidence is None and _graph_available:
        _confidence = ConfidenceEngine()
    return _confidence


def process(lead: Dict[str, Any], source: str = "unknown") -> Dict[str, Any]:
    """
    Map relationships, register in graph, and compute confidence.

    Returns
    -------
    {
      "graph_confidence": 0.0-1.0,
      "graph_score":      0.0-1.0,   # raw connectivity
      "augmented_lead":   dict,       # lead with enriched data_points
      "error":            str | None,
    }
    """
    if not _graph_available:
        return {
            "graph_confidence": 0.0,
            "graph_score": 0.0,
            "augmented_lead": lead,
            "error": "graph_package_unavailable",
        }

    try:
        mapper = _get_mapper()
        confidence_engine = _get_confidence()
        graph = get_entity_graph()

        # 1. Infer implicit relationships and augment data_points
        augmented = mapper.map(lead)

        # 2. Register in entity graph
        graph.add_lead(augmented, source=source)

        # 3. Raw graph connectivity score
        graph_score = graph.score_lead(augmented)

        # 4. Final confidence blending source trust + graph + field signals
        conf = confidence_engine.compute(augmented, graph_score=graph_score)

        return {
            "graph_confidence": conf,
            "graph_score":      graph_score,
            "augmented_lead":   augmented,
            "error":            None,
        }
    except Exception as exc:
        return {
            "graph_confidence": 0.0,
            "graph_score": 0.0,
            "augmented_lead": lead,
            "error": str(exc),
        }


def reset_graph() -> None:
    """Clear the entity graph between collection runs."""
    if _graph_available:
        try:
            get_entity_graph().reset()
        except Exception:
            pass
