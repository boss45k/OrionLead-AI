"""
Orchestrator Agent
==================
Coordinates the enterprise scoring pipeline for a single lead:

  GraphAgent     → relationship mapping + graph_confidence
  IntelligenceAgent → company intelligence + intelligence_score
  ScoringAgent   → final adaptive score fusion

The orchestrator is designed to be called from candidate_pipeline.py
instead of the legacy lead_validator rule score.

Usage
-----
    from app.agents.orchestrator_agent import run_enterprise_pipeline

    result = run_enterprise_pipeline(
        lead,
        ml_score=ml_result.get("score", 0),
        intent="saas",
        source="apollo",
        region="US",
    )
    final_score = result["final_score"]
    grade = result["grade"]
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.agents import intelligence_agent, graph_agent, scoring_agent


def run_enterprise_pipeline(
    lead: Dict[str, Any],
    *,
    ml_score: float = 0.0,
    intent: str = "other",
    industry: str = "unknown",
    company_type: str = "unknown",
    source: str = "unknown",
    region: str = "unknown",
    run_intelligence: bool = True,
    run_graph: bool = True,
) -> Dict[str, Any]:
    """
    Full enterprise scoring pipeline for one lead.

    Parameters
    ----------
    lead             : raw or enriched lead dict
    ml_score         : 0-100 score from ML model (XGBoost or similar)
    intent           : query intent label ("saas", "fintech", …)
    industry         : industry vertical
    company_type     : "saas", "agency", "enterprise", …
    source           : data source ("apollo", "hunter", "web", …)
    region           : ISO country code ("US", "UK", …)
    run_intelligence : set False to skip website/hiring/funding crawl (speed)
    run_graph        : set False to skip graph pass (unit tests, batch)

    Returns
    -------
    {
      "final_score":         0-100,
      "grade":               "A"/"B"/"C"/"D"/"F",
      "rule_score":          0-100,
      "ml_score":            0-100,
      "intelligence_score":  0-100,
      "graph_confidence":    0.0-1.0,
      "graph_score":         0-100,
      "component_weights":   dict,
      "context_breakdown":   dict,
      "adjustments":         [str, …],
      "intel":               dict,     # full company intelligence
      "graph":               dict,     # graph agent output
      "augmented_lead":      dict,     # lead with enriched data_points
    }
    """
    augmented = dict(lead)
    graph_result: Dict[str, Any] = {
        "graph_confidence": 0.0,
        "graph_score": 0.0,
        "augmented_lead": augmented,
        "error": None,
    }
    intel_result: Dict[str, Any] = {
        "intelligence_score": 0.0,
        "company_type": company_type,
        "business_model": "unknown",
        "company_size_band": "unknown",
        "hot_signals": [],
        "cold_signals": [],
        "tech_stack": [],
        "error": None,
    }

    # ── 1. Graph pass ─────────────────────────────────────────────────────
    if run_graph:
        graph_result = graph_agent.process(augmented, source=source)
        augmented = graph_result.get("augmented_lead", augmented)

    # ── 2. Intelligence pass ──────────────────────────────────────────────
    if run_intelligence:
        intel_result = intelligence_agent.analyze(augmented)

        # Back-fill enriched signals into lead data_points for ContextScorer
        dp = dict(augmented.get("data_points") or {})
        if intel_result.get("tech_stack"):
            dp["tech_stack"] = intel_result["tech_stack"]
        if intel_result.get("intelligence_score", 0) > 50:
            dp["intel_hiring_score"] = intel_result.get("intelligence_score", 0)
        if intel_result.get("funding_round"):
            dp["intel_funding_score"] = intel_result.get("intelligence_score", 0)
        augmented["data_points"] = dp

        # Use intelligence-derived company_type if we didn't already have one
        if company_type == "unknown" and intel_result.get("company_type") != "unknown":
            company_type = intel_result["company_type"]

    # ── 3. Final scoring fusion ───────────────────────────────────────────
    score_result = scoring_agent.score_lead(
        augmented,
        ml_score=ml_score,
        intelligence_score=intel_result.get("intelligence_score", 0.0),
        graph_confidence=graph_result.get("graph_confidence", 0.0),
        intent=intent,
        industry=industry,
        company_type=company_type,
        source=source,
        region=region,
    )

    return {
        **score_result,
        "graph_confidence":  graph_result.get("graph_confidence", 0.0),
        "intel":             intel_result,
        "graph":             {k: v for k, v in graph_result.items() if k != "augmented_lead"},
        "augmented_lead":    augmented,
    }
