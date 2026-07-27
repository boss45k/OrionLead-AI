"""
Feedback Engine
===============
Records lead outcome events so the system can learn which scoring signals
actually predict conversion, reply, or disqualification.

Outcomes are stored as a simple in-memory event log (flushed periodically
to a JSON file so they survive restarts).  No external database needed.

Event schema
------------
{
  "lead_id":      str,
  "email":        str,
  "source":       str,
  "intent":       str,
  "final_score":  float,
  "grade":        str,
  "outcome":      "converted" | "replied" | "rejected" | "unqualified" | "bounced",
  "timestamp":    ISO-8601 str,
  "signals":      dict  # snapshot of hot/cold signals at time of scoring
}
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


_OUTCOMES_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "feedback_outcomes.json"
)
_VALID_OUTCOMES = frozenset({
    "converted", "replied", "rejected", "unqualified", "bounced"
})


class FeedbackEngine:
    """
    Thread-safe in-memory outcome log with optional JSON persistence.
    """

    def __init__(self, outcomes_file: str = _OUTCOMES_FILE) -> None:
        self._file = outcomes_file
        self._lock = threading.Lock()
        self._events: List[Dict[str, Any]] = []
        self._load()

    def record(
        self,
        lead_id: str,
        outcome: str,
        *,
        email: str = "",
        source: str = "unknown",
        intent: str = "other",
        final_score: float = 0.0,
        grade: str = "F",
        signals: Optional[Dict[str, Any]] = None,
    ) -> None:
        if outcome not in _VALID_OUTCOMES:
            raise ValueError(f"Unknown outcome '{outcome}'. Must be one of {_VALID_OUTCOMES}")

        event = {
            "lead_id":    lead_id,
            "email":      email,
            "source":     source,
            "intent":     intent,
            "final_score": final_score,
            "grade":      grade,
            "outcome":    outcome,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "signals":    signals or {},
        }
        with self._lock:
            self._events.append(event)
            self._flush()

    def get_events(self, outcome: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if outcome:
                return [e for e in self._events if e["outcome"] == outcome]
            return list(self._events)

    def conversion_rate(self, source: Optional[str] = None, intent: Optional[str] = None) -> float:
        with self._lock:
            events = self._events
            if source:
                events = [e for e in events if e["source"] == source]
            if intent:
                events = [e for e in events if e["intent"] == intent]
            if not events:
                return 0.0
            converted = sum(1 for e in events if e["outcome"] in ("converted", "replied"))
            return round(converted / len(events), 4)

    def _load(self) -> None:
        try:
            if os.path.exists(self._file):
                with open(self._file, "r", encoding="utf-8") as f:
                    self._events = json.load(f)
        except Exception:
            self._events = []

    def _flush(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._file), exist_ok=True)
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._events, f)
        except Exception:
            pass


_instance: Optional[FeedbackEngine] = None
_ilock = threading.Lock()


def get_feedback_engine() -> FeedbackEngine:
    global _instance
    if _instance is None:
        with _ilock:
            if _instance is None:
                _instance = FeedbackEngine()
    return _instance


def record_outcome(
    lead_id: str,
    outcome: str,
    **kwargs: Any,
) -> None:
    get_feedback_engine().record(lead_id, outcome, **kwargs)
