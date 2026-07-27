"""
Anti-Junk Engine
================
Hard-reject rules for companies that are NOT real business prospects.
Any rule hit returns False immediately — no partial scores.

Rejects:
  • Company name is a URL or @handle
  • Company name looks like a person's full name (person-as-company)
  • Company name is generic / empty / too short
  • Company name equals contact person's name
  • Company name contains multiple concatenated person names
  • Domain resolves to a social profile page
  • Website is a known directory/listing/aggregator
  • Website is parked or under construction
  • No product/service page signals
  • No about/contact/pricing/sign-up signal
  • Company is university, NGO, government, ministry, or news-media brand
  • Company has generic free-email only (Gmail/Yahoo) and no business domain
  • Scraped page is a LinkedIn search result, Crunchbase list, Apollo page, or article listing

Returns an AntiJunkResult with:
  passed:           True if the company survived all checks
  rejection_reason: first failing rule key (empty if passed)
  junk_signals:     all triggered junk signals (for audit log)
  junk_score:       0-100 where 100 = definitely junk, 0 = totally clean
  evidence:         list of EvidenceItem for audit trail
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── Company identity patterns ─────────────────────────────────────────────────

# Detects "FirstName LastName" (2-3 capitalized words, no corporate suffix)
_PERSON_NAME_PATTERN = re.compile(
    r'^([A-Z][a-z]{1,20})\s+(?:([A-Z][a-z]{0,5})\s+)?([A-Z][a-z]{1,20})$'
)

# Corporate suffixes that prove it IS a real company (exempts person-name check)
_CORPORATE_SUFFIXES = frozenset({
    "inc", "inc.", "ltd", "ltd.", "llc", "corp", "corp.", "limited",
    "gmbh", "bv", "sas", "sarl", "ag", "plc", "pty", "pvt", "co.",
    "technologies", "technology", "tech", "solutions", "software", "systems",
    "services", "consulting", "group", "holdings", "ventures", "capital",
    "labs", "lab", "studio", "studios", "digital", "global", "international",
    "africa", "platform", "platforms", "cloud", "ai", "io", "hub", "app",
    "analytics", "data", "networks", "network", "media", "agency",
})

# Generic / filler company names that convey no real business identity
_GENERIC_COMPANY_NAMES = frozenset({
    "company", "business", "enterprise", "organization", "organisation",
    "startup", "the company", "my company", "test company", "test business",
    "n/a", "na", "none", "unknown", "untitled", "no company", "not applicable",
    "various", "multiple", "other", "others", "client", "account", "lead",
})

# ── Known junk domains / aggregators ─────────────────────────────────────────

_DIRECTORY_DOMAINS = frozenset({
    # Lead aggregators / databases
    "clutch.co", "g2.com", "capterra.com", "trustpilot.com", "getapp.com",
    "softwareadvice.com", "crozdesk.com", "sourceforge.net",
    "producthunt.com", "alternativeto.net", "slashdot.org",
    # Funding / company data
    "crunchbase.com", "pitchbook.com", "angellist.com", "apollo.io",
    "zoominfo.com", "clearbit.com", "lusha.com", "seamless.ai",
    "leadiq.com", "hunter.io", "rocketreach.com", "snov.io",
    # Job boards used as company source
    "linkedin.com", "glassdoor.com", "indeed.com", "monster.com",
    "ziprecruiter.com", "lever.co", "greenhouse.io", "workable.com",
    # Article / blog aggregators
    "medium.com", "substack.com", "hashnode.dev", "dev.to",
    "techcrunch.com", "forbes.com", "businessinsider.com",
    "entrepreneur.com", "inc.com", "wired.com", "venturebeat.com",
    # Marketplaces
    "fiverr.com", "upwork.com", "freelancer.com", "toptal.com",
    "guru.com", "99designs.com",
    # E-commerce platforms (company IS the platform)
    "shopify.com", "etsy.com", "amazon.com", "ebay.com",
    # Social networks (profile-only source)
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "youtube.com", "tiktok.com", "reddit.com", "telegram.org",
    "t.me", "wa.me",
    # Parked / page builders (not the company's own site)
    "godaddy.com", "namecheap.com", "bluehost.com", "siteground.com",
    "hostgator.com", "wix.com", "weebly.com", "squarespace.com",
    "wordpress.com", "blogspot.com", "webflow.io",
})

_SOCIAL_PROFILE_PREFIXES = (
    "linkedin.com/in/",
    "linkedin.com/company/",
    "linkedin.com/pub/",
    "twitter.com/",
    "x.com/",
    "facebook.com/",
    "instagram.com/",
)

_FREE_EMAIL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "protonmail.com", "mail.com", "yandex.com",
    "live.com", "msn.com", "me.com", "zoho.com", "gmx.com",
})

# ── Keyword-based hard rejects ────────────────────────────────────────────────

_NON_COMMERCIAL_PATTERNS = [
    re.compile(p, re.I) for p in [
        # Education
        r"\buniversity\b", r"\buniversiti\b", r"\bcollege\b",
        r"\bschool\s+of\b", r"\binstitute\s+of\b",
        r"\bacademy\b(?!.*software)(?!.*ai)",
        r"\bfaculty\s+of\b",
        # Government / Ministry
        r"\bministry\s+of\b", r"\bdepartment\s+of\b", r"\bgovernment\s+of\b",
        r"\bmunicipality\b", r"\bcouncil\s+of\b", r"\bparliament\b",
        r"\bembassy\b", r"\bconsulate\b", r"\bauthority\b.*govern",
        # NGO / Non-profit
        r"\bfoundation\b(?!.*software)(?!.*tech)",
        r"\bnon.?profit\b", r"\bcharity\b", r"\bngo\b",
        r"\bhumanitarian\b", r"\baid\s+organization\b",
        # Religious
        r"\bchurch\s+of\b", r"\bmasjid\b", r"\bmosque\b",
        r"\btemple\s+of\b",
        # Research-only
        r"\bresearch\s+center\b", r"\bresearch\s+institute\b",
        r"\blaboratory\b(?!.*software)(?!.*tech)",
    ]
]

# Company field is actually a job title or hiring status, not a company name
_JOB_TITLE_AS_COMPANY_PATTERNS = [
    re.compile(p, re.I) for p in [
        # Recruiting / hiring language in company field
        r"we'?re\s+hiring",
        r"open\s+to\s+(work|opportunities)",
        r"looking\s+for\s+(new\s+)?opportunities",
        r"\b(seeking|available\s+for|freelance\s+available)\b",
        # Pure job title with no company suffix  (e.g. "Owner", "CEO at XYZ", "Head of Sales")
        r"^(owner|ceo|cto|cmo|cfo|coo|vp|svp|evp|president|founder|co.?founder|"
        r"managing\s+director|general\s+manager|head\s+of|director\s+of|"
        r"manager|engineer|developer|designer|consultant|freelancer|contractor)"
        r"(\s+at\b|\s+[@&]\b|\s*[-|]\s*|\s*$)",
        # LinkedIn status strings
        r"\(?(available|open|seeking|looking).{0,30}\)$",
        r"\bopen\s+to\s+work\b",
    ]
]

# Page title / content patterns that indicate a LISTING, not a company
_LISTING_CONTENT_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\btop\s+\d+\s+\w+\s+companies\b",
        r"\bbest\s+\w+\s+companies\s+in\b",
        r"\blist\s+of\s+\w+\s+companies\b",
        r"\b\d+\s+best\s+\w+\b",
        r"\bcompany\s+directory\b",
        r"\bbusiness\s+directory\b",
        r"\byellow\s*pages\b",
        r"\bfind\s+companies\b",
        r"\bsearch\s+companies\b",
        r"\bcompare\s+\w+\s+software\b",
        r"\bsoftware\s+comparison\b",
        r"\breviews?\s+and\s+ratings?\b",
        r"\bwrite\s+a\s+review\b",
    ]
]

# Parked-domain indicators in page text
_PARKED_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"domain\s*(for\s*sale|is\s*for\s*sale)",
        r"this\s*domain\s*is\s*parked",
        r"buy\s*this\s*domain",
        r"coming\s*soon",
        r"under\s*construction",
        r"parking\s*page",
        r"sedoparking",
        r"domainparking",
        r"register\s*your\s*domain",
    ]
]

# URL patterns that identify aggregator/listing pages
_AGGREGATOR_URL_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"/companies/",
        r"/directory/",
        r"/listings/",
        r"/providers/",
        r"/vendors/",
        r"/top-\d+",
        r"/best-\d+",
        r"/compare/",
        r"/reviews/\w+/competitors",
        r"[?&](query|q|search|keyword)=",
    ]
]


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class AntiJunkResult:
    passed: bool
    rejection_reason: str = ""
    junk_signals: List[str] = field(default_factory=list)
    junk_score: int = 0        # 0 = clean, 100 = definite junk

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed":           self.passed,
            "rejection_reason": self.rejection_reason,
            "junk_signals":     self.junk_signals,
            "junk_score":       self.junk_score,
        }


# ── Engine ────────────────────────────────────────────────────────────────────

class AntiJunkEngine:
    """
    Stateless hard-reject engine.
    Call check(lead) for each company candidate.
    """

    def check(
        self,
        lead: Dict[str, Any],
        page_text: str = "",
        source_url: str = "",
    ) -> AntiJunkResult:
        """
        Evaluate a company candidate for junk signals.

        Args:
            lead:       Lead dict with keys: name, company, email, website,
                        domain, linkedin_url, source, data_points
            page_text:  Full scraped text from the company's website (optional)
            source_url: The URL that produced this lead (for aggregator detection)

        Returns:
            AntiJunkResult — check .passed before using the lead
        """
        signals: List[str] = []
        junk_score = 0

        name    = (lead.get("name")    or lead.get("company") or "").strip()
        company = (lead.get("company") or "").strip()
        email   = (lead.get("email")   or "").strip().lower()
        website = (lead.get("website") or "").strip()
        domain  = (lead.get("domain")  or self._extract_domain(website, email)).lower()
        source  = (lead.get("source")  or "").lower()

        # ── Hard rule 0: Fake / test / demo / placeholder lead ───────────────────
        try:
            from app.validation.fake_lead_detector import detect_fake_lead
            _fake = detect_fake_lead(lead)
            if _fake.is_fake:
                if _fake.severity == "hard":
                    return self._reject(_fake.reason, signals, 100)
                else:  # soft — let accumulated junk_score decide
                    signals.append(_fake.reason)
                    junk_score += 50
        except Exception:
            pass  # fail-open: never block real leads if detector import fails

        # ── Hard rule 1: name is a URL ─────────────────────────────────────────
        if self._looks_like_url(name) or self._looks_like_url(company):
            return self._reject("name_is_url", signals, 100)

        # ── Hard rule 2: name is a @handle ────────────────────────────────────
        if re.match(r'^@\w', name) or re.match(r'^@\w', company):
            return self._reject("name_is_social_handle", signals, 100)

        # ── Hard rule 3: company name is empty / too short / generic ──────────
        company_clean = re.sub(r'[^a-z0-9 ]', '', company.lower()).strip()
        if len(company_clean) < 2:
            return self._reject("company_name_too_short", signals, 100)
        if company_clean in _GENERIC_COMPANY_NAMES:
            return self._reject("company_name_generic", signals, 100)

        # ── Hard rule 4: company name looks like a person's full name ─────────
        # Allow if it has a corporate suffix (e.g. "John Smith Technologies")
        if self._is_person_name(company):
            return self._reject("company_is_person_name", signals, 90)

        # ── Soft rule: company name equals contact name ───────────────────────
        contact_name = (lead.get("name") or "").strip()
        if contact_name and company and contact_name.lower() == company.lower():
            signals.append("company_equals_contact_name")
            junk_score += 10

        # ── Hard rule 6: domain is a known directory / aggregator ─────────────
        if domain and domain in _DIRECTORY_DOMAINS:
            return self._reject("domain_is_aggregator", signals, 100)

        for agg in ("crunchbase", "apollo.io", "zoominfo", "clutch.co"):
            if agg in domain:
                return self._reject("domain_is_aggregator", signals, 100)

        # ── Hard rule 7: website URL is a social profile page ─────────────────
        norm_website = website.lower().replace("https://", "").replace("http://", "")
        if any(norm_website.startswith(pfx) for pfx in _SOCIAL_PROFILE_PREFIXES):
            return self._reject("website_is_social_profile", signals, 100)

        # ── Hard rule 8: source URL is an aggregator/listing page ─────────────
        if source_url:
            for pat in _AGGREGATOR_URL_PATTERNS:
                if pat.search(source_url):
                    signals.append("source_url_is_listing_page")
                    junk_score += 30
                    break
            for agg_domain in _DIRECTORY_DOMAINS:
                if agg_domain in source_url.lower():
                    return self._reject("source_is_directory", signals, 90)

        # ── Hard rule 9: non-commercial entity (university/NGO/government) ─────
        check_text = f"{name} {company}"
        for pat in _NON_COMMERCIAL_PATTERNS:
            if pat.search(check_text):
                return self._reject("non_commercial_entity", signals, 100)

        # ── Hard rule 10: name/company is a listing title ──────────────────────
        for pat in _LISTING_CONTENT_PATTERNS:
            if pat.search(check_text):
                return self._reject("name_is_listing_title", signals, 100)

        # ── Hard rule 10b: company field is a job title or LinkedIn status ──────
        for pat in _JOB_TITLE_AS_COMPANY_PATTERNS:
            if pat.search(company):
                return self._reject("company_is_job_title_or_status", signals, 95)

        # ── Hard rule 11: page text reveals parked domain ──────────────────────
        if page_text:
            for pat in _PARKED_PATTERNS:
                if pat.search(page_text):
                    return self._reject("parked_domain", signals, 100)

        # ── Hard rule 12: page text reveals listing/directory ─────────────────
        if page_text:
            for pat in _LISTING_CONTENT_PATTERNS:
                if pat.search(page_text):
                    signals.append("page_is_listing")
                    junk_score += 20
                    break

        # ── Soft rule: no business domain (free email only) ───────────────────
        if email:
            email_domain = email.split("@")[-1] if "@" in email else ""
            if email_domain in _FREE_EMAIL_DOMAINS:
                if not domain or domain in _FREE_EMAIL_DOMAINS:
                    signals.append("free_email_only_no_business_domain")
                    junk_score += 35

        # ── Soft rule: no website at all ──────────────────────────────────────
        if not website and not domain:
            signals.append("no_website_no_domain")
            junk_score += 25

        # ── Soft rule: website lacks any business signals ─────────────────────
        if page_text:
            has_product_signal = bool(re.search(
                r"\b(pricing|plans?|features?|product|platform|solution|demo|trial|signup|sign.up|get.started)\b",
                page_text, re.I,
            ))
            has_about_signal = bool(re.search(
                r"\b(about\s+us|our\s+story|mission|team|founded|headquarters)\b",
                page_text, re.I,
            ))
            has_contact_signal = bool(re.search(
                r"\b(contact\s+us|reach\s+us|email\s+us|sales@|hello@|support@)\b",
                page_text, re.I,
            ))

            if not has_product_signal:
                signals.append("no_product_page_signal")
                junk_score += 10
            if not has_about_signal and not has_contact_signal:
                signals.append("no_about_or_contact_signal")
                junk_score += 8

        # ── Soft rule: source is from a known aggregator feed ─────────────────
        if source in ("crunchbase", "apollo", "zoominfo", "directory", "yellowpages"):
            signals.append("aggregator_source")
            junk_score += 20

        # ── Hard threshold: accumulated junk score ≥ 70 → reject ─────────────
        if junk_score >= 70:
            top_signal = signals[0] if signals else "high_junk_score"
            return self._reject(top_signal, signals, junk_score)

        passed_result = AntiJunkResult(
            passed=True,
            junk_signals=signals,
            junk_score=junk_score,
        )
        if signals:
            logger.debug(
                "[anti_junk] %s — passed with soft signals: %s (junk_score=%d)",
                company or name, signals, junk_score,
            )
        return passed_result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _reject(reason: str, signals: List[str], junk_score: int) -> AntiJunkResult:
        if reason not in signals:
            signals.append(reason)
        logger.debug("[anti_junk] REJECT reason=%s signals=%s", reason, signals)
        return AntiJunkResult(
            passed=False,
            rejection_reason=reason,
            junk_signals=signals,
            junk_score=min(100, junk_score),
        )

    @staticmethod
    def _is_person_name(company: str) -> bool:
        """Return True if company name looks like 'FirstName LastName'."""
        stripped = company.strip()
        if not stripped:
            return False
        # Check for corporate suffix — if present, it's a company not a person
        lower = stripped.lower()
        if any(lower.endswith(" " + sfx) or lower == sfx for sfx in _CORPORATE_SUFFIXES):
            return False
        # Also check if any corporate word is anywhere in the name
        words = lower.split()
        if any(w in _CORPORATE_SUFFIXES for w in words):
            return False
        return bool(_PERSON_NAME_PATTERN.match(stripped))

    @staticmethod
    def _looks_like_url(text: str) -> bool:
        if not text:
            return False
        return bool(re.match(r'^https?://', text.strip()) or
                    re.match(r'^www\.\w', text.strip()) or
                    re.search(r'\.[a-z]{2,4}(/|$)', text.strip().lower()))

    @staticmethod
    def _extract_domain(website: str, email: str) -> str:
        if website:
            try:
                h = urlparse(website).netloc.lower().replace("www.", "")
                if h:
                    return h
            except Exception:
                pass
        if email and "@" in email:
            return email.split("@")[-1].lower()
        return ""


# ── Module-level singleton ────────────────────────────────────────────────────

_engine: Optional[AntiJunkEngine] = None


def get_anti_junk_engine() -> AntiJunkEngine:
    global _engine
    if _engine is None:
        _engine = AntiJunkEngine()
    return _engine


def check_company(
    lead: Dict[str, Any],
    page_text: str = "",
    source_url: str = "",
) -> AntiJunkResult:
    """Module-level convenience wrapper."""
    return get_anti_junk_engine().check(lead, page_text=page_text, source_url=source_url)
