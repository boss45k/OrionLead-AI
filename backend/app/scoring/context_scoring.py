"""
Context Scorer
==============
Computes a context-aware rule score (0-100) for a lead using the
adaptive WeightSet produced by AdaptiveWeightEngine.

This replaces the static field weights in lead_validator.py with
context-sensitive multipliers while remaining backward-compatible.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.scoring.adaptive_weights import AdaptiveContext, AdaptiveWeightEngine, WeightSet


_FREE_EMAIL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "protonmail.com", "mail.com", "yandex.com",
    "live.com", "msn.com", "me.com",
})

_GENERIC_LOCALS = frozenset({
    "info", "contact", "hello", "support", "sales", "admin",
    "team", "marketing", "office", "hr", "press", "media",
    "noreply", "no-reply", "enquiries",
})


class ContextScorer:
    """
    Produces a context-aware rule score for a lead.

    Parameters
    ----------
    weight_engine : AdaptiveWeightEngine (singleton recommended)
    """

    def __init__(
        self,
        weight_engine: Optional[AdaptiveWeightEngine] = None,
    ) -> None:
        self._weights = weight_engine or AdaptiveWeightEngine()

    def score(self, lead: Dict[str, Any], ctx: AdaptiveContext) -> Dict[str, Any]:
        """
        Returns:
            {
                "context_score": 0-100,
                "breakdown": {field: points, …},
                "weights_used": {component: weight, …},
                "adjustments": [reason, …],
            }
        """
        ws = self._weights.get_weights(ctx)
        breakdown: Dict[str, float] = {}
        adjustments = []

        email    = (lead.get("email") or "").strip().lower()
        name     = (lead.get("name") or "").strip()
        company  = (lead.get("company") or "").strip()
        phone    = (lead.get("phone") or "").strip()
        position = (lead.get("position") or "").strip()
        industry = (lead.get("industry") or "").strip()
        website  = (lead.get("website") or "").strip()
        linkedin = (lead.get("linkedin_url") or "").strip()
        dp       = lead.get("data_points") or {}

        # ── Email (max 35 pts, adapted) ───────────────────────────────────
        email_pts = 0.0
        if email:
            local = email.split("@")[0] if "@" in email else email
            domain = email.split("@")[1] if "@" in email else ""
            if domain and domain not in _FREE_EMAIL_DOMAINS and local not in _GENERIC_LOCALS:
                email_pts = 30.0      # corporate email
                if dp.get("email_verified"):
                    email_pts = 35.0  # verified corporate
            elif local in _GENERIC_LOCALS:
                email_pts = 8.0       # generic contact@
            elif domain in _FREE_EMAIL_DOMAINS:
                email_pts = 5.0       # personal free email
        breakdown["email"] = round(email_pts * ws.email_weight, 1)

        # ── Phone (max 15 pts, adapted) ───────────────────────────────────
        phone_pts = 0.0
        if phone and len(re.sub(r"\D", "", phone)) >= 8:
            phone_pts = 15.0
        breakdown["phone"] = round(phone_pts * ws.phone_weight, 1)

        # ── Company (max 15 pts) ──────────────────────────────────────────
        company_pts = 0.0
        if company:
            company_pts = 15.0 if len(company.split()) >= 2 else 10.0
        breakdown["company"] = round(company_pts * ws.company_weight, 1)

        # ── Name (max 10 pts) ─────────────────────────────────────────────
        name_pts = 0.0
        if name and " " in name and len(name) >= 5:
            name_pts = 10.0
        elif name:
            name_pts = 5.0
        breakdown["name"] = round(name_pts, 1)

        # ── Position (max 8 pts) ──────────────────────────────────────────
        position_pts = 0.0
        if position:
            dm_keywords = (
                "ceo", "cto", "cfo", "coo", "cmo", "founder", "director",
                "vp", "vice president", "head of", "president", "partner",
                "manager", "owner",
            )
            if any(kw in position.lower() for kw in dm_keywords):
                position_pts = 8.0
            else:
                position_pts = 4.0
        breakdown["position"] = round(position_pts, 1)

        # ── LinkedIn (max 6 pts, adapted) ─────────────────────────────────
        linkedin_pts = 0.0
        if linkedin:
            linkedin_pts = 6.0 if "/in/" in linkedin else 3.0
        breakdown["linkedin"] = round(linkedin_pts * ws.linkedin_weight, 1)

        # ── Website (max 5 pts) ───────────────────────────────────────────
        website_pts = 5.0 if website else 0.0
        breakdown["website"] = round(website_pts, 1)

        # ── Industry (max 4 pts) ──────────────────────────────────────────
        industry_pts = 3.0 if industry else 0.0
        breakdown["industry"] = round(industry_pts, 1)

        # ── Tech stack bonus (adapted) ────────────────────────────────────
        tech_pts = 0.0
        tech_stack = dp.get("tech_stack") or []
        if tech_stack:
            tech_pts = min(10.0, len(tech_stack) * 2.0)
        breakdown["tech_stack"] = round(tech_pts * ws.tech_stack_weight, 1)

        # ── Hiring signal bonus ───────────────────────────────────────────
        hiring_pts = 0.0
        if dp.get("intel_hiring_score", 0) > 30:
            hiring_pts = 5.0
        breakdown["hiring"] = round(hiring_pts * ws.hiring_weight, 1)

        # ── Funding signal bonus ──────────────────────────────────────────
        funding_pts = 0.0
        if dp.get("intel_funding_score", 0) > 30:
            funding_pts = 5.0
        breakdown["funding"] = round(funding_pts * ws.funding_weight, 1)

        # ── Intent bonus ──────────────────────────────────────────────────
        intent_pts = 0.0
        buying_intent = (dp.get("buying_intent") or lead.get("buying_intent") or "none").lower()
        if buying_intent == "high":
            intent_pts = 8.0
            adjustments.append("high_buying_intent_bonus")
        elif buying_intent == "medium":
            intent_pts = 4.0
        breakdown["intent"] = round(intent_pts * ws.intent_weight, 1)

        # ── Raw sum ───────────────────────────────────────────────────────
        raw = sum(breakdown.values())

        # Cap at 100 before returning
        context_score = min(100.0, max(0.0, raw))

        return {
            "context_score": round(context_score, 1),
            "breakdown":     breakdown,
            "weights_used": {
                "rule":           round(ws.rule_weight, 3),
                "ml":             round(ws.ml_weight, 3),
                "intelligence":   round(ws.intelligence_weight, 3),
                "graph":          round(ws.graph_weight, 3),
            },
            "adjustments": adjustments,
        }
