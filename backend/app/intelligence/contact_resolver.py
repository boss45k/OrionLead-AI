"""
Contact Resolver
================
Finds and validates the best contact(s) for a company that has ALREADY
passed all intelligence checks.

IMPORTANT: This module must only be called AFTER a company's AccountScoreResult
shows passed=True.  Running contact resolution before company validation
defeats the purpose of company-first collection.

Contact priority
----------------
  1. Founder / Co-Founder
  2. CEO / Managing Director
  3. CTO / CPO / COO
  4. Head of Growth / VP Growth
  5. Head of Sales / VP Sales
  6. Marketing Lead / CMO
  7. General manager / any named senior person

Sources used (in order, cost-aware)
-------------------------------------
  a. Lead data_points that already contain contact info
  b. Website contact page scrape (already in WebsiteAuditResult)
  c. Hunter.io domain search (if API key configured)
  d. Apollo.io people search (if API key configured)

Rejection rules (contacts)
---------------------------
  - No real name (length < 3, numbers only, looks like company name)
  - Title not relevant (intern, junior without senior qualifier, admin assistant)
  - Profile belongs to a different company domain
  - Generic free email only with no verified domain match
  - Name equals company name exactly
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Title priority ────────────────────────────────────────────────────────────

_PRIORITY_TITLES = [
    (1, ["founder", "co-founder", "cofounder"]),
    (2, ["ceo", "chief executive", "managing director", "md", "president"]),
    (3, ["cto", "chief technology", "cpo", "chief product", "coo", "chief operating"]),
    (4, ["head of growth", "vp growth", "vp of growth", "growth lead"]),
    (5, ["head of sales", "vp sales", "vp of sales", "chief revenue", "cro"]),
    (6, ["cmo", "head of marketing", "vp marketing", "marketing director"]),
    (7, ["general manager", "director", "partner", "principal"]),
]

_IRRELEVANT_TITLES = frozenset({
    "intern", "junior", "assistant", "receptionist", "secretary",
    "student", "trainee", "apprentice", "coordinator",
    "data entry", "clerk", "admin", "front desk",
})

_GENERIC_ROLES = frozenset({
    "employee", "staff", "team member", "member", "user",
    "contact", "info", "support", "sales", "hello", "enquiries",
})

_FREE_EMAIL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "aol.com", "icloud.com", "protonmail.com", "mail.com",
    "live.com", "msn.com",
})


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ResolvedContact:
    name: str = ""
    email: str = ""
    phone: str = ""
    title: str = ""
    linkedin_url: str = ""
    source: str = ""            # 'lead_data' | 'website' | 'hunter' | 'apollo'
    title_priority: int = 99    # lower = more senior
    email_verified: bool = False
    rejection_reason: str = ""  # non-empty if contact was rejected
    confidence: float = 0.0     # 0.0-1.0

    @property
    def is_valid(self) -> bool:
        return not self.rejection_reason and bool(self.name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":            self.name,
            "email":           self.email,
            "phone":           self.phone,
            "title":           self.title,
            "linkedin_url":    self.linkedin_url,
            "source":          self.source,
            "title_priority":  self.title_priority,
            "email_verified":  self.email_verified,
            "confidence":      round(self.confidence, 2),
        }


@dataclass
class ContactResolutionResult:
    best_contact: Optional[ResolvedContact] = None
    all_candidates: List[ResolvedContact] = field(default_factory=list)
    rejected_contacts: List[ResolvedContact] = field(default_factory=list)
    resolution_ms: int = 0
    sources_tried: List[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.best_contact is not None and self.best_contact.is_valid

    def to_dict(self) -> Dict[str, Any]:
        return {
            "found":            self.found,
            "best_contact":     self.best_contact.to_dict() if self.best_contact else None,
            "sources_tried":    self.sources_tried,
            "n_candidates":     len(self.all_candidates),
            "n_rejected":       len(self.rejected_contacts),
            "resolution_ms":    self.resolution_ms,
        }


# ── Resolver ──────────────────────────────────────────────────────────────────

class ContactResolver:
    """
    Finds the best contact for a company that has passed intelligence checks.
    Thread-safe; instantiate once and reuse.
    """

    def __init__(
        self,
        use_hunter: bool = True,
        use_apollo: bool = True,
        max_contacts: int = 5,
    ) -> None:
        self._use_hunter  = use_hunter
        self._use_apollo  = use_apollo
        self._max_contacts = max_contacts

    def resolve(
        self,
        lead: Dict[str, Any],
        domain: str,
        website_audit: Optional[Any] = None,   # WebsiteAuditResult
    ) -> ContactResolutionResult:
        """
        Find the best contact for the given company/domain.

        Args:
            lead:          Lead dict — may already contain name/email/title
                           from earlier collection stages.
            domain:        Verified company domain (e.g. "acme.io")
            website_audit: Optional WebsiteAuditResult for email hints.

        Returns:
            ContactResolutionResult
        """
        import time
        t0 = time.monotonic()
        result = ContactResolutionResult()
        candidates: List[ResolvedContact] = []

        # ── Source a: existing lead data ───────────────────────────────────────
        result.sources_tried.append("lead_data")
        existing = self._from_lead_data(lead, domain)
        if existing:
            candidates.extend(existing)

        # ── Source b: website contact email ───────────────────────────────────
        if website_audit and website_audit.contact_email:
            result.sources_tried.append("website_scrape")
            site_contact = ResolvedContact(
                name=lead.get("company") or "Contact",
                email=website_audit.contact_email,
                source="website",
                title="",
                confidence=0.5,
            )
            candidates.append(site_contact)

        # ── Source c-pre: Serper domain discovery when no website/domain known ──
        if self._use_hunter and not domain:
            company_name = (lead.get("company") or "").strip()
            country = (lead.get("country") or "").strip()
            if company_name:
                try:
                    import os, requests as _req
                    _key = os.environ.get('SERPER_API_KEY', '')
                    if _key:
                        _q = f'"{company_name}" official website' + (f' {country}' if country else '')
                        _sr = _req.post(
                            'https://google.serper.dev/search',
                            headers={'X-API-KEY': _key, 'Content-Type': 'application/json'},
                            json={'q': _q, 'num': 3},
                            verify=False, timeout=6,
                        )
                        if _sr.ok:
                            from urllib.parse import urlparse as _up
                            for _r in _sr.json().get('organic', []):
                                _lnk = _r.get('link', '')
                                if not _lnk or any(x in _lnk for x in ('linkedin', 'facebook', 'twitter', 'instagram', 'youtube', 'wikipedia', 'clutch', 'crunchbase')):
                                    continue
                                _d = _up(_lnk).netloc.replace('www.', '').split(':')[0]
                                if _d and '.' in _d:
                                    domain = _d
                                    if not lead.get('website'):
                                        lead['website'] = f'https://{_d}'
                                    result.sources_tried.append("serper_domain_discovery")
                                    break
                except Exception:
                    pass

        # ── Source c: Hunter.io domain search ─────────────────────────────────
        if self._use_hunter and domain and len(candidates) < self._max_contacts:
            result.sources_tried.append("hunter")
            hunter_contacts = self._hunter_search(domain, lead.get("company") or "")
            candidates.extend(hunter_contacts)

        # ── Source d: Apollo people search ────────────────────────────────────
        if self._use_apollo and domain and len(candidates) < self._max_contacts:
            result.sources_tried.append("apollo")
            apollo_contacts = self._apollo_search(domain, lead.get("company") or "")
            candidates.extend(apollo_contacts)

        # ── Validate and rank contacts ─────────────────────────────────────────
        valid: List[ResolvedContact] = []
        rejected: List[ResolvedContact] = []

        for c in candidates:
            reason = self._validate_contact(c, domain)
            if reason:
                c.rejection_reason = reason
                rejected.append(c)
            else:
                valid.append(c)

        valid.sort(key=lambda c: (c.title_priority, -c.confidence))

        result.all_candidates    = valid
        result.rejected_contacts = rejected
        result.best_contact      = valid[0] if valid else None
        result.resolution_ms     = int((time.monotonic() - t0) * 1000)

        if result.found:
            bc = result.best_contact
            logger.info(
                "[contact_resolver] %s — found %s <%s> priority=%d via %s",
                domain, bc.name, bc.email or "no-email",
                bc.title_priority, bc.source,
            )
        else:
            logger.info(
                "[contact_resolver] %s — no valid contact found "
                "(%d candidates, %d rejected)",
                domain, len(candidates), len(rejected),
            )

        return result

    # ------------------------------------------------------------------
    # Source extractors
    # ------------------------------------------------------------------

    def _from_lead_data(self, lead: Dict[str, Any], domain: str) -> List[ResolvedContact]:
        name  = (lead.get("name") or "").strip()
        email = (lead.get("email") or "").strip().lower()
        phone = (lead.get("phone") or "").strip()
        title = (lead.get("position") or lead.get("title") or "").strip()
        linkedin = (lead.get("linkedin_url") or "").strip()

        if not name:
            return []

        c = ResolvedContact(
            name=name,
            email=email,
            phone=phone,
            title=title,
            linkedin_url=linkedin,
            source="lead_data",
            confidence=0.7,
        )
        c.title_priority = self._title_priority(title)
        return [c]

    def _hunter_search(self, domain: str, company: str) -> List[ResolvedContact]:
        try:
            from app.services.hunter_service import HunterService
            hunter = HunterService()
            contacts = hunter.domain_search(domain, limit=5)
            if not contacts:
                return []

            result = []
            for c_dict in contacts:
                name  = f"{c_dict.get('first_name','')} {c_dict.get('last_name','')}".strip()
                email = (c_dict.get("email") or "").lower()
                title = c_dict.get("position") or c_dict.get("title") or ""
                contact = ResolvedContact(
                    name=name,
                    email=email,
                    title=title,
                    source="hunter",
                    confidence=0.75,
                )
                contact.title_priority = self._title_priority(title)
                result.append(contact)
            return result

        except Exception as exc:
            logger.debug("[contact_resolver] Hunter search failed: %s", exc)
            return []

    def _apollo_search(self, domain: str, company: str) -> List[ResolvedContact]:
        try:
            from app.services.apollo_service import ApolloService
            apollo = ApolloService()
            contacts = apollo.search_people(domain=domain, company=company, limit=5)
            if not contacts:
                return []

            result = []
            for c_dict in contacts:
                name  = (c_dict.get("name") or "").strip()
                email = (c_dict.get("email") or "").lower()
                title = c_dict.get("title") or c_dict.get("position") or ""
                linkedin = c_dict.get("linkedin_url") or ""
                contact = ResolvedContact(
                    name=name,
                    email=email,
                    title=title,
                    linkedin_url=linkedin,
                    source="apollo",
                    confidence=0.70,
                )
                contact.title_priority = self._title_priority(title)
                result.append(contact)
            return result

        except Exception as exc:
            logger.debug("[contact_resolver] Apollo search failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_contact(self, contact: ResolvedContact, domain: str) -> str:
        """Return rejection reason string, or '' if valid."""
        name  = contact.name.strip()
        email = contact.email.strip().lower()
        title = contact.title.strip().lower()

        # Must have a real name
        if len(name) < 3:
            return "name_too_short"
        if re.match(r'^[\d\s]+$', name):
            return "name_is_numbers_only"
        if not re.search(r'[a-zA-Z]{2,}', name):
            return "name_has_no_alpha"

        # Name must not match the company domain
        company_slug = domain.split(".")[0].lower()
        if name.lower() == company_slug or name.lower() in _GENERIC_ROLES:
            return "name_equals_company_or_generic"

        # Title check
        if title:
            if any(t in title for t in _IRRELEVANT_TITLES):
                return f"irrelevant_title ({title})"

        # Email domain must match company domain (or be empty — phone-only lead)
        if email and "@" in email:
            email_domain = email.split("@")[-1]
            if email_domain in _FREE_EMAIL_DOMAINS:
                if not contact.phone:
                    return "free_email_no_phone"
            elif domain and email_domain != domain:
                # Allow subdomains: m.acme.com / us.acme.com
                if not email_domain.endswith("." + domain) and not domain.endswith("." + email_domain):
                    return f"email_domain_mismatch ({email_domain} ≠ {domain})"

        return ""

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _title_priority(title: str) -> int:
        """Return 1 (highest) to 99 (unknown) for a job title."""
        t = title.lower()
        for priority, keywords in _PRIORITY_TITLES:
            if any(kw in t for kw in keywords):
                return priority
        return 99


# ── Singleton ─────────────────────────────────────────────────────────────────

_resolver: Optional[ContactResolver] = None


def get_contact_resolver() -> ContactResolver:
    global _resolver
    if _resolver is None:
        _resolver = ContactResolver()
    return _resolver
