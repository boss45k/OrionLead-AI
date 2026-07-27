"""
Request Tracer
==============
Lightweight span-based tracing for pipeline stage timing.
No external agent (Jaeger/Zipkin) required — spans are stored in-memory
and can be flushed to the audit log or returned in API responses.

Usage
-----
    tracer = get_tracer()
    with tracer.span("enrichment") as span:
        result = enrich(lead)
        span.tag("provider", "hunter")
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional


class Span:
    def __init__(self, name: str, parent_id: Optional[str] = None) -> None:
        self.name      = name
        self.parent_id = parent_id
        self.span_id   = f"{name}-{id(self)}"
        self.start     = time.perf_counter()
        self.end: Optional[float] = None
        self.tags: Dict[str, Any] = {}
        self.error: Optional[str] = None

    def tag(self, key: str, value: Any) -> None:
        self.tags[key] = value

    def finish(self) -> None:
        if self.end is None:
            self.end = time.perf_counter()

    @property
    def duration_ms(self) -> float:
        end = self.end or time.perf_counter()
        return round((end - self.start) * 1000, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":        self.name,
            "span_id":     self.span_id,
            "parent_id":   self.parent_id,
            "duration_ms": self.duration_ms,
            "tags":        self.tags,
            "error":       self.error,
        }


class Tracer:
    """
    Creates and manages spans for a single request or pipeline run.
    """

    def __init__(self, max_spans: int = 500) -> None:
        self._lock = threading.Lock()
        self._spans: List[Span] = []
        self._max_spans = max_spans

    @contextmanager
    def span(self, name: str, parent: Optional[Span] = None) -> Generator[Span, None, None]:
        s = Span(name, parent_id=parent.span_id if parent else None)
        try:
            yield s
        except Exception as exc:
            s.error = str(exc)
            raise
        finally:
            s.finish()
            with self._lock:
                if len(self._spans) < self._max_spans:
                    self._spans.append(s)

    def spans(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self._spans]

    def reset(self) -> None:
        with self._lock:
            self._spans.clear()

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            spans = list(self._spans)
        total_ms = sum(s.duration_ms for s in spans)
        errors   = [s.name for s in spans if s.error]
        return {
            "total_spans":  len(spans),
            "total_ms":     round(total_ms, 2),
            "errors":       errors,
        }


_instance: Optional[Tracer] = None
_ilock = threading.Lock()


def get_tracer() -> Tracer:
    global _instance
    if _instance is None:
        with _ilock:
            if _instance is None:
                _instance = Tracer()
    return _instance
