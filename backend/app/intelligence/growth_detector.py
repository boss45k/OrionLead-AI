"""
Growth Detector
===============
Scores company growth momentum from available signals.

Input signals (all optional):
  - hiring activity (roles, counts, board presence)
  - team size evidence (LinkedIn headcount, text mentions)
  - recent job postings
  - funding rounds / news mentions
  - recent website or blog updates
  - product maturity indicators
  - market expansion language

Output: GrowthResult with growth_score (0-100) and growth_signals list.

Score interpretation:
  ≥ 70  → active growth (strong prospect signal)
  40-69 → moderate growth
  < 40  → low / unknown growth
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Pattern banks ─────────────────────────────────────────────────────────────

_FUNDING_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\b(series\s+[abcde]|seed\s+round|pre.seed)\b",
        r"\b(raised|secured|closed)\s+\$[\d\.]+\s*(m|million|b|billion)\b",
        r"\b(investment|funding|venture\s+capital|vc\s+backed)\b",
        r"\b(yc|y\s+combinator|techstars|sequoia|andreessen|a16z)\b",
        r"\bipo\b",
        r"\bvalued\s+at\s+\$",
        r"\bunicorn\b",
    ]
]

_TEAM_GROWTH_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\bexpanding\s+(our\s+)?team\b",
        r"\bgrowing\s+(our\s+)?team\b",
        r"\bjoin\s+our\s+growing\s+team\b",
        r"\b\d+\+?\s+employees?\b",
        r"\bheadcount\b",
        r"\b\d+\s+people\s+(strong|worldwide|globally)\b",
        r"\bteam\s+of\s+\d+\b",
        r"\bhiring\s+(across|in|globally|rapidly|aggressively)\b",
    ]
]

_RECENT_ACTIVITY_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\blaunched\b",
        r"\breleased\b",
        r"\bannounced\b",
        r"\bnew\s+(feature|product|partnership|integration)\b",
        r"\brecently\s+(raised|launched|partnered|acquired)\b",
        r"\bthis\s+(month|quarter|year)\b",
        r"\bjust\s+(launched|released|announced)\b",
        r"\b202[3-9]\b",    # recent year mentions
    ]
]

_PRODUCT_MATURITY_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\b(customers?|clients?|users?)\s+across\s+\d+\s+(countries|markets)\b",
        r"\bprocessed?\s+\$?[\d,]+\s*(transactions?|payments?|invoices?)\b",
        r"\b\d+[\,\.]?\d*[kKmM]\+?\s+(users?|customers?|companies)\b",
        r"\bglobal\s+(presence|reach|operations?)\b",
        r"\bmarket\s+leader\b",
        r"\b(iso|soc\s*2|gdpr|hipaa)\s*(certified|compliant)\b",
        r"\bcase\s+stud(y|ies)\b",
        r"\bcustomer\s+(success\s+)?stories\b",
    ]
]

_MARKET_EXPANSION_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\bexpanding\s+to\b",
        r"\bentering\s+the\b",
        r"\bnew\s+markets?\b",
        r"\binternational\s+expansion\b",
        r"\bglobal\s+expansion\b",
        r"\blaunch(ing|ed)\s+in\b",
        r"\bopening\s+offices?\s+in\b",
    ]
]

_HIRING_SALES_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\b(account\s+executive|ae|sdr|bdr)\b",
        r"\bvp\s+(of\s+)?sales\b",
        r"\bhead\s+of\s+sales\b",
        r"\bsales\s+manager\b",
        r"\bbusiness\s+development\s+rep(resentative)?\b",
    ]
]

_HIRING_GROWTH_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\bgrowth\s+(hacker|marketer|manager|lead)\b",
        r"\bdemand\s+gen(eration)?\b",
        r"\bperformance\s+market(er|ing)\b",
        r"\bvp\s+(of\s+)?marketing\b",
        r"\bhead\s+of\s+growth\b",
        r"\bcmo\b",
    ]
]


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class GrowthResult:
    growth_score: float = 0.0            # 0-100
    growth_signals: List[str] = field(default_factory=list)
    hiring_detected: bool = False
    hiring_roles: List[str] = field(default_factory=list)
    funding_detected: bool = False
    recent_activity: bool = False
    team_size_hint: str = ""             # e.g. "50+", "200 employees"
    product_maturity: str = "unknown"   # strong | moderate | early | unknown

    def to_dict(self) -> Dict[str, Any]:
        return {
            "growth_score":    round(self.growth_score, 1),
            "growth_signals":  self.growth_signals,
            "hiring_detected": self.hiring_detected,
            "hiring_roles":    self.hiring_roles,
            "funding_detected":self.funding_detected,
            "recent_activity": self.recent_activity,
            "team_size_hint":  self.team_size_hint,
            "product_maturity":self.product_maturity,
        }


# ── Detector ──────────────────────────────────────────────────────────────────

class GrowthDetector:
    """
    Stateless growth signal detector.
    Combines lead metadata + scraped text into a GrowthResult.
    """

    def detect(
        self,
        lead: Dict[str, Any],
        page_text: str = "",
        website_audit: Optional[Any] = None,   # WebsiteAuditResult
        existing_intel: Optional[Dict[str, Any]] = None,   # CompanyProfile.to_dict()
    ) -> GrowthResult:
        """
        Detect growth signals.

        Args:
            lead:           Lead dict with keys: company, industry,
                            data_points, linkedin_url.
            page_text:      Raw text from website pages (combined).
            website_audit:  Optional WebsiteAuditResult.
            existing_intel: Optional output from CompanyIntelligenceEngine.analyze().

        Returns:
            GrowthResult
        """
        result = GrowthResult()
        score = 0.0
        signals: List[str] = []

        # Combined search corpus
        dp = lead.get("data_points") or {}
        corpus = " ".join([
            lead.get("company") or "",
            lead.get("industry") or "",
            dp.get("snippet") or "",
            dp.get("description") or "",
            page_text[:5000],
        ])

        # ── Funding signals (high weight) ──────────────────────────────────────
        funding_hits = sum(1 for p in _FUNDING_PATTERNS if p.search(corpus))
        if funding_hits > 0:
            result.funding_detected = True
            signals.append("funding_signal")
            score += min(30.0, funding_hits * 10.0)

        # ── Hiring sales / growth roles (strong intent signal) ────────────────
        sales_hits  = sum(1 for p in _HIRING_SALES_PATTERNS  if p.search(corpus))
        growth_hits = sum(1 for p in _HIRING_GROWTH_PATTERNS if p.search(corpus))

        if sales_hits > 0:
            result.hiring_detected = True
            signals.append("hiring_sales_roles")
            result.hiring_roles.append("sales")
            score += min(20.0, sales_hits * 7.0)

        if growth_hits > 0:
            result.hiring_detected = True
            signals.append("hiring_growth_roles")
            result.hiring_roles.append("growth/marketing")
            score += min(15.0, growth_hits * 5.0)

        # ── Team growth language ───────────────────────────────────────────────
        team_hits = sum(1 for p in _TEAM_GROWTH_PATTERNS if p.search(corpus))
        if team_hits > 0:
            signals.append("team_growth_language")
            score += min(15.0, team_hits * 5.0)

        # Try to extract a team size hint
        m = re.search(r'\b(\d+[\,\.]?\d*[kKmM]?\+?)\s+(?:employees?|people|team\s+members?)\b', corpus, re.I)
        if m:
            result.team_size_hint = m.group(0).strip()
            signals.append("team_size_mentioned")
            score += 5.0

        # ── Recent activity ────────────────────────────────────────────────────
        activity_hits = sum(1 for p in _RECENT_ACTIVITY_PATTERNS if p.search(corpus))
        if activity_hits > 0:
            result.recent_activity = True
            signals.append("recent_activity")
            score += min(15.0, activity_hits * 5.0)

        # ── Blog/news activity from website audit ──────────────────────────────
        if website_audit is not None and website_audit.last_activity_hint:
            signals.append("active_blog")
            result.recent_activity = True
            score += 8.0

        # ── Product maturity ───────────────────────────────────────────────────
        maturity_hits = sum(1 for p in _PRODUCT_MATURITY_PATTERNS if p.search(corpus))
        if maturity_hits >= 3:
            result.product_maturity = "strong"
            signals.append("product_maturity_strong")
            score += 15.0
        elif maturity_hits >= 1:
            result.product_maturity = "moderate"
            signals.append("product_maturity_moderate")
            score += 7.0

        # ── Market expansion ───────────────────────────────────────────────────
        expansion_hits = sum(1 for p in _MARKET_EXPANSION_PATTERNS if p.search(corpus))
        if expansion_hits > 0:
            signals.append("market_expansion")
            score += min(10.0, expansion_hits * 5.0)

        # ── Bonus from existing intelligence engine results ────────────────────
        if existing_intel:
            score += min(15.0, float(existing_intel.get("hiring_score", 0)) * 0.15)
            score += min(15.0, float(existing_intel.get("funding_score", 0)) * 0.15)
            for gs in (existing_intel.get("growth_signals") or []):
                if gs not in signals:
                    signals.append(gs)

        # ── Website audit bonuses ──────────────────────────────────────────────
        if website_audit is not None:
            if website_audit.careers_exists:
                signals.append("careers_page")
                score += 8.0
            if website_audit.pricing_exists:
                score += 5.0
            if website_audit.tech_stack_hints:
                score += min(10.0, len(website_audit.tech_stack_hints) * 2.0)

        result.growth_score  = min(100.0, score)
        result.growth_signals = signals

        logger.debug(
            "[growth_detector] %s — score=%.1f signals=%s",
            lead.get("company"), result.growth_score, signals,
        )
        return result


# ── Singleton ─────────────────────────────────────────────────────────────────

_detector: Optional[GrowthDetector] = None


def get_growth_detector() -> GrowthDetector:
    global _detector
    if _detector is None:
        _detector = GrowthDetector()
    return _detector
