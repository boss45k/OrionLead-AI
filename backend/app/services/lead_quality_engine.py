"""
Lead Quality Engine
===================
Central gate for all lead quality decisions.

Every lead that enters the system passes through evaluate_lead_quality()
before being saved.  The function enforces strict rules:

  • Generated / inferred emails are NEVER counted as a contact method.
  • A lead with no verified contact method is rejected or saved as pending.
  • Source reliability is factored into the quality score.
  • Every rejected lead records the reason — nothing is silently discarded.
  • CollectionQualityReport tracks per-run statistics for all sources.

Usage
-----
    from app.services.lead_quality_engine import evaluate_lead_quality, CollectionQualityReport

    report = CollectionQualityReport(source='hunter')
    decision = evaluate_lead_quality(lead_dict, source='hunter', report=report)

    if decision.decision in ('save', 'pending'):
        save_to_db(lead_dict)
    else:
        log_rejection(lead_dict, decision.reasons)

    print(report.to_dict())
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy import — name_validator lives in the same package
try:
    from app.services.name_validator import (
        is_cdn_email as _is_cdn_email,
        is_free_email_extended as _is_free_email_extended,
        is_valid_person_name as _is_valid_person_name,
    )
    _NAME_VALIDATOR_AVAILABLE = True
except ImportError:
    _NAME_VALIDATOR_AVAILABLE = False

    def _is_cdn_email(email: str) -> bool:          # type: ignore[misc]
        return False

    def _is_free_email_extended(email: str) -> bool:  # type: ignore[misc]
        return False

    def _is_valid_person_name(name: str) -> "tuple[bool, str]":  # type: ignore[misc]
        return True, ''


# ---------------------------------------------------------------------------
# Constants — source reliability scores (0-100)
# ---------------------------------------------------------------------------

SOURCE_RELIABILITY: Dict[str, float] = {
    'hunter':               90.0,
    'hunter_api':           90.0,
    'pdl':                  85.0,
    'clearbit':             80.0,
    'apollo':               82.0,
    'explorium':            85.0,
    'crunchbase':           78.0,
    'github':               68.0,
    # Google structured sources — highest field accuracy
    'google_places':        92.0,
    'serper':               75.0,
    # Web scraping — all variants including country-suffixed forms (e.g. web_public_in)
    'news':                 60.0,
    'web':                  65.0,
    'public_web':           65.0,
    'public_web_collector': 65.0,
    'web_public':           65.0,   # used by public_web_collector (stripped of country suffix)
    'web_people':           60.0,   # person leads from web scraping
    'linkedin_search':      65.0,   # LinkedIn search results
    'linkedin':             65.0,
    'reddit':               30.0,
    'twitter':              30.0,
    'facebook':             30.0,
    'telegram':             25.0,
    'social_media':         30.0,
    'generated':             0.0,
    'inferred':              5.0,
    'unknown':              20.0,
    'manual':               88.0,   # human-entered — treat as high-reliability
}

SOCIAL_SOURCES = frozenset({'reddit', 'twitter', 'facebook', 'telegram', 'social_media'})

# Email sources that should NEVER be treated as a real contact method
GENERATED_EMAIL_SOURCES = frozenset({
    'generated', 'generated_personal', 'generated_generic',
    'inferred', 'guessed',
})

# Company field values that indicate a missing/unknown company (not a real company name)
PLACEHOLDER_COMPANIES = frozenset({'n/a', 'na', 'none', 'unknown', 'n.a.', '-', '--', 'null', 'undefined'})

# Non-B2B organization keywords — hard reject unless a named decision maker is present.
# Split into strong (education/government) and soft (associations that may buy software).
NON_B2B_STRONG_KEYWORDS = frozenset({
    'university', 'université', 'universidad', 'universidade', 'università',
    'polytechnic', 'polytechnique',
    'ministry', 'ministre', 'ministerio', 'ministério',
    'government', 'gouvernement', 'gobierno',
    'municipality', 'municipalité', 'municipio',
    'department of ', 'dept of ',
    'national institute', 'national centre', 'national center',
    'public school', 'secondary school', 'high school',
    'college of ', 'faculty of ', 'school of ',
    'hospital', 'health authority', 'health service',
    'embassy', 'consulate', 'parliament', 'senate', 'congress',
    'public library', 'national library',
})

NON_B2B_SOFT_KEYWORDS = frozenset({
    ' ngo', 'non-governmental', 'nonprofit', 'non-profit', 'charity', 'charities',
    'foundation', 'endowment', 'philanthropic',
    'association', 'society ', 'council ', 'federation ',
    'relief ', 'humanitarian',
})

# ---------------------------------------------------------------------------
# Rejection reasons
# ---------------------------------------------------------------------------

class RejectionReason:
    NO_CONTACT_METHOD      = 'no_contact_method'
    USERNAME_ONLY          = 'username_only'
    INVALID_EMAIL          = 'invalid_email'
    INVALID_PHONE          = 'invalid_phone'
    LOW_QUALITY_SOCIAL     = 'low_quality_social'
    DUPLICATE              = 'duplicate'
    SPAM_DETECTED          = 'spam_detected'
    FAKE_OR_GENERATED_EMAIL = 'fake_or_generated_email'
    MISSING_COMPANY        = 'missing_company'
    WEAK_BUSINESS_SIGNAL   = 'weak_business_signal'
    LOW_COMPLETENESS       = 'low_completeness'
    MISSING_NAME           = 'missing_name'
    CDN_TRACKER_EMAIL      = 'cdn_tracker_email'
    URL_AS_NAME            = 'url_as_name'
    PAGE_TITLE_AS_NAME     = 'page_title_as_name'
    NON_B2B_ORGANIZATION   = 'non_b2b_organization'


# ---------------------------------------------------------------------------
# Quality tiers
# ---------------------------------------------------------------------------

class QualityTier:
    HIGH_QUALITY = 'high_quality'   # ≥ 80  — verified personal email + company + name
    QUALIFIED    = 'qualified'       # ≥ 60  — strong data, actionable
    PENDING      = 'pending'         # ≥ 35  — worth enriching
    LOW_QUALITY  = 'low_quality'     # ≥ 15  — stored but flagged
    REJECTED     = 'rejected'        # < 15 or hard rule violation


# ---------------------------------------------------------------------------
# Free / generic email helpers
# ---------------------------------------------------------------------------

FREE_EMAIL_DOMAINS = frozenset({
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com',
    'aol.com', 'msn.com', 'icloud.com', 'protonmail.com', 'proton.me',
    'zoho.com', 'mail.com', 'gmx.com', 'gmx.net', 'yandex.com',
    'yandex.ru', 'tutanota.com', 'fastmail.com', 'hey.com',
})

GENERIC_LOCAL_PARTS = frozenset({
    'info', 'contact', 'hello', 'support', 'sales', 'admin', 'team',
    'business', 'inquiry', 'inquiries', 'enquiry', 'enquiries', 'help',
    'feedback', 'service', 'office', 'general', 'mail', 'reception',
    'marketing', 'press', 'media', 'hr', 'jobs', 'careers', 'billing',
    'accounts', 'customerservice', 'cs', 'newsletter', 'subscriptions',
    'subscribe', 'editor', 'newsroom', 'communications', 'webmaster',
    'noreply', 'no-reply', 'donotreply', 'bounce', 'unsubscribe',
    'contacto', 'ventas', 'hola', 'atencion', 'notifications', 'automated',
    'system', 'robot', 'alerts', 'updates', 'digest', 'postmaster',
    'mailer-daemon', 'sales-team', 'hello-team', 'reach', 'enquire',
    'enquiries', 'getintouch', 'get-in-touch', 'contactus',
})

_EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9][a-zA-Z0-9._%+\-]{0,62}@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,18}$'
)


def _is_generic_email(email: str) -> bool:
    if not email or '@' not in email:
        return False
    return email.lower().split('@')[0] in GENERIC_LOCAL_PARTS


def _is_free_email(email: str) -> bool:
    if not email or '@' not in email:
        return False
    domain = email.lower().split('@')[1]
    return domain in FREE_EMAIL_DOMAINS or _is_free_email_extended(email)


def _is_personal_business_email(email: str) -> bool:
    if not email or '@' not in email:
        return False
    return not _is_generic_email(email) and not _is_free_email(email)


def _email_is_structurally_valid(email: str) -> bool:
    if not email:
        return False
    return bool(_EMAIL_RE.match(email.strip().lower()))


# ---------------------------------------------------------------------------
# QualityDecision — return type of evaluate_lead_quality
# ---------------------------------------------------------------------------

@dataclass
class QualityDecision:
    """Result of evaluate_lead_quality."""
    decision: str               # 'save' | 'pending' | 'enrich' | 'reject'
    quality_score: float        # 0–100
    tier: str                   # QualityTier.*
    reasons: List[str]          # why this decision was made
    metadata: Dict[str, Any]    # enriched fields for data_points

    @property
    def should_save(self) -> bool:
        # 'enrich' means: save now, trigger enrichment afterwards
        return self.decision in ('save', 'pending', 'enrich')

    def to_dict(self) -> Dict[str, Any]:
        return {
            'decision':      self.decision,
            'quality_score': round(self.quality_score, 1),
            'tier':          self.tier,
            'reasons':       self.reasons,
            'metadata':      self.metadata,
        }


# ---------------------------------------------------------------------------
# Main evaluation function
# ---------------------------------------------------------------------------

def evaluate_lead_quality(
    lead: Dict[str, Any],
    source: str = 'unknown',
    *,
    report: Optional['CollectionQualityReport'] = None,
) -> QualityDecision:
    """
    Evaluate a lead's quality and decide what to do with it.

    Enforces strict rules:
      1. Generated/inferred emails are NEVER a valid contact method.
      2. A lead with no real contact method is rejected or pending (not saved as-is).
      3. Social leads face stricter thresholds.
      4. Username-only leads are always rejected.

    Args:
        lead:   The lead dict (collector output). NOT mutated here.
        source: The collector source string ('hunter', 'reddit', etc.)
        report: Optional CollectionQualityReport to track run statistics.

    Returns:
        QualityDecision
    """
    pts        = 0.0
    reasons:  List[str] = []
    metadata: Dict[str, Any] = {}
    source_key = source.lower().strip()
    # Strip trailing 2-letter country code (e.g. 'web_public_in' → 'web_public')
    _normalized_source = re.sub(r'_[a-z]{2}$', '', source_key)
    source_reliability = SOURCE_RELIABILITY.get(
        source_key,
        SOURCE_RELIABILITY.get(_normalized_source, SOURCE_RELIABILITY['unknown'])
    )
    is_social  = source_key in SOCIAL_SOURCES

    dp          = lead.get('data_points') or {}
    email_raw   = (lead.get('email') or '').strip().lower()
    email_src   = (dp.get('email_source') or '').strip().lower()
    email_verified_flag = bool(dp.get('email_verified', False))
    phone_raw   = (lead.get('phone') or '').strip()
    company_raw = (lead.get('company') or '').strip()
    name_raw    = (lead.get('name') or '').strip()
    website_raw = (lead.get('website') or '').strip()
    linkedin_raw= (lead.get('linkedin_url') or '').strip()

    # ── 0. Pre-filter: CDN/tracker emails and URL/page-title names ───────────
    #    These are always hard rejects — no scoring needed.
    if email_raw and _is_cdn_email(email_raw):
        reasons.append(RejectionReason.CDN_TRACKER_EMAIL)
        _record(report, 'reject', reasons)
        return QualityDecision(
            decision='reject', quality_score=0.0,
            tier=QualityTier.REJECTED, reasons=reasons,
            metadata={**metadata, 'cdn_email_blocked': email_raw},
        )

    if name_raw:
        _name_ok_pre, _name_reason = _is_valid_person_name(name_raw)
        if not _name_ok_pre and _name_reason in ('url_as_name', 'page_title_as_name'):
            reasons.append(
                RejectionReason.URL_AS_NAME
                if _name_reason == 'url_as_name'
                else RejectionReason.PAGE_TITLE_AS_NAME
            )
            # Don't hard-reject — clear the bad name and let the lead continue
            # (it may still have a good company + email worth enriching).
            name_raw = ''
            lead = dict(lead)       # shallow copy — don't mutate caller's dict
            lead['name'] = ''

    # ── 1. Hard rule: generated email is not a contact method ─────────────────
    email_is_generated = email_src in GENERATED_EMAIL_SOURCES
    if email_is_generated and email_raw:
        reasons.append(RejectionReason.FAKE_OR_GENERATED_EMAIL)
        metadata['generated_email_blocked'] = email_raw
        metadata['email_candidates'] = dp.get('email_candidates', [])
        # We treat this lead as if it has no email
        email_raw = ''
        email_verified_flag = False

    # ── 2. Structural email validation ───────────────────────────────────────
    email_structurally_valid = _email_is_structurally_valid(email_raw) if email_raw else False
    if email_raw and not email_structurally_valid:
        reasons.append(RejectionReason.INVALID_EMAIL)
        email_raw = ''

    # ── 3. Email scoring ──────────────────────────────────────────────────────
    email_type = 'missing'
    email_confidence = 0.0

    if email_raw:
        if _is_personal_business_email(email_raw):
            email_type = 'personal_business'
            if email_verified_flag:
                pts += 35
                email_confidence = 0.95
            else:
                # Unverified personal-looking email — partial credit only
                pts += 15
                email_confidence = 0.45
        elif _is_generic_email(email_raw):
            email_type = 'generic'
            if email_verified_flag:
                pts += 12
                email_confidence = 0.70
            else:
                # Unverified generic — boost if domain matches company website
                # (info@cctintl.com from cctintl.com is trustworthy)
                _email_domain = email_raw.split('@')[-1] if '@' in email_raw else ''
                _website_domain = (website_raw or '').lower().replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]
                _domain_match = bool(_email_domain and _website_domain and _email_domain == _website_domain)
                if _domain_match:
                    pts += 6   # domain match confirms org exists but generic = no real contact
                    email_confidence = 0.35
                else:
                    pts += 3
                    email_confidence = 0.15
        elif _is_free_email(email_raw):
            email_type = 'free'
            if email_verified_flag:
                pts += 18
                email_confidence = 0.75
            else:
                pts += 12
                email_confidence = 0.50
        else:
            email_type = 'company'
            pts += 10
            email_confidence = 0.40
    else:
        metadata['no_email'] = True

    metadata['email_type'] = email_type
    metadata['email_confidence'] = round(email_confidence, 2)
    metadata['email_verified'] = email_verified_flag
    metadata['email_source'] = email_src or source_key

    # ── 4. Phone scoring ──────────────────────────────────────────────────────
    phone_valid = _validate_phone(phone_raw)
    if phone_valid:
        pts += 15
        metadata['phone_valid'] = True
    elif phone_raw:
        reasons.append(RejectionReason.INVALID_PHONE)
        metadata['phone_valid'] = False
    else:
        metadata['phone_valid'] = False

    # ── 5. Company ────────────────────────────────────────────────────────────
    company_present = (
        bool(company_raw)
        and len(company_raw) >= 2
        and company_raw.lower() not in PLACEHOLDER_COMPANIES
    )
    if company_present:
        pts += 15
    else:
        metadata['missing_company'] = True

    # ── 6. Name (not placeholder, not username) ────────────────────────────────
    name_ok = _name_is_real(name_raw, company_raw)
    if name_ok:
        pts += 10
    else:
        if name_raw and re.match(r'^[a-z0-9_\-\.]+$', name_raw):
            reasons.append(RejectionReason.USERNAME_ONLY)
        elif not name_raw:
            reasons.append(RejectionReason.MISSING_NAME)

    # ── 6b. Non-B2B organization filter ──────────────────────────────────────
    # Universities, government ministries, charities, NGOs are not B2B prospects.
    # Hard-reject if no named decision maker; apply heavy penalty if one is present
    # (they might still be a buyer/IT lead worth talking to).
    _company_lower = company_raw.lower() if company_raw else ''
    _is_strong_non_b2b = any(kw in _company_lower for kw in NON_B2B_STRONG_KEYWORDS)
    _is_soft_non_b2b   = (not _is_strong_non_b2b and
                          any(kw in _company_lower for kw in NON_B2B_SOFT_KEYWORDS))
    if _is_strong_non_b2b:
        reasons.append(RejectionReason.NON_B2B_ORGANIZATION)
        metadata['non_b2b_type'] = 'strong'
        if not name_ok:
            # No named person — hard reject
            _record(report, 'reject', reasons)
            return QualityDecision(
                decision='reject',
                quality_score=max(0.0, pts - 40),
                tier=QualityTier.REJECTED,
                reasons=reasons,
                metadata=metadata,
            )
        else:
            # Named DM present — allow but penalize heavily
            pts = max(0.0, pts - 30)
    elif _is_soft_non_b2b:
        reasons.append(RejectionReason.NON_B2B_ORGANIZATION)
        metadata['non_b2b_type'] = 'soft'
        pts = max(0.0, pts - 15)

    # ── 7. Position ───────────────────────────────────────────────────────────
    if (lead.get('position') or '').strip():
        pts += 8

    # ── 8. Industry ──────────────────────────────────────────────────────────
    if (lead.get('industry') or '').strip():
        pts += 5

    # ── 9. Website ────────────────────────────────────────────────────────────
    if website_raw and website_raw.startswith('http'):
        pts += 5

    # ── 10. LinkedIn ─────────────────────────────────────────────────────────
    if linkedin_raw and 'linkedin.com' in linkedin_raw:
        pts += 4

    # ── 11. Location ─────────────────────────────────────────────────────────
    if (lead.get('country') or lead.get('city') or '').strip():
        pts += 3

    # ── 12. Source reliability modifier ───────────────────────────────────────
    # High-reliability sources add up to +10 bonus; low-reliability subtract
    reliability_bonus = (source_reliability - 50.0) / 50.0 * 10.0
    pts = max(0.0, pts + reliability_bonus)

    score = min(pts, 100.0)
    metadata['source_reliability_score'] = source_reliability
    metadata['enrichment_source'] = source_key

    # ── 13. Determine effective contact methods ────────────────────────────────
    has_verified_email    = bool(email_raw and email_verified_flag and email_type != 'generic')
    has_any_email         = bool(email_raw)
    has_phone             = phone_valid
    has_website           = bool(website_raw and website_raw.startswith('http'))
    has_linkedin          = bool(linkedin_raw and 'linkedin.com' in linkedin_raw)
    has_any_contact       = has_any_email or has_phone or has_website or has_linkedin

    metadata['has_verified_email']    = has_verified_email
    metadata['has_phone']             = has_phone
    metadata['company_present']       = company_present
    metadata['has_website']           = has_website

    # ── 14. Social source strict rules ────────────────────────────────────────
    if is_social:
        # Social leads must have at least one of: real email, phone, website,
        # or a LinkedIn URL with a known company (reachable via LinkedIn DM).
        social_has_substance = (
            (company_present and has_any_email) or
            has_phone or
            has_website or
            (has_linkedin and company_present)
        )
        if not social_has_substance:
            reasons.append(RejectionReason.LOW_QUALITY_SOCIAL)
            reasons.append(RejectionReason.WEAK_BUSINESS_SIGNAL)
            decision = 'reject'
            tier = QualityTier.REJECTED
            _record(report, decision, reasons)
            return QualityDecision(
                decision=decision, quality_score=score,
                tier=tier, reasons=reasons, metadata=metadata,
            )
        # Social threshold is +15 points higher than web
        qualified_threshold = 75
        pending_threshold   = 50
        low_quality_threshold = 30
    else:
        qualified_threshold   = 35   # company with domain-matched generic email scores ~34-40 pts
        pending_threshold     = 20
        low_quality_threshold = 8

    # ── 15. Hard rejection: no contact data at all ────────────────────────────
    if not has_any_contact:
        reasons.append(RejectionReason.NO_CONTACT_METHOD)
        decision = 'reject'
        tier = QualityTier.REJECTED
        _record(report, decision, reasons)
        return QualityDecision(
            decision=decision, quality_score=score,
            tier=tier, reasons=reasons, metadata=metadata,
        )

    # ── 16. Determine tier and decision ───────────────────────────────────────
    if score >= 80 and has_verified_email and company_present and name_ok:
        tier     = QualityTier.HIGH_QUALITY
        decision = 'save'
    elif score >= qualified_threshold:
        tier     = QualityTier.QUALIFIED
        decision = 'save'
    elif score >= pending_threshold:
        tier     = QualityTier.PENDING
        # If enrichment APIs are available, prefer enriching first
        decision = 'enrich' if not has_verified_email else 'pending'
    elif score >= low_quality_threshold:
        tier     = QualityTier.LOW_QUALITY
        decision = 'pending'
        reasons.append(RejectionReason.LOW_COMPLETENESS)
    else:
        tier     = QualityTier.REJECTED
        decision = 'reject'
        reasons.append(RejectionReason.LOW_COMPLETENESS)

    metadata['quality_tier'] = tier

    logger.info(
        f"[quality] '{name_raw or company_raw or email_raw}' "
        f"source={source_key} score={score:.0f} tier={tier} decision={decision} "
        f"email_type={email_type} verified={email_verified_flag} "
        f"reasons={reasons}"
    )

    _record(report, decision, reasons)
    return QualityDecision(
        decision=decision, quality_score=score,
        tier=tier, reasons=reasons, metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Helper — phone validation
# ---------------------------------------------------------------------------

def _validate_phone(phone: str) -> bool:
    """True if phone looks like a real, dialable number."""
    if not phone:
        return False
    digits = re.sub(r'[^\d]', '', phone)
    if len(digits) < 7 or len(digits) > 15:
        return False
    # All-same digits
    if len(set(digits)) <= 2:
        return False
    # Known fake patterns
    if digits.startswith('000') or digits.startswith('555555'):
        return False
    if digits.startswith('555') and len(digits) == 10:
        return False
    _asc = '01234567890123456789'
    _dsc = '98765432109876543210'
    if digits in _asc or digits in _dsc:
        return False
    # Accept international format (+...) or formatted (has +-() space)
    # Accept plain 10-11 digit strings (US/standard) or 7-9 digit local numbers
    # (Lebanon: 01 819 500 = 8 digits, mobile: 71050505 = 8 digits)
    has_formatting = any(c in phone for c in '+-() ')
    plain_digits_ok = len(digits) in (7, 8, 9, 10, 11)
    if not has_formatting and not plain_digits_ok and not phone.strip().startswith('+'):
        return False
    return True


# ---------------------------------------------------------------------------
# Helper — name validation
# ---------------------------------------------------------------------------

_NAME_KW = frozenset({
    'artificial', 'intelligence', 'machine', 'learning', 'deep',
    'software', 'technology', 'tech', 'digital', 'data', 'science',
    'cloud', 'cyber', 'security', 'automation', 'blockchain',
    'saas', 'fintech', 'startup', 'enterprise', 'platform',
    'analytics', 'developer', 'engineering', 'innovation',
    'smart', 'intelligent', 'advanced', 'professional', 'services',
    'solutions', 'consulting', 'agency', 'group', 'global',
    'marketing', 'media', 'company', 'corporation', 'limited',
})

_NAME_WORD_RE = re.compile(r"^[A-ZÀ-Ö][a-zA-ZÀ-öÀ-ÿ'\-]{1,30}$")


def _name_is_real(name: str, company: str = '') -> bool:
    """True if name looks like a real person's name (not a placeholder or username)."""
    if not name:
        return False
    # Known placeholders
    if name.lower() in ('unknown contact', 'unknown', '', 'n/a', 'none'):
        return False
    # Same as company
    if company and name.strip().lower() == company.strip().lower():
        return False
    # Looks like a username (all lowercase alphanumeric + symbols)
    if re.match(r'^[a-z0-9_\-\.]+$', name):
        return False
    # All words are keyword/industry terms
    words = [w.strip('.,()-').lower() for w in name.split() if w.strip('.,()-')]
    if words and all(w in _NAME_KW for w in words):
        return False
    # Must have 2+ words, each starting with a capital
    word_list = name.strip().split()
    if len(word_list) < 2 or len(word_list) > 5:
        return False
    for w in word_list:
        clean = w.strip("'-.,()")
        if not clean:
            continue
        if not _NAME_WORD_RE.match(clean):
            return False
    return True


# ---------------------------------------------------------------------------
# Report helper
# ---------------------------------------------------------------------------

def _record(report: Optional['CollectionQualityReport'], decision: str, reasons: List[str]) -> None:
    if report is None:
        return
    if decision in ('save', 'pending', 'enrich'):
        report.saved += 1
    else:
        report.rejected += 1
        for r in reasons:
            report.rejection_reasons[r] = report.rejection_reasons.get(r, 0) + 1


# ---------------------------------------------------------------------------
# CollectionQualityReport
# ---------------------------------------------------------------------------

class CollectionQualityReport:
    """
    Accumulates statistics for a single collection run.

    Usage:
        report = CollectionQualityReport(source='hunter')
        for lead in raw_leads:
            report.raw_candidates += 1
            decision = evaluate_lead_quality(lead, source='hunter', report=report)
            if decision.should_save:
                save(lead)

        print(report.to_dict())
    """

    def __init__(self, source: str) -> None:
        self.source             = source
        self.raw_candidates     = 0
        self.parsed_candidates  = 0
        self.rejected           = 0
        self.saved              = 0
        self.duplicates         = 0
        self._scores: List[float] = []

        self.rejection_reasons: Dict[str, int] = {}

        # Email breakdown
        self.verified_personal  = 0
        self.company_generic    = 0
        self.unverified         = 0
        self.missing_email      = 0

        # Extended pipeline metrics
        self.intent_detected: int = 0           # leads with buying_intent detected
        self.api_calls_made: Dict[str, int] = {}  # {hunter: n, zerobounce: n, ...}
        self.cache_hits: int = 0                # candidates served from candidate_cache
        self.enriched_candidates: int = 0       # candidates that went through enrichment
        self.top_sources: Dict[str, int] = {}   # {source_name: leads_saved}

    def record_score(self, score: float) -> None:
        self._scores.append(score)

    def record_email(self, email_type: str, verified: bool) -> None:
        if not email_type or email_type == 'missing':
            self.missing_email += 1
        elif email_type in ('personal_business',) and verified:
            self.verified_personal += 1
        elif email_type == 'generic':
            self.company_generic += 1
        else:
            self.unverified += 1

    def record_duplicate(self) -> None:
        self.duplicates += 1

    @property
    def average_quality_score(self) -> float:
        return round(sum(self._scores) / len(self._scores), 1) if self._scores else 0.0

    def record_api_call(self, api_name: str) -> None:
        self.api_calls_made[api_name] = self.api_calls_made.get(api_name, 0) + 1

    def record_source(self, source_name: str) -> None:
        self.top_sources[source_name] = self.top_sources.get(source_name, 0) + 1

    def to_dict(self) -> Dict[str, Any]:
        # Sort rejection reasons by count desc
        sorted_rejections = dict(
            sorted(self.rejection_reasons.items(), key=lambda x: x[1], reverse=True)
        )
        sorted_sources = dict(
            sorted(self.top_sources.items(), key=lambda x: x[1], reverse=True)
        )
        return {
            'source':                self.source,
            'raw_candidates':        self.raw_candidates,
            'enriched_candidates':   self.enriched_candidates,
            'parsed_candidates':     self.parsed_candidates,
            'rejected':              self.rejected,
            'saved':                 self.saved,
            'duplicates':            self.duplicates,
            'average_quality_score': self.average_quality_score,
            'intent_detected':       self.intent_detected,
            'cache_hits':            self.cache_hits,
            'api_calls_made':        self.api_calls_made,
            'top_sources':           sorted_sources,
            'rejection_reasons':     sorted_rejections,
            'email_breakdown': {
                'verified_personal': self.verified_personal,
                'company_generic':   self.company_generic,
                'unverified':        self.unverified,
                'missing':           self.missing_email,
            },
        }

    def log_summary(self) -> None:
        logger.info(
            f"[quality_report] source={self.source} "
            f"raw={self.raw_candidates} parsed={self.parsed_candidates} "
            f"saved={self.saved} rejected={self.rejected} "
            f"duplicates={self.duplicates} "
            f"avg_score={self.average_quality_score} "
            f"rejections={self.rejection_reasons}"
        )
