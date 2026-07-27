"""
RocketReach professional contact data service.
Free tier: 5 lookups/month.

Returns verified work emails, direct-dial phones, and LinkedIn URLs for
professionals identified by name + company or by LinkedIn URL.

Wired into lead_fallback.py as enrichment step 2.8.
"""
import os
import logging
import time
import threading
import requests
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

ROCKETREACH_BASE = 'https://api.rocketreach.co/v2/api'
_RATE_INTERVAL = 1.5


class RocketReachService:
    def __init__(self):
        self.api_key = os.getenv('ROCKETREACH_API_KEY', '').strip()
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._rate_limited = False
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({'Api-Key': self.api_key})

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _throttle(self) -> None:
        with self._lock:
            wait = _RATE_INTERVAL - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def lookup_person(
        self,
        name: str = '',
        company: str = '',
        linkedin_url: str = '',
        email: str = '',
    ) -> Optional[Dict[str, Any]]:
        """
        Look up a person via RocketReach.

        Provide at least one of: name+company, linkedin_url, or email.
        Returns dict with any subset of: email, email_verified, email_source,
        phone, linkedin_url, position, company.
        Returns None if not found or not configured.
        """
        if not self.is_configured() or self._rate_limited:
            return None
        if not any([name, linkedin_url, email]):
            return None
        self._throttle()
        params: Dict[str, str] = {}
        if name:
            params['name'] = name
        if company:
            params['company'] = company
        if linkedin_url:
            params['li_url'] = linkedin_url
        if email:
            params['email'] = email
        try:
            resp = self.session.get(
                f'{ROCKETREACH_BASE}/lookupProfile',
                params=params,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                result: Dict[str, Any] = {}
                # Emails — prefer smtp-verified ones
                emails: List[Dict] = data.get('emails', [])
                emails_sorted = sorted(
                    emails,
                    key=lambda x: x.get('smtp_valid', '') == 'valid',
                    reverse=True,
                )
                for em in emails_sorted:
                    addr = em.get('email', '')
                    if addr:
                        result['email'] = addr
                        result['email_verified'] = em.get('smtp_valid') == 'valid'
                        result['email_source'] = 'rocketreach'
                        break
                # Phones
                for ph in data.get('phones', []):
                    number = ph.get('number', '')
                    if number:
                        result['phone'] = number
                        break
                # LinkedIn
                li = data.get('linkedin_url', '')
                if li:
                    result['linkedin_url'] = li if li.startswith('http') else f'https://{li}'
                # Position / company (fill blanks only)
                if data.get('title'):
                    result['position'] = data['title']
                if data.get('current_employer'):
                    result['company'] = data['current_employer']
                return result or None
            elif resp.status_code == 429:
                logger.warning('[rocketreach] rate limited — disabling for this session')
                self._rate_limited = True
            elif resp.status_code == 401:
                logger.warning('[rocketreach] invalid API key')
            else:
                logger.debug('[rocketreach] HTTP %s for name=%s', resp.status_code, name)
        except Exception as exc:
            logger.warning('[rocketreach] lookup_person error: %s', exc)
        return None


_instance: Optional[RocketReachService] = None


def get_rocketreach_service() -> RocketReachService:
    global _instance
    if _instance is None:
        _instance = RocketReachService()
    return _instance
