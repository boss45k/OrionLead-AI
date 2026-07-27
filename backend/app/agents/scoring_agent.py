"""
Scoring Agent
=============
Specialized agent that runs the full adaptive scoring pipeline for a lead:
  1. Context-aware rule scoring (ContextScorer)
  2. Fetches or accepts ML score
  3. Accepts intelligence score from IntelligenceAgent
  4. Accepts graph confidence from GraphAgent
  5. Fuses all into a final score via ScoreOptimizer
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from app.scoring import AdaptiveContext, ScoreOptimizer
    from app.scoring.adaptive_weights import AdaptiveWeightEngine
    _scoring_available = True
except ImportError:
    _scoring_available = False


_engine: Optional[Any] = None


def _get_engine() -> Any:
    global _engine
    if _engine is None and _scoring_available:
        _engine = ScoreOptimizer()
    return _engine


def score_lead(
    lead: Dict[str, Any],
    *,
    ml_score: float = 0.0,
    intelligence_score: float = 0.0,
    graph_confidence: float = 0.0,
    intent: str = "other",
    industry: str = "unknown",
    company_type: str = "unknown",
    source: str = "unknown",
    region: str = "unknown",
) -> Dict[str, Any]:
    """
    Full scoring pipeline for a single lead.

    Returns the optimize() result dict including final_score and grade,
    or a fallback dict if the scoring package is unavailable.
    """
    if not _scoring_available:
        return {
            "final_score": 0.0,
            "rule_score": 0.0,
            "ml_score": ml_score,
            "intelligence_score": intelligence_score,
            "graph_score": graph_confidence * 100.0,
            "component_weights": {"rule": 0.30, "ml": 0.30, "intelligence": 0.25, "graph": 0.15},
            "context_breakdown": {},
            "adjustments": [],
            "grade": "F",
            "error": "scoring_package_unavailable",
        }

    ctx = AdaptiveContext(
        intent=intent,
        industry=industry,
        company_type=company_type,
        source=source,
        region=region,
    )
    try:
        return _get_engine().optimize(
            lead,
            ctx,
            ml_score=ml_score,
            intelligence_score=intelligence_score,
            graph_confidence=graph_confidence,
        )
    except Exception as exc:
        return {
            "final_score": 0.0,
            "rule_score": 0.0,
            "ml_score": ml_score,
            "intelligence_score": intelligence_score,
            "graph_score": graph_confidence * 100.0,
            "component_weights": {},
            "context_breakdown": {},
            "adjustments": [],
            "grade": "F",
            "error": str(exc),
        }
