"""
Semantic Intent Engine
======================
Infers buying stage, urgency, and commercial intent from available lead
signals without making external API calls.

Signal sources (all optional, engine degrades gracefully):
  - lead.buying_intent         (explicit string from scraper)
  - lead.data_points.*         (hot/cold signals from intelligence engine)
  - lead.position              (seniority → decision-making power)
  - lead.industry              (vertical-based commercial bias)
  - tech_stack                 (active buyer if using commercial tools)

Buying stages
-------------
  awareness     : early research, no urgency signals
  consideration : comparing vendors, demo/pricing signals
  decision      : high urgency + DM title + corporate email
  unknown       : insufficient signals

Commercial intent score
-----------------------
  0.0 = definitely not buying
  1.0 = actively in buying process
"""

from __future__ import annotations

import re
import threading
from typing import Any, Dict, List, Optional


# ── Signal keyword sets ───────────────────────────────────────────────────────

_DECISION_SIGNALS = frozenset({
    "demo_booking", "pricing_page", "requested_trial", "booked_call",
    "high_buying_intent",
})

_CONSIDERATION_SIGNALS = frozenset({
    "uses_stripe", "uses_hubspot", "uses_intercom", "uses_salesforce",
    "uses_marketo", "uses_outreach", "competitor_research",
})

_AWARENESS_SIGNALS = frozenset({
    "blog_visitor", "content_download", "webinar_attended",
})

_URGENCY_KEYWORDS_HIGH = frozenset({
    "asap", "immediately", "urgent", "this week", "this month",
    "q1", "q2", "q3", "q4", "end of quarter", "budget approved",
})

_URGENCY_KEYWORDS_MEDIUM = frozenset({
    "evaluating", "comparing", "shortlisting", "next quarter",
    "planning", "roadmap",
})

_DM_TITLES = frozenset({
    "ceo", "cto", "cfo", "coo", "cmo", "founder", "co-founder",
    "vp", "vice president", "director", "head of", "president",
    "partner", "managing director", "chief",
})

# Industries with inherently high commercial intent for B2B SaaS/tools
_HIGH_COMMERCIAL_INDUSTRIES = frozenset({
    "software", "technology", "saas", "fintech", "ecommerce",
    "marketing", "sales", "hr tech", "legal tech",
})


class SemanticIntentEngine:
    """
    Infers buying intent from lead signals without LLM calls.
    """

    def infer(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns
        -------
        {
          "buying_stage":      "awareness" | "consideration" | "decision" | "unknown",
          "urgency":           "high" | "medium" | "low",
          "commercial_intent": 0.0-1.0,
          "signals_found":     [str, …],
          "is_decision_maker": bool,
        }
        """
        dp = lead.get("data_points") or {}
        hot_signals: List[str] = dp.get("hot_signals") or []
        hot_set = frozenset(s.lower() for s in hot_signals)

        # Explicit buying_intent string
        explicit = (
            (dp.get("buying_intent") or lead.get("buying_intent") or "none")
            .lower().strip()
        )

        signals_found: List[str] = []

        # ── Decision-maker check ──────────────────────────────────────────
        position = (lead.get("position") or "").lower()
        is_dm = any(kw in position for kw in _DM_TITLES)

        # ── Stage signals ─────────────────────────────────────────────────
        decision_hits    = hot_set & _DECISION_SIGNALS
        consideration_hits = hot_set & _CONSIDERATION_SIGNALS
        awareness_hits   = hot_set & _AWARENESS_SIGNALS
        signals_found.extend(decision_hits | consideration_hits | awareness_hits)

        if explicit == "high":
            decision_hits = decision_hits | {"high_buying_intent"}
            signals_found.append("explicit_high_intent")
        elif explicit == "medium":
            consideration_hits = consideration_hits | {"medium_buying_intent"}
            signals_found.append("explicit_medium_intent")

        # ── Buying stage ──────────────────────────────────────────────────
        if decision_hits and (is_dm or explicit == "high"):
            buying_stage = "decision"
        elif decision_hits or (consideration_hits and is_dm):
            buying_stage = "consideration"
        elif consideration_hits or awareness_hits or explicit == "medium":
            buying_stage = "awareness"
        else:
            buying_stage = "unknown"

        # ── Urgency ───────────────────────────────────────────────────────
        query = (lead.get("query") or dp.get("source_query") or "").lower()
        if explicit == "high" or any(kw in query for kw in _URGENCY_KEYWORDS_HIGH):
            urgency = "high"
            signals_found.append("urgency_high")
        elif explicit == "medium" or any(kw in query for kw in _URGENCY_KEYWORDS_MEDIUM):
            urgency = "medium"
        else:
            urgency = "low"

        # ── Commercial intent score ───────────────────────────────────────
        score = 0.0

        # Stage contribution
        if buying_stage == "decision":
            score += 0.50
        elif buying_stage == "consideration":
            score += 0.30
        elif buying_stage == "awareness":
            score += 0.15

        # DM bonus
        if is_dm:
            score += 0.15

        # Urgency bonus
        if urgency == "high":
            score += 0.20
        elif urgency == "medium":
            score += 0.10

        # Industry bonus
        industry = (lead.get("industry") or "").lower()
        if any(ind in industry for ind in _HIGH_COMMERCIAL_INDUSTRIES):
            score += 0.10

        # Tech stack bonus (active buyers use commercial tools)
        tech_stack = dp.get("tech_stack") or []
        if len(tech_stack) >= 3:
            score += 0.05

        commercial_intent = round(min(1.0, max(0.0, score)), 3)

        return {
            "buying_stage":      buying_stage,
            "urgency":           urgency,
            "commercial_intent": commercial_intent,
            "signals_found":     signals_found,
            "is_decision_maker": is_dm,
        }


_instance: Optional[SemanticIntentEngine] = None
_ilock = threading.Lock()


def get_intent_engine() -> SemanticIntentEngine:
    global _instance
    if _instance is None:
        with _ilock:
            if _instance is None:
                _instance = SemanticIntentEngine()
    return _instance


def infer_intent(lead: Dict[str, Any]) -> Dict[str, Any]:
    return get_intent_engine().infer(lead)
