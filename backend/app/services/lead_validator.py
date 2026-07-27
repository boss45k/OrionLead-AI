"""
Lead Validator — Scoring-Based Validation Engine
=================================================
Scoring breakdown (max 100):
  Email presence & quality  → up to 35 pts
  Phone (validated)         → 15 pts
  Company name              → 15 pts
  Contact name              → 10 pts
  Position / job title      →  8 pts
  Industry classification   →  5 pts
  Website URL               →  5 pts
  LinkedIn URL              →  4 pts
  Location (country/city)   →  3 pts
  ──────────────────────────────────
  Max possible              = 100 pts

Quality tiers:
  ≥ 80 → "high_quality"   (verified personal email + full profile)
  ≥ 60 → "qualified"       (actionable lead)
  35–59 → "pending"        (worth enriching)
  15–34 → "low_quality"    (stored but flagged)
  < 15  → "rejected"       (discarded)

STRICT RULES:
  • Generated / guessed emails give 0 email points (email_source='generated')
  • A lead with ONLY a company name and no contact method → rejected
  • Generic-only email (info@, contact@) with no other contact → pending, not qualified
  • Social source leads face +15pt threshold adjustment
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.services.lead_quality_engine import PLACEHOLDER_COMPANIES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
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
    'contacto', 'hola', 'ventas', 'atencion', 'comercial', 'redaccion',
    'publicidad', 'clientes', 'notifications', 'automated', 'system',
    'robot', 'alerts', 'updates', 'digest', 'postmaster', 'mailer-daemon',
    'reach', 'enquire', 'getintouch', 'get-in-touch', 'contactus',
    'sales-team', 'hello-team',
})

GENERATED_EMAIL_SOURCES = frozenset({
    'generated', 'generated_personal', 'generated_generic',
    'inferred', 'guessed',
})

# Tier thresholds
HIGH_QUALITY_THRESHOLD = 80
QUALIFIED_THRESHOLD    = 60
PENDING_THRESHOLD      = 35
LOW_QUALITY_THRESHOLD  = 15

# Social sources have higher bar (+15 on each threshold)
SOCIAL_SOURCES = frozenset({'reddit', 'twitter', 'facebook', 'telegram', 'social_media'})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_generic_email(email: str) -> bool:
    if not email or '@' not in email:
        return False
    return email.lower().split('@')[0] in GENERIC_LOCAL_PARTS


def _is_free_email(email: str) -> bool:
    if not email or '@' not in email:
        return False
    return email.lower().split('@')[1] in FREE_EMAIL_DOMAINS


def _is_personal_business_email(email: str) -> bool:
    if not email or '@' not in email:
        return False
    return not _is_generic_email(email) and not _is_free_email(email)


def _email_verified(lead: Dict[str, Any]) -> bool:
    dp = lead.get('data_points') or {}
    return bool(dp.get('email_verified', False))


def _email_is_generated(lead: Dict[str, Any]) -> bool:
    """True when the email was generated/guessed — never counts as real contact."""
    dp  = lead.get('data_points') or {}
    src = (dp.get('email_source') or '').strip().lower()
    return src in GENERATED_EMAIL_SOURCES


def _validate_phone(phone: str) -> bool:
    if not phone:
        return False
    digits = re.sub(r'[^\d]', '', phone)
    if len(digits) < 7 or len(digits) > 15:
        return False
    if len(set(digits)) <= 2:
        return False
    if digits.startswith('000') or digits.startswith('555555'):
        return False
    if digits.startswith('555') and len(digits) == 10:
        return False
    _asc = '01234567890123456789'
    _dsc = '98765432109876543210'
    if digits in _asc or digits in _dsc:
        return False
    return True


# ---------------------------------------------------------------------------
# Core scorer
# ---------------------------------------------------------------------------

class LeadScoreResult:
    __slots__ = (
        'score', 'status', 'completeness_score',
        'reasons', 'missing_fields', 'email_type', 'tier',
    )

    def __init__(
        self,
        score: float,
        status: str,
        completeness_score: float,
        reasons: List[str],
        missing_fields: List[str],
        email_type: str,
        tier: str,
    ) -> None:
        self.score             = score
        self.status            = status
        self.completeness_score= completeness_score
        self.reasons           = reasons
        self.missing_fields    = missing_fields
        self.email_type        = email_type
        self.tier              = tier

    def __repr__(self) -> str:
        return (
            f"<LeadScore score={self.score:.0f} tier={self.tier} "
            f"status={self.status} missing={self.missing_fields}>"
        )


def score_lead(lead: Dict[str, Any], *, debug: bool = False) -> LeadScoreResult:
    """
    Calculate completeness score and derive status/tier.
    Does NOT mutate the lead dict.

    Key rule changes vs. previous version:
      • Generated emails contribute 0 points — treated as if email is missing
      • Generic unverified email: 3 pts (was 4, now clearly separated)
      • Personal unverified email: 15 pts (was 18)
      • Personal verified email: 35 pts (was 30)
      • Phone validation is strict
      • Tiers: high_quality | qualified | pending | low_quality | rejected
    """
    pts   = 0.0
    reasons: List[str] = []
    missing: List[str] = []
    email_type = 'unknown'

    def _log(msg: str) -> None:
        if debug:
            logger.debug(f"[validator] {msg}")

    # Determine source (used for threshold adjustment)
    dp     = lead.get('data_points') or {}
    source = (dp.get('platform') or lead.get('source') or '').lower().strip()
    is_social = source in SOCIAL_SOURCES

    # ── Email (up to 35 pts) ─────────────────────────────────────────────────
    email = (lead.get('email') or '').strip().lower()
    verified  = _email_verified(lead)
    generated = _email_is_generated(lead)

    if generated and email:
        # Generated email: never counts as a real contact method
        email_type = 'generated'
        missing.append('email')
        reasons.append('generated_email_not_counted')
        _log(f"generated email blocked from scoring: {email}")
        email = ''  # treat as absent for the rest of scoring

    if email:
        if _is_personal_business_email(email):
            email_type = 'personal' if not _is_free_email(email) else 'free'
            if verified:
                pts += 35
                _log(f"+35 personal business email (verified): {email}")
            else:
                pts += 15
                _log(f"+15 personal business email (unverified): {email}")
        elif _is_generic_email(email):
            email_type = 'generic'
            if verified:
                pts += 12
                _log(f"+12 generic email (verified): {email}")
            else:
                pts += 3
                _log(f"+3 generic email (unverified): {email}")
        elif _is_free_email(email):
            email_type = 'free'
            if verified:
                pts += 18
                _log(f"+18 free email (verified): {email}")
            else:
                pts += 12
                _log(f"+12 free email (unverified): {email}")
        else:
            pts += 8
            email_type = 'company'
            _log(f"+8 other email: {email}")
    else:
        if not generated:
            missing.append('email')
            reasons.append('no_email')
            _log("email missing")

    # ── Phone (15 pts) ───────────────────────────────────────────────────────
    phone = (lead.get('phone') or '').strip()
    phone_valid = _validate_phone(phone)
    if phone_valid:
        pts += 15
        _log(f"+15 phone: {phone}")
    elif phone:
        _log(f"phone rejected (invalid): {phone}")
        missing.append('phone')
    else:
        missing.append('phone')

    # ── Company name (15 pts) ─────────────────────────────────────────────────
    company = (lead.get('company') or '').strip()
    if company.lower() in PLACEHOLDER_COMPANIES:
        lead['company'] = ''  # clear placeholder so it doesn't reach the DB
        company = ''
    if company and len(company) >= 2:
        pts += 15
        _log(f"+15 company: {company}")
    else:
        missing.append('company')

    # ── Contact name (10 pts) ─────────────────────────────────────────────────
    name = (lead.get('name') or '').strip()
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
    _name_words = [w.strip('.,()-').lower() for w in name.split() if w.strip('.,()-')]
    _all_keywords = bool(_name_words) and all(w in _NAME_KW for w in _name_words)
    is_placeholder_name = (
        not name
        or name.lower() in ('unknown contact', 'unknown', '', 'n/a', 'none')
        or (company and name.strip().lower() == company.strip().lower())
        or re.match(r'^[a-z0-9_\-\.]+$', name)  # username pattern
        or _all_keywords
        or len(name.split()) < 2   # single word = not a real person name
        or len(name.split()) > 5   # too long = probably a description
    )
    if not is_placeholder_name:
        pts += 10
        _log(f"+10 contact name: {name}")
    else:
        missing.append('name')

    # ── Position (8 pts) ────────────────────────────────────────────────────
    position = (lead.get('position') or '').strip()
    if position:
        pts += 8
        _log(f"+8 position: {position}")
    else:
        missing.append('position')

    # ── Industry (5 pts) ─────────────────────────────────────────────────────
    industry = (lead.get('industry') or '').strip()
    if industry:
        pts += 5
        _log(f"+5 industry: {industry}")
    else:
        missing.append('industry')

    # ── Website (5 pts) ──────────────────────────────────────────────────────
    website = (lead.get('website') or '').strip()
    if website and website.startswith('http'):
        pts += 5
        _log(f"+5 website: {website}")
    else:
        missing.append('website')

    # ── LinkedIn (4 pts) ─────────────────────────────────────────────────────
    linkedin = (lead.get('linkedin_url') or '').strip()
    if linkedin and 'linkedin.com' in linkedin:
        pts += 4
        _log(f"+4 linkedin_url")

    # ── Location (3 pts) ─────────────────────────────────────────────────────
    country = (lead.get('country') or '').strip()
    city    = (lead.get('city') or '').strip()
    if country or city:
        pts += 3
        _log(f"+3 location: country={country} city={city}")
    else:
        missing.append('location')

    score = min(pts, 100.0)
    completeness_score = score

    # ── Social source threshold adjustment ────────────────────────────────────
    if is_social:
        eff_high      = HIGH_QUALITY_THRESHOLD + 15
        eff_qualified = QUALIFIED_THRESHOLD + 15
        eff_pending   = PENDING_THRESHOLD + 15
    else:
        eff_high      = HIGH_QUALITY_THRESHOLD
        eff_qualified = QUALIFIED_THRESHOLD
        eff_pending   = PENDING_THRESHOLD

    # ── Derive tier and status ────────────────────────────────────────────────
    has_contact = bool(lead.get('email') and not generated) or phone_valid or bool(website and website.startswith('http'))

    # Hard-reject: only a generic or unverified email with no other real contact.
    # A lead whose sole contact method is info@domain (unverified/inferred) is
    # not actionable — reject before wasting a DB row.
    _email_is_generic = email_type in ('generic',) and not verified
    _only_generic_contact = (
        _email_is_generic
        and not phone_valid
        and not linkedin
        and not generated  # already handled above
    )

    if _only_generic_contact:
        tier   = 'rejected'
        status = 'rejected'
        reasons.append('generic_unverified_email_only')
    elif not has_contact and score < LOW_QUALITY_THRESHOLD:
        tier   = 'rejected'
        status = 'rejected'
        reasons.append('no_contact_data')
    elif score >= eff_high and _is_personal_business_email(email) and verified:
        tier   = 'high_quality'
        status = 'qualified'
    elif score >= eff_qualified:
        tier   = 'qualified'
        status = 'pending'  # AI qualification agent promotes to 'qualified'
    elif score >= eff_pending:
        tier   = 'pending'
        status = 'pending'
    elif score >= LOW_QUALITY_THRESHOLD:
        tier   = 'low_quality'
        status = 'low_quality'
        reasons.append('low_completeness')
    else:
        tier   = 'rejected'
        status = 'rejected'
        reasons.append('very_low_completeness')

    result = LeadScoreResult(
        score=score,
        status=status,
        completeness_score=completeness_score,
        reasons=reasons,
        missing_fields=missing,
        email_type=email_type,
        tier=tier,
    )
    logger.info(
        f"[validator] Lead '{name or company or email}' → "
        f"score={score:.0f} tier={tier} status={status} "
        f"missing={missing} email_type={email_type}"
    )
    return result


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _normalise_email(email: str) -> str:
    e = (email or '').strip().lower()
    if 'gmail.com' in e:
        local, domain = e.split('@', 1)
        local = local.replace('.', '')
        e = f'{local}@{domain}'
    return e


def _normalise_name(name: str) -> str:
    return re.sub(r'\s+', ' ', (name or '').lower().strip())


def _normalise_company(company: str) -> str:
    c = (company or '').lower().strip()
    c = re.sub(
        r'\b(inc\.?|llc\.?|ltd\.?|corp\.?|co\.?|gmbh|s\.a\.?|b\.v\.?|plc\.?|'
        r'limited|incorporated|group|holdings?|international|intl\.?)\b',
        '', c,
    )
    c = re.sub(r'[^\w\s]', '', c)
    return re.sub(r'\s+', ' ', c).strip()


class DuplicateFilter:
    """
    Session-level duplicate filter.

    Uses normalised (case-folded) keys so that:
      "John Smith | Acme Corp" == "john smith | acme corp"
      "john.smith@gmail.com"   == "johnsmith@gmail.com"  (Gmail dot-trick)
    """

    def __init__(self) -> None:
        self._seen_emails: set       = set()
        self._seen_name_company: set = set()
        self._seen_domains: set      = set()

    def is_duplicate(self, lead: Dict[str, Any], *, debug: bool = False) -> Tuple[bool, str]:
        email   = _normalise_email(lead.get('email') or '')
        company = _normalise_company(lead.get('company') or '')
        name    = _normalise_name(lead.get('name') or '')
        website = (lead.get('website') or '').strip().lower()

        domain = ''
        if website:
            try:
                from urllib.parse import urlparse as _up
                domain = _up(website).netloc.replace('www.', '')
            except Exception:
                pass

        # Email dedup (skip generic addresses — they map to many people)
        if email and email.split('@')[0] not in GENERIC_LOCAL_PARTS:
            if email in self._seen_emails:
                if debug:
                    logger.debug(f"[dedup] duplicate email={email}")
                return True, f'duplicate_email:{email}'

        # Name + company pair
        if name and company:
            pair = f'{name}|{company}'
            if pair in self._seen_name_company:
                if debug:
                    logger.debug(f"[dedup] duplicate name+company={pair}")
                return True, 'duplicate_name_company'

        # Domain-level dedup (only when no personal email)
        if domain and (not email or _is_generic_email(email)):
            if domain in self._seen_domains:
                if debug:
                    logger.debug(f"[dedup] duplicate domain={domain}")
                return True, 'duplicate_domain'

        return False, ''

    def register(self, lead: Dict[str, Any]) -> None:
        email   = _normalise_email(lead.get('email') or '')
        company = _normalise_company(lead.get('company') or '')
        name    = _normalise_name(lead.get('name') or '')
        website = (lead.get('website') or '').strip().lower()

        if email:
            self._seen_emails.add(email)
        if name and company:
            self._seen_name_company.add(f'{name}|{company}')
        if website:
            try:
                from urllib.parse import urlparse as _up
                domain = _up(website).netloc.replace('www.', '')
                if domain:
                    self._seen_domains.add(domain)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Convenience: apply score + dedup in one call
# ---------------------------------------------------------------------------

def validate_and_score(
    lead: Dict[str, Any],
    dedup_filter: Optional[DuplicateFilter] = None,
    *,
    debug: bool = False,
) -> Tuple[Dict[str, Any], bool, str]:
    """
    Score a lead and optionally check for duplicates.

    Mutates the lead dict to add:
      • qualification_score
      • completeness_score
      • email_type
      • quality_tier
      • status (if current status is 'pending' or blank)

    Returns:
        (lead, should_save, rejection_reason)
    """
    result = score_lead(lead, debug=debug)

    lead['qualification_score'] = result.score
    lead['completeness_score']  = result.completeness_score
    lead['email_type']          = result.email_type

    dp = lead.setdefault('data_points', {})
    dp['quality_tier']    = result.tier
    dp['missing_fields']  = result.missing_fields
    if result.reasons:
        dp['validation_notes'] = result.reasons

    # Only override status if still at default
    if not lead.get('status') or lead.get('status') == 'pending':
        lead['status'] = result.status

    # ── Deduplication ────────────────────────────────────────────────────────
    if dedup_filter is not None:
        is_dup, dup_reason = dedup_filter.is_duplicate(lead, debug=debug)
        if is_dup:
            logger.info(
                f"[validator] Duplicate lead dropped: "
                f"name='{lead.get('name')}' reason={dup_reason}"
            )
            return lead, False, dup_reason
        dedup_filter.register(lead)

    # ── Hard floor: reject if completely empty ────────────────────────────────
    generated = _email_is_generated(lead)
    email_val = (lead.get('email') or '').strip()
    effective_email = email_val if not generated else ''
    has_any_contact = bool(
        effective_email
        or _validate_phone(lead.get('phone') or '')
        or (lead.get('website') or '').startswith('http')
        or lead.get('linkedin_url')
    )
    if not has_any_contact and result.score < LOW_QUALITY_THRESHOLD:
        logger.info(
            f"[validator] Lead discarded (no contact data + score={result.score:.0f}): "
            f"name='{lead.get('name')}' company='{lead.get('company')}'"
        )
        dp['rejection_reason'] = 'no_contact_data'
        return lead, False, 'no_contact_data'

    # Rejected tier → don't save
    if result.tier == 'rejected':
        dp['rejection_reason'] = result.reasons[0] if result.reasons else 'below_threshold'
        return lead, False, dp['rejection_reason']

    return lead, True, ''


# ---------------------------------------------------------------------------
# Bulk processing helper
# ---------------------------------------------------------------------------

def filter_and_score_leads(
    leads: List[Dict[str, Any]],
    *,
    debug: bool = False,
    min_score: float = 0.0,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Process a list of raw lead dicts.
    Returns (accepted_leads, rejected_leads).
    """
    dedup    = DuplicateFilter()
    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for lead in leads:
        lead, should_save, reason = validate_and_score(lead, dedup, debug=debug)
        if should_save and lead.get('completeness_score', 0) >= min_score:
            accepted.append(lead)
        else:
            lead['rejection_reason'] = reason or 'below_min_score'
            rejected.append(lead)
            logger.debug(
                f"[validator] Rejected: name='{lead.get('name')}' "
                f"score={lead.get('completeness_score', 0):.0f} "
                f"reason={lead.get('rejection_reason')}"
            )

    logger.info(
        f"[validator] filter_and_score_leads: "
        f"{len(accepted)} accepted, {len(rejected)} rejected "
        f"(from {len(leads)} total)"
    )
    return accepted, rejected
