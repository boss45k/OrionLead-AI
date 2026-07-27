"""
Company Classifier
==================
Classifies a company's business model, type, and size band from
available signals: website URL patterns, domain name, industry field,
HTML content, and scraped text.

All analysis is heuristic / pattern-based — no external API calls.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


# ── URL / page patterns ───────────────────────────────────────────────────────

_SAAS_SIGNALS = frozenset({
    "/pricing", "/plans", "/features", "/product", "/solutions",
    "/platform", "/integrations", "/api", "/docs", "/changelog",
    "/customers", "/case-studies", "/testimonials", "/free-trial",
    "/get-started", "/signup", "/demo", "/book-demo",
})

_AGENCY_SIGNALS = frozenset({
    "/services", "/our-work", "/portfolio", "/clients", "/projects",
    "/agency", "/studio", "/consulting", "/strategy", "/branding",
})

_ECOMMERCE_SIGNALS = frozenset({
    "/shop", "/store", "/cart", "/checkout", "/products", "/catalogue",
    "/collections", "/buy", "/order",
})

_B2B_DOMAIN_KEYWORDS = frozenset({
    "software", "tech", "platform", "solutions", "systems", "cloud",
    "digital", "analytics", "data", "ai", "saas", "fintech", "crm",
    "erp", "api", "b2b", "enterprise", "intelligence", "automation",
})

_B2C_DOMAIN_KEYWORDS = frozenset({
    "shop", "store", "deals", "buy", "sale", "fashion", "beauty",
    "food", "delivery", "fitness", "health", "wellness", "travel",
    "hotel", "resort", "restaurant", "cafe",
})

_PARKED_PATTERNS = [
    re.compile(r, re.I) for r in [
        r"domain\s*for\s*sale",
        r"this\s*domain\s*is\s*parked",
        r"buy\s*this\s*domain",
        r"coming\s*soon",
        r"under\s*construction",
        r"parking\s*page",
        r"godaddy\.com",
        r"sedoparking",
        r"domainparking",
    ]
]

_SIZE_KEYWORDS: Dict[str, str] = {
    "startup":    r"\b(startup|early.stage|seed.stage|pre.seed|series.a)\b",
    "smb":        r"\b(small\s*business|smb|sme|boutique)\b",
    "mid_market": r"\b(mid.market|growing\s*company|scale.up|series\s*[bc])\b",
    "enterprise": r"\b(enterprise|fortune\s*500|global\s*company|multinational|publicly\s*traded)\b",
}

_SIZE_EMPLOYEE_MAP = [
    (10,   "startup"),
    (200,  "smb"),
    (1000, "mid_market"),
    (1e9,  "enterprise"),
]

# Known parked / free hosting domains
_FREE_HOSTING = frozenset({
    "wordpress.com", "wix.com", "weebly.com", "blogspot.com",
    "squarespace.com", "webflow.io", "carrd.co", "notion.site",
    "sites.google.com", "github.io",
})


class CompanyClassifier:
    """
    Produces company_type, business_model, company_size_band,
    hot_signals, and cold_signals from available lead data.
    """

    def classify(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        website   = (lead.get("website") or "").lower()
        domain    = (lead.get("domain")  or "").lower()
        industry  = (lead.get("industry") or "").lower()
        text_blob = self._gather_text(lead)

        # Scraped page paths from data_points (set by public_web_collector)
        page_paths: List[str] = (
            lead.get("data_points", {}).get("page_paths", []) or []
        )

        company_type   = self._detect_type(website, domain, industry, page_paths, text_blob)
        business_model = self._detect_b2b(domain, industry, company_type, text_blob)
        size_band      = self._detect_size(lead, text_blob)
        hot_signals    = self._extract_hot_signals(page_paths, website, text_blob)
        cold_signals   = self._extract_cold_signals(domain, text_blob)

        return {
            "company_type":     company_type,
            "business_model":   business_model,
            "company_size_band":size_band,
            "hot_signals":      hot_signals,
            "cold_signals":     cold_signals,
        }

    # ------------------------------------------------------------------

    def _gather_text(self, lead: Dict[str, Any]) -> str:
        parts = [
            lead.get("company", ""),
            lead.get("industry", ""),
            lead.get("notes", ""),
            lead.get("data_points", {}).get("raw_text", ""),
            lead.get("data_points", {}).get("search_snippet", ""),
            lead.get("data_points", {}).get("meta_description", ""),
        ]
        return " ".join(str(p) for p in parts if p).lower()

    def _detect_type(
        self,
        website: str,
        domain: str,
        industry: str,
        page_paths: List[str],
        text: str,
    ) -> str:
        paths_set = {p.lower() for p in page_paths}

        # SaaS / software
        saas_hits = len(_SAAS_SIGNALS & paths_set)
        if saas_hits >= 2 or "/pricing" in paths_set:
            return "saas"
        if any(kw in domain for kw in ("saas", "software", "platform", "cloud")):
            return "saas"
        if any(kw in industry for kw in ("software", "saas", "technology", "cloud")):
            return "saas"

        # Agency / services
        agency_hits = len(_AGENCY_SIGNALS & paths_set)
        if agency_hits >= 2:
            return "agency"
        if any(kw in industry for kw in ("agency", "consulting", "marketing", "design")):
            return "agency"

        # E-commerce
        ecom_hits = len(_ECOMMERCE_SIGNALS & paths_set)
        if ecom_hits >= 1:
            return "ecommerce"

        # Enterprise (large company signals)
        if any(re.search(p, text) for p in [r"fortune\s*500", r"publicly\s*traded", r"nasdaq", r"nyse"]):
            return "enterprise"

        # Keyword fallbacks in text
        if re.search(r"\bsoftware\s+as\s+a\s+service\b|\bsaas\b", text):
            return "saas"
        if re.search(r"\b(marketing|design|creative|pr)\s+agency\b", text):
            return "agency"

        return "unknown"

    def _detect_b2b(
        self,
        domain: str,
        industry: str,
        company_type: str,
        text: str,
    ) -> str:
        if company_type in ("saas", "enterprise"):
            return "b2b"

        domain_name = domain.replace(".", " ")
        b2b_hits = sum(1 for kw in _B2B_DOMAIN_KEYWORDS if kw in domain_name or kw in industry)
        b2c_hits = sum(1 for kw in _B2C_DOMAIN_KEYWORDS if kw in domain_name or kw in text)

        if b2b_hits > b2c_hits:
            return "b2b"
        if b2c_hits > b2b_hits:
            return "b2c"
        if b2b_hits > 0 and b2c_hits > 0:
            return "both"
        return "unknown"

    def _detect_size(self, lead: Dict[str, Any], text: str) -> str:
        # Direct employee count from data_points
        emp = lead.get("data_points", {}).get("employee_count")
        if emp and isinstance(emp, (int, float)) and emp > 0:
            for threshold, band in _SIZE_EMPLOYEE_MAP:
                if emp <= threshold:
                    return band

        # Text pattern matching
        for band, pattern in _SIZE_KEYWORDS.items():
            if re.search(pattern, text, re.I):
                return band

        return "unknown"

    def _extract_hot_signals(
        self,
        page_paths: List[str],
        website: str,
        text: str,
    ) -> List[str]:
        signals: List[str] = []
        paths_str = " ".join(page_paths).lower()

        if "/pricing" in paths_str or "/plans" in paths_str:
            signals.append("pricing_page")
        if "/team" in paths_str or "/about" in paths_str:
            signals.append("team_page")
        if "/product" in paths_str or "/features" in paths_str:
            signals.append("product_page")
        if "/case-stud" in paths_str or "/customers" in paths_str:
            signals.append("case_studies")
        if "/integrations" in paths_str or "/ecosystem" in paths_str:
            signals.append("integrations_page")
        if "/demo" in paths_str or "book-demo" in paths_str or "request-demo" in paths_str:
            signals.append("demo_booking")
        if re.search(r"\bblog\b", paths_str):
            signals.append("blog_active")

        return signals

    def _extract_cold_signals(self, domain: str, text: str) -> List[str]:
        signals: List[str] = []

        for pattern in _PARKED_PATTERNS:
            if pattern.search(text):
                signals.append("parked_domain")
                break

        if any(h in domain for h in _FREE_HOSTING):
            signals.append("free_hosting")

        if re.search(r"under\s+construction|coming\s+soon", text, re.I):
            signals.append("under_construction")

        if not text or len(text) < 50:
            signals.append("no_business_identity")

        return signals
