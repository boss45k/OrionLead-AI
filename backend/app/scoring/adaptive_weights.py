"""
Adaptive Weight Engine
======================
Produces a WeightSet that controls how each scoring component and
individual lead attribute contributes to the final score.

Weights are NOT static — they shift based on:
  - Query intent (saas, fintech, local_sme, ecommerce, …)
  - Industry vertical
  - Company type (saas, agency, enterprise, …)
  - Source type (apollo, web, social, …)
  - Region / country

Examples
--------
  SaaS intent:
    linkedin_weight  ↑  (LinkedIn profiles = decision makers)
    pricing_page     ↑  (competitor research signal)
    phone_weight     ↓  (less critical for SaaS outreach)

  Local SME intent:
    google_places    ↑  (local business data)
    phone_weight     ↑  (primary contact method)
    linkedin_weight  ↓  (less relevant)

  Fintech:
    email_corporate  ↑  (professional identity required)
    company_size     ↑  (regulated industry = larger targets)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ── Weight set ────────────────────────────────────────────────────────────────

@dataclass
class WeightSet:
    """
    Normalized weights that sum to 1.0 across scoring_components.
    Individual field_weights adjust sub-scores within a component.
    """
    # Top-level component weights (must sum to 1.0)
    rule_weight:          float = 0.30
    ml_weight:            float = 0.30
    intelligence_weight:  float = 0.25
    graph_weight:         float = 0.15

    # Field-level importance multipliers (applied inside rule scoring)
    email_weight:         float = 1.0   # corporate email signal
    phone_weight:         float = 1.0
    linkedin_weight:      float = 1.0
    company_weight:       float = 1.0
    tech_stack_weight:    float = 1.0
    hiring_weight:        float = 1.0
    funding_weight:       float = 1.0
    pricing_page_weight:  float = 1.0
    intent_weight:        float = 1.0


# ── Context ───────────────────────────────────────────────────────────────────

@dataclass
class AdaptiveContext:
    intent:       str = "other"        # from CollectionStrategy
    industry:     str = "unknown"
    company_type: str = "unknown"
    source:       str = "unknown"
    region:       str = "unknown"      # country code or continent
    query:        str = ""


# ── Profile table ─────────────────────────────────────────────────────────────
# Each profile defines weight deltas from the base WeightSet.
# Values are multiplied against the base weight.

_INTENT_PROFILES: Dict[str, Dict[str, float]] = {
    "saas": {
        "linkedin_weight":   1.5,
        "tech_stack_weight": 1.4,
        "pricing_page_weight": 1.5,
        "email_weight":      1.3,
        "hiring_weight":     1.2,
        "phone_weight":      0.7,
        "intelligence_weight": 0.30,   # company intelligence very relevant
        "ml_weight":         0.28,
    },
    "fintech": {
        "email_weight":      1.5,
        "linkedin_weight":   1.3,
        "company_weight":    1.4,
        "phone_weight":      1.2,
        "funding_weight":    1.5,
        "intelligence_weight": 0.30,
        "ml_weight":         0.28,
    },
    "tech_startup": {
        "linkedin_weight":   1.4,
        "funding_weight":    1.5,
        "hiring_weight":     1.3,
        "tech_stack_weight": 1.3,
        "intelligence_weight": 0.28,
        "rule_weight":       0.28,
    },
    "ecommerce": {
        "phone_weight":      1.3,
        "company_weight":    1.2,
        "email_weight":      1.2,
        "linkedin_weight":   0.8,
        "tech_stack_weight": 0.9,
    },
    "local_sme": {
        "phone_weight":      1.8,
        "email_weight":      0.9,
        "linkedin_weight":   0.6,
        "company_weight":    1.3,
        "rule_weight":       0.35,
        "ml_weight":         0.25,
        "intelligence_weight": 0.25,
        "graph_weight":      0.15,
    },
    "consulting": {
        "linkedin_weight":   1.4,
        "email_weight":      1.2,
        "company_weight":    1.1,
        "hiring_weight":     1.1,
    },
    "healthcare_b2b": {
        "email_weight":      1.4,
        "company_weight":    1.3,
        "phone_weight":      1.3,
        "linkedin_weight":   1.1,
        "intent_weight":     1.3,
    },
    "real_estate": {
        "phone_weight":      1.6,
        "email_weight":      1.1,
        "linkedin_weight":   0.8,
        "company_weight":    1.2,
        "rule_weight":       0.35,
    },
}

_SOURCE_PROFILES: Dict[str, Dict[str, float]] = {
    "apollo":     {"ml_weight": 0.32, "graph_weight": 0.18},
    "hunter":     {"ml_weight": 0.30, "graph_weight": 0.17},
    "clearbit":   {"ml_weight": 0.30, "intelligence_weight": 0.27},
    "crunchbase": {"funding_weight": 1.6, "intelligence_weight": 0.28},
    "linkedin":   {"linkedin_weight": 1.6, "graph_weight": 0.18},
    "github":     {"tech_stack_weight": 1.5, "hiring_weight": 1.2},
    "reddit":     {"rule_weight": 0.35, "ml_weight": 0.25},
    "news":       {"funding_weight": 1.4, "rule_weight": 0.35},
    "web":        {"rule_weight": 0.33, "ml_weight": 0.27},
}

_REGION_PROFILES: Dict[str, Dict[str, float]] = {
    "US": {"ml_weight": 0.32, "intelligence_weight": 0.26},
    "UK": {"ml_weight": 0.30, "intelligence_weight": 0.26},
    "NG": {"phone_weight": 1.4, "email_weight": 0.9, "rule_weight": 0.35},   # Nigeria: phone-first
    "IN": {"phone_weight": 1.3, "rule_weight": 0.33},
    "AE": {"email_weight": 1.2, "company_weight": 1.3},
    "DE": {"email_weight": 1.3, "company_weight": 1.2},
}


class AdaptiveWeightEngine:
    """
    Produces a WeightSet for a given AdaptiveContext by blending
    intent, source, and region profiles over the base defaults.
    """

    def get_weights(self, ctx: AdaptiveContext) -> WeightSet:
        ws = WeightSet()

        # Apply profiles in priority order: intent > source > region
        for profile_map, key in [
            (_INTENT_PROFILES,  ctx.intent),
            (_SOURCE_PROFILES,  ctx.source),
            (_REGION_PROFILES,  ctx.region.upper() if ctx.region else ""),
        ]:
            deltas = profile_map.get(key.lower() if key else "", {})
            self._apply_deltas(ws, deltas)

        # Renormalize top-level component weights to sum to 1.0
        total = ws.rule_weight + ws.ml_weight + ws.intelligence_weight + ws.graph_weight
        if total > 0:
            factor = 1.0 / total
            ws.rule_weight          *= factor
            ws.ml_weight            *= factor
            ws.intelligence_weight  *= factor
            ws.graph_weight         *= factor

        return ws

    @staticmethod
    def _apply_deltas(ws: WeightSet, deltas: Dict[str, float]) -> None:
        for attr, value in deltas.items():
            if hasattr(ws, attr):
                setattr(ws, attr, value)
