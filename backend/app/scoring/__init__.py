"""
Adaptive Scoring Engine
=======================
Replaces static ML weights with context-aware, dynamically adjusted
scoring that adapts to query intent, industry, company type, and region.

Final score formula:
  final = (rule_score × 0.30) + (ml_score × 0.30) +
          (intelligence_score × 0.25) + (graph_confidence × 0.15) × 100

Usage
-----
    from app.scoring import compute_final_score, AdaptiveContext

    ctx = AdaptiveContext(
        intent="saas",
        industry="software",
        company_type="saas",
        region="US",
    )
    final = compute_final_score(
        rule_score=65,
        ml_score=72,
        intelligence_score=58,
        graph_confidence=0.7,
        context=ctx,
    )
"""

from app.scoring.adaptive_weights import AdaptiveWeightEngine, AdaptiveContext
from app.scoring.context_scoring   import ContextScorer
from app.scoring.score_optimizer   import ScoreOptimizer, compute_final_score

__all__ = [
    "AdaptiveWeightEngine",
    "AdaptiveContext",
    "ContextScorer",
    "ScoreOptimizer",
    "compute_final_score",
]
