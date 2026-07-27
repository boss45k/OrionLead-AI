"""
Score Optimizer
===============
Fuses rule, ML, intelligence, and graph scores into a single final score
using context-adaptive component weights from AdaptiveWeightEngine.

Final score formula (default weights):
  final = (rule_score × 0.30) + (ml_score × 0.30) +
          (intelligence_score × 0.25) + (graph_confidence × 0.15) × 100
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.scoring.adaptive_weights import AdaptiveContext, AdaptiveWeightEngine, WeightSet
from app.scoring.context_scoring import ContextScorer


class ScoreOptimizer:
    """
    Fuses all scoring components into a final 0-100 score.

    Parameters
    ----------
    weight_engine : AdaptiveWeightEngine — shared singleton recommended
    """

    def __init__(self, weight_engine: Optional[AdaptiveWeightEngine] = None) -> None:
        self._weights = weight_engine or AdaptiveWeightEngine()
        self._context_scorer = ContextScorer(self._weights)

    def optimize(
        self,
        lead: Dict[str, Any],
        ctx: AdaptiveContext,
        *,
        ml_score: float = 0.0,
        intelligence_score: float = 0.0,
        graph_confidence: float = 0.0,
        rule_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Compute the final adaptive score for a lead.

        Parameters
        ----------
        lead              : raw or enriched lead dict
        ctx               : AdaptiveContext describing query/source/region
        ml_score          : ML model output 0-100
        intelligence_score: company intelligence score 0-100
        graph_confidence  : graph confidence 0.0-1.0 (converted to 0-100 internally)
        rule_score        : override rule score; if None, computed via ContextScorer

        Returns
        -------
        {
          "final_score":         0-100,
          "rule_score":          0-100,
          "ml_score":            0-100,
          "intelligence_score":  0-100,
          "graph_score":         0-100,
          "component_weights":   {rule, ml, intelligence, graph},
          "context_breakdown":   {field: pts, …},
          "adjustments":         [reason, …],
          "grade":               "A"/"B"/"C"/"D"/"F",
        }
        """
        ws = self._weights.get_weights(ctx)

        # ── Rule score ────────────────────────────────────────────────────
        if rule_score is None:
            ctx_result = self._context_scorer.score(lead, ctx)
            rule_score = ctx_result["context_score"]
            context_breakdown = ctx_result["breakdown"]
            adjustments = ctx_result["adjustments"]
        else:
            context_breakdown = {}
            adjustments = []

        # ── Normalise inputs ──────────────────────────────────────────────
        rule_score         = float(min(100.0, max(0.0, rule_score)))
        ml_score           = float(min(100.0, max(0.0, ml_score)))
        intelligence_score = float(min(100.0, max(0.0, intelligence_score)))
        graph_score        = float(min(100.0, max(0.0, graph_confidence * 100.0)))

        # ── Weighted fusion ───────────────────────────────────────────────
        final = (
            rule_score         * ws.rule_weight +
            ml_score           * ws.ml_weight +
            intelligence_score * ws.intelligence_weight +
            graph_score        * ws.graph_weight
        )
        final = round(min(100.0, max(0.0, final)), 1)

        return {
            "final_score":        final,
            "rule_score":         round(rule_score, 1),
            "ml_score":           round(ml_score, 1),
            "intelligence_score": round(intelligence_score, 1),
            "graph_score":        round(graph_score, 1),
            "component_weights": {
                "rule":          round(ws.rule_weight, 3),
                "ml":            round(ws.ml_weight, 3),
                "intelligence":  round(ws.intelligence_weight, 3),
                "graph":         round(ws.graph_weight, 3),
            },
            "context_breakdown": context_breakdown,
            "adjustments":       adjustments,
            "grade":             _grade(final),
        }


def _grade(score: float) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


# ── Module-level convenience ──────────────────────────────────────────────────

_optimizer: Optional[ScoreOptimizer] = None


def _get_optimizer() -> ScoreOptimizer:
    global _optimizer
    if _optimizer is None:
        _optimizer = ScoreOptimizer()
    return _optimizer


def compute_final_score(
    rule_score: float,
    ml_score: float,
    intelligence_score: float,
    graph_confidence: float,
    context: Optional[AdaptiveContext] = None,
    lead: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Convenience function returning just the final_score float.

    Compatible with the signature shown in scoring/__init__.py docstring.
    """
    ctx = context or AdaptiveContext()
    result = _get_optimizer().optimize(
        lead or {},
        ctx,
        ml_score=ml_score,
        intelligence_score=intelligence_score,
        graph_confidence=graph_confidence,
        rule_score=rule_score,
    )
    return result["final_score"]
