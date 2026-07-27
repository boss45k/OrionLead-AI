"""
Lusha B2B contact data service.
Free tier: 5 credits/month.

Returns verified work emails and direct-dial phone numbers for a person
identified by name + company or domain.

Wired into lead_fallback.py as enrichment step 2.7.
"""
import os
import logging
import time
import threading
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

LUSHA_BASE = 'https://api.lusha.com/v2'
_RATE_INTERVAL = 1.0


class LushaService:
    def __init__(self):
        self.api_key = os.getenv('LUSHA_API_KEY', '').strip()
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._credit_exhausted = False
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({'api_key': self.api_key})

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _throttle(self) -> None:
        with self._lock:
            wait = _RATE_INTERVAL - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def enrich_person(
        self,
        first_name: str,
        last_name: str,
        company: str = '',
        domain: str = '',
    ) -> Optional[Dict[str, Any]]:
        """
        Enrich a person via Lusha.

        Returns dict with any subset of: email, email_verified, email_source, phone.
        Returns None if not found or not configured.
        """
        if not self.is_configured() or self._credit_exhausted:
            return None
        if not first_name:
            return None
        self._throttle()
        params: Dict[str, str] = {
            'firstName': first_name,
            'lastName': last_name or '',
        }
        if company:
            params['company'] = company
        if domain:
            params['companyWebsite'] = domain
        try:
            resp = self.session.get(f'{LUSHA_BASE}/person', params=params, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                result: Dict[str, Any] = {}
                for em in data.get('emails', []):
                    addr = em.get('emailAddress', '')
                    if addr:
                        result['email'] = addr
                        result['email_verified'] = True
                        result['email_source'] = 'lusha'
                        break
                for ph in data.get('phoneNumbers', []):
                    number = ph.get('localizedNumber') or ph.get('number', '')
                    if number:
                        result['phone'] = str(number)
                        break
                return result or None
            elif resp.status_code == 401:
                logger.warning('[lusha] invalid API key')
            elif resp.status_code == 402:
                logger.warning('[lusha] credit limit reached — disabling for this session')
                self._credit_exhausted = True
            else:
                logger.debug('[lusha] HTTP %s for %s %s', resp.status_code, first_name, last_name)
        except Exception as exc:
            logger.warning('[lusha] enrich_person error: %s', exc)
        return None


_instance: Optional[LushaService] = None


def get_lusha_service() -> LushaService:
    global _instance
    if _instance is None:
        _instance = LushaService()
    return _instance
