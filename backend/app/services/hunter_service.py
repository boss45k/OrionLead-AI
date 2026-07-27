"""
Hunter.io email finding and verification service.
Free tier: 25 searches/month.

Quality rules:
  • Confidence threshold: ≥ 80 (was 50 — too permissive)
  • domain_search() checks per-email confidence before returning
  • All returned leads are tagged with email_source='hunter' and email_verified=True
  • Generic/shared mailboxes (info@, contact@, ...) are excluded from domain_search
  • enrich_lead() adds enrichment metadata to data_points
"""
import os
import time
import logging
import threading
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

HUNTER_BASE_URL       = "https://api.hunter.io/v2"
HUNTER_MIN_CONFIDENCE = 80   # Minimum confidence score to accept an email
_RATE_INTERVAL        = 1.5  # minimum seconds between Hunter API calls

GENERIC_LOCAL_PARTS = frozenset({
    'info', 'contact', 'hello', 'support', 'sales', 'admin', 'team',
    'business', 'inquiry', 'inquiries', 'enquiry', 'enquiries', 'help',
    'feedback', 'service', 'office', 'general', 'mail', 'reception',
    'marketing', 'press', 'media', 'hr', 'jobs', 'careers', 'billing',
    'accounts', 'customerservice', 'cs', 'newsletter', 'noreply',
    'no-reply', 'donotreply',
})


def _is_generic(email: str) -> bool:
    if not email or '@' not in email:
        return True
    return email.lower().split('@')[0] in GENERIC_LOCAL_PARTS


class HunterService:
    def __init__(self):
        self.api_key = (
            os.getenv('HUNTER_API_KEY')
            or os.getenv('HUNTER_IO_API_KEY', '')
        ).strip()
        self.session = requests.Session()
        self._lock            = threading.Lock()
        self._last_call       = 0.0   # monotonic time of last API call
        self._rate_limited    = False  # set True on 429 — skip for this session
        self._domain_cache: Dict[str, List[Dict[str, Any]]] = {}  # domain → leads

    def _throttle(self) -> None:
        """Block until at least _RATE_INTERVAL seconds have passed since last call."""
        with self._lock:
            wait = _RATE_INTERVAL - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def find_email(
        self,
        first_name: str,
        last_name: str,
        domain: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Find a corporate email for a person at a company domain.

        Returns a dict with:
          email, confidence, email_verified, email_source, email_type
        or None if not found / confidence too low.
        """
        if not self.is_configured() or not domain or self._rate_limited:
            return None
        try:
            self._throttle()
            resp = self.session.get(
                f"{HUNTER_BASE_URL}/email-finder",
                params={
                    'domain':      domain,
                    'first_name':  first_name,
                    'last_name':   last_name,
                    'api_key':     self.api_key,
                },
                timeout=10,
            )
            if resp.status_code == 429:
                logger.warning("[Hunter] 429 rate limit reached — skipping Hunter for this session")
                self._rate_limited = True
                return None
            resp.raise_for_status()
            data       = resp.json().get('data', {})
            email      = (data.get('email') or '').strip().lower()
            confidence = data.get('score', 0)

            if not email:
                return None
            if confidence < HUNTER_MIN_CONFIDENCE:
                logger.debug(
                    f"[Hunter] find_email rejected (confidence={confidence} < {HUNTER_MIN_CONFIDENCE}): {email}"
                )
                return None

            logger.info(f"[Hunter] find_email → {email} (confidence={confidence})")
            return {
                'email':          email,
                'confidence':     confidence,
                'email_verified': True,
                'email_source':   'hunter',
                'email_type':     'generic' if _is_generic(email) else 'personal_business',
                'enriched_at':    datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.warning(f"[Hunter] find_email error: {exc}")
            return None

    def domain_search(self, domain: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Return verified leads at a company domain.

        Filters:
          • Only emails with confidence ≥ HUNTER_MIN_CONFIDENCE
          • Excludes generic/shared mailboxes (info@, contact@, etc.)
          • Each lead includes email_source='hunter' and email_verified=True
        """
        if not self.is_configured() or not domain or self._rate_limited:
            return []
        if domain in self._domain_cache:
            return self._domain_cache[domain]
        try:
            self._throttle()
            resp = self.session.get(
                f"{HUNTER_BASE_URL}/domain-search",
                params={'domain': domain, 'limit': limit, 'api_key': self.api_key},
                timeout=10,
            )
            if resp.status_code == 429:
                logger.warning("[Hunter] 429 rate limit reached — skipping Hunter for this session")
                self._rate_limited = True
                return []
            resp.raise_for_status()
            data   = resp.json().get('data', {})
            org    = data.get('organization', '')
            emails = data.get('emails', [])
            leads  = []
            skipped_low_conf = 0
            skipped_generic  = 0

            for e in emails:
                email      = (e.get('value') or '').strip().lower()
                confidence = e.get('confidence', 0)
                first      = e.get('first_name', '')
                last       = e.get('last_name', '')
                name       = f"{first} {last}".strip()

                if not email or not name:
                    continue
                if confidence < HUNTER_MIN_CONFIDENCE:
                    skipped_low_conf += 1
                    continue
                if _is_generic(email):
                    skipped_generic += 1
                    continue

                leads.append({
                    'name':         name,
                    'email':        email,
                    'company':      org,
                    'position':     e.get('position', ''),
                    'website':      f"https://{domain}",
                    'linkedin_url': e.get('linkedin', '') or '',
                    'source':       'hunter',
                    'data_points': {
                        'email_verified':  True,
                        'email_source':    'hunter',
                        'email_type':      'personal_business',
                        'email_confidence': confidence / 100.0,
                        'enrichment_source': 'hunter',
                        'enriched_at':     datetime.now(timezone.utc).isoformat(),
                    },
                })

            logger.info(
                f"[Hunter] domain_search({domain}) → {len(leads)} leads "
                f"(skipped low_conf={skipped_low_conf} generic={skipped_generic})"
            )
            self._domain_cache[domain] = leads
            return leads
        except Exception as exc:
            logger.warning(f"[Hunter] domain_search error: {exc}")
            return []

    def verify_email(self, email: str) -> bool:
        """Returns True if email is deliverable according to Hunter."""
        if not self.is_configured() or not email or self._rate_limited:
            return False
        try:
            self._throttle()
            resp = self.session.get(
                f"{HUNTER_BASE_URL}/email-verifier",
                params={'email': email, 'api_key': self.api_key},
                timeout=10,
            )
            if resp.status_code == 429:
                logger.warning("[Hunter] 429 rate limit reached — skipping Hunter for this session")
                self._rate_limited = True
                return False
            resp.raise_for_status()
            status = resp.json().get('data', {}).get('status', '')
            return status in ('valid', 'accept_all')
        except Exception as exc:
            logger.warning(f"[Hunter] verify_email error: {exc}")
            return False

    def enrich_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Try to fill missing email on a lead using Hunter.
        Adds enrichment metadata to data_points.
        Returns updated lead dict (original if nothing found).
        """
        if lead.get('email') or not self.is_configured():
            return lead

        website = lead.get('website', '')
        domain  = ''
        if website:
            domain = website.replace('https://', '').replace('http://', '').split('/')[0]
        elif lead.get('company'):
            slug   = lead['company'].lower().replace(' ', '').replace(',', '').replace('.', '')
            domain = f"{slug}.com"

        if not domain:
            return lead

        name_parts = (lead.get('name') or '').split()
        first = name_parts[0]  if name_parts else ''
        last  = name_parts[-1] if len(name_parts) > 1 else ''

        result = self.find_email(first, last, domain)
        if result:
            lead = dict(lead)
            lead['email'] = result['email']
            dp = lead.setdefault('data_points', {})
            dp.update({
                'email_verified':    result['email_verified'],
                'email_source':      result['email_source'],
                'email_type':        result['email_type'],
                'email_confidence':  result['confidence'] / 100.0,
                'enrichment_source': 'hunter',
                'enriched_at':       result['enriched_at'],
            })
            logger.info(f"[Hunter] enriched email for {lead.get('name')}: {result['email']}")
        return lead


# ── Singleton ─────────────────────────────────────────────────────────────────
_instance: Optional[HunterService] = None


def get_hunter_service() -> HunterService:
    global _instance
    if _instance is None:
        _instance = HunterService()
    return _instance


def is_hunter_configured() -> bool:
    return bool(
        (os.getenv('HUNTER_API_KEY') or os.getenv('HUNTER_IO_API_KEY', '')).strip()
    )
