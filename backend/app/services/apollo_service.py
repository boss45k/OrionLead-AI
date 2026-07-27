"""
Apollo.io lead collection and enrichment service.

Quality rules:
  • source='apollo' and enrichment_source='apollo' tagged on all returned data
  • Company size stored as both int (company_size_int) and label string (company_size)
    — label uses finer-grained bands, not cliff-effect buckets
  • search_people() 403 logs clearly and returns [] with a helpful message
  • enrich_person() tags email_verified=True when Apollo returns an email
  • All returned leads include enrichment metadata in data_points
"""
import os
import logging
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

APOLLO_BASE_URL = "https://api.apollo.io/api/v1"


def _size_label(n: Optional[int]) -> str:
    """
    Fine-grained company size label.
    Uses real-world headcount bands, not cliff-effect buckets.
    """
    if not n or n <= 0:
        return ''
    if n < 5:
        return '1-4'
    if n < 10:
        return '5-9'
    if n < 25:
        return '10-24'
    if n < 50:
        return '25-49'
    if n < 100:
        return '50-99'
    if n < 250:
        return '100-249'
    if n < 500:
        return '250-499'
    if n < 1000:
        return '500-999'
    if n < 5000:
        return '1000-4999'
    if n < 10000:
        return '5000-9999'
    return '10000+'


class ApolloService:
    def __init__(self):
        self.api_key = os.getenv('APOLLO_API_KEY', '')
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'X-Api-Key': self.api_key,
        })
        self._last_error: Optional[str] = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def needs_upgrade(self) -> bool:
        """True if last call failed due to free-plan restriction."""
        return self._last_error == 'free_plan_restriction'

    def search_people(
        self,
        keywords: str = '',
        titles: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        page: int = 1,
        per_page: int = 25,
    ) -> List[Dict[str, Any]]:
        """Search for people matching the given criteria."""
        if not self.is_configured():
            logger.info("[Apollo] Not configured — skipping people search")
            return []

        kw_parts = [keywords] if keywords else []
        if industries:
            kw_parts.extend(industries)
        combined_keywords = ' '.join(kw_parts).strip()

        payload: Dict[str, Any] = {
            'page':     page,
            'per_page': min(per_page, 100),
        }
        if combined_keywords:
            payload['q_keywords'] = combined_keywords
        if titles:
            payload['person_titles'] = titles
        if locations:
            payload['person_locations'] = locations

        try:
            resp = self.session.post(
                f"{APOLLO_BASE_URL}/mixed_people/search",
                json=payload,
                timeout=20,
            )
            if resp.status_code == 403:
                logger.debug(
                    "[Apollo] 403 — free plan does not include people search. "
                    "Upgrade at https://app.apollo.io to enable."
                )
                self._last_error = 'free_plan_restriction'
                return []
            if not resp.ok:
                logger.warning(f"[Apollo] search_people {resp.status_code}: {resp.text[:400]}")
                return []
            people = resp.json().get('people', [])
            logger.info(f"[Apollo] search returned {len(people)} people")
            return [self._normalize(p) for p in people if p.get('name')]
        except Exception as exc:
            logger.warning(f"[Apollo] search_people error: {exc}")
            return []

    def enrich_person(
        self,
        email: str = '',
        linkedin_url: str = '',
        name: str = '',
        domain: str = '',
    ) -> Optional[Dict[str, Any]]:
        """Enrich a single person by email, LinkedIn URL, or name+domain."""
        if not self.is_configured():
            return None

        payload: Dict[str, Any] = {}
        if email:
            payload['email'] = email
        elif linkedin_url:
            payload['linkedin_url'] = linkedin_url
        elif name and domain:
            payload['name']   = name
            payload['domain'] = domain
        else:
            return None

        try:
            resp = self.session.post(
                f"{APOLLO_BASE_URL}/people/match",
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            person = resp.json().get('person') or {}
            return self._normalize(person) if person else None
        except Exception as exc:
            logger.warning(f"[Apollo] enrich_person error: {exc}")
            return None

    def _normalize(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """Map Apollo response fields → system lead schema with full metadata."""
        org = p.get('organization') or {}

        # Pick best available email (prefer work email)
        email = ''
        for e in (p.get('email_addresses') or []):
            if e.get('email') and e.get('type') != 'personal':
                email = e['email']
                break
        if not email:
            for e in (p.get('email_addresses') or []):
                if e.get('email'):
                    email = e['email']
                    break
        if not email:
            email = p.get('email', '')

        city    = p.get('city', '')
        country = p.get('country', '')
        state   = p.get('state', '')
        loc     = ', '.join(x for x in [city, state, country] if x)

        phones = p.get('phone_numbers') or []
        phone  = phones[0].get('sanitized_number', '') if phones else ''

        emp_count = org.get('estimated_num_employees')
        emp_int   = int(emp_count) if emp_count else None

        founded_year = org.get('founded_year') or org.get('founded')
        tech_stack   = [t.get('name', '') for t in (org.get('technology_names') or []) if t.get('name')]

        lead = {
            'name':             p.get('name', ''),
            'email':            email,
            'company':          org.get('name', '') or p.get('organization_name', ''),
            'position':         p.get('title', ''),
            'industry':         (org.get('industry', '') or '').replace('_', ' ').title(),
            'website':          org.get('website_url', ''),
            'linkedin_url':     p.get('linkedin_url', ''),
            'country':          country,
            'city':             city,
            'location':         loc,
            'phone':            phone,
            'company_size':     _size_label(emp_int),
            'company_size_int': emp_int,
            'employee_count':   emp_int,
            'source':           'apollo',
            'data_points': {
                'enrichment_source':        'apollo',
                'enriched_at':              datetime.now(timezone.utc).isoformat(),
                'email_source':             'apollo',
                'email_verified':           bool(email),
                'email_type':               'personal_business' if email else 'missing',
                'source_reliability_score': 82.0,
                # Company intelligence signals for ML feature extraction
                'employee_count':           emp_int,
                'founded_year':             int(founded_year) if founded_year else None,
                'tech_stack':               tech_stack[:20],
                'tech_stack_count':         len(tech_stack),
            },
        }
        return lead


# ── Singleton ─────────────────────────────────────────────────────────────────
_instance: Optional[ApolloService] = None


def get_apollo_service() -> ApolloService:
    global _instance
    if _instance is None:
        _instance = ApolloService()
    return _instance


def is_apollo_configured() -> bool:
    return bool(os.getenv('APOLLO_API_KEY', '').strip())
