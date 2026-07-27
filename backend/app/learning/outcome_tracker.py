"""
Outcome Tracker
===============
Aggregates feedback events into per-source, per-intent, and per-grade
statistics so the score learner can detect which combinations perform best.

All computations are derived live from FeedbackEngine events — no extra storage.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.learning.feedback_engine import get_feedback_engine


class OutcomeTracker:
    """
    Derives outcome statistics from the live feedback event log.
    """

    def stats_by_source(self) -> Dict[str, Dict[str, Any]]:
        events = get_feedback_engine().get_events()
        return self._aggregate(events, key="source")

    def stats_by_intent(self) -> Dict[str, Dict[str, Any]]:
        events = get_feedback_engine().get_events()
        return self._aggregate(events, key="intent")

    def stats_by_grade(self) -> Dict[str, Dict[str, Any]]:
        events = get_feedback_engine().get_events()
        return self._aggregate(events, key="grade")

    def top_converting_sources(self, n: int = 5) -> List[Dict[str, Any]]:
        stats = self.stats_by_source()
        ranked = sorted(stats.items(), key=lambda kv: kv[1]["conversion_rate"], reverse=True)
        return [{"source": k, **v} for k, v in ranked[:n]]

    def top_converting_intents(self, n: int = 5) -> List[Dict[str, Any]]:
        stats = self.stats_by_intent()
        ranked = sorted(stats.items(), key=lambda kv: kv[1]["conversion_rate"], reverse=True)
        return [{"intent": k, **v} for k, v in ranked[:n]]

    def summary(self) -> Dict[str, Any]:
        events = get_feedback_engine().get_events()
        total = len(events)
        if total == 0:
            return {"total_events": 0, "conversion_rate": 0.0, "by_outcome": {}}

        by_outcome: Dict[str, int] = defaultdict(int)
        for e in events:
            by_outcome[e["outcome"]] += 1

        converted = by_outcome.get("converted", 0) + by_outcome.get("replied", 0)
        return {
            "total_events":    total,
            "conversion_rate": round(converted / total, 4),
            "by_outcome":      dict(by_outcome),
        }

    @staticmethod
    def _aggregate(events: List[Dict], key: str) -> Dict[str, Dict[str, Any]]:
        groups: Dict[str, List[Dict]] = defaultdict(list)
        for e in events:
            groups[e.get(key, "unknown")].append(e)

        result = {}
        for group_val, group_events in groups.items():
            total = len(group_events)
            converted = sum(
                1 for e in group_events if e["outcome"] in ("converted", "replied")
            )
            avg_score = sum(e.get("final_score", 0) for e in group_events) / total
            result[group_val] = {
                "total":           total,
                "converted":       converted,
                "conversion_rate": round(converted / total, 4),
                "avg_score":       round(avg_score, 1),
            }
        return result


_instance: Optional[OutcomeTracker] = None
_ilock = threading.Lock()


def get_outcome_tracker() -> OutcomeTracker:
    global _instance
    if _instance is None:
        with _ilock:
            if _instance is None:
                _instance = OutcomeTracker()
    return _instance
