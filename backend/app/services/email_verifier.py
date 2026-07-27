"""
Email Verification Layer
========================
Verifies whether a collected email is actually deliverable before it upgrades
to email_verified=True inside the quality engine.

Two-tier verification:
  TIER 1 — ZeroBounce API (ZEROBOUNCE_API_KEY configured)
    • Returns: valid | invalid | catch-all | unknown | spamtrap | abuse | do_not_mail
    • 'valid' → email_verified=True
    • 'catch-all' → email_verified=False, email_type stays as-is
    • anything else → email_verified=False, flag in data_points

  TIER 2 — DNS / MX fallback (no API key needed)
    • Check that the email domain has at least one MX record
    • Does NOT confirm the mailbox exists — only that the domain accepts mail
    • email_verified=False even on MX success (we only confirmed domain, not mailbox)
    • Marks email_mx_valid=True in data_points

Important:
  • NEVER sets email_verified=True for catch-all or MX-only checks.
  • NEVER modifies lead['email'] — only updates data_points.
  • Result is cached in-process (LRU, 500 entries) to avoid re-checking.
  • Rate-limited: max 1 ZeroBounce call per 0.5s (free plan: 100/month).
"""

import os
import re
import socket
import logging
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Dict, Any, List, Optional, Tuple

try:
    import dns.resolver
    _DNS_AVAILABLE = True
except ImportError:
    _DNS_AVAILABLE = False

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

logger = logging.getLogger(__name__)

ZEROBOUNCE_API = "https://api.zerobounce.net/v2"
ABSTRACT_API   = "https://emailvalidation.abstractapi.com/v1"

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

# ZeroBounce statuses that mean the email is genuinely deliverable
_VALID_STATUSES    = frozenset({'valid'})
# Statuses where the domain accepts all mail — we know the domain is live but not the mailbox
_CATCHALL_STATUSES = frozenset({'catch-all'})
# Statuses that mean we should discard or downrank the email
_BAD_STATUSES      = frozenset({'invalid', 'spamtrap', 'abuse', 'do_not_mail', 'disposable'})

_last_zb_call = 0.0
_ZB_MIN_INTERVAL = 0.5  # seconds between ZeroBounce calls


class VerificationResult:
    """Outcome of a single email verification attempt."""
    __slots__ = ('verified', 'mx_valid', 'provider', 'status', 'sub_status', 'checked_at')

    def __init__(
        self,
        verified: bool,
        mx_valid: bool,
        provider: str,
        status: str,
        sub_status: str = '',
    ):
        self.verified    = verified
        self.mx_valid    = mx_valid
        self.provider    = provider
        self.status      = status
        self.sub_status  = sub_status
        self.checked_at  = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'email_verified':     self.verified,
            'email_mx_valid':     self.mx_valid,
            'email_verify_provider': self.provider,
            'email_verify_status':   self.status,
            'email_verify_sub':      self.sub_status,
            'email_verified_at':     self.checked_at,
        }


def _domain_of(email: str) -> str:
    return email.split('@', 1)[1].lower() if '@' in email else ''


# ---------------------------------------------------------------------------
# DNS / MX check (Tier 2 — no API key needed)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=500)
def _check_mx(domain: str) -> bool:
    """Return True if domain has at least one MX record."""
    if not domain:
        return False
    if _DNS_AVAILABLE:
        try:
            answers = dns.resolver.resolve(domain, 'MX', lifetime=5)
            return bool(answers)
        except Exception:
            pass
    # Fallback: raw socket getaddrinfo on smtp host
    try:
        socket.setdefaulttimeout(5)
        socket.getaddrinfo(domain, 25)
        return True
    except Exception:
        return False


def _verify_via_dns(email: str) -> VerificationResult:
    domain  = _domain_of(email)
    mx_ok   = _check_mx(domain)
    return VerificationResult(
        verified=False,   # MX check alone never upgrades to verified
        mx_valid=mx_ok,
        provider='dns_mx',
        status='mx_exists' if mx_ok else 'no_mx',
    )


# ---------------------------------------------------------------------------
# ZeroBounce (Tier 1 — requires API key)
# ---------------------------------------------------------------------------

def _verify_via_zerobounce(email: str) -> Optional[VerificationResult]:
    # Read key fresh on each call so keys saved via Settings take effect immediately
    _zb_key = os.getenv('ZEROBOUNCE_API_KEY', '')
    global _last_zb_call
    if not _zb_key or not _REQUESTS_AVAILABLE:
        return None
    # Rate-limit
    now = time.monotonic()
    gap = _last_zb_call + _ZB_MIN_INTERVAL - now
    if gap > 0:
        time.sleep(gap)
    _last_zb_call = time.monotonic()

    try:
        resp = _requests.get(
            f"{ZEROBOUNCE_API}/validate",
            params={'api_key': _zb_key, 'email': email, 'ip_address': ''},
            timeout=10,
        )
        if resp.status_code == 400:
            logger.debug(f"[ZeroBounce] credits exhausted or invalid key")
            return None
        if not resp.ok:
            logger.debug(f"[ZeroBounce] {resp.status_code}: {resp.text[:200]}")
            return None

        data       = resp.json()
        status     = (data.get('status') or '').lower()
        sub_status = (data.get('sub_status') or '').lower()
        mx_found   = data.get('mx_found', '').lower() == 'true'

        verified = status in _VALID_STATUSES
        return VerificationResult(
            verified   = verified,
            mx_valid   = mx_found,
            provider   = 'zerobounce',
            status     = status,
            sub_status = sub_status,
        )
    except Exception as exc:
        logger.debug(f"[ZeroBounce] error: {exc}")
        return None


def _verify_via_abstract(email: str) -> Optional[VerificationResult]:
    _abs_key = os.getenv('ABSTRACT_EMAIL_API_KEY', '')
    if not _abs_key or not _REQUESTS_AVAILABLE:
        return None
    try:
        resp = _requests.get(
            ABSTRACT_API,
            params={'api_key': _abs_key, 'email': email},
            timeout=10,
        )
        if not resp.ok:
            return None
        data          = resp.json()
        deliverability = (data.get('deliverability') or '').upper()
        is_valid_fmt  = data.get('is_valid_format', {}).get('value', False)
        is_mx         = data.get('is_mx_found', {}).get('value', False)
        is_smtp       = data.get('is_smtp_valid', {}).get('value', False)
        verified      = deliverability == 'DELIVERABLE' and is_smtp
        return VerificationResult(
            verified=verified,
            mx_valid=is_mx,
            provider='abstract',
            status=deliverability.lower(),
        )
    except Exception as exc:
        logger.debug(f"[Abstract] email verify error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_email(email: str) -> VerificationResult:
    """
    Verify a single email address.
    Returns a VerificationResult — never raises.

    Priority:
      1. ZeroBounce (if configured)
      2. Abstract API (if configured)
      3. DNS/MX fallback (always)
    """
    if not email or not _EMAIL_RE.match(email):
        return VerificationResult(False, False, 'none', 'invalid_format')

    # Tier 1a: ZeroBounce
    result = _verify_via_zerobounce(email)
    if result is not None:
        return result

    # Tier 1b: Abstract API
    result = _verify_via_abstract(email)
    if result is not None:
        return result

    # Tier 2: DNS/MX
    return _verify_via_dns(email)


def verify_and_update_lead(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run email verification on lead['email'] and update lead['data_points'] in-place.

    Rules:
      • Only calls verify_email() if lead has a non-empty email that isn't generated.
      • Sets data_points fields from VerificationResult.to_dict().
      • If ZeroBounce says 'invalid' → marks email_verified=False and adds reason.
      • Never removes or replaces lead['email'].
    """
    email = (lead.get('email') or '').strip().lower()
    dp    = lead.setdefault('data_points', {})

    if not email:
        return lead

    # Skip if already verified by a high-quality API source
    if dp.get('email_verified') and dp.get('email_source') in ('pdl', 'hunter'):
        return lead

    # Skip generated / inferred emails
    generated_sources = frozenset({
        'generated', 'generated_personal', 'generated_generic', 'inferred', 'guessed',
    })
    if dp.get('email_source') in generated_sources:
        return lead

    result = verify_email(email)
    dp.update(result.to_dict())

    if result.status in _BAD_STATUSES:
        dp['email_reject_reason'] = f'verifier:{result.status}'
        logger.info(f"[EmailVerifier] {email} → {result.status} (flagged)")
    elif result.verified:
        logger.info(f"[EmailVerifier] {email} → verified via {result.provider}")
    else:
        logger.debug(f"[EmailVerifier] {email} → {result.status}/{result.provider}")

    return lead


def bulk_verify(leads: List[Dict[str, Any]], max_to_verify: int = 50) -> List[Dict[str, Any]]:
    """
    Verify emails for a list of leads.
    Caps at max_to_verify to respect API quotas.
    Returns the same list (mutated in-place).
    """
    verified_count = 0
    for ld in leads:
        if verified_count >= max_to_verify:
            break
        email = (ld.get('email') or '').strip()
        if email:
            verify_and_update_lead(ld)
            verified_count += 1
    logger.info(f"[EmailVerifier] verified {verified_count}/{len(leads)} leads")
    return leads
