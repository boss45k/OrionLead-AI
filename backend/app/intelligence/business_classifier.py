"""
Business Classifier
===================
Classifies a company into a strict business type used by the ICP (Ideal
Customer Profile) gate.  Builds on CompanyClassifier's heuristics and adds
hard-reject categories.

Output types
------------
    b2b_saas        — software sold to businesses, subscription/seat model
    b2c_saas        — consumer software app
    agency          — services firm / consultancy / design studio
    marketplace     — two-sided marketplace or platform
    ecommerce       — sells physical or digital goods direct
    university      — educational institution
    ngo             — non-profit / NGO / foundation
    government      — ministry, department, municipality, authority
    directory       — listing site, yellow-pages, aggregator
    blog_media      — blog, news site, media brand
    unknown         — not enough signals

ICP check
---------
Pass an `allowed_types` frozenset to `is_icp_match()`.
Default ICP = {'b2b_saas'} — only B2B SaaS companies pass.
The ICP can be widened by the caller (e.g. add 'agency' if targeting agencies).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional

# ── Type-specific keyword lists ───────────────────────────────────────────────

_UNIVERSITY_WORDS = frozenset({
    "university", "universiti", "college", "faculty", "school of",
    "institute of", "academia", "polytechnic", "graduate school",
})

_NGO_WORDS = frozenset({
    "foundation", "non-profit", "nonprofit", "ngo", "ngos",
    "charity", "charitable", "humanitarian", "aid organization",
    "civil society", "social enterprise", "relief organization",
})

_GOVERNMENT_WORDS = frozenset({
    "ministry", "ministries", "department of", "government of",
    "municipality", "council of", "parliament", "embassy",
    "consulate", "authority", "tribunal", "commission",
    "regulatory body", "public sector",
})

_DIRECTORY_WORDS = frozenset({
    "directory", "listings", "yellow pages", "business finder",
    "company list", "find companies", "compare software",
    "software comparison", "reviews and ratings", "top companies",
    "best companies", "rank", "ranking",
})

_BLOG_MEDIA_WORDS = frozenset({
    "techcrunch", "forbes", "businessinsider", "wired", "venturebeat",
    "entrepreneur", "inc.com", "fastcompany", "hbr", "harvard business",
    "blog", "newsletter", "editorial", "news site", "media company",
    "publisher", "magazine", "journal",
})

_MARKETPLACE_SIGNALS = [
    re.compile(p, re.I) for p in [
        r"\btwo.sided\s+marketplace\b",
        r"\bconnect\s+buyers\s+and\s+sellers\b",
        r"\bsell\s+on\s+our\s+platform\b",
        r"\bvendors?\s+and\s+buyers?\b",
        r"\boutdoor\s+marketplace\b",
        r"\bonline\s+marketplace\b",
        r"\bgig\s+marketplace\b",
        r"\bfreelancer\s+marketplace\b",
    ]
]

_AGENCY_SIGNALS = [
    re.compile(p, re.I) for p in [
        r"\bdigital\s+agency\b",
        r"\bmarketing\s+agency\b",
        r"\bdesign\s+agency\b",
        r"\bcreative\s+agency\b",
        r"\bconsulting\s+firm\b",
        r"\bmanagement\s+consulting\b",
        r"\bIT\s+consulting\b",
        r"\bsoftware\s+development\s+company\b",
        r"\boutstaff\b",
        r"\boutsourc(e|ing)\b",
        r"\bour\s+(work|portfolio|clients)\b",
        r"\bwe\s+build\s+(websites?|apps?|software)\s+for\b",
    ]
]

_FREELANCER_SIGNALS = [
    re.compile(p, re.I) for p in [
        r"\bfreelance(r|rs)?\b",
        r"\bindependent\s+contractor\b",
        r"\bsolo\s+(developer|designer|consultant|founder)\b",
        r"\bavailable\s+for\s+hire\b",
        r"\bhire\s+me\b",
        r"\bmy\s+portfolio\b",
        r"\bmy\s+services\b",
        r"\bi\s+(offer|provide|help|build|design)\b",
    ]
]

_ECOMMERCE_SIGNALS = [
    re.compile(p, re.I) for p in [
        r"\badd\s+to\s+cart\b",
        r"\bshop\s+now\b",
        r"\bbuy\s+now\b",
        r"\bfree\s+(shipping|delivery)\b",
        r"\bcollections?\b",
        r"\bproduct\s+catalogue\b",
        r"\bcheck\s*out\b",
        r"\bshopping\s+cart\b",
    ]
]

_B2B_SAAS_SIGNALS = [
    re.compile(p, re.I) for p in [
        r"\bper\s+(seat|user|month)\b",
        r"\bAPI\s+access\b",
        r"\benterprise\s+plan\b",
        r"\bbook\s+a\s+demo\b",
        r"\btalk\s+to\s+(sales|us)\b",
        r"\bcustom\s+pricing\b",
        r"\bB2B\b",
        r"\bSaaS\b",
        r"\bplatform\s+for\s+teams?\b",
        r"\bfor\s+businesses?\b",
        r"\bpowered\s+by\s+AI\b",
        r"\bwork\s*flow\s+automation\b",
    ]
]

_B2C_SAAS_SIGNALS = [
    re.compile(p, re.I) for p in [
        r"\bdownload\s+(the\s+)?app\b",
        r"\bapp\s+store\b",
        r"\bgoogle\s+play\b",
        r"\bpersonal\s+use\b",
        r"\bindividual\s+plan\b",
        r"\bsign\s+up\s+free\b",
        r"\bno\s+credit\s+card\b",
    ]
]


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class BusinessClassification:
    business_type: str = "unknown"       # see module docstring
    confidence: float = 0.0              # 0.0 – 1.0
    signals_found: List[str] = None      # which patterns triggered
    is_hard_reject: bool = False         # university/NGO/gov/directory/blog

    def __post_init__(self):
        if self.signals_found is None:
            self.signals_found = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "business_type":  self.business_type,
            "confidence":     round(self.confidence, 2),
            "signals_found":  self.signals_found,
            "is_hard_reject": self.is_hard_reject,
        }


# ── Classifier ────────────────────────────────────────────────────────────────

class BusinessClassifier:
    """
    Classifies a company based on available text signals.
    Stateless — safe to reuse across threads.
    """

    # Default ICP: only B2B SaaS companies pass
    DEFAULT_ICP: FrozenSet[str] = frozenset({"b2b_saas"})

    def classify(
        self,
        lead: Dict[str, Any],
        page_text: str = "",
        website_audit: Optional[Any] = None,   # WebsiteAuditResult
    ) -> BusinessClassification:
        """
        Classify a company.

        Args:
            lead:          Dict with keys: name, company, industry, website,
                           domain, data_points.
            page_text:     Raw text extracted from company website.
            website_audit: Optional WebsiteAuditResult for richer signals.

        Returns:
            BusinessClassification
        """
        company  = (lead.get("company") or lead.get("name") or "").lower()
        industry = (lead.get("industry") or "").lower()
        domain   = (lead.get("domain") or "").lower()
        signals: List[str] = []
        check_text = f"{company} {industry} {page_text[:3000]}"

        # ── Hard-reject types (checked first) ─────────────────────────────────

        if self._matches_wordlist(check_text, _UNIVERSITY_WORDS):
            return BusinessClassification(
                business_type="university",
                confidence=0.95,
                signals_found=["university_keyword"],
                is_hard_reject=True,
            )

        if self._matches_wordlist(check_text, _NGO_WORDS):
            return BusinessClassification(
                business_type="ngo",
                confidence=0.95,
                signals_found=["ngo_keyword"],
                is_hard_reject=True,
            )

        if self._matches_wordlist(check_text, _GOVERNMENT_WORDS):
            return BusinessClassification(
                business_type="government",
                confidence=0.95,
                signals_found=["government_keyword"],
                is_hard_reject=True,
            )

        if self._matches_wordlist(check_text, _DIRECTORY_WORDS):
            return BusinessClassification(
                business_type="directory",
                confidence=0.90,
                signals_found=["directory_keyword"],
                is_hard_reject=True,
            )

        if self._matches_wordlist(check_text, _BLOG_MEDIA_WORDS):
            return BusinessClassification(
                business_type="blog_media",
                confidence=0.85,
                signals_found=["blog_media_keyword"],
                is_hard_reject=True,
            )

        # Derive audit-based signals
        if website_audit is not None:
            if website_audit.pricing_exists:
                signals.append("pricing_page")
            if website_audit.demo_or_trial_exists:
                signals.append("demo_or_trial")
            if website_audit.careers_exists:
                signals.append("careers_page")
            bm = website_audit.business_model
        else:
            bm = "unknown"

        # ── Score each remaining type ──────────────────────────────────────────

        b2b_saas_score  = self._count_patterns(check_text, _B2B_SAAS_SIGNALS)
        b2c_saas_score  = self._count_patterns(check_text, _B2C_SAAS_SIGNALS)
        agency_score    = self._count_patterns(check_text, _AGENCY_SIGNALS)
        ecomm_score     = self._count_patterns(check_text, _ECOMMERCE_SIGNALS)
        market_score    = self._count_patterns(check_text, _MARKETPLACE_SIGNALS)
        freelancer_score = self._count_patterns(check_text, _FREELANCER_SIGNALS)

        # Hard-reject freelancer if it's clearly a solo contractor site
        if freelancer_score >= 2 and b2b_saas_score < 2:
            return BusinessClassification(
                business_type="freelancer",
                confidence=min(0.95, freelancer_score * 0.2),
                signals_found=signals + ["freelancer_signals"],
                is_hard_reject=True,
            )

        # Boost from website audit
        if bm == "b2b":
            b2b_saas_score += 3
        elif bm == "b2c":
            b2c_saas_score += 2

        # Audit pricing + demo = strong B2B SaaS signal
        if "pricing_page" in signals:
            b2b_saas_score += 2
        if "demo_or_trial" in signals:
            b2b_saas_score += 2

        # Domain keyword hints
        if any(kw in domain for kw in ("saas", "platform", "cloud", "software", "crm", "erp", "api")):
            b2b_saas_score += 2
        if any(kw in domain for kw in ("shop", "store", "mart", "buy", "market")):
            ecomm_score += 2

        # ── Pick the winner ────────────────────────────────────────────────────

        scores = {
            "b2b_saas":    b2b_saas_score,
            "b2c_saas":    b2c_saas_score,
            "agency":      agency_score,
            "marketplace": market_score,
            "ecommerce":   ecomm_score,
        }
        best_type  = max(scores, key=scores.__getitem__)
        best_score = scores[best_type]

        if best_score == 0:
            return BusinessClassification(
                business_type="unknown",
                confidence=0.0,
                signals_found=signals,
                is_hard_reject=False,
            )

        total      = sum(scores.values()) or 1
        confidence = min(0.95, best_score / total)

        return BusinessClassification(
            business_type=best_type,
            confidence=confidence,
            signals_found=signals + [f"{best_type}_signals={best_score}"],
            is_hard_reject=False,
        )

    def is_icp_match(
        self,
        classification: BusinessClassification,
        allowed_types: Optional[FrozenSet[str]] = None,
    ) -> bool:
        """
        Return True if the classified business type is in the ICP allow-list.

        Hard-reject types always return False regardless of the ICP.
        """
        if classification.is_hard_reject:
            return False
        icp = allowed_types or self.DEFAULT_ICP
        return classification.business_type in icp

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_wordlist(text: str, wordlist: FrozenSet[str]) -> bool:
        return any(w in text for w in wordlist)

    @staticmethod
    def _count_patterns(text: str, patterns: List[re.Pattern]) -> int:
        return sum(1 for p in patterns if p.search(text))


# ── Singleton ─────────────────────────────────────────────────────────────────

_classifier: Optional[BusinessClassifier] = None


def get_business_classifier() -> BusinessClassifier:
    global _classifier
    if _classifier is None:
        _classifier = BusinessClassifier()
    return _classifier
