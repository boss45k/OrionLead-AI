"""
Metrics Collector
=================
In-memory counters and histograms for pipeline observability.
Exposed via /api/monitoring/metrics endpoint (wired separately).

No external dependencies — all state is thread-safe in-process.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional


class MetricsCollector:
    """
    Tracks counters, gauges, and timing histograms for the pipeline.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters:   Dict[str, int]           = defaultdict(int)
        self._gauges:     Dict[str, float]          = {}
        self._histograms: Dict[str, List[float]]   = defaultdict(list)
        self._start_time = time.time()

    # ── Counters ──────────────────────────────────────────────────────────
    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def counter(self, name: str) -> int:
        with self._lock:
            return self._counters[name]

    # ── Gauges ────────────────────────────────────────────────────────────
    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def gauge(self, name: str) -> float:
        with self._lock:
            return self._gauges.get(name, 0.0)

    # ── Histograms ────────────────────────────────────────────────────────
    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._histograms[name].append(value)

    def histogram_stats(self, name: str) -> Dict[str, float]:
        with self._lock:
            values = self._histograms.get(name, [])
        if not values:
            return {"count": 0, "min": 0.0, "max": 0.0, "avg": 0.0, "p95": 0.0}
        sorted_v = sorted(values)
        n = len(sorted_v)
        p95_idx = int(n * 0.95)
        return {
            "count": n,
            "min":   round(sorted_v[0], 3),
            "max":   round(sorted_v[-1], 3),
            "avg":   round(sum(sorted_v) / n, 3),
            "p95":   round(sorted_v[min(p95_idx, n - 1)], 3),
        }

    # ── Snapshot ──────────────────────────────────────────────────────────
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            counters  = dict(self._counters)
            gauges    = dict(self._gauges)
            hist_keys = list(self._histograms.keys())

        histograms = {k: self.histogram_stats(k) for k in hist_keys}
        return {
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "counters":       counters,
            "gauges":         gauges,
            "histograms":     histograms,
        }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


_instance: Optional[MetricsCollector] = None
_ilock = threading.Lock()


def get_metrics() -> MetricsCollector:
    global _instance
    if _instance is None:
        with _ilock:
            if _instance is None:
                _instance = MetricsCollector()
    return _instance
