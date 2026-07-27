"""
Confidence Engine
=================
Combines entity graph score, relationship mapper signals, and raw
lead data quality into a single graph_confidence value (0.0-1.0).

This value flows into the final adaptive score as the "graph" component:
  final_score += graph_confidence × 0.15 × 100
"""

from __future__ import annotations

from typing import Any, Dict


class ConfidenceEngine:
    """
    Computes graph_confidence for a lead by aggregating:
      1. Entity graph connectivity score
      2. Relationship mapper inferences (email-name match, domain corroboration)
      3. Source-level baseline trust
      4. Multi-source corroboration bonus

    All inputs are optional — engine degrades gracefully when any is missing.
    """

    # Source baseline trust (same scale as lead_merger.py source ranks)
    _SOURCE_TRUST: Dict[str, float] = {
        "pdl":       0.95,
        "hunter":    0.90,
        "hunter_api":0.90,
        "clearbit":  0.85,
        "apollo":    0.85,
        "explorium": 0.85,
        "crunchbase":0.78,
        "linkedin":  0.75,
        "github":    0.65,
        "news":      0.55,
        "web":       0.55,
        "public_web":0.55,
        "reddit":    0.30,
        "twitter":   0.30,
        "facebook":  0.30,
        "telegram":  0.25,
        "unknown":   0.25,
    }

    def compute(
        self,
        lead: Dict[str, Any],
        graph_score: float = 0.0,   # from EntityGraph.score_lead()
    ) -> float:
        """
        Returns graph_confidence in [0.0, 1.0].

        Parameters
        ----------
        lead:        raw or enriched lead dict
        graph_score: connectivity score from EntityGraph (0.0-1.0)
        """
        dp = lead.get("data_points") or {}
        source = (lead.get("source") or "unknown").lower().split("_")[0]

        weights: list = []   # (weight, value) pairs

        # ── 1. Source trust baseline ──────────────────────────────────────
        trust = self._SOURCE_TRUST.get(source, 0.25)
        weights.append((0.25, trust))

        # ── 2. Graph connectivity score ───────────────────────────────────
        weights.append((0.30, min(1.0, graph_score)))

        # ── 3. Email-name match ───────────────────────────────────────────
        if dp.get("email_name_match"):
            email_conf = float(dp.get("email_name_confidence", 0.8))
            weights.append((0.20, email_conf))
        else:
            weights.append((0.20, 0.2))

        # ── 4. Email domain matches website domain ────────────────────────
        if dp.get("email_domain_matches_website"):
            weights.append((0.10, 1.0))
        elif dp.get("resolved_domain"):
            weights.append((0.10, 0.5))
        else:
            weights.append((0.10, 0.1))

        # ── 5. LinkedIn corroboration ─────────────────────────────────────
        if dp.get("linkedin_company_corroborated"):
            weights.append((0.10, 1.0))
        elif lead.get("linkedin_url"):
            weights.append((0.10, 0.6))
        else:
            weights.append((0.10, 0.0))

        # ── 6. Email verified bonus ───────────────────────────────────────
        if dp.get("email_verified"):
            weights.append((0.05, 1.0))
        else:
            weights.append((0.05, 0.0))

        # Weighted average
        total_w = sum(w for w, _ in weights)
        if total_w == 0:
            return 0.0
        confidence = sum(w * v for w, v in weights) / total_w

        return round(min(1.0, max(0.0, confidence)), 4)
