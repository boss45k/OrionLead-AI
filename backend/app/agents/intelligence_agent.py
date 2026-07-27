"""
Intelligence Agent
==================
Specialized agent that runs the Company Intelligence Engine for a lead
and returns a structured intelligence score + profile for use in
the final scoring pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from app.intelligence import analyze_company, CompanyProfile
    _intel_available = True
except ImportError:
    _intel_available = False


def analyze(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run company intelligence analysis for a lead.

    Returns
    -------
    {
      "intelligence_score": 0-100,
      "company_type":       str,
      "business_model":     str,
      "company_size_band":  str,
      "hot_signals":        [str, …],
      "cold_signals":       [str, …],
      "tech_stack":         [str, …],
      "hiring_roles":       [str, …],
      "growth_signals":     [str, …],
      "funding_round":      str | None,
      "error":              str | None,
    }
    """
    if not _intel_available:
        return {
            "intelligence_score": 0.0,
            "company_type": "unknown",
            "business_model": "unknown",
            "company_size_band": "unknown",
            "hot_signals": [],
            "cold_signals": [],
            "tech_stack": [],
            "hiring_roles": [],
            "growth_signals": [],
            "funding_round": None,
            "error": "intelligence_package_unavailable",
        }

    try:
        profile: CompanyProfile = analyze_company(lead)
        return {
            "intelligence_score": profile.intelligence_score,
            "company_type":       profile.company_type,
            "business_model":     profile.business_model,
            "company_size_band":  profile.company_size_band,
            "hot_signals":        profile.hot_signals,
            "cold_signals":       profile.cold_signals,
            "tech_stack":         profile.tech_stack,
            "hiring_roles":       profile.hiring_roles,
            "growth_signals":     profile.growth_signals,
            "funding_round":      profile.funding_round,
            "error":              None,
        }
    except Exception as exc:
        return {
            "intelligence_score": 0.0,
            "company_type": "unknown",
            "business_model": "unknown",
            "company_size_band": "unknown",
            "hot_signals": [],
            "cold_signals": [],
            "tech_stack": [],
            "hiring_roles": [],
            "growth_signals": [],
            "funding_round": None,
            "error": str(exc),
        }
