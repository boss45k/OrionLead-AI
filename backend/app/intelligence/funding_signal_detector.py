"""
Funding Signal Detector
=======================
Detects funding rounds, press mentions, and growth news from:
  - Scraped text / search snippets
  - News RSS content (collected by news_collector)
  - data_points metadata attached to the lead

Why funding matters:
  - Recently funded companies have budget approval to spend
  - Series A/B = hiring AND buying software
  - News mentions = social proof of active, growing business

Signal scoring:
  recent_funding  → strongest (just got budget)
  news_mention    → medium (active company)
  press_release   → medium (outward-facing company)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ── Funding patterns ──────────────────────────────────────────────────────────

_FUNDING_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\b(seed\s+round|pre.?seed)\b",
        r"\bseries\s+[abcde]\b",
        r"\b(raised|secured|closed)\s+\$[\d,.]+\s*(m|million|k|thousand|b|billion)?\b",
        r"\b(funding|investment|venture|capital)\b.{0,40}\$[\d,.]+",
        r"\$[\d,.]+\s*(m|million|b|billion).{0,40}\b(funding|round|raised|investment)\b",
        r"\b(vc|venture\s+capital|angel\s+investor|series)\b.{0,30}fund",
        r"\b(techcrunch|crunchbase|venturebeat)\b.{0,80}(raised|funding|round)",
    ]
]

_NEWS_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\bpress\s+release\b",
        r"\bannounces?\b.{0,60}\b(launch|product|partnership|expansion)\b",
        r"\b(featured\s+in|covered\s+by|as\s+seen\s+on)\b",
        r"\b(techcrunch|forbes|bloomberg|wired|wsj|inc\.com|entrepreneur)\b",
        r"\b(award|recognition|accolade|top\s+\d+\s+startup)\b",
    ]
]

# Recency keywords — suggest the event is recent (within last 12 months)
_RECENT_KEYWORDS = re.compile(
    r"\b(just|recently|this\s+(week|month|year)|announced\s+today|earlier\s+today|new|latest)\b",
    re.I,
)

# LinkedIn active company signals in text
_LINKEDIN_SIGNALS = [
    re.compile(p, re.I) for p in [
        r"linkedin\.com/company/",
        r"\b(\d{2,6})\s+followers?\b",        # follower count
        r"follow\s+us\s+on\s+linkedin",
    ]
]


class FundingSignalDetector:
    """
    Detects funding and news momentum signals.
    """

    def detect(
        self,
        company: str,
        domain: str,
        lead: Dict[str, Any],
    ) -> Dict[str, Any]:
        text_blob = self._gather_text(lead)
        linkedin  = (lead.get("linkedin_url") or "").lower()

        hot_signals:    List[str] = []
        growth_signals: List[str] = []
        funding_score   = 0.0

        # ── 1. Funding round detection ────────────────────────────────────
        funding_hits = [p for p in _FUNDING_PATTERNS if p.search(text_blob)]
        if funding_hits:
            hot_signals.append("recent_funding")
            growth_signals.append("funding_detected")
            funding_score += 40.0

            # Bonus for recency language
            if _RECENT_KEYWORDS.search(text_blob):
                growth_signals.append("very_recent_news")
                funding_score += 15.0

        # ── 2. Press / news mentions ──────────────────────────────────────
        news_hits = [p for p in _NEWS_PATTERNS if p.search(text_blob)]
        if news_hits:
            hot_signals.append("news_mention")
            growth_signals.append("press_coverage")
            funding_score += 15.0

        # ── 3. Press release page ─────────────────────────────────────────
        page_paths = lead.get("data_points", {}).get("page_paths", []) or []
        if any("press" in p.lower() or "news" in p.lower() for p in page_paths):
            hot_signals.append("press_release")
            funding_score += 10.0

        # ── 4. LinkedIn company signals ───────────────────────────────────
        if linkedin:
            hot_signals.append("linkedin_company")
            funding_score += 8.0

        if any(p.search(text_blob) for p in _LINKEDIN_SIGNALS):
            hot_signals.append("linkedin_active")
            funding_score += 10.0

        # ── 5. Source: news_collector already found this via RSS ──────────
        source = (lead.get("source") or "").lower()
        if source in ("news", "rss", "techcrunch", "venturebeat"):
            hot_signals.append("news_mention")
            funding_score += 8.0

        funding_score = min(100.0, funding_score)

        return {
            "hot_signals":    list(set(hot_signals)),
            "growth_signals": list(set(growth_signals)),
            "funding_score":  funding_score,
        }

    def _gather_text(self, lead: Dict[str, Any]) -> str:
        dp = lead.get("data_points") or {}
        parts = [
            lead.get("notes", ""),
            dp.get("raw_text", ""),
            dp.get("search_snippet", ""),
            dp.get("post_text", ""),
            dp.get("meta_description", ""),
            lead.get("company", ""),
        ]
        return " ".join(str(p) for p in parts if p)
