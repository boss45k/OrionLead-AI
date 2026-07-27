"""
Observability Package
=====================
Lightweight, zero-dependency monitoring for the lead intelligence platform.

Components
----------
metrics       : counters and histograms for pipeline throughput
tracing       : per-request span timing (no external agent needed)
lead_audit_log: immutable per-lead decision record
"""

from app.monitoring.metrics       import MetricsCollector, get_metrics
from app.monitoring.tracing       import Tracer, get_tracer, Span
from app.monitoring.lead_audit_log import LeadAuditLog, get_audit_log, audit_lead

__all__ = [
    "MetricsCollector", "get_metrics",
    "Tracer", "get_tracer", "Span",
    "LeadAuditLog", "get_audit_log", "audit_lead",
]
