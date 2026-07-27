"""
Score Learner
=============
Inspects outcome statistics and suggests weight profile adjustments for
AdaptiveWeightEngine.  Does NOT retrain the ML model — it shifts the
context-level field weights based on which signals actually converted.

Strategy
--------
  For each (intent, source) pair with ≥10 outcomes:
    - If conversion_rate > 0.30 → boost email_weight, linkedin_weight
    - If avg_score of converted leads >> avg_score of rejected → weights are
      calibrated; no action needed
    - If high-score leads have low conversion → penalise over-weighted signals

Currently returns recommendations as a dict — a future version could write
them directly into adaptive_weights._INTENT_PROFILES.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from app.learning.outcome_tracker import get_outcome_tracker


_MIN_SAMPLE = 10   # minimum events before recommendations are generated


class ScoreLearner:
    """
    Generates weight-adjustment recommendations from observed outcomes.
    """

    def recommendations(self) -> List[Dict[str, Any]]:
        tracker = get_outcome_tracker()
        recs: List[Dict[str, Any]] = []

        # ── By intent ────────────────────────────────────────────────────
        for entry in tracker.top_converting_intents(n=20):
            intent = entry["intent"]
            if entry["total"] < _MIN_SAMPLE:
                continue
            cr = entry["conversion_rate"]
            if cr > 0.35:
                recs.append({
                    "type":    "boost",
                    "scope":   "intent",
                    "key":     intent,
                    "signals": ["linkedin_weight", "email_weight"],
                    "reason":  f"High conversion rate {cr:.0%} for intent={intent}",
                })
            elif cr < 0.05:
                recs.append({
                    "type":    "penalise",
                    "scope":   "intent",
                    "key":     intent,
                    "signals": ["tech_stack_weight", "hiring_weight"],
                    "reason":  f"Low conversion rate {cr:.0%} for intent={intent}",
                })

        # ── By source ─────────────────────────────────────────────────────
        for entry in tracker.top_converting_sources(n=20):
            source = entry["source"]
            if entry["total"] < _MIN_SAMPLE:
                continue
            cr = entry["conversion_rate"]
            if cr > 0.40:
                recs.append({
                    "type":    "boost",
                    "scope":   "source",
                    "key":     source,
                    "signals": ["ml_weight", "graph_weight"],
                    "reason":  f"High conversion rate {cr:.0%} for source={source}",
                })

        return recs

    def apply_recommendations(self) -> int:
        """
        Apply recommendations to in-memory INTENT/SOURCE profiles.
        Returns count of applied changes.
        """
        try:
            from app.scoring.adaptive_weights import _INTENT_PROFILES, _SOURCE_PROFILES
        except ImportError:
            return 0

        recs = self.recommendations()
        applied = 0
        _BOOST = 1.15
        _PENALTY = 0.90

        for rec in recs:
            target = _INTENT_PROFILES if rec["scope"] == "intent" else _SOURCE_PROFILES
            key = rec["key"]
            if key not in target:
                target[key] = {}
            for signal in rec["signals"]:
                current = target[key].get(signal, 1.0)
                if rec["type"] == "boost":
                    target[key][signal] = round(min(2.0, current * _BOOST), 3)
                else:
                    target[key][signal] = round(max(0.3, current * _PENALTY), 3)
                applied += 1

        return applied


_instance: Optional[ScoreLearner] = None
_ilock = threading.Lock()


def get_score_learner() -> ScoreLearner:
    global _instance
    if _instance is None:
        with _ilock:
            if _instance is None:
                _instance = ScoreLearner()
    return _instance
