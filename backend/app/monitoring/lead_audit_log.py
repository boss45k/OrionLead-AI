"""
Lead Audit Log
==============
Immutable per-lead decision record.  Every lead that passes or fails
the enterprise save policy is logged here with:
  - final score and grade
  - which gate passed/failed
  - all scoring component breakdown
  - timestamp and source

Records are stored in-memory (circular buffer, max 10 000 entries) and
can be flushed to the feedback engine for learning purposes.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional


_MAX_RECORDS = 10_000


class LeadAuditRecord:
    __slots__ = (
        "lead_id", "email", "source", "intent",
        "final_score", "grade", "saved", "drop_reason",
        "score_breakdown", "timestamp",
    )

    def __init__(
        self,
        lead_id: str,
        email: str,
        source: str,
        intent: str,
        final_score: float,
        grade: str,
        saved: bool,
        drop_reason: str,
        score_breakdown: Dict[str, Any],
    ) -> None:
        self.lead_id        = lead_id
        self.email          = email
        self.source         = source
        self.intent         = intent
        self.final_score    = final_score
        self.grade          = grade
        self.saved          = saved
        self.drop_reason    = drop_reason
        self.score_breakdown = score_breakdown
        self.timestamp      = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lead_id":       self.lead_id,
            "email":         self.email,
            "source":        self.source,
            "intent":        self.intent,
            "final_score":   self.final_score,
            "grade":         self.grade,
            "saved":         self.saved,
            "drop_reason":   self.drop_reason,
            "breakdown":     self.score_breakdown,
            "timestamp":     self.timestamp,
        }


class LeadAuditLog:
    def __init__(self, max_records: int = _MAX_RECORDS) -> None:
        self._lock = threading.Lock()
        self._records: Deque[LeadAuditRecord] = deque(maxlen=max_records)

    def log(
        self,
        lead: Dict[str, Any],
        *,
        final_score: float = 0.0,
        grade: str = "F",
        saved: bool = False,
        drop_reason: str = "",
        score_breakdown: Optional[Dict[str, Any]] = None,
        source: str = "unknown",
        intent: str = "other",
    ) -> None:
        record = LeadAuditRecord(
            lead_id        = str(lead.get("id") or lead.get("email") or "unknown"),
            email          = (lead.get("email") or "").lower().strip(),
            source         = source,
            intent         = intent,
            final_score    = final_score,
            grade          = grade,
            saved          = saved,
            drop_reason    = drop_reason,
            score_breakdown = score_breakdown or {},
        )
        with self._lock:
            self._records.append(record)

    def recent(self, n: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            records = list(self._records)
        return [r.to_dict() for r in records[-n:]]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            records = list(self._records)
        total  = len(records)
        saved  = sum(1 for r in records if r.saved)
        grades = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        drops: Dict[str, int] = {}
        for r in records:
            grades[r.grade] = grades.get(r.grade, 0) + 1
            if not r.saved and r.drop_reason:
                drops[r.drop_reason] = drops.get(r.drop_reason, 0) + 1
        return {
            "total":       total,
            "saved":       saved,
            "dropped":     total - saved,
            "save_rate":   round(saved / total, 4) if total else 0.0,
            "grade_dist":  grades,
            "drop_reasons": dict(sorted(drops.items(), key=lambda kv: -kv[1])),
        }

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


_instance: Optional[LeadAuditLog] = None
_ilock = threading.Lock()


def get_audit_log() -> LeadAuditLog:
    global _instance
    if _instance is None:
        with _ilock:
            if _instance is None:
                _instance = LeadAuditLog()
    return _instance


def audit_lead(
    lead: Dict[str, Any],
    *,
    final_score: float = 0.0,
    grade: str = "F",
    saved: bool = False,
    drop_reason: str = "",
    score_breakdown: Optional[Dict[str, Any]] = None,
    source: str = "unknown",
    intent: str = "other",
) -> None:
    get_audit_log().log(
        lead,
        final_score=final_score,
        grade=grade,
        saved=saved,
        drop_reason=drop_reason,
        score_breakdown=score_breakdown,
        source=source,
        intent=intent,
    )
