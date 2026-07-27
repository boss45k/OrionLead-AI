"""
Intelligence Models
===================
Shared dataclasses used across the entire intelligence pipeline.

EvidenceItem — a single traceable data point used in a decision.
IntelligenceDecision — the unified result object produced by AccountScorer
  and consumed by IntelligenceOrchestrator, EnterpriseSavePolicy, and audit logs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Evidence ──────────────────────────────────────────────────────────────────

@dataclass
class EvidenceItem:
    """
    One atomic piece of evidence that influenced an intelligence decision.

    Attributes:
        source:     Where the data came from — 'website' | 'apollo' | 'hunter' |
                    'lead_data' | 'anti_junk' | 'classifier' | 'domain_tld' | etc.
        field:      Which property was checked — 'country' | 'business_type' |
                    'domain' | 'company_name' | 'email' | etc.
        value:      The actual value found (may be empty if not found).
        confidence: 0.0 – 1.0 confidence in this data point.
        reason:     Human-readable explanation of what was found and why it
                    supports or contradicts the decision.
    """
    source: str
    field: str
    value: str
    confidence: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source":     self.source,
            "field":      self.field,
            "value":      self.value,
            "confidence": round(self.confidence, 2),
            "reason":     self.reason,
        }


# ── Decision ──────────────────────────────────────────────────────────────────

@dataclass
class IntelligenceDecision:
    """
    Unified result produced by AccountScorer (and enriched by the Orchestrator).

    All gates must pass for `passed` to be True.
    Evidence carries the full reasoning chain so every decision is auditable.

    Backward-compat aliases are included in to_dict():
        final_company_score == final_score
        data_confidence     == confidence_score
    """

    # ── Core scores ──────────────────────────────────────────────────────────
    passed:           bool  = False
    final_score:      float = 0.0
    confidence_score: float = 0.0
    risk_score:       float = 0.0
    fit_score:        float = 0.0
    intent_score:     float = 0.0
    growth_score:     float = 0.0

    # ── Gate flags (ALL must be True for passed=True) ─────────────────────────
    company_identity_passed: bool = False
    user_intent_passed:      bool = False
    anti_junk_passed:        bool = False
    business_type_allowed:   bool = False
    location_match:          bool = True   # True when no location constraint

    # ── Rejection detail ──────────────────────────────────────────────────────
    rejection_reason: str = ""
    failed_stage:     str = ""
    decision_log:     List[str] = field(default_factory=list)

    # ── Evidence chain ────────────────────────────────────────────────────────
    evidence: List[EvidenceItem] = field(default_factory=list)

    # ── Explainability ────────────────────────────────────────────────────────
    why_saved:                  str       = ""
    recommended_outreach_angle: str       = ""
    top_positive_signals:       List[str] = field(default_factory=list)
    top_risk_signals:           List[str] = field(default_factory=list)

    # ── Confidence sub-scores (for UI breakdown display) ──────────────────────
    # identity: company name / entity quality
    # company:  website / domain / industry signals (fit_score proxy)
    # email:    email quality and verification
    # source:   reliability of the data source
    # intent:   buying intent signals (intent_score proxy)
    confidence_breakdown: Dict[str, float] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def add_evidence(
        self,
        source: str,
        field: str,
        value: str,
        confidence: float,
        reason: str,
    ) -> None:
        self.evidence.append(EvidenceItem(source, field, value, confidence, reason))

    def reject(self, reason: str, stage: str, log_msg: str = "") -> "IntelligenceDecision":
        """Mark this decision as rejected. Returns self for chaining."""
        self.passed           = False
        self.rejection_reason = reason
        self.failed_stage     = stage
        if log_msg:
            self.decision_log.append(f"REJECTED [{stage}]: {log_msg or reason}")
        return self

    # ── Backward-compat properties ────────────────────────────────────────────

    @property
    def final_company_score(self) -> float:
        return self.final_score

    @property
    def data_confidence(self) -> float:
        return self.confidence_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            # Current names
            "passed":                     self.passed,
            "final_score":                round(self.final_score, 1),
            "confidence_score":           round(self.confidence_score, 1),
            "risk_score":                 round(self.risk_score, 1),
            "fit_score":                  round(self.fit_score, 1),
            "intent_score":               round(self.intent_score, 1),
            "growth_score":               round(self.growth_score, 1),
            # Backward-compat aliases
            "final_company_score":        round(self.final_score, 1),
            "data_confidence":            round(self.confidence_score, 1),
            # Gate flags
            "company_identity_passed":    self.company_identity_passed,
            "user_intent_passed":         self.user_intent_passed,
            "anti_junk_passed":           self.anti_junk_passed,
            "business_type_allowed":      self.business_type_allowed,
            "location_match":             self.location_match,
            # Rejection
            "rejection_reason":           self.rejection_reason,
            "failed_stage":               self.failed_stage,
            "decision_log":               self.decision_log,
            # Evidence & explainability
            "evidence":                   [e.to_dict() for e in self.evidence],
            "why_saved":                  self.why_saved,
            "recommended_outreach_angle": self.recommended_outreach_angle,
            "top_positive_signals":       self.top_positive_signals,
            "top_risk_signals":           self.top_risk_signals,
            "confidence_breakdown":       self.confidence_breakdown,
        }
