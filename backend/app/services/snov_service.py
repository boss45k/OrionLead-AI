"""
Snov.io email finder service.
Free tier: 50 credits/month.

Auth:
  SNOV_API_KEY supports two formats:
    • "client_id:client_secret"  → auto-fetches OAuth2 access token
    • bare access token          → used directly

Wired into lead_fallback.py as enrichment step 2.6.
"""
import os
import logging
import time
import threading
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

SNOV_BASE = 'https://app.snov.io/restapi'
_RATE_INTERVAL = 1.0


class SnovService:
    def __init__(self):
        raw = os.getenv('SNOV_API_KEY', '').strip()
        self._client_id: str = ''
        self._client_secret: str = ''
        self._access_token: str = ''
        self._token_expiry: float = 0.0

        if ':' in raw:
            parts = raw.split(':', 1)
            self._client_id = parts[0].strip()
            self._client_secret = parts[1].strip()
        elif raw:
            self._access_token = raw
            self._token_expiry = time.time() + 3600

        self._lock = threading.Lock()
        self._last_call = 0.0
        self.session = requests.Session()

    def is_configured(self) -> bool:
        return bool(self._client_id or self._access_token)

    def _throttle(self) -> None:
        with self._lock:
            wait = _RATE_INTERVAL - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def _get_token(self) -> Optional[str]:
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token
        if not self._client_id:
            return None
        try:
            resp = self.session.post(
                f'{SNOV_BASE}/oauth/access_token',
                json={
                    'grant_type': 'client_credentials',
                    'client_id': self._client_id,
                    'client_secret': self._client_secret,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._access_token = data.get('access_token', '')
                expires_in = int(data.get('expires_in', 3600))
                self._token_expiry = time.time() + expires_in - 60
                return self._access_token
            logger.warning('[snov] token refresh failed: %s', resp.status_code)
        except Exception as exc:
            logger.warning('[snov] token refresh error: %s', exc)
        return None

    def find_email(self, first_name: str, last_name: str, domain: str) -> Optional[str]:
        """Find work email for a person at a domain. Returns email string or None."""
        if not self.is_configured() or not domain or not first_name:
            return None
        token = self._get_token()
        if not token:
            return None
        self._throttle()
        try:
            resp = self.session.post(
                f'{SNOV_BASE}/get-emails-from-name',
                json={
                    'firstName': first_name,
                    'lastName': last_name or '',
                    'domain': domain,
                    'access_token': token,
                },
                timeout=12,
            )
            if resp.status_code == 200:
                for em in resp.json().get('emails', []):
                    addr = em.get('email', '')
                    status = em.get('emailStatus', '')
                    if addr and status in ('valid', 'Accept All', 'unknown'):
                        return addr
            elif resp.status_code == 401:
                self._access_token = ''  # force token refresh next call
                logger.warning('[snov] 401 — access token invalidated')
        except Exception as exc:
            logger.warning('[snov] find_email error: %s', exc)
        return None

    def domain_search(self, domain: str) -> Optional[str]:
        """Return the first email found for a domain. Used when name is unknown."""
        if not self.is_configured() or not domain:
            return None
        token = self._get_token()
        if not token:
            return None
        self._throttle()
        try:
            resp = self.session.post(
                f'{SNOV_BASE}/get-domain-emails-count',
                json={'domain': domain, 'access_token': token},
                timeout=12,
            )
            if resp.status_code == 200:
                for em in resp.json().get('emails', []):
                    addr = em.get('email', '')
                    if addr:
                        return addr
        except Exception as exc:
            logger.warning('[snov] domain_search error: %s', exc)
        return None


_instance: Optional[SnovService] = None


def get_snov_service() -> SnovService:
    global _instance
    if _instance is None:
        _instance = SnovService()
    return _instance
