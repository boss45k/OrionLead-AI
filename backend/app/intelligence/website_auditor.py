"""
Website Auditor
===============
Scrapes and analyzes a company's public website to build a structured
WebsiteAuditResult used by the intelligence pipeline.

Pages visited (budget-aware, in priority order):
  1. Homepage  (always)
  2. /pricing  or /plans
  3. /about    or /about-us
  4. /product  or /features or /platform or /solutions
  5. /careers  or /jobs
  6. /contact  or /contact-us
  7. /blog     or /news

Extracted signals:
  - company_name, domain, product_description (snippet from homepage)
  - business_model:        'b2b' | 'b2c' | 'both' | 'unknown'
  - saas_signals:          list of detected SaaS page paths
  - pricing_exists:        bool
  - demo_or_trial_exists:  bool
  - signup_exists:         bool
  - careers_exists:        bool
  - contact_email:         first found business email
  - social_links:          list of social profile URLs
  - tech_stack_hints:      list of detected JS libs / pixels from homepage <head>
  - team_signals:          bool (found team/people page)
  - last_activity_hint:    str from blog/news dates
  - trust_signals:         list ('ssl', 'verified_domain', 'blog_active', …)
  - red_flags:             list ('no_about', 'no_contact', 'parked', …)
  - pages_visited:         list of URLs actually fetched
  - audit_ms:              int
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_TIMEOUT = 8          # per-request timeout (seconds)
_MAX_PAGES = 6        # maximum pages to fetch per company
_MAX_CONTENT = 40_000  # max bytes of text to process per page

_PAGE_PRIORITY = [
    ("/",           "homepage"),
    ("/pricing",    "pricing"),
    ("/plans",      "pricing"),
    ("/about",      "about"),
    ("/about-us",   "about"),
    ("/product",    "product"),
    ("/features",   "product"),
    ("/platform",   "product"),
    ("/solutions",  "product"),
    ("/careers",    "careers"),
    ("/jobs",       "careers"),
    ("/contact",    "contact"),
    ("/contact-us", "contact"),
    ("/blog",       "blog"),
    ("/news",       "blog"),
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; LeadAuditBot/1.0; "
        "+https://example.com/bot)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Detector patterns ─────────────────────────────────────────────────────────

_B2B_SIGNALS = [
    re.compile(p, re.I) for p in [
        r"\benterprise\b", r"\bB2B\b", r"\bbusiness\s+solution\b",
        r"\bfor\s+teams?\b", r"\bfor\s+companies\b", r"\bfor\s+businesses\b",
        r"\bbook\s+a\s+demo\b", r"\brequest\s+demo\b", r"\btalk\s+to\s+sales\b",
        r"\bAPI\b", r"\bintegrations?\b", r"\bcustom\s+pricing\b",
        r"\bper\s+seat\b", r"\bper\s+user\b", r"\bmonthly\s+active\b",
    ]
]

_B2C_SIGNALS = [
    re.compile(p, re.I) for p in [
        r"\bfor\s+(individuals?|consumers?|personal use)\b",
        r"\bdownload\s+(the\s+)?app\b",
        r"\b(free|premium)\s+plan\b",
        r"\bsign\s+up\s+free\b",
        r"\bno\s+credit\s+card\s+required\b",
        r"\bapp\s+store\b",
        r"\bgoogle\s+play\b",
    ]
]

_PRICING_SIGNALS = [
    re.compile(p, re.I) for p in [
        r"\$\s*\d+[\.,]?\d*\s*(\/|per)\s*(mo|month|year|yr|user|seat)",
        r"\bstarting\s+at\s+\$",
        r"\bfree\s+plan\b",
        r"\bpro\s+plan\b",
        r"\benterprise\s+plan\b",
        r"\bchoose\s+your\s+plan\b",
        r"\bcompare\s+plans\b",
        r"\bview\s+pricing\b",
        r"\bget\s+started\s+for\s+free\b",
    ]
]

_SAAS_PAGE_HINTS = frozenset({
    "/pricing", "/plans", "/features", "/product", "/platform",
    "/solutions", "/integrations", "/api", "/docs", "/changelog",
    "/customers", "/case-studies", "/demo", "/book-demo", "/free-trial",
    "/get-started", "/signup", "/sign-up",
})

_TECH_STACK_PATTERNS = {
    "HubSpot":      re.compile(r"hubspot|hs-scripts", re.I),
    "Salesforce":   re.compile(r"salesforce|pardot", re.I),
    "Intercom":     re.compile(r"intercom\.", re.I),
    "Stripe":       re.compile(r"js\.stripe\.com", re.I),
    "Segment":      re.compile(r"cdn\.segment\.", re.I),
    "Mixpanel":     re.compile(r"cdn\.mxpnl\.|mixpanel", re.I),
    "Google Analytics": re.compile(r"google-analytics|gtag/js|ga\(", re.I),
    "Meta Pixel":   re.compile(r"connect\.facebook\.net|fbq\(", re.I),
    "Calendly":     re.compile(r"calendly\.com", re.I),
    "Zendesk":      re.compile(r"zendesk\.|zopim\.", re.I),
    "Crisp":        re.compile(r"client\.crisp\.chat", re.I),
    "Hotjar":       re.compile(r"static\.hotjar\.com|hotjar", re.I),
    "Drift":        re.compile(r"js\.driftt\.com|drift\.com", re.I),
    "Amplitude":    re.compile(r"cdn\.amplitude\.com", re.I),
    "Heap":         re.compile(r"heapanalytics\.com", re.I),
    "Typeform":     re.compile(r"typeform\.com", re.I),
}

_EMAIL_PATTERN = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
)

_SOCIAL_PATTERNS = {
    "linkedin":  re.compile(r"linkedin\.com/(company|in)/[\w\-]+", re.I),
    "twitter":   re.compile(r"(?:twitter|x)\.com/[\w\-]+", re.I),
    "facebook":  re.compile(r"facebook\.com/[\w\-]+", re.I),
    "instagram": re.compile(r"instagram\.com/[\w\-]+", re.I),
    "youtube":   re.compile(r"youtube\.com/(?:c/|channel/|@)[\w\-]+", re.I),
}

_BLOG_DATE_PATTERN = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+\d{1,2},?\s+20\d{2}\b",
    re.I,
)

_LOCATION_IN_TEXT_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\bbased\s+in\s+([A-Z][a-zA-Z\s]{2,30}?)(?:\.|,|\s*[-–]|\s{2}|$)",
        r"\bheadquartered\s+in\s+([A-Z][a-zA-Z\s]{2,30}?)(?:\.|,|\s*[-–]|\s{2}|$)",
        r"\boffices?\s+in\s+([A-Z][a-zA-Z\s]{2,30}?)(?:\.|,|\s*[-–]|\s{2}|$)",
        r"\bfounded\s+in\s+([A-Z][a-zA-Z\s]{2,30}?)(?:\.|,|\s*[-–]|\s{2}|$)",
        r"\bserving\s+(?:clients?\s+in\s+)?([A-Z][a-zA-Z\s]{2,30}?)(?:\.|,|\s*[-–]|\s{2}|$)",
        r"\blocated\s+in\s+([A-Z][a-zA-Z\s]{2,30}?)(?:\.|,|\s*[-–]|\s{2}|$)",
    ]
]


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class WebsiteAuditResult:
    domain: str = ""
    company_name: str = ""
    product_description: str = ""

    business_model: str = "unknown"    # b2b | b2c | both | unknown
    saas_signals: List[str] = field(default_factory=list)
    pricing_exists: bool = False
    demo_or_trial_exists: bool = False
    signup_exists: bool = False
    careers_exists: bool = False
    contact_email: str = ""
    social_links: List[str] = field(default_factory=list)
    tech_stack_hints: List[str] = field(default_factory=list)
    team_signals: bool = False
    last_activity_hint: str = ""

    # Location / country signals (NEW)
    location_signals: List[str] = field(default_factory=list)   # raw extracted phrases
    country_detected: str = ""                                   # best-guess country

    trust_signals: List[str] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)
    pages_visited: List[str] = field(default_factory=list)
    raw_text_snippet: str = ""         # first 500 chars from homepage
    homepage_fetched: bool = False

    audit_ms: int = 0
    error: str = ""

    def has_substance(self) -> bool:
        """Return True if the website looks like a real business."""
        if "parked" in self.red_flags or "no_product_signal" in self.red_flags:
            return False
        return self.pricing_exists or self.demo_or_trial_exists or self.signup_exists or \
               bool(self.saas_signals) or self.careers_exists

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain":               self.domain,
            "company_name":         self.company_name,
            "product_description":  self.product_description,
            "business_model":       self.business_model,
            "saas_signals":         self.saas_signals,
            "pricing_exists":       self.pricing_exists,
            "demo_or_trial_exists": self.demo_or_trial_exists,
            "signup_exists":        self.signup_exists,
            "careers_exists":       self.careers_exists,
            "contact_email":        self.contact_email,
            "social_links":         self.social_links,
            "tech_stack_hints":     self.tech_stack_hints,
            "team_signals":         self.team_signals,
            "last_activity_hint":   self.last_activity_hint,
            "location_signals":     self.location_signals,
            "country_detected":     self.country_detected,
            "trust_signals":        self.trust_signals,
            "red_flags":            self.red_flags,
            "pages_visited":        self.pages_visited,
            "homepage_fetched":     self.homepage_fetched,
            "audit_ms":             self.audit_ms,
        }


# ── Auditor ───────────────────────────────────────────────────────────────────

class WebsiteAuditor:
    """
    Fetches and analyses a company website.
    Thread-safe; create one instance per app or per request.
    """

    def __init__(self, timeout: int = _TIMEOUT, max_pages: int = _MAX_PAGES) -> None:
        self._timeout  = timeout
        self._max_pages = max_pages

    def audit(self, website: str, domain: str = "") -> WebsiteAuditResult:
        """
        Run a full website audit.

        Args:
            website: Full URL (https://...) or bare domain.
            domain:  Fallback domain if website is not a full URL.

        Returns:
            WebsiteAuditResult with all extracted signals.
        """
        t0 = time.monotonic()
        result = WebsiteAuditResult()

        # Normalise the base URL
        base_url = self._normalise_url(website or domain)
        if not base_url:
            result.error = "no_url"
            return result

        parsed = urlparse(base_url)
        result.domain = parsed.netloc.lower().replace("www.", "")

        # Trust signal: HTTPS
        if base_url.startswith("https://"):
            result.trust_signals.append("ssl")

        # Fetch pages in priority order, respecting max_pages budget
        pages_fetched = 0
        seen_types: set = set()
        full_text = ""

        for path, page_type in _PAGE_PRIORITY:
            if pages_fetched >= self._max_pages:
                break
            if page_type in seen_types and page_type != "homepage":
                continue

            url = urljoin(base_url, path) if path != "/" else base_url
            html, text = self._fetch(url)
            if not text:
                continue

            pages_fetched += 1
            seen_types.add(page_type)
            result.pages_visited.append(url)
            full_text += " " + text[:_MAX_CONTENT]

            if page_type == "homepage":
                result.homepage_fetched = True
                result.raw_text_snippet = text[:500]
                result.tech_stack_hints = self._detect_tech_stack(html)
                self._extract_company_name(text, result)
                self._extract_product_description(text, result)
                # Detect saas signals from links in homepage HTML
                self._detect_saas_links(html, result)

            elif page_type == "pricing":
                result.pricing_exists = True
                result.saas_signals.append("pricing_page")

            elif page_type == "about":
                if re.search(r"\b(our\s+team|meet\s+the\s+team|founders?)\b", text, re.I):
                    result.team_signals = True

            elif page_type == "product":
                result.saas_signals.append("product_page")

            elif page_type == "careers":
                result.careers_exists = True
                result.saas_signals.append("careers_page")

            elif page_type == "blog":
                dates = _BLOG_DATE_PATTERN.findall(text)
                if dates:
                    result.last_activity_hint = dates[0] if dates else ""
                    result.trust_signals.append("blog_active")

        # Analyse full combined text
        if full_text:
            self._classify_business_model(full_text, result)
            self._detect_pricing_signals(full_text, result)
            self._extract_contact_email(full_text, result)
            self._extract_social_links(full_text, result)
            self._detect_red_flags(full_text, result)
            self._extract_location_signals(full_text, result)

        # Derive trust signals
        if result.pricing_exists or result.demo_or_trial_exists:
            result.trust_signals.append("conversion_signals")
        if result.contact_email:
            result.trust_signals.append("has_contact_email")
        if result.careers_exists:
            result.trust_signals.append("hiring_signals")

        result.audit_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "[website_auditor] %s — model=%s pricing=%s demo=%s pages=%d in %dms",
            result.domain, result.business_model, result.pricing_exists,
            result.demo_or_trial_exists, pages_fetched, result.audit_ms,
        )
        return result

    # ------------------------------------------------------------------
    # Page fetching
    # ------------------------------------------------------------------

    def _fetch(self, url: str):
        """Fetch URL, return (raw_html: str, plain_text: str).
        Returns ('', '') on any failure."""
        try:
            import requests
            resp = requests.get(
                url, headers=_HEADERS, timeout=self._timeout,
                allow_redirects=True,
            )
            if resp.status_code >= 400:
                return "", ""
            html = resp.text[:_MAX_CONTENT * 2]
            text = self._html_to_text(html)
            return html, text
        except Exception as exc:
            logger.debug("[website_auditor] fetch %s failed: %s", url, exc)
            return "", ""

    @staticmethod
    def _html_to_text(html: str) -> str:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "meta", "link", "noscript"]):
                tag.decompose()
            return " ".join(soup.get_text(separator=" ").split())
        except Exception:
            # Fallback: strip HTML tags with regex
            return re.sub(r"<[^>]+>", " ", html)

    # ------------------------------------------------------------------
    # Signal extractors
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_url(url: str) -> str:
        url = url.strip()
        if not url:
            return ""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    @staticmethod
    def _detect_tech_stack(html: str) -> List[str]:
        found = []
        for tool, pat in _TECH_STACK_PATTERNS.items():
            if pat.search(html):
                found.append(tool)
        return found

    @staticmethod
    def _detect_saas_links(html: str, result: WebsiteAuditResult) -> None:
        links = re.findall(r'href=["\']([^"\']+)["\']', html, re.I)
        for link in links:
            path = urlparse(link).path.lower().rstrip("/")
            if path in _SAAS_PAGE_HINTS:
                if path not in result.saas_signals:
                    result.saas_signals.append(path)
                if "/demo" in path or "/book" in path:
                    result.demo_or_trial_exists = True
                if "/signup" in path or "/sign-up" in path or "/free-trial" in path:
                    result.signup_exists = True

    @staticmethod
    def _extract_company_name(text: str, result: WebsiteAuditResult) -> None:
        # Heuristic: first capitalised phrase in the first 300 chars
        m = re.search(r'\b([A-Z][a-zA-Z0-9&\s\-]{2,40}(?:Inc\.?|Ltd\.?|LLC|Corp\.?|GmbH|SaaS|AI|Technologies?|Solutions?|Platform)?)\b', text[:300])
        if m:
            result.company_name = m.group(1).strip()

    @staticmethod
    def _extract_product_description(text: str, result: WebsiteAuditResult) -> None:
        # Try to grab the hero / tagline (first meaningful sentence ≤ 200 chars)
        sentences = re.split(r'(?<=[.!?])\s+', text[:1000])
        for s in sentences:
            s = s.strip()
            if 20 < len(s) < 200 and re.search(r'[a-zA-Z]{4,}', s):
                result.product_description = s
                break

    @staticmethod
    def _classify_business_model(text: str, result: WebsiteAuditResult) -> None:
        b2b_hits = sum(1 for p in _B2B_SIGNALS if p.search(text))
        b2c_hits = sum(1 for p in _B2C_SIGNALS if p.search(text))
        if b2b_hits > 0 and b2c_hits == 0:
            result.business_model = "b2b"
        elif b2c_hits > 0 and b2b_hits == 0:
            result.business_model = "b2c"
        elif b2b_hits > 0 and b2c_hits > 0:
            result.business_model = "both"

    @staticmethod
    def _detect_pricing_signals(text: str, result: WebsiteAuditResult) -> None:
        for pat in _PRICING_SIGNALS:
            if pat.search(text):
                result.pricing_exists = True
                break
        if re.search(r"\b(book\s+a\s+demo|request\s+demo|schedule\s+demo|free\s+trial|start\s+free)\b", text, re.I):
            result.demo_or_trial_exists = True
        if re.search(r"\b(sign\s+up|create\s+(an?\s+)?account|get\s+started\s+free)\b", text, re.I):
            result.signup_exists = True

    @staticmethod
    def _extract_contact_email(text: str, result: WebsiteAuditResult) -> None:
        if result.contact_email:
            return
        _free = _FREE_EMAIL_DOMAINS = frozenset({
            "gmail.com","yahoo.com","hotmail.com","outlook.com",
        })
        for m in _EMAIL_PATTERN.finditer(text):
            email = m.group(0).lower()
            domain = email.split("@")[-1]
            if domain not in _free:
                result.contact_email = email
                return
        # Accept free email as last resort
        for m in _EMAIL_PATTERN.finditer(text):
            result.contact_email = m.group(0).lower()
            return

    @staticmethod
    def _extract_social_links(text: str, result: WebsiteAuditResult) -> None:
        for platform, pat in _SOCIAL_PATTERNS.items():
            m = pat.search(text)
            if m:
                url = "https://" + m.group(0)
                if url not in result.social_links:
                    result.social_links.append(url)

    @staticmethod
    def _extract_location_signals(text: str, result: WebsiteAuditResult) -> None:
        """Extract location/country phrases from the full website text."""
        seen: set = set()
        for pat in _LOCATION_IN_TEXT_PATTERNS:
            for m in pat.finditer(text[:8000]):
                phrase = m.group(1).strip().rstrip(".,;")
                if phrase and phrase.lower() not in seen and len(phrase) > 2:
                    seen.add(phrase.lower())
                    result.location_signals.append(phrase)

        # Also detect TLD-based country from domain
        domain_lower = result.domain.lower()
        from app.intelligence.user_intent_contract import _TLD_COUNTRY as _TLD_MAP
        for tld, country in _TLD_MAP:
            if domain_lower.endswith(tld):
                if country not in result.location_signals:
                    result.location_signals.append(country)
                result.country_detected = country
                break

    @staticmethod
    def _detect_red_flags(text: str, result: WebsiteAuditResult) -> None:
        from app.intelligence.anti_junk_engine import _PARKED_PATTERNS
        for pat in _PARKED_PATTERNS:
            if pat.search(text):
                result.red_flags.append("parked")
                return

        if not re.search(r"\b(product|solution|platform|features?|service)\b", text, re.I):
            result.red_flags.append("no_product_signal")

        if not re.search(r"\b(about|team|founded|our\s+story|mission)\b", text, re.I):
            result.red_flags.append("no_about_signal")

        if not re.search(r"\b(contact|reach\s+us|email\s+us|sales@|support@|hello@)\b", text, re.I):
            result.red_flags.append("no_contact_signal")

        if re.search(r"\b(powered\s+by\s+wix|powered\s+by\s+weebly|this\s+site\s+was\s+made\s+with)\b", text, re.I):
            result.red_flags.append("free_website_builder")


# Standalone usage
_FREE_EMAIL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
})


def audit_website(website: str, domain: str = "") -> WebsiteAuditResult:
    """Module-level convenience function."""
    return WebsiteAuditor().audit(website, domain=domain)
