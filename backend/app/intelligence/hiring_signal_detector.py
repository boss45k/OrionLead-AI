"""
Hiring Signal Detector
======================
Detects active hiring activity from:
  - Scraped text / snippets (LinkedIn, Glassdoor, job boards)
  - Company careers page presence
  - Job title patterns found in collected text

Why hiring matters for B2B sales:
  - Hiring SALES → currently growing, has budget
  - Hiring ENGINEERING → building product, tech-savvy buyer
  - Hiring MARKETING → spending on growth, open to tools
  - Rapid hiring overall → expansion phase, high-value prospect

All analysis is heuristic — no external API calls.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


# ── Role category patterns ────────────────────────────────────────────────────

_SALES_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\b(account\s+executive|ae)\b",
        r"\b(sales\s+development\s+rep|sdr|bdr)\b",
        r"\b(sales\s+manager|vp\s+of?\s+sales|chief\s+revenue)\b",
        r"\b(business\s+development|bd\s+rep)\b",
        r"\bsales\s+engineer\b",
        r"\bcustomer\s+success\s+manager\b",
    ]
]

_MARKETING_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\b(growth\s+hacker|growth\s+marketer)\b",
        r"\b(demand\s+gen|demand\s+generation)\b",
        r"\b(marketing\s+manager|cmo|vp\s+marketing)\b",
        r"\b(content\s+marketer|seo\s+specialist)\b",
        r"\b(performance\s+marketer|paid\s+ads)\b",
        r"\bproduct\s+marketing\b",
    ]
]

_ENGINEERING_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\b(software\s+engineer|swe|backend\s+developer)\b",
        r"\b(full.?stack\s+developer|front.?end\s+developer)\b",
        r"\b(cto|vp\s+engineering|engineering\s+manager)\b",
        r"\b(devops|platform\s+engineer|sre)\b",
        r"\b(data\s+scientist|ml\s+engineer|ai\s+engineer)\b",
    ]
]

_HIRING_CONTEXT_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"(we('re| are)\s+hiring|join\s+our\s+team|open\s+positions?)",
        r"(apply\s+now|view\s+jobs?|see\s+openings?|career\s+opportunities)",
        r"(glassdoor|linkedin\.com/jobs|indeed\.com|lever\.co|greenhouse\.io|workable\.com)",
        r"(\d+\s+open\s+(roles?|positions?|jobs?))",
    ]
]

# Signals that suggest a careers page exists
_CAREERS_PAGE_PATHS = frozenset({
    "/careers", "/jobs", "/work-with-us", "/join-us",
    "/join", "/open-positions", "/opportunities",
})


class HiringSignalDetector:
    """
    Detects hiring activity from scraped text and page structure.
    Returns hiring_score (0-100), hiring_roles list, and growth_signals.
    """

    def detect(
        self,
        company: str,
        domain: str,
        lead: Dict[str, Any],
    ) -> Dict[str, Any]:
        text_blob = self._gather_text(lead)
        page_paths: List[str] = (
            lead.get("data_points", {}).get("page_paths", []) or []
        )

        hiring_roles: List[str] = []
        hot_signals:  List[str] = []
        growth_signals: List[str] = []

        # ── 1. Careers page presence ──────────────────────────────────────
        has_careers = any(
            p.lower() in _CAREERS_PAGE_PATHS for p in page_paths
        )
        if has_careers:
            hot_signals.append("hiring_active")
            growth_signals.append("has_careers_page")

        # ── 2. Hiring context language ────────────────────────────────────
        hiring_context = any(p.search(text_blob) for p in _HIRING_CONTEXT_PATTERNS)
        if hiring_context:
            hot_signals.append("hiring_active")

        # ── 3. Role-specific detection ────────────────────────────────────
        if any(p.search(text_blob) for p in _SALES_PATTERNS):
            hiring_roles.append("sales")
            hot_signals.append("hiring_sales")
            growth_signals.append("growing_sales_team")

        if any(p.search(text_blob) for p in _MARKETING_PATTERNS):
            hiring_roles.append("marketing")
            hot_signals.append("hiring_marketing")
            growth_signals.append("growing_marketing_team")

        if any(p.search(text_blob) for p in _ENGINEERING_PATTERNS):
            hiring_roles.append("engineering")
            hot_signals.append("hiring_engineering")

        # ── 4. Volume signal — many job mentions → very active ────────────
        job_mentions = len(re.findall(
            r"\b(job|position|opening|role|vacancy|hire)\b", text_blob, re.I
        ))
        if job_mentions >= 5:
            growth_signals.append("high_hiring_volume")
            if "hiring_active" not in hot_signals:
                hot_signals.append("hiring_active")

        # ── 5. Compute score ──────────────────────────────────────────────
        hiring_score = 0.0
        if "hiring_sales"       in hot_signals: hiring_score += 35.0
        if "hiring_marketing"   in hot_signals: hiring_score += 25.0
        if "hiring_engineering" in hot_signals: hiring_score += 20.0
        if "hiring_active"      in hot_signals: hiring_score += 15.0
        if "high_hiring_volume" in growth_signals: hiring_score += 10.0
        if has_careers:                         hiring_score += 5.0

        hiring_score = min(100.0, hiring_score)

        return {
            "hiring_roles":   list(set(hiring_roles)),
            "hot_signals":    list(set(hot_signals)),
            "growth_signals": list(set(growth_signals)),
            "hiring_score":   hiring_score,
        }

    def _gather_text(self, lead: Dict[str, Any]) -> str:
        dp = lead.get("data_points") or {}
        parts = [
            lead.get("notes", ""),
            dp.get("raw_text", ""),
            dp.get("search_snippet", ""),
            dp.get("job_postings", ""),
            lead.get("interests", []),
        ]
        blob = " ".join(
            " ".join(p) if isinstance(p, list) else str(p)
            for p in parts if p
        )
        return blob
