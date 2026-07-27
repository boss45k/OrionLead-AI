"""
Explorium B2B Data Service
==========================
Integrates the Explorium API for three use-cases:

  1. enrich_lead(lead)
       Given a lead with name + company (or email), match it to an Explorium
       prospect ID then pull verified contact details (work email, phone).

  2. search_prospects(titles, locations, industries, ...)
       Discover new prospects by job title / location / industry filters.
       Returns leads in the system's standard schema — all pass through
       evaluate_lead_quality() before saving.

  3. enrich_company(company, domain)
       Pull firmographic data (size, industry, revenue, tech stack) for a
       company and merge it back into any matching leads.

Quality rules:
  • source = 'explorium', enrichment_source = 'explorium'
  • Emails returned by Explorium are marked email_verified = True
    (Explorium verifies contact details before returning them)
  • source_reliability_score = 85
  • Leads with no name AND no company are never returned
  • All returned leads still pass through evaluate_lead_quality()

API details:
  Base URL : https://api.explorium.ai/v1
  Auth     : header  api_key: <key>
  Rate     : 200 qpm
"""

import os
import logging
import requests
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EXPLORIUM_BASE = "https://api.explorium.ai/v1"
_RELIABILITY   = 85.0


class ExploriumService:
    def __init__(self):
        self.api_key = os.getenv('EXPLORIUM_API_KEY', '')
        self.session = requests.Session()
        self.session.headers.update({
            'accept':       'application/json',
            'content-type': 'application/json',
            'api_key':      self.api_key,
        })

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _post(self, path: str, payload: dict, timeout: int = 20) -> Optional[dict]:
        if not self.is_configured():
            return None
        try:
            resp = self.session.post(
                f"{EXPLORIUM_BASE}{path}",
                json=payload,
                timeout=timeout,
            )
            if resp.status_code == 401:
                logger.warning("[Explorium] 401 — invalid API key")
                return None
            if resp.status_code == 429:
                logger.warning("[Explorium] 429 — rate limit hit")
                return None
            if not resp.ok:
                lvl = logger.debug if resp.status_code == 404 else logger.warning
                lvl(f"[Explorium] {resp.status_code} {path}: {resp.text[:200]}")
                return None
            return resp.json()
        except Exception as exc:
            logger.warning(f"[Explorium] request error {path}: {exc}")
            return None

    def _get(self, path: str, params: dict = None, timeout: int = 15) -> Optional[dict]:
        if not self.is_configured():
            return None
        try:
            resp = self.session.get(
                f"{EXPLORIUM_BASE}{path}",
                params=params or {},
                timeout=timeout,
            )
            if not resp.ok:
                logger.warning(f"[Explorium] GET {resp.status_code} {path}")
                return None
            return resp.json()
        except Exception as exc:
            logger.warning(f"[Explorium] GET error {path}: {exc}")
            return None

    # ------------------------------------------------------------------
    # 1. Match a person → get their Explorium prospect_id
    # ------------------------------------------------------------------

    def _match_prospect(
        self,
        name: str = '',
        company: str = '',
        email: str = '',
        domain: str = '',
    ) -> Optional[str]:
        """Return Explorium prospect_id or None.

        API requires body: {"prospects_to_match": [{...}]}
        Each item uses 'full_name' (not 'name') and supports
        email | full_name+company_name | linkedin.
        """
        prospect: Dict[str, Any] = {}
        if email:
            prospect['email'] = email
        elif name and (company or domain):
            prospect['full_name']    = name
            prospect['company_name'] = company or domain
        else:
            return None

        data = self._post('/prospects/match', {'prospects_to_match': [prospect]})
        if not data:
            return None

        # Response: {"matched_prospects": [{"input": {...}, "prospect_id": "..."}]}
        matched = data.get('matched_prospects', [])
        if matched and isinstance(matched, list):
            return matched[0].get('prospect_id') or None
        return None

    # ------------------------------------------------------------------
    # 2. Enrich a prospect by ID → get contact details
    # ------------------------------------------------------------------

    def _enrich_prospect(self, prospect_id: str) -> Optional[Dict[str, Any]]:
        """Fetch verified contact details for a known prospect_id."""
        data = self._post('/prospects/enrich', {'prospect_ids': [prospect_id]})
        if not data:
            return None
        # Response: {"prospects": [{...}]}
        prospects = data.get('prospects') or data.get('data') or []
        if isinstance(prospects, list) and prospects:
            return prospects[0]
        return data  # fallback: treat whole response as the record

    # ------------------------------------------------------------------
    # 3. Public: enrich a lead dict
    # ------------------------------------------------------------------

    def enrich_lead(self, lead: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Enrich a lead using Explorium.

        Flow:
          1. Match name+company (or email) → prospect_id
          2. Enrich prospect_id → verified email, phone, LinkedIn, title
          3. Return enriched fields merged into the lead dict

        Returns None if Explorium has no record for this person.
        """
        if not self.is_configured():
            return None

        name    = (lead.get('name') or '').strip()
        company = (lead.get('company') or '').strip()
        email   = (lead.get('email') or '').strip()
        website = (lead.get('website') or '').strip()

        # Generic catch-all emails (info@, contact@, etc.) won't match a specific
        # prospect — only pass a personal email to the match API.
        _GENERIC = {'info', 'contact', 'hello', 'support', 'sales', 'admin',
                    'team', 'marketing', 'office', 'enquiries', 'enquiry'}
        if email and email.split('@')[0].lower() in _GENERIC:
            email = ''

        # Need at least email OR (name + company/domain) to attempt a match
        if not email and not (name and company):
            return None

        # Extract bare domain from website
        domain = ''
        if website:
            from urllib.parse import urlparse
            host = urlparse(website).netloc or website
            domain = host.replace('www.', '').split('/')[0]

        prospect_id = self._match_prospect(
            name=name, company=company, email=email, domain=domain,
        )
        if not prospect_id:
            logger.debug(f"[Explorium] no match for '{name}' @ '{company}'")
            return None

        raw = self._enrich_prospect(prospect_id)
        if not raw:
            return None

        return self._normalize_prospect(raw, lead)

    def _normalize_prospect(
        self, raw: Dict[str, Any], original: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Map Explorium prospect response onto the system lead schema."""
        # Explorium may return a nested 'data' or 'contact' wrapper
        p = raw.get('data') or raw.get('contact') or raw

        def _pick(*keys):
            for k in keys:
                v = p.get(k)
                if v:
                    return str(v).strip()
            return ''

        email      = _pick('email', 'work_email', 'professional_email')
        phone      = _pick('phone', 'phone_number', 'mobile_phone', 'direct_phone')
        name       = _pick('full_name', 'name') or original.get('name', '')
        title      = _pick('job_title', 'title', 'position') or original.get('position', '')
        company    = _pick('company_name', 'company', 'employer') or original.get('company', '')
        linkedin   = _pick('linkedin_url', 'linkedin') or original.get('linkedin_url', '')
        location   = _pick('location', 'city_state', 'address') or original.get('location', '')
        country    = _pick('country') or original.get('country', '')
        city       = _pick('city') or original.get('city', '')
        industry   = _pick('industry', 'sector') or original.get('industry', '')
        website    = _pick('company_website', 'website') or original.get('website', '')

        # Company size from Explorium firmographics
        emp_count  = p.get('employee_count') or p.get('company_size')
        emp_int    = int(emp_count) if emp_count and str(emp_count).isdigit() else None

        enriched = {
            'name':             name,
            'email':            email,
            'phone':            phone,
            'company':          company,
            'position':         title,
            'industry':         industry,
            'website':          website,
            'linkedin_url':     linkedin,
            'location':         location,
            'country':          country,
            'city':             city,
            'company_size_int': emp_int,
            'source':           original.get('source', 'explorium'),
            'employee_count': emp_int,
            'data_points': {
                'enrichment_source':        'explorium',
                'enriched_at':              datetime.now(timezone.utc).isoformat(),
                'email_source':             'explorium' if email else 'missing',
                'email_verified':           bool(email),
                'email_type':               'personal_business' if email else 'missing',
                'source_reliability_score': _RELIABILITY,
                'explorium_prospect_id':    p.get('prospect_id') or p.get('id', ''),
                'employee_count':           emp_int,
            },
        }

        # Carry over original data_points not overwritten by enrichment
        orig_dp = original.get('data_points') or {}
        for k, v in orig_dp.items():
            if k not in enriched['data_points'] or not enriched['data_points'][k]:
                enriched['data_points'][k] = v

        return enriched

    # ------------------------------------------------------------------
    # 4. Public: search / discover new prospects
    # ------------------------------------------------------------------

    def search_prospects(
        self,
        titles:     Optional[List[str]] = None,
        locations:  Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        keywords:   str = '',
        seniority:  Optional[List[str]] = None,
        page:       int = 1,
        per_page:   int = 25,
    ) -> List[Dict[str, Any]]:
        """
        Find new B2B prospects using Explorium's fetch_prospects endpoint.
        Returns raw leads in system schema — must pass evaluate_lead_quality() before saving.
        """
        if not self.is_configured():
            return []

        # API requires filters nested under "filters" key; pagination uses "page_size"
        filters: Dict[str, Any] = {}
        if titles:
            filters['job_title'] = {
                'values': titles,
                'include_related_job_titles': True,
            }
        if locations:
            # Explorium expects ISO country codes; pass as-is and let the API handle
            filters['country_code'] = {'values': locations}
        if seniority:
            filters['seniority'] = {'values': seniority}

        payload: Dict[str, Any] = {
            'mode':      'full',
            'page':      page,
            'page_size': min(per_page, 100),
        }
        if filters:
            payload['filters'] = filters
        if keywords:
            payload['keywords'] = keywords

        data = self._post('/prospects/fetch_prospects', payload)
        if not data:
            return []

        items = data if isinstance(data, list) else (
            data.get('prospects') or data.get('results') or data.get('data') or []
        )
        logger.info(f"[Explorium] search_prospects → {len(items)} results")

        results = []
        for item in items:
            lead = self._normalize_search_result(item)
            if lead:
                results.append(lead)
        return results

    def _normalize_search_result(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Map a fetch_prospects result item to the system lead schema."""
        def _pick(*keys):
            for k in keys:
                v = item.get(k)
                if v:
                    return str(v).strip()
            return ''

        name    = _pick('full_name', 'name')
        company = _pick('company_name', 'company', 'employer')
        if not name and not company:
            return None

        email    = _pick('email', 'work_email')
        phone    = _pick('phone', 'phone_number', 'direct_phone')
        title    = _pick('job_title', 'title')
        linkedin = _pick('linkedin_url', 'linkedin')
        location = _pick('location', 'city_state')
        country  = _pick('country')
        city     = _pick('city')
        industry = _pick('industry', 'sector')
        website  = _pick('company_website', 'website')

        emp_count = item.get('employee_count') or item.get('company_size')
        emp_int   = int(emp_count) if emp_count and str(emp_count).isdigit() else None

        return {
            'name':             name,
            'email':            email,
            'phone':            phone,
            'company':          company,
            'position':         title,
            'industry':         industry,
            'website':          website,
            'linkedin_url':     linkedin,
            'location':         location,
            'country':          country,
            'city':             city,
            'company_size_int': emp_int,
            'source':           'explorium',
            'data_points': {
                'enrichment_source':        'explorium',
                'enriched_at':              datetime.now(timezone.utc).isoformat(),
                'email_source':             'explorium' if email else 'missing',
                'email_verified':           bool(email),
                'email_type':               'personal_business' if email else 'missing',
                'source_reliability_score': _RELIABILITY,
                'explorium_prospect_id':    _pick('prospect_id', 'id'),
            },
        }

    # ------------------------------------------------------------------
    # 5. Company enrichment
    # ------------------------------------------------------------------

    def enrich_company(
        self,
        company: str = '',
        domain:  str = '',
    ) -> Optional[Dict[str, Any]]:
        """
        Get firmographic data for a company.
        Returns a dict of enrichment fields to merge into matching leads.
        """
        if not self.is_configured() or not (company or domain):
            return None

        payload: Dict[str, Any] = {}
        if domain:
            payload['domain'] = domain
        elif company:
            payload['company_name'] = company

        match_data = self._post('/businesses/match', payload)
        if not match_data:
            return None

        items = match_data if isinstance(match_data, list) else (
            match_data.get('businesses') or match_data.get('results') or []
        )
        if not items:
            return None

        business_id = (items[0].get('business_id') or items[0].get('id', '')) if items else ''
        if not business_id:
            return None

        enrich_data = self._post('/businesses/enrich', {'business_id': business_id})
        if not enrich_data:
            return None

        b = enrich_data.get('data') or enrich_data
        emp = b.get('employee_count') or b.get('num_employees')
        return {
            'industry':         (b.get('industry') or b.get('sector') or '').replace('_', ' ').title(),
            'website':          b.get('website') or b.get('domain') or '',
            'company_size_int': int(emp) if emp and str(emp).isdigit() else None,
            'country':          b.get('country') or b.get('hq_country') or '',
            'city':             b.get('city') or b.get('hq_city') or '',
        }

    # ------------------------------------------------------------------
    # 6. Bulk enrich a list of leads (used in enrichment cascade)
    # ------------------------------------------------------------------

    def bulk_enrich(
        self,
        leads: List[Dict[str, Any]],
        max_calls: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Run enrich_lead() on every lead that is missing an email or phone.
        Caps at max_calls to stay inside quota.
        Returns the same list with enriched fields filled in.
        """
        enriched_count = 0
        for i, lead in enumerate(leads):
            if enriched_count >= max_calls:
                break
            # Only call if there's something to gain
            if lead.get('email') and lead.get('phone'):
                continue
            if not (lead.get('name') or lead.get('company')):
                continue
            result = self.enrich_lead(lead)
            if result:
                leads[i] = result
                enriched_count += 1

        logger.info(f"[Explorium] bulk_enrich: enriched {enriched_count}/{len(leads)} leads")
        return leads


# ── Singleton ──────────────────────────────────────────────────────────────────
_instance: Optional[ExploriumService] = None


def get_explorium_service() -> ExploriumService:
    global _instance
    if _instance is None:
        _instance = ExploriumService()
    return _instance


def is_explorium_configured() -> bool:
    return bool(os.getenv('EXPLORIUM_API_KEY', '').strip())
