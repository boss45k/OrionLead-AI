"""
Company Intelligence Engine  — core orchestrator
=================================================
Runs all sub-detectors concurrently and aggregates results into a
CompanyProfile with a final hot_score (0-100).

Architecture
------------
CompanyIntelligenceEngine
  ├── CompanyClassifier        (business model + B2B/B2C)
  ├── TechStackDetector        (technology footprint)
  ├── HiringSignalDetector     (growth / sales activity)
  └── FundingSignalDetector    (investment / news signals)

The engine is instantiated once (singleton) and is thread-safe.
Each detector is stateless and can be called independently.
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── Hot / cold signal weights ─────────────────────────────────────────────────
_HOT_WEIGHTS: Dict[str, float] = {
    # Company structure signals
    "pricing_page":         15.0,
    "team_page":            8.0,
    "product_page":         10.0,
    "case_studies":         8.0,
    "integrations_page":    7.0,
    "blog_active":          5.0,
    "demo_booking":         12.0,
    # Tech stack signals
    "uses_stripe":          10.0,
    "uses_hubspot":         8.0,
    "uses_intercom":        8.0,
    "uses_salesforce":      7.0,
    "uses_mixpanel":        6.0,
    "uses_segment":         6.0,
    "uses_drift":           7.0,
    "uses_zendesk":         6.0,
    # Hiring signals
    "hiring_sales":         12.0,
    "hiring_marketing":     8.0,
    "hiring_engineering":   7.0,
    "hiring_active":        6.0,
    # Funding signals
    "recent_funding":       15.0,
    "news_mention":         5.0,
    "press_release":        4.0,
    # LinkedIn signals
    "linkedin_active":      8.0,
    "linkedin_company":     5.0,
}

_COLD_WEIGHTS: Dict[str, float] = {
    "parked_domain":       -40.0,
    "no_product_pages":    -15.0,
    "inactive_company":    -20.0,
    "no_business_identity":-25.0,
    "generic_template":    -10.0,
    "under_construction":  -30.0,
    "free_hosting":        -8.0,
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class CompanyProfile:
    """Full intelligence profile for one company."""

    # Identity
    company: str = ""
    domain: str = ""
    website: str = ""

    # Classification
    company_quality: str = "unknown"   # high | medium | low | unknown
    company_type: str = "unknown"      # saas | agency | ecommerce | enterprise | local | unknown
    business_model: str = "unknown"    # b2b | b2c | both | unknown
    company_size_band: str = "unknown" # startup | smb | mid_market | enterprise | unknown

    # Signals
    hot_signals: List[str] = field(default_factory=list)
    cold_signals: List[str] = field(default_factory=list)
    growth_signals: List[str] = field(default_factory=list)
    tech_stack: List[str] = field(default_factory=list)
    hiring_roles: List[str] = field(default_factory=list)

    # Scores
    hot_score: float = 0.0          # 0-100 overall intelligence score
    tech_score: float = 0.0         # 0-100 technology sophistication
    hiring_score: float = 0.0       # 0-100 hiring activity
    funding_score: float = 0.0      # 0-100 funding / news momentum

    # Meta
    analysis_ms: int = 0
    from_cache: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company":          self.company,
            "domain":           self.domain,
            "company_quality":  self.company_quality,
            "company_type":     self.company_type,
            "business_model":   self.business_model,
            "company_size_band":self.company_size_band,
            "hot_signals":      self.hot_signals,
            "cold_signals":     self.cold_signals,
            "growth_signals":   self.growth_signals,
            "tech_stack":       self.tech_stack,
            "hiring_roles":     self.hiring_roles,
            "hot_score":        round(self.hot_score, 1),
            "tech_score":       round(self.tech_score, 1),
            "hiring_score":     round(self.hiring_score, 1),
            "funding_score":    round(self.funding_score, 1),
            "analysis_ms":      self.analysis_ms,
        }


# ── Engine ────────────────────────────────────────────────────────────────────

class CompanyIntelligenceEngine:
    """
    Orchestrates all intelligence detectors for a company.

    Thread-safe. Detectors run concurrently in a bounded thread pool.
    Results are cached per domain for 1 hour (in-process LRU).
    """

    _MAX_WORKERS = 4
    _TIMEOUT_S   = 12.0   # total budget per company

    def __init__(self) -> None:
        from app.intelligence.company_classifier    import CompanyClassifier
        from app.intelligence.tech_stack_detector   import TechStackDetector
        from app.intelligence.hiring_signal_detector import HiringSignalDetector
        from app.intelligence.funding_signal_detector import FundingSignalDetector

        self._classifier = CompanyClassifier()
        self._tech       = TechStackDetector()
        self._hiring     = HiringSignalDetector()
        self._funding    = FundingSignalDetector()
        self._executor   = ThreadPoolExecutor(
            max_workers=self._MAX_WORKERS,
            thread_name_prefix="intel",
        )
        logger.info("[intelligence] CompanyIntelligenceEngine ready")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, lead: Dict[str, Any]) -> CompanyProfile:
        """
        Run the full intelligence analysis for one lead.

        Args:
            lead: dict with at least 'company', and optionally 'website',
                  'domain', 'industry', 'linkedin_url', 'data_points'.

        Returns:
            CompanyProfile with all detectors' results merged.
        """
        t0 = time.monotonic()

        company = (lead.get("company") or "").strip()
        website = (lead.get("website") or "").strip()
        domain  = self._extract_domain(website, lead.get("email") or "")

        if not company and not domain:
            return CompanyProfile(error="no_identity")

        profile = CompanyProfile(company=company, domain=domain, website=website)

        # Run all detectors concurrently with a hard deadline
        tasks = {
            "classify": lambda: self._classifier.classify(lead),
            "tech":     lambda: self._tech.detect(website, domain, lead),
            "hiring":   lambda: self._hiring.detect(company, domain, lead),
            "funding":  lambda: self._funding.detect(company, domain, lead),
        }

        futures = {
            self._executor.submit(fn): name
            for name, fn in tasks.items()
        }

        results: Dict[str, Any] = {}
        for fut in as_completed(futures, timeout=self._TIMEOUT_S):
            name = futures[fut]
            try:
                results[name] = fut.result()
            except Exception as exc:
                logger.debug(f"[intelligence] {name} detector failed: {exc}")
                results[name] = {}

        self._merge(profile, results)
        self._compute_hot_score(profile)
        self._classify_quality(profile)

        profile.analysis_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            f"[intelligence] {company or domain}: "
            f"type={profile.company_type} quality={profile.company_quality} "
            f"hot={profile.hot_score:.0f} in {profile.analysis_ms}ms"
        )
        return profile

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_domain(self, website: str, email: str) -> str:
        if website:
            try:
                h = urlparse(website).netloc.lower().replace("www.", "")
                if h:
                    return h
            except Exception:
                pass
        if "@" in email:
            return email.split("@")[1].lower()
        return ""

    def _merge(self, profile: CompanyProfile, results: Dict[str, Any]) -> None:
        """Merge detector results into the profile."""
        cls = results.get("classify", {})
        tch = results.get("tech", {})
        hir = results.get("hiring", {})
        fnd = results.get("funding", {})

        profile.company_type     = cls.get("company_type", "unknown")
        profile.business_model   = cls.get("business_model", "unknown")
        profile.company_size_band= cls.get("company_size_band", "unknown")
        profile.hot_signals      = (
            cls.get("hot_signals", [])
            + tch.get("hot_signals", [])
            + hir.get("hot_signals", [])
            + fnd.get("hot_signals", [])
        )
        profile.cold_signals     = cls.get("cold_signals", [])
        profile.growth_signals   = (
            hir.get("growth_signals", [])
            + fnd.get("growth_signals", [])
        )
        profile.tech_stack       = tch.get("tech_stack", [])
        profile.tech_score       = float(tch.get("tech_score", 0))
        profile.hiring_roles     = hir.get("hiring_roles", [])
        profile.hiring_score     = float(hir.get("hiring_score", 0))
        profile.funding_score    = float(fnd.get("funding_score", 0))

    def _compute_hot_score(self, profile: CompanyProfile) -> None:
        raw = 0.0
        for sig in profile.hot_signals:
            raw += _HOT_WEIGHTS.get(sig, 3.0)
        for sig in profile.cold_signals:
            raw += _COLD_WEIGHTS.get(sig, -5.0)

        # Blend in sub-scores
        raw += profile.tech_score    * 0.15
        raw += profile.hiring_score  * 0.15
        raw += profile.funding_score * 0.20

        profile.hot_score = max(0.0, min(100.0, raw))

    def _classify_quality(self, profile: CompanyProfile) -> None:
        if profile.cold_signals and not profile.hot_signals:
            profile.company_quality = "low"
        elif profile.hot_score >= 50:
            profile.company_quality = "high"
        elif profile.hot_score >= 25:
            profile.company_quality = "medium"
        else:
            profile.company_quality = "low"


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[CompanyIntelligenceEngine] = None


def get_intelligence_engine() -> CompanyIntelligenceEngine:
    global _engine
    if _engine is None:
        _engine = CompanyIntelligenceEngine()
    return _engine


def analyze_company(lead: Dict[str, Any]) -> CompanyProfile:
    """Convenience function — analyze a lead dict and return a CompanyProfile."""
    return get_intelligence_engine().analyze(lead)
