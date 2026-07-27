"""
Crunchbase Lead Collector
=========================
Finds startup founders, executives, and investors from Crunchbase.

Two-path strategy:
  PATH A — Crunchbase Basic API (CRUNCHBASE_API_KEY set)
    POST /searches/people  → filter by role, location, funding round recency
    GET  /entities/people/{permalink} → full profile with LinkedIn, email

  PATH B — Public web scrape (no API key)
    Scrapes Crunchbase "recently funded companies" pages and recent-hire
    announcements via Google News RSS, then extracts founder/exec names.

Quality notes:
  • email_source = 'crunchbase' (curated professional data, no SMTP check)
  • email_verified = False  (Crunchbase confirms identity, not deliverability)
  • source_reliability_score = 78 (high-quality professional database)
  • LinkedIn URLs are extracted when present — enables PDL enrichment
  • Leads without at least a name + company are dropped

Rate limits (API path):
  • Basic plan: 200 calls/day — collector caps at 100 per run
"""

import os
import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

CRUNCHBASE_API  = "https://api.crunchbase.com/api/v4"
CRUNCHBASE_BASE = "https://www.crunchbase.com"

# Public endpoints that need no API key
_CB_RECENTLY_FUNDED_URL = (
    "https://www.crunchbase.com/discover/organizations"
    "?field_ids=short_description,primary_role,num_employees_enum"
    "&order=funded_at%20DESC"
)

_GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search"
    "?q={query}+crunchbase+founder+CEO+funding&hl=en-US&gl=US&ceid=US:en"
)

# Heuristic: titles that indicate decision-makers
_EXEC_TITLE_PATTERNS = re.compile(
    r'\b(Founder|Co-Founder|CEO|CTO|CFO|COO|President|Managing Director|'
    r'VP|Vice President|Director|Head of|Partner|Investor)\b',
    re.IGNORECASE,
)

_LINKEDIN_RE = re.compile(
    r'https?://(?:www\.)?linkedin\.com/in/([a-zA-Z0-9\-_%]+)/?',
    re.IGNORECASE,
)


def _extract_linkedin(text: str) -> str:
    m = _LINKEDIN_RE.search(text or '')
    return m.group(0).rstrip('/') if m else ''


def _is_exec_title(title: str) -> bool:
    return bool(_EXEC_TITLE_PATTERNS.search(title or ''))


class CrunchbaseCollector:
    def __init__(self):
        self.api_key = os.getenv('CRUNCHBASE_API_KEY', '')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
        })

    def is_api_configured(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------
    # PATH A: Crunchbase Basic API
    # ------------------------------------------------------------------

    def _api_search_people(
        self,
        locations: Optional[List[str]] = None,
        roles: Optional[List[str]] = None,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """Search Crunchbase people via Basic API."""
        if not self.is_api_configured():
            return []

        predicate_values = roles or ['founder', 'ceo', 'cto']
        predicates = [
            {'field_id': 'facet_ids', 'operator_id': 'includes', 'values': predicate_values},
        ]
        if locations:
            predicates.append({
                'field_id': 'location_identifiers',
                'operator_id': 'includes',
                'values': locations,
            })

        payload = {
            'field_ids': [
                'first_name', 'last_name', 'title', 'primary_job_title',
                'primary_organization', 'location_identifiers', 'short_description',
                'linkedin', 'profile_image_url',
            ],
            'order': [{'field_id': 'updated_at', 'sort': 'desc', 'nulls': 'last'}],
            'predicates': predicates,
            'limit': min(max_results, 100),
        }

        results = []
        try:
            resp = self.session.post(
                f"{CRUNCHBASE_API}/searches/people",
                json=payload,
                params={'user_key': self.api_key},
                timeout=20,
            )
            if resp.status_code == 401:
                logger.warning("[Crunchbase] API key invalid or expired")
                return []
            if resp.status_code == 429:
                logger.warning("[Crunchbase] API daily limit reached")
                return []
            if not resp.ok:
                logger.warning(f"[Crunchbase] API {resp.status_code}: {resp.text[:300]}")
                return []

            entities = resp.json().get('entities', [])
            logger.info(f"[Crunchbase] API search → {len(entities)} results")

            for entity in entities:
                props = entity.get('properties', {})
                lead = self._normalize_api_person(props)
                if lead:
                    results.append(lead)

        except Exception as exc:
            logger.warning(f"[Crunchbase] API search error: {exc}")

        return results

    def _normalize_api_person(self, props: dict) -> Optional[Dict[str, Any]]:
        first  = (props.get('first_name') or '').strip()
        last   = (props.get('last_name') or '').strip()
        name   = ' '.join(x for x in [first, last] if x)
        title  = (props.get('primary_job_title') or props.get('title') or '').strip()
        org    = props.get('primary_organization', {}) or {}
        company = (org.get('value') or '').strip()
        li_raw  = props.get('linkedin', {}) or {}
        linkedin = _extract_linkedin(li_raw.get('value', ''))

        loc_list = props.get('location_identifiers', []) or []
        location = ', '.join(
            loc.get('value', '') for loc in loc_list[:2] if loc.get('value')
        )

        if not name or not company:
            return None

        return {
            'name':         name,
            'email':        '',
            'company':      company,
            'position':     title,
            'website':      '',
            'linkedin_url': linkedin,
            'location':     location,
            'source':       'crunchbase',
            'data_points': {
                'enrichment_source':        'crunchbase',
                'enriched_at':              datetime.now(timezone.utc).isoformat(),
                'email_source':             'missing',
                'email_verified':           False,
                'source_reliability_score': 78.0,
            },
        }

    # ------------------------------------------------------------------
    # PATH B: Public web scrape (no API key)
    # ------------------------------------------------------------------

    def _scrape_recently_funded(self, max_results: int = 30) -> List[Dict[str, Any]]:
        """
        Scrape Crunchbase 'Discover' page for recently-funded companies,
        then use Google News to find named founders/execs from those companies.
        """
        results: List[Dict[str, Any]] = []

        # 1. Get recently funded company names from Crunchbase public JSON endpoint
        companies = self._fetch_public_companies(max_companies=15)
        logger.info(f"[Crunchbase] scrape found {len(companies)} companies")

        # 2. For each company, find its founder/exec via Google News RSS
        for company in companies:
            if len(results) >= max_results:
                break
            leads = self._find_execs_via_news(company, max_per_company=3)
            results.extend(leads)
            time.sleep(0.5)

        return results

    def _fetch_public_companies(self, max_companies: int = 15) -> List[str]:
        """Pull company names from Crunchbase trending/recent lists via RSS/public JSON."""
        companies = []
        # Use Google News to find recently-mentioned Crunchbase companies
        rss_url = (
            "https://news.google.com/rss/search"
            "?q=site:crunchbase.com+funding+round+2024+OR+2025&hl=en-US&gl=US&ceid=US:en"
        )
        try:
            resp = self.session.get(rss_url, timeout=15)
            if not resp.ok:
                return []
            soup = BeautifulSoup(resp.text, 'xml')
            for item in soup.find_all('item')[:40]:
                title = (item.find('title') or {}).get_text('') if item.find('title') else ''
                # Extract company name: "CompanyName raises $XM Series Y"
                m = re.match(
                    r'^([A-Z][a-zA-Z0-9\.\-\s]{2,40}?)\s+(?:raises|secures|closes|lands|gets)\b',
                    title,
                )
                if m:
                    companies.append(m.group(1).strip())
                if len(companies) >= max_companies:
                    break
        except Exception as exc:
            logger.debug(f"[Crunchbase] company RSS error: {exc}")

        return list(dict.fromkeys(companies))  # deduplicate, preserve order

    def _find_execs_via_news(
        self, company: str, max_per_company: int = 2
    ) -> List[Dict[str, Any]]:
        """Use Google News RSS to find exec names associated with a company."""
        results = []
        query = requests.utils.quote(f'"{company}" CEO OR founder OR CTO')
        rss_url = (
            f"https://news.google.com/rss/search"
            f"?q={query}&hl=en-US&gl=US&ceid=US:en"
        )
        try:
            resp = self.session.get(rss_url, timeout=12)
            if not resp.ok:
                return []
            soup = BeautifulSoup(resp.text, 'xml')

            for item in soup.find_all('item')[:5]:
                title = (item.find('title') or {}).get_text('') if item.find('title') else ''
                desc  = (item.find('description') or {}).get_text('') if item.find('description') else ''
                text  = f"{title} {desc}"

                # Find "Name, Title at Company" or "Name (Title)"
                name, position = self._extract_exec_name(text, company)
                if not name:
                    continue

                results.append({
                    'name':         name,
                    'email':        '',
                    'company':      company,
                    'position':     position,
                    'website':      '',
                    'linkedin_url': _extract_linkedin(text),
                    'location':     '',
                    'source':       'crunchbase',
                    'data_points': {
                        'enrichment_source':        'crunchbase_news',
                        'enriched_at':              datetime.now(timezone.utc).isoformat(),
                        'email_source':             'missing',
                        'email_verified':           False,
                        'source_reliability_score': 65.0,
                        'news_title':               title[:200],
                    },
                })
                if len(results) >= max_per_company:
                    break

        except Exception as exc:
            logger.debug(f"[Crunchbase] news scrape error for {company}: {exc}")

        return results

    _PERSON_RE = re.compile(
        r'\b([A-Z][a-z]{1,15}(?:\s+[A-Z][a-z]{1,15})+)'
        r'(?:\s*,\s*|\s+)([A-Z][a-zA-Z\s&]{3,40}?)'
        r'(?:\s+(?:of|at|@)\s+|\s+(?:and|is|says|said)\b)',
        re.UNICODE,
    )

    def _extract_exec_name(self, text: str, company: str) -> tuple:
        """Return (name, position) from news snippet, or ('', '')."""
        # Pattern: "John Smith, CEO of Acme" / "John Smith (Founder, Acme)"
        for m in self._PERSON_RE.finditer(text):
            name     = m.group(1).strip()
            raw_role = m.group(2).strip()
            if _is_exec_title(raw_role) and len(name.split()) >= 2:
                return name, raw_role
        return '', ''

    # ------------------------------------------------------------------
    # Public collect() entry point
    # ------------------------------------------------------------------

    def collect(
        self,
        keywords: str = '',
        locations: Optional[List[str]] = None,
        max_results: int = 40,
    ) -> List[Dict[str, Any]]:
        """
        Collect startup founders / executives from Crunchbase.
        All returned leads must pass evaluate_lead_quality() before saving.
        """
        results: List[Dict[str, Any]] = []
        seen_keys: set = set()

        def _add(leads):
            for ld in leads:
                key = (ld.get('name', '') + '|' + ld.get('company', '')).lower()
                if key in seen_keys or len(key) < 4:
                    continue
                seen_keys.add(key)
                results.append(ld)

        if self.is_api_configured():
            _add(self._api_search_people(locations=locations, max_results=max_results))
        else:
            _add(self._scrape_recently_funded(max_results=max_results))

        logger.info(f"[Crunchbase] collected {len(results)} candidate leads")
        return results[:max_results]


# ── Singleton ──────────────────────────────────────────────────────────────────
_instance: Optional[CrunchbaseCollector] = None


def get_crunchbase_collector() -> CrunchbaseCollector:
    global _instance
    if _instance is None:
        _instance = CrunchbaseCollector()
    return _instance
