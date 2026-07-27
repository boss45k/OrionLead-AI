"""
Public Web Data Collector
Collects lead data from public web sources by country/region.
Sources: Business directories, public company registries, news sites, job boards.
Uses ethical scraping with rate limiting and robots.txt compliance.
"""

import os
import re
import time
import logging
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urljoin, urlparse, quote_plus

logger = logging.getLogger(__name__)

# ── New production-grade modules ─────────────────────────────────────────────
try:
    from app.services.lead_extractor import extract_all as _ext_extract_all, _email_type
    from app.services.lead_validator import validate_and_score, DuplicateFilter
    _MODULES_AVAILABLE = True
except ImportError as _imp_err:
    logger.warning(f"lead_extractor/validator/fallback not available: {_imp_err}")
    _MODULES_AVAILABLE = False

# ── Smart pipeline helpers ────────────────────────────────────────────────────
try:
    from app.services.name_validator import pre_filter_lead, is_cdn_email as _cdn_check
    from app.services.candidate_cache import get_candidate_cache as _get_cache
    from app.services.intent_detector import detect_intent as _detect_intent
    _PIPELINE_AVAILABLE = True
except ImportError as _pip_err:
    logger.warning(f"[web] smart pipeline modules not available: {_pip_err}")
    _PIPELINE_AVAILABLE = False

    def pre_filter_lead(lead: dict) -> "tuple[bool, str]":  # type: ignore[misc]
        return True, ''

    def _cdn_check(email: str) -> bool:    # type: ignore[misc]
        return False

    def _detect_intent(*a, **kw) -> dict:  # type: ignore[misc]
        return {'buying_intent': 'none', 'intent_confidence': 0.0}

# Countries with their search engines and directory URLs
COUNTRY_SOURCES = {
    'US': {
        'name': 'United States',
        'directories': [
            'https://www.yelp.com/search?find_desc={query}&find_loc={city}',
            'https://www.bbb.org/search?find_text={query}&find_loc={city}',
        ],
        'search_tld': 'com',
        'default_cities': ['New York', 'San Francisco', 'Los Angeles', 'Chicago', 'Houston'],
    },
    'UK': {
        'name': 'United Kingdom',
        'directories': [
            'https://www.yell.com/ucs/UcsSearchAction.do?keywords={query}&location={city}',
        ],
        'search_tld': 'co.uk',
        'default_cities': ['London', 'Manchester', 'Birmingham', 'Leeds', 'Edinburgh'],
    },
    'DE': {
        'name': 'Germany',
        'directories': [
            'https://www.gelbeseiten.de/Suche/{query}/{city}',
        ],
        'search_tld': 'de',
        'default_cities': ['Berlin', 'Munich', 'Hamburg', 'Frankfurt', 'Cologne'],
    },
    'FR': {
        'name': 'France',
        'directories': [
            'https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui={query}&ou={city}',
        ],
        'search_tld': 'fr',
        'default_cities': ['Paris', 'Lyon', 'Marseille', 'Toulouse', 'Nice'],
    },
    'AE': {
        'name': 'United Arab Emirates',
        'directories': [
            'https://www.yellowpages.ae/search/{query}/{city}',
        ],
        'search_tld': 'ae',
        'default_cities': ['Dubai', 'Abu Dhabi', 'Sharjah', 'Ajman', 'Fujairah'],
    },
    'SA': {
        'name': 'Saudi Arabia',
        'directories': [
            'https://www.yellowpages.com.sa/search/{query}/{city}',
        ],
        'search_tld': 'com.sa',
        'default_cities': ['Riyadh', 'Jeddah', 'Mecca', 'Medina', 'Dammam'],
    },
    'IN': {
        'name': 'India',
        'directories': [
            'https://www.justdial.com/{city}/{query}',
        ],
        'search_tld': 'co.in',
        'default_cities': ['Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Chennai'],
    },
    'CA': {
        'name': 'Canada',
        'directories': [
            'https://www.yellowpages.ca/search/si/1/{query}/{city}',
        ],
        'search_tld': 'ca',
        'default_cities': ['Toronto', 'Vancouver', 'Montreal', 'Calgary', 'Ottawa'],
    },
    'AU': {
        'name': 'Australia',
        'directories': [
            'https://www.yellowpages.com.au/find/{query}/{city}',
        ],
        'search_tld': 'com.au',
        'default_cities': ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide'],
    },
    'JP': {
        'name': 'Japan',
        'directories': [],
        'search_tld': 'co.jp',
        'default_cities': ['Tokyo', 'Osaka', 'Yokohama', 'Nagoya', 'Sapporo'],
    },
    'BR': {
        'name': 'Brazil',
        'directories': [],
        'search_tld': 'com.br',
        'default_cities': ['São Paulo', 'Rio de Janeiro', 'Brasília', 'Salvador', 'Fortaleza'],
    },
    'EG': {
        'name': 'Egypt',
        'directories': [],
        'search_tld': 'com.eg',
        'default_cities': ['Cairo', 'Alexandria', 'Giza', 'Luxor', 'Aswan'],
    },
    'NG': {
        'name': 'Nigeria',
        'directories': [],
        'search_tld': 'com.ng',
        'default_cities': ['Lagos', 'Abuja', 'Port Harcourt', 'Kano', 'Ibadan'],
    },
    'ZA': {
        'name': 'South Africa',
        'directories': [],
        'search_tld': 'co.za',
        'default_cities': ['Johannesburg', 'Cape Town', 'Durban', 'Pretoria', 'Port Elizabeth'],
    },
    'SG': {
        'name': 'Singapore',
        'directories': [],
        'search_tld': 'com.sg',
        'default_cities': ['Singapore'],
    },
    'KR': {
        'name': 'South Korea',
        'directories': [],
        'search_tld': 'co.kr',
        'default_cities': ['Seoul', 'Busan', 'Incheon', 'Daegu', 'Daejeon'],
    },
    'MX': {
        'name': 'Mexico',
        'directories': [],
        'search_tld': 'com.mx',
        'default_cities': ['Mexico City', 'Guadalajara', 'Monterrey', 'Puebla', 'Tijuana'],
    },
    'TR': {
        'name': 'Turkey',
        'directories': [],
        'search_tld': 'com.tr',
        'default_cities': ['Istanbul', 'Ankara', 'Izmir', 'Bursa', 'Antalya'],
    },
    'ID': {
        'name': 'Indonesia',
        'directories': [],
        'search_tld': 'co.id',
        'default_cities': ['Jakarta', 'Surabaya', 'Bandung', 'Medan', 'Semarang'],
    },
    'TH': {
        'name': 'Thailand',
        'directories': [],
        'search_tld': 'co.th',
        'default_cities': ['Bangkok', 'Chiang Mai', 'Phuket', 'Pattaya', 'Nonthaburi'],
    },
    'PH': {
        'name': 'Philippines',
        'directories': [],
        'search_tld': 'com.ph',
        'default_cities': ['Manila', 'Quezon City', 'Cebu', 'Davao', 'Makati'],
    },
    'MY': {
        'name': 'Malaysia',
        'directories': [],
        'search_tld': 'com.my',
        'default_cities': ['Kuala Lumpur', 'Penang', 'Johor Bahru', 'Ipoh', 'Kota Kinabalu'],
    },
    'PK': {
        'name': 'Pakistan',
        'directories': [],
        'search_tld': 'com.pk',
        'default_cities': ['Karachi', 'Lahore', 'Islamabad', 'Rawalpindi', 'Faisalabad'],
    },
    'KE': {
        'name': 'Kenya',
        'directories': [],
        'search_tld': 'co.ke',
        'default_cities': ['Nairobi', 'Mombasa', 'Kisumu', 'Nakuru', 'Eldoret'],
    },
    'GH': {
        'name': 'Ghana',
        'directories': [],
        'search_tld': 'com.gh',
        'default_cities': ['Accra', 'Kumasi', 'Tamale', 'Takoradi', 'Cape Coast'],
    },
    'MA': {
        'name': 'Morocco',
        'directories': [],
        'search_tld': 'co.ma',
        'default_cities': ['Casablanca', 'Rabat', 'Marrakech', 'Fez', 'Tangier'],
    },
    'CO': {
        'name': 'Colombia',
        'directories': [],
        'search_tld': 'com.co',
        'default_cities': ['Bogotá', 'Medellín', 'Cali', 'Barranquilla', 'Cartagena'],
    },
    'CL': {
        'name': 'Chile',
        'directories': [],
        'search_tld': 'cl',
        'default_cities': ['Santiago', 'Valparaíso', 'Concepción', 'Antofagasta', 'Viña del Mar'],
    },
    'AR': {
        'name': 'Argentina',
        'directories': [],
        'search_tld': 'com.ar',
        'default_cities': ['Buenos Aires', 'Córdoba', 'Rosario', 'Mendoza', 'La Plata'],
    },
    'PL': {
        'name': 'Poland',
        'directories': [],
        'search_tld': 'pl',
        'default_cities': ['Warsaw', 'Krakow', 'Gdansk', 'Wroclaw', 'Poznan'],
    },
    'NL': {
        'name': 'Netherlands',
        'directories': [],
        'search_tld': 'nl',
        'default_cities': ['Amsterdam', 'Rotterdam', 'The Hague', 'Utrecht', 'Eindhoven'],
    },
    'SE': {
        'name': 'Sweden',
        'directories': [],
        'search_tld': 'se',
        'default_cities': ['Stockholm', 'Gothenburg', 'Malmö', 'Uppsala', 'Linköping'],
    },
    'CH': {
        'name': 'Switzerland',
        'directories': [],
        'search_tld': 'ch',
        'default_cities': ['Zurich', 'Geneva', 'Basel', 'Bern', 'Lausanne'],
    },
    'IT': {
        'name': 'Italy',
        'directories': [],
        'search_tld': 'it',
        'default_cities': ['Milan', 'Rome', 'Turin', 'Florence', 'Naples'],
    },
    'ES': {
        'name': 'Spain',
        'directories': [],
        'search_tld': 'es',
        'default_cities': ['Madrid', 'Barcelona', 'Valencia', 'Seville', 'Bilbao'],
    },
    'QA': {
        'name': 'Qatar',
        'directories': [],
        'search_tld': 'qa',
        'default_cities': ['Doha', 'Al Wakrah', 'Al Khor', 'Umm Salal', 'Al Rayyan'],
    },
    'KW': {
        'name': 'Kuwait',
        'directories': [],
        'search_tld': 'com.kw',
        'default_cities': ['Kuwait City', 'Hawalli', 'Salmiya', 'Farwaniya', 'Fahaheel'],
    },
    'BH': {
        'name': 'Bahrain',
        'directories': [],
        'search_tld': 'bh',
        'default_cities': ['Manama', 'Muharraq', 'Riffa', 'Hamad Town', 'Isa Town'],
    },
    'OM': {
        'name': 'Oman',
        'directories': [],
        'search_tld': 'com.om',
        'default_cities': ['Muscat', 'Salalah', 'Sohar', 'Nizwa', 'Sur'],
    },
    'JO': {
        'name': 'Jordan',
        'directories': [],
        'search_tld': 'jo',
        'default_cities': ['Amman', 'Zarqa', 'Irbid', 'Aqaba', 'Madaba'],
    },
    'LB': {
        'name': 'Lebanon',
        'directories': [],
        'search_tld': 'com.lb',
        'default_cities': ['Beirut', 'Tripoli', 'Sidon', 'Jounieh', 'Byblos'],
    },
    'NZ': {
        'name': 'New Zealand',
        'directories': [],
        'search_tld': 'co.nz',
        'default_cities': ['Auckland', 'Wellington', 'Christchurch', 'Hamilton', 'Tauranga'],
    },
    'IE': {
        'name': 'Ireland',
        'directories': [],
        'search_tld': 'ie',
        'default_cities': ['Dublin', 'Cork', 'Galway', 'Limerick', 'Waterford'],
    },
    'IL': {
        'name': 'Israel',
        'directories': [],
        'search_tld': 'co.il',
        'default_cities': ['Tel Aviv', 'Jerusalem', 'Haifa', 'Herzliya', 'Ramat Gan'],
    },
}

# Industry keywords for classification
INDUSTRY_KEYWORDS = {
    'technology': ['software', 'tech', 'it ', 'saas', 'cloud', 'digital', 'cyber', 'data', 'ai', 'ml'],
    'healthcare': ['health', 'medical', 'pharma', 'hospital', 'clinic', 'biotech', 'wellness'],
    'finance': ['finance', 'bank', 'insurance', 'investment', 'fintech', 'accounting', 'trading'],
    'manufacturing': ['manufacturing', 'industrial', 'factory', 'production', 'assembly'],
    'retail': ['retail', 'shop', 'store', 'ecommerce', 'e-commerce', 'marketplace'],
    'real_estate': ['real estate', 'property', 'construction', 'building', 'architect'],
    'education': ['education', 'university', 'school', 'training', 'academy', 'learning'],
    'consulting': ['consulting', 'advisory', 'management', 'strategy', 'professional services'],
    'marketing': ['marketing', 'advertising', 'agency', 'media', 'branding', 'pr '],
    'logistics': ['logistics', 'shipping', 'transport', 'supply chain', 'freight', 'delivery'],
    'food_beverage': ['restaurant', 'food', 'beverage', 'catering', 'cafe', 'dining'],
    'energy': ['energy', 'oil', 'gas', 'solar', 'renewable', 'power', 'utility'],
    'automotive': ['automotive', 'car', 'vehicle', 'auto', 'motor', 'dealer'],
    'telecom': ['telecom', 'mobile', 'wireless', 'network', 'communication'],
}

# ── Smart pipeline constants ──────────────────────────────────────────────────

# Country TLDs — used to generate site:.tld targeted searches (highest quality)
_COUNTRY_TLDS: dict = {
    'AE': 'ae',      'SA': 'com.sa',  'KW': 'com.kw',  'QA': 'qa',
    'BH': 'bh',      'OM': 'com.om',  'LB': 'lb',      'JO': 'jo',
    'EG': 'eg',      'IQ': 'iq',      'TR': 'com.tr',
    'DE': 'de',      'FR': 'fr',      'IT': 'it',      'ES': 'es',
    'NL': 'nl',      'PL': 'pl',      'SE': 'se',      'CH': 'ch',
    'IE': 'ie',      'IN': 'co.in',   'PK': 'com.pk',  'MY': 'com.my',
    'PH': 'com.ph',  'ID': 'co.id',   'TH': 'co.th',   'SG': 'com.sg',
    'AU': 'com.au',  'NZ': 'co.nz',   'CA': 'ca',      'MX': 'com.mx',
    'BR': 'com.br',  'CL': 'cl',      'AR': 'com.ar',  'CO': 'co',
    'PE': 'pe',      'MA': 'ma',      'KE': 'co.ke',   'GH': 'com.gh',
    'ZA': 'co.za',   'IL': 'co.il',   'NG': 'com.ng',
}

# Generic single-word names that are never real company names
_GENERIC_COMPANY_NAMES: frozenset = frozenset({
    'online', 'digital', 'global', 'solutions', 'services', 'technology',
    'tech', 'group', 'company', 'business', 'consulting', 'media',
    'network', 'networks', 'systems', 'software', 'data', 'startup',
    'startups', 'dictionary', 'thesaurus', 'encyclopedia', 'directory',
    'news', 'blog', 'home', 'website', 'web', 'store', 'shop', 'market',
    'hub', 'center', 'centre', 'platform', 'portal', 'analytics', 'cloud',
    'connect', 'smart', 'pro', 'plus', 'app', 'apps', 'ai', 'io', 'co',
    'corp', 'inc', 'ltd', 'llc', 'gmbh', 'srl', 'careers', 'jobs',
    'contact', 'about', 'team', 'people', 'staff', 'enterprise',
})

# Title patterns that indicate an article/listicle — NOT a company page
_ARTICLE_TITLE_SIGNALS: tuple = (
    'top ', 'best ', 'leading ', 'list of ', ' companies in ',
    ' agencies in ', ' startups in ', ' firms in ', 'comparison',
    'guide to ', 'how to ', 'what is ', 'ranking of', 'review of',
    '2024 ', '2025 ', '2026 ', 'the best', 'top ten', 'top 10',
)

# Globally irrelevant domains — never produce local leads
_GLOBALLY_IRRELEVANT_DOMAINS: frozenset = frozenset({
    'nordstrom.com', 'walmart.com', 'target.com', 'costco.com', 'macys.com',
    'ebay.com', 'aliexpress.com', 'dictionary.com', 'merriam-webster.com',
    'thesaurus.com', 'startupdata.com', 'startupblink.com',
    'github.com', 'gitlab.com', 'stackoverflow.com', 'npmjs.com', 'pypi.org',
    'office.com', 'microsoft.com', 'apple.com', 'samsung.com',
})


class PublicWebCollector:
    """Collects business/lead data from public web sources"""

    def __init__(self, rate_limit: float = 1.0, timeout: int = 5):
        self.rate_limit = rate_limit  # seconds between requests
        self.timeout = timeout
        self._ai_svc = None   # lazy-loaded on first use
        self.session = requests.Session()
        try:
            import certifi as _certifi
            self.session.verify = _certifi.where()
        except ImportError:
            pass
        self._user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
        ]
        self._ua_index = 0
        self.session.headers.update({
            'User-Agent': self._user_agents[0],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        self._last_request_time = 0

    def _get_ai(self):
        """Lazy-load AIService singleton (Gemini primary, Groq fallback)."""
        if self._ai_svc is None:
            try:
                from app.services.gemini_service import get_ai_service
                self._ai_svc = get_ai_service()
            except Exception:
                pass
        return self._ai_svc

    def _ai_extract_missing(self, text: str, lead: Dict[str, Any], url: str) -> Dict[str, Any]:
        """
        Use Gemini to fill fields that regex extraction missed.

        Only fires when at least one of (contact name, position, industry) is empty
        AND an AI provider is available. Uses a tight token budget (max_tokens=150)
        so it adds minimal latency — Groq fallback keeps it under 2 s even if Gemini
        is slow.

        Fields filled:
          contact_name → lead['name']  (only if name is still the company name / unknown)
          position     → lead['position']
          industry     → lead['industry']
          interests    → lead['interests']
        """
        ai = self._get_ai()
        if not ai or not ai.is_available:
            return lead

        name_is_placeholder = (
            not lead.get('name')
            or lead.get('name') == lead.get('company')
            or lead.get('name') == 'Unknown Contact'
        )
        missing = []
        if name_is_placeholder:
            missing.append('contact_name')
        if not lead.get('position'):
            missing.append('position')
        if not lead.get('industry'):
            missing.append('industry')

        if not missing:
            return lead   # regex got everything — skip AI call

        known = (
            f"company={lead.get('company') or '?'}, "
            f"country={lead.get('country') or '?'}, "
            f"email={lead.get('email') or '?'}"
        )

        prompt = (
            f"Extract B2B lead details from this webpage.\n"
            f"URL: {url}\n"
            f"Known: {known}\n"
            f"Need: {', '.join(missing)}\n\n"
            f"Page text:\n{text[:1500]}\n\n"
            f'Return ONLY JSON (use "" if not found):\n'
            f'{{"contact_name":"<human name, not company>","position":"<job title>",'
            f'"industry":"<Technology|Finance|Healthcare|Retail|Manufacturing|Education|'
            f'Real Estate|Legal|Consulting|Marketing|Hospitality|Construction|Other>",'
            f'"interests":["<keyword1>","<keyword2>"]}}'
        )

        try:
            raw = ai._generate(
                prompt,
                system="B2B data extraction expert. Return JSON only.",
                temperature=0.1,
                max_tokens=150,
            )
            parsed = ai._parse_json(raw or '')
            if not parsed:
                return lead

            if parsed.get('contact_name') and name_is_placeholder:
                lead['name'] = parsed['contact_name']
            if parsed.get('position') and not lead.get('position'):
                lead['position'] = parsed['position']
            if parsed.get('industry') and not lead.get('industry'):
                lead['industry'] = parsed['industry']
            if parsed.get('interests') and not lead.get('interests'):
                lead['interests'] = parsed['interests']

            logger.debug(
                f"AI filled missing fields for {url}: "
                f"name={lead.get('name')} pos={lead.get('position')} "
                f"industry={lead.get('industry')}"
            )
        except Exception as e:
            logger.debug(f"AI extraction skipped for {url}: {e}")

        return lead

    def _rate_limit_wait(self):
        """Enforce rate limiting between requests"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request_time = time.time()

    def _rotate_user_agent(self):
        """Rotate user agent to reduce blocks"""
        self._ua_index = (self._ua_index + 1) % len(self._user_agents)
        self.session.headers['User-Agent'] = self._user_agents[self._ua_index]

    def _safe_fetch(self, url: str, retries: int = 1, use_browser: bool = False) -> Optional[str]:
        """
        Fetch URL content with rate limiting and retry logic.
        Browser fallback is opt-in (use_browser=True) — disabled by default
        to keep batch collection fast.
        """
        self._rate_limit_wait()
        self._rotate_user_agent()

        last_exc: Optional[Exception] = None
        permanent_fail = False
        for attempt in range(1, retries + 2):  # +2 → retries attempts after first
            try:
                logger.debug(f"[fetch] attempt={attempt} url={url}")
                response = self.session.get(
                    url, timeout=self.timeout, allow_redirects=True
                )
                response.raise_for_status()
                html = response.text

                # Browser fallback only when explicitly requested
                if use_browser and self._is_js_only_page(html):
                    logger.debug(f"[fetch] JS-only page detected: {url}")
                    browser_html = self._fetch_with_browser(url)
                    if browser_html:
                        return browser_html

                return html

            except requests.exceptions.Timeout:
                logger.debug(f"[fetch] timeout attempt={attempt} url={url}")
                last_exc = None
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else '?'
                if status in (403, 404, 410):
                    logger.debug(f"[fetch] HTTP {status} (blocked/not found) url={url}")
                    permanent_fail = True
                    break  # Permanent — don't retry
                else:
                    logger.warning(f"[fetch] HTTP {status} attempt={attempt} url={url}")
                last_exc = e
            except requests.exceptions.ConnectionError as e:
                err_str = str(e)
                if 'getaddrinfo failed' in err_str or 'NameResolutionError' in err_str or 'Failed to resolve' in err_str:
                    # DNS is down — retrying the same host won't help
                    permanent_fail = True
                    logger.debug(f"[fetch] DNS failure (no internet?), skipping retries: {url}")
                    break
                logger.debug(f"[fetch] connection error attempt={attempt} url={url}")
                last_exc = e
            except Exception as e:
                logger.error(f"[fetch] unexpected error attempt={attempt} url={url}: {e}")
                last_exc = e

            if attempt <= retries:
                backoff = attempt * 1.5
                logger.debug(f"[fetch] backing off {backoff}s before retry")
                time.sleep(backoff)
                self._rotate_user_agent()

        if not permanent_fail:
            logger.warning(f"[fetch] all attempts failed for {url}: {last_exc}")
        return None

    @staticmethod
    def _is_js_only_page(html: str) -> bool:
        """
        Detect pages whose body is effectively empty because content is
        rendered by JavaScript (SPAs, Cloudflare challenges, etc.).
        """
        if not html or len(html) < 500:
            return True
        # Very short <body> relative to full HTML → JS placeholder
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        if body_match:
            body_text = re.sub(r'<[^>]+>', '', body_match.group(1)).strip()
            if len(body_text) < 100:
                return True
        # Common JS-framework root divs with no text content
        if re.search(r'<div id=["\'](?:app|root|__next|__nuxt)["\'][^>]*>\s*</div>', html):
            return True
        # Cloudflare challenge
        if 'cf-browser-verification' in html or 'Just a moment...' in html:
            return True
        return False

    @staticmethod
    def _fetch_with_browser(url: str) -> Optional[str]:
        """
        Optional Playwright / Selenium fallback for JS-heavy pages.
        Returns rendered HTML or None if neither is installed.
        """
        # Try Playwright first (async-capable, fast)
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_extra_http_headers({
                    'User-Agent': (
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/124.0.0.0 Safari/537.36'
                    )
                })
                page.goto(url, timeout=20_000, wait_until='domcontentloaded')
                page.wait_for_timeout(2000)  # Let JS settle
                html = page.content()
                browser.close()
                return html
        except ImportError:
            pass  # Playwright not installed
        except Exception as exc:
            logger.debug(f"[browser] Playwright error for {url}: {exc}")

        # Fallback: Selenium with Chrome
        try:
            from selenium import webdriver  # type: ignore
            from selenium.webdriver.chrome.options import Options  # type: ignore
            opts = Options()
            opts.add_argument('--headless')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--disable-gpu')
            driver = webdriver.Chrome(options=opts)
            try:
                driver.set_page_load_timeout(20)
                driver.get(url)
                time.sleep(2)
                return driver.page_source
            finally:
                driver.quit()
        except ImportError:
            pass  # Selenium not installed
        except Exception as exc:
            logger.debug(f"[browser] Selenium error for {url}: {exc}")

        return None

    # Generic email prefixes — these are catch-all addresses, not personal contacts
    GENERIC_EMAIL_PREFIXES = (
        'info', 'contact', 'hello', 'support', 'sales', 'admin',
        'team', 'business', 'inquiry', 'inquiries', 'help', 'feedback',
        'service', 'office', 'general', 'mail', 'enquiry', 'enquiries',
        'reception', 'marketing', 'press', 'media', 'hr', 'jobs',
        'careers', 'billing', 'accounts', 'customerservice',
        # Spanish generic prefixes
        'contacto', 'hola', 'ventas', 'atencion', 'comercial',
        'suscripciones', 'suscripcion', 'noticias', 'redaccion',
        'editorial', 'publicidad', 'administracion', 'clientes',
        # News / publication prefixes
        'newsletter', 'subscriptions', 'subscribe', 'editor', 'newsroom',
        'communications', 'publicrelations', 'prensa',
    )

    @staticmethod
    def _is_generic_email(email: str) -> bool:
        """Check if an email is a generic catch-all address (info@, contact@, etc)."""
        if not email or '@' not in email:
            return False
        local = email.lower().split('@')[0]
        return local in PublicWebCollector.GENERIC_EMAIL_PREFIXES

    @staticmethod
    def _personal_email_only(email: Optional[str]) -> Optional[str]:
        """Return email if it is a personal address, else None.
        Use this for person leads — generic emails (info@, contact@, etc.)
        are useless for individual outreach.
        """
        if not email:
            return None
        if PublicWebCollector._is_generic_email(email):
            return None
        return email

    @staticmethod
    def _extract_emails(text: str) -> List[str]:
        """Extract email addresses from text with strict validation.
        Returns emails sorted: personal emails first, then generic ones."""
        # First decode any URL-encoded emails (mailto: links often have %20, %40 etc)
        from urllib.parse import unquote
        clean_text = unquote(text)
        
        pattern = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
        emails = re.findall(pattern, clean_text)
        # Reject patterns — file extensions, tracking/system emails, placeholder domains
        reject_suffixes = ('.png', '.jpg', '.gif', '.css', '.js', '.svg', '.woff', '.ttf', '.webp')
        reject_domains = (
            'example.com', 'sentry.io', 'gravatar.com', 'w3.org',
            'schema.org', 'wordpress.org', 'wixpress.com',
            'googleusercontent.com', 'cloudflare.com',
            # Additional CDN / analytics pixel domains
            'cloudflareinsights.com', 'doubleclick.net', 'googletagmanager.com',
            'google-analytics.com', 'fbcdn.net', 'hotjar.com', 'mixpanel.com',
            'segment.io', 'intercom.io', 'hubspot.net', 'marketo.com',
            'pardot.com', 'akamaihd.net', 'cloudfront.net', 'fastly.net',
            'newrelic.com', 'datadog-browser-agent.com', 'amplitude.com',
            'sendgrid.net', 'mailchimp.com', 'amazonses.com',
        )
        reject_prefixes = (
            'noreply', 'no-reply', 'mailer-daemon', 'postmaster',
            'donotreply', 'bounce', 'unsubscribe', 'webmaster',
        )
        personal = []
        generic = []
        seen = set()
        for e in emails:
            # Clean any remaining URL encoding artifacts
            e = e.replace('%20', '').replace('%40', '@').strip()
            e_lower = e.lower()
            if e_lower in seen:
                continue
            seen.add(e_lower)
            if any(e_lower.endswith(s) for s in reject_suffixes):
                continue
            domain = e_lower.split('@')[-1]
            if any(rd in domain for rd in reject_domains):
                continue
            # CDN / pixel tracker domain check (catches subdomain variants)
            if _cdn_check(e_lower):
                continue
            local = e_lower.split('@')[0]
            if any(local.startswith(rp) for rp in reject_prefixes):
                continue
            if len(local) < 2 or len(domain) < 4:
                continue
            # Reject emails with consecutive dots in local part
            if '..' in local:
                continue
            # Sort: personal emails first, generic last
            if local in PublicWebCollector.GENERIC_EMAIL_PREFIXES:
                generic.append(e)
            else:
                personal.append(e)
        return personal + generic

    @staticmethod
    def _extract_phones(text: str) -> List[str]:
        """Extract phone numbers from text with strict validation"""
        # Only extract from visible text (strip HTML tags if present)
        visible_text = re.sub(r'<[^>]+>', ' ', text)

        # First: extract from tel: links (most reliable)
        tel_phones = re.findall(r'href=["\']tel:([+\d\s\-().]+)["\']', text)

        patterns = [
            r'\+?\d{1,4}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}',
            r'\(\d{3}\)\s?\d{3}[\-\s]?\d{4}',
            r'\+\d{1,3}\s?\d{2,4}\s?\d{3,4}\s?\d{3,4}',
        ]
        phones = list(tel_phones)  # tel: links first (highest quality)
        for pattern in patterns:
            found = re.findall(pattern, visible_text)
            phones.extend(found)
        # Validate: must have 7-15 digits, reject tracking pixels and CSS values
        validated = []
        seen = set()
        for p in phones:
            stripped = p.strip()
            digits = re.sub(r'[^\d]', '', stripped)
            if digits in seen:
                continue
            seen.add(digits)
            if len(digits) < 7 or len(digits) > 15:
                continue
            # Must have phone-like formatting (not bare numbers from IDs)
            has_formatting = any(c in stripped for c in '+-() ')
            if not has_formatting:
                continue
            # Reject numbers that are clearly dates/years/dimensions
            if re.match(r'^\d{4}$', digits) or re.match(r'^\d{8}$', digits):
                continue
            # Reject sequential digits (1234567890)
            if digits in '012345678901234567890':
                continue
            # Reject repeated digit patterns (e.g. 0000000)
            if len(set(digits)) <= 2:
                continue
            # Reject common test/placeholder numbers
            if digits.startswith('555') and len(digits) == 10:
                continue
            validated.append(stripped)
        return validated[:5]

    @staticmethod
    def _extract_websites(text: str, base_url: str = '') -> List[str]:
        """Extract website URLs from text"""
        pattern = r'https?://[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(?:/[^\s"\'<>]*)?'
        urls = re.findall(pattern, text)
        # Filter out common non-business URLs
        blacklist = ['google', 'facebook.com/tr', 'twitter.com/intent',
                     'youtube.com/embed', 'cdn.', 'static.', 'ajax.',
                     'duckduckgo', 'bing.com', 'schema.org']
        filtered = [u for u in urls if not any(b in u.lower() for b in blacklist)]
        return list(set(filtered))[:5]

    @staticmethod
    def _extract_linkedin_url(soup: BeautifulSoup, text: str) -> Optional[str]:
        """Extract LinkedIn company or personal URL from page"""
        # Check links
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'linkedin.com/company/' in href or 'linkedin.com/in/' in href:
                return href.split('?')[0]  # Strip tracking params
        # Check text patterns
        linkedin_pattern = r'https?://(?:www\.)?linkedin\.com/(?:company|in)/[a-zA-Z0-9\-_/]+'
        matches = re.findall(linkedin_pattern, text)
        if matches:
            return matches[0].split('?')[0]
        return None

    @staticmethod
    def _extract_social_profiles(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
        """Extract social media profile URLs"""
        profiles: Dict[str, Optional[str]] = {}
        social_patterns = {
            'twitter': r'https?://(?:www\.)?(?:twitter|x)\.com/[a-zA-Z0-9_]+',
            'facebook': r'https?://(?:www\.)?facebook\.com/[a-zA-Z0-9.]+',
            'instagram': r'https?://(?:www\.)?instagram\.com/[a-zA-Z0-9_.]+',
        }
        page_text = str(soup)
        for platform, pattern in social_patterns.items():
            matches = re.findall(pattern, page_text)
            if matches:
                profiles[platform] = matches[0].split('?')[0]
        return profiles

    @staticmethod
    def _classify_industry(text: str) -> Optional[str]:
        """Classify business industry from text content"""
        text_lower = text.lower()
        scores = {}
        for industry, keywords in INDUSTRY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[industry] = score
        if scores:
            return max(scores.keys(), key=lambda k: scores[k])
        return None

    def _search_serper(
        self,
        query: str,
        country_code: str = '',
        num: int = 8,
    ) -> List[Dict[str, Any]]:
        """Search via Serper.dev (real Google results). Returns list of {href, title, body}."""
        import os, json as _json
        api_key = os.environ.get('SERPER_API_KEY', '')
        if not api_key:
            return []
        self._rate_limit_wait()
        try:
            payload = _json.dumps({'q': query, 'num': num, 'gl': country_code.lower() or 'us'})
            resp = requests.post(
                'https://google.serper.dev/search',
                headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'},
                data=payload,
                timeout=10,
                verify=False,
            )
            if resp.status_code != 200:
                logger.warning("[serper] HTTP %s: %s", resp.status_code, resp.text[:200])
                return []
            data = resp.json()
            results = []
            for item in data.get('organic', []):
                results.append({
                    'href':  item.get('link', ''),
                    'title': item.get('title', ''),
                    'body':  item.get('snippet', ''),
                })
            return results
        except Exception as exc:
            logger.warning("[serper] search error: %s", exc)
            return []

    def _search_bing(self, query: str, n: int = 8) -> List[Dict[str, Any]]:
        """Bing Web Search API — optional 3rd engine (requires BING_API_KEY env var)."""
        _bkey = os.environ.get('BING_API_KEY', '').strip()
        if not _bkey:
            return []
        try:
            resp = requests.get(
                'https://api.bing.microsoft.com/v7.0/search',
                headers={'Ocp-Apim-Subscription-Key': _bkey},
                params={'q': query, 'count': n, 'responseFilter': 'Webpages'},
                timeout=10,
                verify=False,
            )
            if not resp.ok:
                return []
            return [
                {'href': p.get('url', ''), 'title': p.get('name', ''), 'snippet': p.get('snippet', '')}
                for p in resp.json().get('webPages', {}).get('value', [])
            ]
        except Exception as _be:
            logger.debug("[web] Bing search error: %s", _be)
            return []

    def _search_places(
        self,
        query: str,
        city: str,
        country_name: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Stage 0 — Google Places API (New) text search.

        Returns leads pre-populated with name, phone, website, address.
        These skip URL discovery and go straight into collect_from_url()
        for email extraction.
        """
        import os, json as _json
        api_key = os.environ.get('GOOGLE_PLACES_API_KEY', '')
        if not api_key:
            return []
        self._rate_limit_wait()
        try:
            text_query = f'{query} {city} {country_name}'
            payload = _json.dumps({
                'textQuery': text_query,
                'maxResultCount': min(max_results, 20),
            })
            resp = requests.post(
                'https://places.googleapis.com/v1/places:searchText',
                headers={
                    'X-Goog-Api-Key': api_key,
                    'Content-Type': 'application/json',
                    'X-Goog-FieldMask': (
                        'places.displayName,places.formattedAddress,'
                        'places.nationalPhoneNumber,places.websiteUri,'
                        'places.businessStatus,places.primaryTypeDisplayName'
                    ),
                },
                data=payload,
                timeout=10,
                verify=False,
            )
            if resp.status_code != 200:
                logger.warning("[places] HTTP %s: %s", resp.status_code, resp.text[:200])
                return []

            leads = []
            for place in resp.json().get('places', []):
                if place.get('businessStatus') == 'CLOSED_PERMANENTLY':
                    continue
                name    = (place.get('displayName') or {}).get('text', '').strip()
                website = place.get('websiteUri', '').strip()
                phone   = place.get('nationalPhoneNumber', '').strip()
                address = place.get('formattedAddress', '').strip()
                if not name or not website:
                    continue
                leads.append({
                    'company':  name,
                    'phone':    phone,
                    'website':  website,
                    'address':  address,
                    'source':   'google_places',
                    '_places_url': website,
                })
                logger.debug("[places] %s — %s — %s", name, phone, website)
            logger.info("[places] %d leads from Places API for %r in %s", len(leads), query, city)
            return leads
        except Exception as exc:
            logger.warning("[places] error: %s", exc)
            return []

    @staticmethod
    def _prescreen_ddg_result(
        href: str, title: str, snippet: str,
        query_core: str, target_city: str, country_name: str,
        country_code: str, local_tld: str,
    ) -> bool:
        """
        Pipeline Stage 1 — Search Discovery gate.
        Returns True only if this DDG result is likely a real local company page.
        Rejects articles, directories, off-topic global brands, and results
        with no connection to the target country/city.
        """
        if not href:
            return False
        try:
            domain = urlparse(href).netloc.lower().replace('www.', '')
        except Exception:
            domain = ''

        combined = (title + ' ' + snippet).lower()
        title_lower = title.lower()

        # ── 1. Location relevance — must connect to the target geography ─────
        is_local_tld = bool(
            local_tld and (
                domain.endswith('.' + local_tld)
                or ('.' + local_tld + '/') in href.lower()
            )
        )
        location_mentioned = (
            target_city.lower() in combined
            or country_name.lower() in combined
            or is_local_tld
        )
        if not location_mentioned:
            return False

        # ── 2. Not an article/listicle ────────────────────────────────────────
        # Real company pages have short, specific titles; articles are long/generic
        if any(sig in title_lower for sig in _ARTICLE_TITLE_SIGNALS) and len(title.split()) > 5:
            return False

        # ── 3. Not a globally irrelevant brand ───────────────────────────────
        if domain in _GLOBALLY_IRRELEVANT_DOMAINS:
            return False

        # ── 4. Title must not look like a data product / directory page ──────
        bad_title_exact = (
            'find email', 'email lookup', 'phone lookup', 'email finder',
            'contact information', 'people search', 'background check',
        )
        if any(b in title_lower for b in bad_title_exact):
            return False

        return True

    @staticmethod
    def _extract_interests(text: str, industry: Optional[str] = None, query: str = '') -> List[str]:
        """Extract interests/topics from page text, industry, and search query."""
        text_lower = (text[:2000] + ' ' + query).lower()
        interests = set()

        keyword_map = {
            'saas': 'SaaS', 'cloud': 'Cloud Computing', 'ai': 'Artificial Intelligence',
            'machine learning': 'Machine Learning', 'automation': 'Automation',
            'cybersecurity': 'Cybersecurity', 'blockchain': 'Blockchain',
            'ecommerce': 'E-commerce', 'e-commerce': 'E-commerce',
            'data analytics': 'Data Analytics', 'big data': 'Big Data',
            'digital marketing': 'Digital Marketing', 'seo': 'SEO',
            'social media': 'Social Media', 'content marketing': 'Content Marketing',
            'real estate': 'Real Estate', 'fintech': 'Fintech',
            'mobile app': 'Mobile Development', 'web development': 'Web Development',
            'iot': 'IoT', 'devops': 'DevOps', 'consulting': 'Consulting',
            'crm': 'CRM', 'erp': 'ERP', 'hr tech': 'HR Tech',
            'logistics': 'Logistics', 'supply chain': 'Supply Chain',
            'renewable': 'Renewable Energy', 'solar': 'Solar Energy',
            'healthcare': 'Healthcare', 'biotech': 'Biotech',
            'edtech': 'EdTech', 'insurance': 'Insurance',
            'investment': 'Investment', 'trading': 'Trading',
            'design': 'Design', 'branding': 'Branding',
            'startup': 'Startups', 'entrepreneur': 'Entrepreneurship',
            'b2b': 'B2B', 'b2c': 'B2C',
        }

        for kw, interest in keyword_map.items():
            if kw in text_lower:
                interests.add(interest)

        # Map industry to an interest if nothing else matched
        if industry and not interests:
            industry_interest_map = {
                'technology': 'Technology', 'healthcare': 'Healthcare',
                'finance': 'Finance', 'manufacturing': 'Manufacturing',
                'retail': 'Retail', 'real_estate': 'Real Estate',
                'education': 'Education', 'consulting': 'Consulting',
                'marketing': 'Marketing', 'logistics': 'Logistics',
                'food_beverage': 'Food & Beverage', 'energy': 'Energy',
                'automotive': 'Automotive', 'telecom': 'Telecommunications',
            }
            mapped = industry_interest_map.get(industry)
            if mapped:
                interests.add(mapped)

        return list(interests)[:5]

    def _try_find_email(self, url: str, emails: List[str],
                        company: Optional[str] = None, fast: bool = True) -> tuple:  # noqa: ARG002
        """Try harder to find an email. Returns (email, is_verified) tuple.
        fast=True (default): skip contact-page scraping, return found email or infer info@domain.
        """
        if emails:
            clean = emails[0].replace('%20', '').replace('%40', '@').strip()
            return (clean, True)

        # Fast mode: infer info@domain instead of scraping contact pages
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '')
        if fast or not domain:
            if domain:
                return (f'info@{domain}', False)
            return (None, False)

        # Slow path (only if fast=False): try contact/about pages
        base = f"{parsed.scheme}://{parsed.netloc}"
        contact_paths = ['/contact', '/contact-us', '/about']
        best_generic = None  # Track best generic email as fallback

        def _extract_from_html(html: str):
            """Return (personal_email, generic_email) found in html block."""
            import json as _json
            personal = None
            generic = None

            # 1. JSON-LD structured data (schema.org)
            for ld_block in re.findall(
                r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                html, re.DOTALL | re.IGNORECASE
            ):
                try:
                    obj = _json.loads(ld_block)
                    items = obj if isinstance(obj, list) else [obj]
                    for item in items:
                        if isinstance(item, dict):
                            ld_e = item.get('email', '')
                            if ld_e and '@' in ld_e:
                                valid = self._extract_emails(ld_e)
                                if valid:
                                    if not self._is_generic_email(valid[0]):
                                        personal = personal or valid[0]
                                    else:
                                        generic = generic or valid[0]
                except Exception:
                    pass

            # 2. itemProp="email"
            for m in re.finditer(
                r'itemprop=["\']email["\'][^>]*(?:content=["\']([^"\']+)["\']|>([^<]+)<)',
                html, re.IGNORECASE
            ):
                candidate = (m.group(1) or m.group(2) or '').strip()
                valid = self._extract_emails(candidate)
                if valid:
                    if not self._is_generic_email(valid[0]):
                        personal = personal or valid[0]
                    else:
                        generic = generic or valid[0]

            # 3. mailto: links
            mailto_match = re.findall(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', html)
            if mailto_match:
                valid = self._extract_emails(' '.join(mailto_match))
                if valid:
                    if not self._is_generic_email(valid[0]):
                        personal = personal or valid[0]
                    else:
                        generic = generic or valid[0]

            # 4. All emails in page
            found = self._extract_emails(html)
            if found:
                if not self._is_generic_email(found[0]):
                    personal = personal or found[0]
                else:
                    generic = generic or found[0]

            # 5. Obfuscated patterns: user [at] domain [dot] com
            decoded = re.sub(
                r'\s*[\[\(](?:at|AT)[\]\)]\s*', '@',
                re.sub(r'\s*[\[\(](?:dot|DOT)[\]\)]\s*', '.', re.sub(r'<[^>]+>', ' ', html))
            )
            obf_found = self._extract_emails(decoded)
            if obf_found:
                if not self._is_generic_email(obf_found[0]):
                    personal = personal or obf_found[0]
                else:
                    generic = generic or obf_found[0]

            return personal, generic

        domain_blocked = False  # set True after 2x 403 — skip remaining paths
        consecutive_403 = 0

        for contact_path in contact_paths:
            if domain_blocked:
                break
            contact_url = base + contact_path
            html = self._safe_fetch(contact_url)
            if html:
                consecutive_403 = 0
                personal, generic = _extract_from_html(html)
                if personal:
                    return (personal, True)
                if generic and not best_generic:
                    best_generic = generic
            else:
                # _safe_fetch returns None on 403/404/timeout.
                # Detect 403-blocked domains by checking the last recorded failure.
                # We track via a simple heuristic: if 2+ paths fail in a row on the
                # same domain, the domain is blocking us — stop wasting requests.
                consecutive_403 += 1
                if consecutive_403 >= 2:
                    logger.debug(
                        f"[web] {base} blocked consecutive sub-pages — skipping rest"
                    )
                    domain_blocked = True

        # Also check the original page (only if domain not blocked)
        main_html = self._safe_fetch(url) if not domain_blocked else None
        if main_html:
            personal, generic = _extract_from_html(main_html)
            if personal:
                return (personal, True)
            if generic and not best_generic:
                best_generic = generic

        # Return generic email found on real pages (verified but generic)
        if best_generic:
            return (best_generic, True)

        # Last resort: infer info@domain (marked as unverified)
        # Handle subdomains: blog.acme.com → acme.com
        domain = parsed.netloc.replace('www.', '')
        if domain and '.' in domain:
            # Strip subdomains for common patterns
            parts = domain.split('.')
            if len(parts) > 2:
                # Handle co.uk, com.au etc.
                if parts[-2] in ('co', 'com', 'org', 'net', 'ac', 'gov'):
                    domain = '.'.join(parts[-3:])
                else:
                    domain = '.'.join(parts[-2:])
            return (f'info@{domain}', False)

        return (None, False)

    def _try_find_phone(self, url: str, phones: List[str]) -> Optional[str]:
        """Try harder to find a phone number by scraping contact pages.
        Returns the first valid phone found, or None.
        """
        if phones:
            return phones[0]

        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        contact_paths = [
            '/contact', '/contact-us',
        ]
        for contact_path in contact_paths:
            contact_url = base + contact_path
            html = self._safe_fetch(contact_url)
            if html:
                # tel: links first (most reliable)
                tel_phones = re.findall(r'href=["\']tel:([+\d\s\-().]+)["\']', html)
                for tp in tel_phones:
                    digits = re.sub(r'[^\d]', '', tp)
                    if 7 <= len(digits) <= 15 and len(set(digits)) > 2:
                        return tp.strip()
                # JSON-LD telephone
                try:
                    import json as _json
                    for ld_block in re.findall(
                        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                        html, re.DOTALL | re.IGNORECASE
                    ):
                        try:
                            obj = _json.loads(ld_block)
                            items = obj if isinstance(obj, list) else [obj]
                            for item in items:
                                if isinstance(item, dict):
                                    ld_phone = item.get('telephone', '') or item.get('phone', '')
                                    if ld_phone:
                                        digits = re.sub(r'[^\d]', '', ld_phone)
                                        if 7 <= len(digits) <= 15:
                                            return ld_phone.strip()
                        except Exception:
                            pass
                except Exception:
                    pass
                # itemProp="telephone"
                for m in re.finditer(
                    r'itemprop=["\']telephone["\'][^>]*(?:content=["\']([^"\']+)["\']|>([^<]+)<)',
                    html, re.IGNORECASE
                ):
                    candidate = (m.group(1) or m.group(2) or '').strip()
                    digits = re.sub(r'[^\d]', '', candidate)
                    if 7 <= len(digits) <= 15:
                        return candidate
                found = self._extract_phones(html)
                if found:
                    return found[0]
        return None

    @staticmethod
    def _extract_company_name(soup: BeautifulSoup, text: str) -> Optional[str]:
        """Try to extract company name from page"""
        # Patterns that indicate the extracted text is NOT a company name
        bad_patterns = [
            'find email', 'phone number', 'search', 'lookup', 'database',
            'contact info', 'free tool', 'sign up', 'log in', 'server',
            'page not found', '404', '403', 'forbidden', 'error',
            'cookie', 'privacy policy', 'terms of', 'subscribe',
            'nothing found', 'no results',
            'contact us', 'about us', 'our team', 'get in touch',
            'home page', 'homepage', 'welcome to',
        ]
        # Words that indicate a page title, not a company name
        title_indicators = [
            'agency in ', 'agencies in ', 'company in ', 'companies in ',
            'services in ', 'firm in ', 'firms in ', 'solutions in ',
            'top ', 'best ', 'leading ', 'premier ',
            'marketing in ', 'consulting in ',
        ]

        def _is_valid_company(name: str) -> bool:
            if not name or len(name) < 2 or len(name) > 150:
                return False
            # Fix DuckDuckGo space stripping before validation
            expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
            lower = expanded.lower().strip()
            if any(bp in lower for bp in bad_patterns):
                return False
            # Reject names that look like SEO page titles
            if any(ti in lower for ti in title_indicators):
                return False
            # Reject if it's just "X Marketing" + city name pattern
            if len(expanded.split()) > 5:
                return False  # Real company names are usually short
            # Reject names that start with "at " or contain semicolons
            if lower.startswith('at ') or ';' in name:
                return False
            return True

        # Try og:site_name
        og_name = soup.find('meta', property='og:site_name')
        if og_name and og_name.get('content'):
            name = og_name['content'].strip()[:255]
            if _is_valid_company(name):
                return name
        # Try title tag
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
            # Clean common suffixes; handle bare | (e.g. "ContactUs|Company Name")
            for sep in [' | ', ' - ', ' – ', ' :: ', ' — ']:
                if sep in title:
                    title = title.split(sep)[0].strip()
                    break
            else:
                if '|' in title:
                    parts = [p.strip() for p in title.split('|') if p.strip()]
                    # Pick first part that isn't a navigation label; fall back to longest
                    title = next((p for p in parts if _is_valid_company(p)), max(parts, key=len, default=title))
            # Remove generic page names
            noise = ['contact us', 'about us', 'home', 'welcome to',
                     'homepage', 'official website', 'contact', 'about',
                     'our team', 'meet the team', 'leadership', 'staff directory',
                     'team members', 'management team']
            cleaned = title
            for n in noise:
                cleaned = re.sub(rf'\b{n}\b', '', cleaned, flags=re.IGNORECASE).strip(' -–—|:')
            result = (cleaned or title)[:255] if cleaned else title[:255]
            if _is_valid_company(result):
                return result
        return None

    @staticmethod
    def _extract_person_name(soup: BeautifulSoup) -> Optional[str]:
        """Try to extract a contact person name from page"""
        # Look for common patterns
        for selector in ['[itemprop="name"]', '.contact-name', '.person-name',
                         '.team-member-name', 'h2.name', 'h3.name',
                         '.author-name', '.speaker-name', '.staff-name',
                         '.team-name', '.profile-name', '.member-name',
                         '[class*="author"] h2', '[class*="author"] h3',
                         '[class*="team"] h3', '[class*="team"] h4',
                         '[class*="staff"] h3', '[class*="people"] h3']:
            elem = soup.select_one(selector)
            if elem and elem.get_text(strip=True):
                name = elem.get_text(strip=True)
                # Must be 3-80 chars, contain a space (first + last name)
                if 3 < len(name) < 80 and ' ' in name:
                    # Validate: looks like a real person name
                    words = name.split()
                    if len(words) < 2 or len(words) > 5:
                        continue
                    # Each word should start with uppercase and be mostly alpha
                    valid = True
                    for w in words:
                        clean = w.strip('.,()-\'')
                        if not clean:
                            continue
                        if not clean[0].isupper():
                            valid = False
                            break
                        if not all(c.isalpha() or c in "'-.àáâãäåæçèéêëìíîïñòóôõöøùúûüý" for c in clean.lower()):
                            valid = False
                            break
                    if not valid:
                        continue
                    # Reject known non-person patterns
                    lower = name.lower()
                    non_person = [
                        'company', 'group', 'inc', 'llc', 'ltd', 'corp', 'agency',
                        'services', 'solutions', 'marketing', 'digital', 'global',
                        'consulting', 'team', 'staff', 'contact us', 'about us',
                        'our team', 'privacy', 'terms', 'policy', 'cookie',
                    ]
                    if any(np in lower for np in non_person):
                        continue
                    return name
        return None

    @staticmethod
    def _extract_position(soup: BeautifulSoup) -> Optional[str]:
        """Try to extract job title/position from page"""
        for selector in ['[itemprop="jobTitle"]', '.contact-title', '.person-title',
                         '.team-member-title', '.author-title', '.speaker-title',
                         '.staff-title', '.team-role', '.profile-title',
                         '.member-title', '.member-role',
                         '[class*="role"]', '[class*="designation"]',
                         '[class*="position"]', '[class*="job-title"]']:
            elem = soup.select_one(selector)
            if elem and elem.get_text(strip=True):
                title = elem.get_text(strip=True)
                if len(title) < 200:
                    return title[:255]
        return None

    @staticmethod
    def _extract_people_from_page(soup: BeautifulSoup, text: str,
                                   base_url: str = '') -> List[Dict[str, Any]]:
        """
        Extract multiple people/contacts from a single page.
        Looks for team pages, about pages, staff directories, speaker lists.
        Returns list of person dicts with name, position, email, linkedin, etc.
        """
        people = []
        seen_names = set()

        # Common container patterns for team/people sections
        person_selectors = [
            # Schema.org Person markup
            '[itemtype*="schema.org/Person"]',
            # Common class patterns
            '.team-member', '.staff-member', '.people-item', '.person-card',
            '.team-card', '.member-card', '.leadership-card', '.executive-card',
            '.speaker-card', '.author-card', '.profile-card',
            '[class*="team-member"]', '[class*="staff-member"]',
            '[class*="person-card"]', '[class*="people-card"]',
            '[class*="member-item"]', '[class*="leadership"]',
            '[class*="executive"]', '[class*="speaker"]',
            # vCard format
            '.vcard', '.h-card',
        ]

        for selector in person_selectors:
            cards = soup.select(selector)
            for card in cards[:20]:  # Limit to prevent over-extraction
                card_text = card.get_text(separator=' ', strip=True)

                # Extract name
                name = None
                for name_sel in ['h2', 'h3', 'h4', '.name', '[itemprop="name"]',
                                 '.person-name', '.member-name', '.fn', '.p-name']:
                    name_el = card.select_one(name_sel)
                    if name_el:
                        n = name_el.get_text(strip=True)
                        if 3 < len(n) < 80 and ' ' in n:
                            name = n
                            break

                if not name or name.lower() in seen_names:
                    continue
                seen_names.add(name.lower())

                # Extract position/title
                position = None
                for title_sel in ['.title', '.role', '.position', '.designation',
                                  '[itemprop="jobTitle"]', '.job-title', 'p', 'span']:
                    title_el = card.select_one(title_sel)
                    if title_el and title_el != card.select_one('h2') and title_el != card.select_one('h3'):
                        t = title_el.get_text(strip=True)
                        if 3 < len(t) < 150 and t != name:
                            position = t
                            break

                # Extract email from card
                email = None
                email_match = re.findall(
                    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
                    card_text
                )
                if email_match:
                    email = email_match[0]
                else:
                    mailto = card.select_one('a[href^="mailto:"]')
                    if mailto:
                        email = mailto['href'].replace('mailto:', '').split('?')[0]

                # Extract LinkedIn from card
                linkedin = None
                for link in card.select('a[href*="linkedin.com"]'):
                    href = link.get('href', '')
                    if '/in/' in href or '/company/' in href:
                        linkedin = href.split('?')[0]
                        break

                # Extract phone from card
                phone = None
                phone_match = re.findall(
                    r'\+?\d{1,4}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}',
                    card_text
                )
                if phone_match:
                    phone = phone_match[0].strip()
                else:
                    tel_link = card.select_one('a[href^="tel:"]')
                    if tel_link:
                        phone = tel_link['href'].replace('tel:', '').strip()

                people.append({
                    'name': name,
                    'position': position,
                    'email': email,
                    'phone': phone,
                    'linkedin_url': linkedin,
                })

        # Also try JSON-LD structured data for Person type
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                import json
                ld_data = json.loads(script.string or '{}')
                items = ld_data if isinstance(ld_data, list) else [ld_data]
                for item in items:
                    if item.get('@type') in ('Person', 'ProfilePage'):
                        name = item.get('name', '')
                        if name and name.lower() not in seen_names and ' ' in name:
                            seen_names.add(name.lower())
                            people.append({
                                'name': name,
                                'position': item.get('jobTitle'),
                                'email': item.get('email'),
                                'phone': item.get('telephone'),
                                'linkedin_url': None,
                            })
            except Exception:
                pass

        return people

    @staticmethod
    def _extract_address(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
        """Extract address components from structured data"""
        address: Dict[str, Optional[str]] = {'city': None, 'country': None, 'full': None}
        # Schema.org address via microdata
        addr_elem = soup.find(attrs={'itemprop': 'address'})
        if addr_elem:
            city_elem = addr_elem.find(attrs={'itemprop': 'addressLocality'})
            country_elem = addr_elem.find(attrs={'itemprop': 'addressCountry'})
            if city_elem:
                address['city'] = city_elem.get_text(strip=True)
            if country_elem:
                address['country'] = country_elem.get_text(strip=True)
            street = addr_elem.find(attrs={'itemprop': 'streetAddress'})
            region = addr_elem.find(attrs={'itemprop': 'addressRegion'})
            parts = []
            if street:
                parts.append(street.get_text(strip=True))
            if city_elem:
                parts.append(city_elem.get_text(strip=True))
            if region:
                parts.append(region.get_text(strip=True))
            if country_elem:
                parts.append(country_elem.get_text(strip=True))
            if parts:
                address['full'] = ', '.join(parts)
        return address

    @staticmethod
    def _extract_structured_data(soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract rich structured data from JSON-LD (Organization, LocalBusiness, etc.)"""
        result: Dict[str, Any] = {}
        target_types = (
            'Organization', 'LocalBusiness', 'Corporation', 'Company',
            'ProfessionalService', 'Store', 'Restaurant', 'MedicalBusiness',
            'LegalService', 'FinancialService', 'RealEstateAgent',
            'InsuranceAgency', 'TravelAgency', 'EducationalOrganization',
        )
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                import json
                ld_data = json.loads(script.string or '{}')
                items = ld_data if isinstance(ld_data, list) else [ld_data]
                # Handle @graph
                for item in items:
                    if isinstance(item, dict) and '@graph' in item:
                        items.extend(item['@graph'])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get('@type', '')
                    if isinstance(item_type, list):
                        item_type = item_type[0] if item_type else ''
                    if not any(t in str(item_type) for t in target_types):
                        continue
                    # Extract all useful fields
                    if item.get('name'):
                        result['company'] = str(item['name'])[:255]
                    if item.get('email'):
                        result['email'] = str(item['email'])
                    if item.get('telephone'):
                        result['phone'] = str(item['telephone'])
                    if item.get('url'):
                        result['website'] = str(item['url'])
                    if item.get('description'):
                        result['description'] = str(item['description'])[:500]
                    if item.get('foundingDate'):
                        result['founded'] = str(item['foundingDate'])
                    if item.get('numberOfEmployees'):
                        emp = item['numberOfEmployees']
                        if isinstance(emp, dict):
                            result['employees'] = emp.get('value', '')
                        else:
                            result['employees'] = str(emp)
                    if item.get('sameAs'):
                        same_as = item['sameAs'] if isinstance(item['sameAs'], list) else [item['sameAs']]
                        for sa in same_as:
                            sa_str = str(sa)
                            if 'linkedin.com' in sa_str:
                                result['linkedin'] = sa_str
                            elif 'twitter.com' in sa_str or 'x.com' in sa_str:
                                result['twitter'] = sa_str
                            elif 'facebook.com' in sa_str:
                                result['facebook'] = sa_str
                    # Address from JSON-LD
                    addr = item.get('address', {})
                    if isinstance(addr, dict):
                        if addr.get('addressLocality'):
                            result['city'] = str(addr['addressLocality'])
                        if addr.get('addressCountry'):
                            result['country'] = str(addr['addressCountry'])
                    # Industry from JSON-LD
                    if item.get('industry'):
                        result['industry'] = str(item['industry'])
                    if item.get('naics') or item.get('isicV4'):
                        result['industry_code'] = str(item.get('naics') or item.get('isicV4'))
                    break  # Take first matching organization
            except Exception:
                pass
        return result

    @staticmethod
    def _extract_meta_description(soup: BeautifulSoup) -> str:
        """Extract meta description for richer context"""
        for attr in [{'name': 'description'}, {'property': 'og:description'}]:
            tag = soup.find('meta', attrs=attr)
            if tag and tag.get('content'):
                return tag['content'].strip()[:500]
        return ''

    def collect_from_url(self, url: str, country_code: str = '') -> Optional[Dict[str, Any]]:
        """
        Collect lead data from a single public URL.

        Extraction pipeline (in order of priority):
          1. lead_extractor.extract_all() — JSON-LD, microdata, mailto,
             obfuscated text, structured data
          2. Existing regex-based helpers for any gaps
          3. AI enrichment (Gemini/Groq) for name/position/industry
          4. Fallback strategies (contact-page scrape, Hunter, generation)
        """
        logger.debug(f"[collector] collect_from_url: {url}")
        html = self._safe_fetch(url)
        if not html:
            logger.info(f"[collector] fetch returned None for {url}")
            return None

        try:
            # ── New extractor (handles obfuscation, JSON-LD, microdata) ──────
            if _MODULES_AVAILABLE:
                extracted = _ext_extract_all(html, url, debug=False)
                emails = extracted.get('emails') or []
                phones = extracted.get('phones') or []
                ext_company = extracted.get('company')
                ext_name = extracted.get('contact_name')
                ext_position = extracted.get('position')
                ext_linkedin = extracted.get('linkedin_url')
                ext_industry = extracted.get('industry')
                ext_interests = extracted.get('interests') or []
                structured = extracted.get('structured_data') or {}
            else:
                emails, phones, ext_company, ext_name, ext_position = [], [], None, None, None
                ext_linkedin, ext_industry, ext_interests, structured = None, None, [], {}

            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
            meta_desc = self._extract_meta_description(soup)

            # ── Merge legacy helpers for anything the new extractor missed ───
            if not emails:
                emails = self._extract_emails(text)
            if not phones:
                phones = self._extract_phones(html)
            websites = self._extract_websites(html, url)

            # ── Pipeline Stage 3: Entity Normalization ───────────────────────
            # Company: new extractor → legacy → structured data.
            # NEVER fall back to domain name — "dictionary.com" → "Dictionary" is garbage.
            company = (
                ext_company
                or self._extract_company_name(soup, text)
                or structured.get('company')
            )
            # Reject if no real company name found
            if not company:
                logger.debug("[collector] no extractable company name at %s — skipping", url)
                return None
            # Reject single-word generic names: "Online", "Digital", "Solutions"…
            _co_words = [w.lower() for w in company.split() if w.isalpha()]
            if len(_co_words) == 1 and _co_words[0] in _GENERIC_COMPANY_NAMES:
                logger.debug("[collector] rejected generic company name '%s' at %s", company, url)
                return None

            # ── Contact name: new extractor wins, legacy as fallback ─────────
            person = ext_name or self._extract_person_name(soup)

            # ── Position ─────────────────────────────────────────────────────
            position = ext_position or self._extract_position(soup)

            # ── Industry ─────────────────────────────────────────────────────
            industry = (
                ext_industry
                or self._classify_industry(text)
                or structured.get('industry')
            )

            # ── LinkedIn ──────────────────────────────────────────────────────
            linkedin = ext_linkedin or self._extract_linkedin_url(soup, html)
            if not linkedin and structured.get('linkedin'):
                linkedin = structured['linkedin']

            # ── Address ───────────────────────────────────────────────────────
            address = self._extract_address(soup)
            if structured.get('city') and not address.get('city'):
                address['city'] = structured['city']

            # ── Structured data top-ups ───────────────────────────────────────
            if structured.get('email') and structured['email'] not in emails:
                emails.insert(0, structured['email'])
            if structured.get('phone') and structured['phone'] not in phones:
                phones.insert(0, structured['phone'])

            # ── Social profiles ───────────────────────────────────────────────
            socials = self._extract_social_profiles(soup)

            # ── Country ───────────────────────────────────────────────────────
            country_info = COUNTRY_SOURCES.get(country_code, {})
            country_name = country_info.get(
                'name',
                address.get('country', structured.get('country', '')),
            )

            # Need at least one of: company, email, person
            if not company and not emails and not person:
                logger.debug(f"[collector] insufficient data at {url} — skipping")
                return None

            context_text = f"{text[:2000]} {meta_desc}"

            had_real_emails = bool(emails)  # True = emails found on page before fallback
            found_email, email_verified = self._try_find_email(url, emails, company)
            found_phone = self._try_find_phone(url, phones)

            # Tag last-resort inferred emails so the validator treats them as generated.
            # Condition: email came from fallback (no real page emails) AND unverified.
            email_source = None
            if found_email and not email_verified and not had_real_emails:
                email_source = 'inferred'

            # ── Interests: new extractor → legacy helper ──────────────────────
            interests = ext_interests or self._extract_interests(context_text, industry)

            lead = {
                'name': person or company or 'Unknown Contact',
                'email': found_email,
                'phone': found_phone,
                'company': company,
                'position': position,
                'country': country_name,
                'city': address.get('city', ''),
                'location': f"{address.get('city', '')}, {country_name}".strip(', '),
                'industry': industry,
                # Prefer email domain as canonical website — avoids directory URLs
                # (e.g. scraped from clutch.co but email is info@stratahive.com →
                #  website becomes https://stratahive.com for domain-match scoring)
                'website': (
                    f'https://{found_email.split("@")[1]}'
                    if found_email and '@' in found_email and not email_source
                    else url
                ),
                'linkedin_url': linkedin,
                'interests': interests,
                'source': f'web_public_{country_code.lower()}' if country_code else 'web_public',
                'lead_type': 'company',
                'email_type': _email_type(found_email) if _MODULES_AVAILABLE and found_email else 'unknown',
                'completeness_score': 0.0,
                'qualification_score': 0.0,
                'status': 'pending',
                'data_points': {
                    'all_emails': emails,
                    'all_phones': phones,
                    'email_verified': email_verified,
                    'email_source': email_source,
                    'extracted_websites': websites,
                    'social_profiles': socials,
                    'structured_data': structured if structured else None,
                    'meta_description': meta_desc or None,
                    'collected_at': datetime.utcnow().isoformat(),
                    'source_url': url,
                    'country_code': country_code,
                    'text_snippet': text[:300],
                },
            }

            # AI enrichment and Hunter/Explorium fallbacks are intentionally skipped
            # here to keep per-URL collection fast. The route layer calls them once
            # on the full collected batch after all URLs are processed.

            # ── Scoring (new validator replaces hard reject) ──────────────────
            if _MODULES_AVAILABLE:
                lead, should_save, rejection_reason = validate_and_score(lead)
                if not should_save:
                    logger.info(
                        f"[collector] lead dropped: {url} reason={rejection_reason}"
                    )
                    return None
                # Keep legacy score field in sync
                lead['qualification_score'] = max(
                    lead.get('qualification_score', 0),
                    self._calculate_initial_score(lead),
                )
            else:
                # Legacy scoring path
                lead['qualification_score'] = self._calculate_initial_score(lead)
                found_email = lead.get('email')
                if (found_email and not email_verified
                        and not found_phone and not linkedin
                        and not lead.get('position')):
                    logger.debug(f"[collector] low-quality inferred-email lead: {url}")
                    return None

            logger.info(
                f"[collector] collected lead: name='{lead.get('name')}' "
                f"company='{lead.get('company')}' email='{lead.get('email')}' "
                f"score={lead.get('qualification_score', 0):.0f} "
                f"completeness={lead.get('completeness_score', 0):.0f}"
            )
            return lead

        except Exception as e:
            logger.error(f"[collector] error parsing {url}: {e}", exc_info=True)
            return None

    @staticmethod
    def _calculate_initial_score(lead: Dict[str, Any]) -> float:
        """Calculate an initial qualification score for a collected lead"""
        score = 0.0
        data_points = lead.get('data_points', {})
        email = lead.get('email', '')
        is_generic = PublicWebCollector._is_generic_email(email)
        is_verified = data_points.get('email_verified', False)

        if email:
            if is_verified and not is_generic:
                score += 25  # Real personal verified email (john@company.com)
            elif is_verified and is_generic:
                score += 12  # Generic but found on real page (info@ on contact page)
            elif not is_verified and is_generic:
                score += 3   # Inferred info@domain — very low confidence
            else:
                score += 8   # Unverified but personal-looking email
        if lead.get('phone'):
            score += 15
        if lead.get('company'):
            score += 15
        if lead.get('position'):
            score += 10
        if lead.get('industry'):
            score += 10
        if lead.get('website'):
            score += 5
        if lead.get('country'):
            score += 5
        if lead.get('city'):
            score += 5
        if lead.get('linkedin_url'):
            score += 10
        # Business email bonus (only for verified non-generic emails)
        if email and '@' in email and is_verified and not is_generic:
            domain = email.split('@')[1].lower()
            free_domains = ('gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
                            'aol.com', 'protonmail.com', 'icloud.com', 'mail.com',
                            'live.com', 'msn.com', 'yandex.com', 'zoho.com',
                            'tutanota.com', 'gmx.com', 'gmx.net', 'mail.ru')
            if domain not in free_domains:
                score += 15
        # Structured data bonus (JSON-LD = verified business data)
        if data_points.get('structured_data'):
            score += 5
        # Social profiles bonus
        socials = data_points.get('social_profiles', {})
        if socials:
            score += min(len(socials) * 3, 9)
        return min(score, 100.0)

    def search_businesses(self, query: str, country_code: str,
                          city: Optional[str] = None,
                          max_results: int = 20,
                          deadline: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Search for businesses in a specific country using DuckDuckGo API (via ddgs library).
        Returns a list of URLs to process.

        Args:
            query: Business/industry search term (e.g. "software companies")
            country_code: ISO country code (US, UK, DE, etc.)
            city: Optional city to narrow results
            max_results: Maximum number of result URLs to return
            deadline: Unix timestamp; stop searching early if exceeded
        """
        country_info = COUNTRY_SOURCES.get(country_code, {})
        country_name = country_info.get('name', country_code)
        cities = [city] if city else country_info.get('default_cities', [country_name])[:1]

        all_urls = []
        seen_urls: set = set()  # O(1) dedup instead of O(n) list scan per URL

        skip_domains = [
            # ── Search engines ───────────────────────────────────────────────
            'duckduckgo.com', 'google.com', 'bing.com', 'yahoo.com', 'yandex.com',
            # ── Social platforms ─────────────────────────────────────────────
            'facebook.com', 'twitter.com', 'x.com', 'instagram.com', 'tiktok.com',
            'youtube.com', 'reddit.com', 'pinterest.com', 'linkedin.com',
            'snapchat.com', 'tumblr.com', 'whatsapp.com', 'telegram.org',
            # ── Reference / utility sites ────────────────────────────────────
            'wikipedia.org', 'wikimedia.org', 'dictionary.com', 'merriam-webster.com',
            'thesaurus.com', 'britannica.com', 'encyclopedia.com',
            # ── B2B data aggregators ─────────────────────────────────────────
            'crunchbase.com', 'zoominfo.com', 'lusha.com', 'lusha.co',
            'apollo.io', 'hunter.io', 'leadiq.com', 'rocketreach.co',
            'snov.io', 'clearbit.com', 'contactout.com', 'signalhire.com',
            'seamless.ai', 'uplead.com', 'peopledatalabs.com',
            'dnb.com', 'owler.com', 'pitchbook.com', 'mattermark.com',
            'startupdata.com', 'startupblink.com', 'startupranking.com',
            # ── Company / lead directories ───────────────────────────────────
            'clutch.co', 'goodfirms.co', 'g2.com', 'capterra.com', 'getapp.com',
            'yelp.com', 'yellowpages.', 'bbb.org', 'manta.com', 'hotfrog.com',
            'cylex.com', 'superpages.com', 'bizbuysell.com', 'glassdoor.com',
            'trustpilot.com', 'sortlist.com', 'designrush.com', 'upcity.com',
            'bark.com', 'expertise.com', 'themanifest.com', 'techbehemoths.com',
            'agencyspotter.com', 'digitalagencynetwork.com', 'uscompanieslist.com',
            # ── Freelance / marketplace ──────────────────────────────────────
            'toptal.com', 'upwork.com', 'fiverr.com', 'freelancer.com',
            'guru.com', 'angieslist.com', 'angi.com', 'homeadvisor.com',
            'thumbtack.com',
            # ── Job boards ───────────────────────────────────────────────────
            'indeed.com', 'wellfound.com', 'angellist.com', 'f6s.com',
            'startupjobs.com', 'ziprecruiter.com', 'monster.com',
            # ── News / media / blogs ─────────────────────────────────────────
            'techcrunch.com', 'forbes.com', 'businessinsider.com', 'inc.com',
            'entrepreneur.com', 'fastcompany.com', 'medium.com', 'venturebeat.com',
            'wired.com', 'theverge.com', 'arstechnica.com', 'zdnet.com',
            'cnn.com', 'bbc.com', 'bbc.co.uk', 'reuters.com', 'bloomberg.com',
            'nytimes.com', 'washingtonpost.com', 'cnbc.com', 'apnews.com',
            'builtinsf.com', 'builtin.com', 'fundraiseinsider.com',
            # ── Product / startup discovery ──────────────────────────────────
            'producthunt.com', 'betalist.com', 'alternativeto.net',
            # ── E-commerce / global retail ───────────────────────────────────
            'amazon.com', 'ebay.com', 'aliexpress.com', 'alibaba.com',
            'nordstrom.com', 'walmart.com', 'target.com', 'macys.com',
            # ── Developer platforms ──────────────────────────────────────────
            'github.com', 'gitlab.com', 'stackoverflow.com', 'npmjs.com',
            # ── Events ──────────────────────────────────────────────────────
            'eventbrite.com', 'meetup.com', 'lu.ma',
            # ── Government / edu ─────────────────────────────────────────────
            'whitehouse.gov', '.gov',
        ]

        # Map country codes to DuckDuckGo region tokens for localised results
        _DDG_REGIONS = {
            'US': 'us-en', 'GB': 'uk-en', 'AU': 'au-en', 'CA': 'ca-en',
            'DE': 'de-de', 'FR': 'fr-fr', 'NL': 'nl-nl', 'ES': 'es-es',
            'IT': 'it-it', 'IN': 'in-en', 'SG': 'sg-en',
            # Middle East / Gulf
            'AE': 'xa-ar', 'SA': 'xa-ar', 'KW': 'xa-ar', 'QA': 'xa-ar',
            'BH': 'xa-ar', 'OM': 'xa-ar', 'EG': 'xa-ar', 'JO': 'xa-ar',
            'LB': 'xa-ar', 'IQ': 'xa-ar', 'TR': 'tr-tr',
            # Asia-Pacific
            'PK': 'pk-en', 'ID': 'id-id', 'MY': 'my-en', 'PH': 'ph-en',
            'TH': 'th-th', 'VN': 'vn-vi', 'KR': 'kr-ko', 'JP': 'jp-jp',
            # Africa
            'NG': 'wt-wt', 'ZA': 'za-en', 'KE': 'wt-wt', 'GH': 'wt-wt',
            # Americas
            'BR': 'br-pt', 'MX': 'mx-es', 'AR': 'ar-es', 'CO': 'co-es',
            'CL': 'cl-es', 'PE': 'pe-es',
        }
        ddg_region = _DDG_REGIONS.get(country_code.upper(), 'wt-wt')

        # Strip generic list-words that produce directory/article results
        _STRIP = {'top', 'best', 'leading', 'list', 'find', 'companies', 'company',
                  'businesses', 'agencies', 'firms'}
        query_core = ' '.join(w for w in query.split() if w.lower() not in _STRIP).strip() or query

        # Country TLD for targeted local search (highest-quality candidates)
        local_tld = _COUNTRY_TLDS.get(country_code.upper(), '')

        # ── Stage 0: Google Places API — structured local business data ─────────
        # Runs once (not per city) — gives phone + website before any scraping.
        # Results are returned as pre-built lead dicts with _places_url set.
        places_leads = self._search_places(
            query=query_core,
            city=cities[0] if cities else country_name,
            country_name=country_name,
            max_results=min(max_results, 10),
        )
        for pl in places_leads:
            url = pl.get('_places_url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_urls.append({
                    'url':          url,
                    'city':         cities[0] if cities else country_name,
                    'country_code': country_code,
                    'title':        pl.get('company', ''),
                    'snippet':      pl.get('address', ''),
                    '_places_data': pl,
                })

        for target_city in cities:
            if deadline is not None and time.time() > deadline:
                logger.info("[search_businesses] deadline reached, skipping remaining cities")
                break

            # ── Pipeline Stage 1: Search Discovery ───────────────────────────
            # Strategies ordered from most-to-least targeted.
            # Strategy 0 only runs when the country has a meaningful non-.com TLD.
            search_strategies: List[str] = []

            if local_tld and local_tld != 'com':
                # Strategy 0 (HIGHEST QUALITY): country-TLD-only search
                # site:.lb / site:.de etc. guarantees local company domains
                search_strategies.append(
                    f'"{query_core}" email contact phone site:.{local_tld}'
                )

            # Strategy 1: Exact city in quotes + contact-page signal
            # Quoted city forces DDG to surface pages mentioning this specific city
            search_strategies.append(
                f'"{query_core}" "{target_city}" inurl:contact OR inurl:about '
                f'"email" -inurl:blog -inurl:news -inurl:article -inurl:list'
            )

            # Strategy 2: Named executive at a local company
            # "CEO" / "founder" filters out article pages that list companies
            search_strategies.append(
                f'"{query_core}" "{country_name}" CEO OR founder OR owner '
                f'"contact" email -site:linkedin.com -inurl:directory -inurl:list'
            )

            # Strategy 3: Contact-page with phone/email visible
            search_strategies.append(
                f'"{query_core}" {target_city} "contact us" OR "email us" '
                f'phone -site:linkedin.com -inurl:news -inurl:blog'
            )

            for search_query in search_strategies:
                if len(all_urls) >= max_results:
                    break
                if deadline is not None and time.time() > deadline:
                    logger.info("[search_businesses] deadline reached, skipping remaining strategies")
                    break

                # ── Primary: Serper.dev (real Google results) ─────────────────
                serper_results = self._search_serper(
                    search_query, country_code=country_code, num=min(max_results, 8)
                )
                if serper_results:
                    logger.debug("[search_businesses] serper returned %d results", len(serper_results))
                else:
                    # ── Fallback: DuckDuckGo ──────────────────────────────────
                    logger.debug("[search_businesses] serper empty, falling back to DDG")
                    try:
                        from ddgs import DDGS
                        import re as _re
                        # DDG does not support Google operators — strip them
                        _ddg_q = _re.sub(r'[-]?(inurl|intitle|site|filetype):\S+', '', search_query)
                        _ddg_q = _re.sub(r'\s+', ' ', _ddg_q).strip() or search_query
                        serper_results = list(DDGS(timeout=8).text(
                            _ddg_q,
                            region=ddg_region,
                            max_results=min(max_results, 8),
                        ))
                    except Exception as ddg_exc:
                        logger.warning("[search_businesses] DDG fallback failed: %s", ddg_exc)
                        if deadline is None or time.time() < deadline:
                            self._search_ddg_html_fallback(search_query, target_city,
                                                           country_code, skip_domains,
                                                           all_urls, max_results)
                        serper_results = []

                for r in serper_results:
                    href = r.get('href', '') or r.get('link', '')
                    if not href or not href.startswith('http'):
                        continue
                    domain = urlparse(href).netloc.lower()
                    if any(sd in domain for sd in skip_domains):
                        continue
                    if href in seen_urls:
                        continue

                    # ── Pipeline Stage 1 gate: pre-screen before visiting ──────
                    title_r   = r.get('title', '')
                    snippet_r = r.get('body', '') or r.get('snippet', '')
                    if not self._prescreen_ddg_result(
                        href, title_r, snippet_r,
                        query_core, target_city, country_name,
                        country_code, local_tld,
                    ):
                        logger.debug("[prescreen] skipped: %s", href[:80])
                        continue

                    seen_urls.add(href)
                    all_urls.append({
                        'url': href,
                        'city': target_city,
                        'country_code': country_code,
                        'title': title_r,
                        'snippet': snippet_r,
                    })
                    if len(all_urls) >= max_results:
                        break

            if len(all_urls) >= max_results:
                break

        logger.info("[search_businesses] %d candidate URLs for %s/%s",
                    len(all_urls), country_code, target_city if cities else '*')
        return all_urls[:max_results]

    def _search_ddg_html_fallback(self, search_query: str, target_city: str,
                                   country_code: str, skip_domains: List[str],
                                   all_urls: List[Dict[str, Any]],
                                   max_results: int) -> None:
        """Fallback: search DuckDuckGo via raw HTML scraping"""
        encoded_query = quote_plus(search_query)
        search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        html = self._safe_fetch(search_url)
        if not html:
            return
        try:
            soup = BeautifulSoup(html, 'html.parser')
            links = soup.select('a.result__a')
            for link in links:
                href = link.get('href', '')
                if href and href.startswith('http'):
                    domain = urlparse(href).netloc.lower()
                    if not any(sd in domain for sd in skip_domains):
                        all_urls.append({
                            'url': href,
                            'city': target_city,
                            'country_code': country_code,
                        })
                    if len(all_urls) >= max_results:
                        break
        except Exception as e:
            logger.error(f"Error parsing fallback search results: {e}")

    def collect_by_country(self, query: str, country_code: str,
                           city: Optional[str] = None,
                           max_leads: int = 20,
                           deadline: Optional[float] = None,
                           on_progress=None) -> List[Dict[str, Any]]:
        """
        Main collection method: search for businesses in a country and extract lead data.

        Args:
            query: What to search for (e.g. "technology companies", "marketing agencies")
            country_code: Target country ISO code
            city: Optional city filter
            max_leads: Maximum leads to collect
            deadline: Unix timestamp after which the URL loop should stop early
            on_progress: Optional callable(done, total) fired after each URL

        Returns:
            List of structured lead dictionaries ready for database insertion
        """
        logger.info(
            f"[collector] collect_by_country: query='{query}' country={country_code} city={city}"
        )

        # Step 1: Search for business URLs — only fetch what we need (no over-fetch)
        urls = self.search_businesses(query, country_code, city, max_results=max_leads, deadline=deadline)
        logger.info(f"[collector] found {len(urls)} candidate URLs to process")

        # Step 2: Visit each URL and extract lead data
        leads: List[Dict[str, Any]] = []
        dedup = DuplicateFilter() if _MODULES_AVAILABLE else None
        seen_emails: set = set()
        seen_companies: set = set()

        for url_idx, url_info in enumerate(urls):
            if len(leads) >= max_leads:
                break
            if deadline is not None and time.time() > deadline:
                logger.info(f"[collector] deadline reached, stopping at {len(leads)}/{max_leads} leads")
                break

            logger.debug(f"[collector] processing URL: {url_info['url']}")
            if on_progress:
                on_progress(url_idx, len(urls))

            # ── Places pre-seed: inject structured data before fetch ────────
            places_data = url_info.get('_places_data', {})

            # ── Snippet-first optimisation ─────────────────────────────────
            snippet_text = url_info.get('snippet', '')
            snippet_emails = self._extract_emails(snippet_text)
            snippet_phones = self._extract_phones(snippet_text)
            if places_data.get('phone'):
                snippet_phones = snippet_phones or [places_data['phone']]
            _time_left = (deadline - time.time()) if deadline else 999
            _skip_fetch = bool(snippet_emails or snippet_phones) or _time_left < 15

            lead = None if _skip_fetch else self.collect_from_url(url_info['url'], url_info['country_code'])

            # ── Merge Places structured fields into extracted lead ──────────
            if lead and places_data:
                if not lead.get('company') and places_data.get('company'):
                    lead['company'] = places_data['company']
                if not lead.get('phone') and places_data.get('phone'):
                    lead['phone'] = places_data['phone']
                if not lead.get('address') and places_data.get('address'):
                    lead['address'] = places_data['address']

            # ── Snippet fallback: build a partial lead from search metadata ──
            if not lead and url_info.get('title'):
                snippet = url_info.get('snippet', '')
                snippet_emails = self._extract_emails(snippet)
                snippet_phones = self._extract_phones(snippet)
                country_info = COUNTRY_SOURCES.get(url_info['country_code'], {})
                country_name = country_info.get('name', '')

                raw_title = url_info['title']
                company_name = raw_title.split(' - ')[0].split(' | ')[0].split(' :: ')[0].strip()
                generic_patterns = [
                    r'^(top|best|leading|list|find|search|hire)\b',
                    r'\b(agencies|companies|firms|services|solutions)\s+(in|near|for)\b',
                    r'\b\d{4}\b',
                    r'\{.*\}',
                ]
                is_generic = any(re.search(p, company_name, re.IGNORECASE) for p in generic_patterns)
                if is_generic or len(company_name) > 80:
                    raw_domain = urlparse(url_info['url']).netloc.replace('www.', '')
                    company_name = raw_domain.split('.')[0].replace('-', ' ').title()

                fallback_email, fallback_email_verified = self._try_find_email(
                    url_info['url'], snippet_emails, company_name
                )
                snippet_industry = self._classify_industry(url_info['title'] + ' ' + snippet)
                lead = {
                    'name': company_name[:100],
                    'email': fallback_email,
                    'phone': snippet_phones[0] if snippet_phones else None,
                    'company': company_name[:255],
                    'position': None,
                    'country': country_name,
                    'city': url_info.get('city', ''),
                    'location': f"{url_info.get('city', '')}, {country_name}".strip(', '),
                    'industry': snippet_industry,
                    'website': url_info['url'],
                    'linkedin_url': None,
                    'interests': self._extract_interests(
                        url_info['title'] + ' ' + snippet, snippet_industry
                    ),
                    'source': f"web_public_{url_info['country_code'].lower()}",
                    'lead_type': 'company',
                    'email_type': 'unknown',
                    'completeness_score': 0.0,
                    'qualification_score': 0.0,
                    'status': 'pending',
                    'data_points': {
                        'email_verified': fallback_email_verified,
                        'collected_at': datetime.utcnow().isoformat(),
                        'source_url': url_info['url'],
                        'country_code': url_info['country_code'],
                        'search_title': url_info.get('title', ''),
                        'search_snippet': snippet[:300],
                    },
                }
                lead['qualification_score'] = self._calculate_initial_score(lead)
                logger.debug(
                    f"[collector] snippet fallback lead: company='{company_name}' "
                    f"email='{fallback_email}'"
                )

            if not lead:
                continue

            # ── Pipeline Stage A: name pre-filter ──────────────────────────────
            # Rejects URL-shaped names ("https://wholesalemotorgroup.com.au/"),
            # page-title names ("Contact Us"), and CDN emails before any scoring.
            _pf_ok, _pf_reason = pre_filter_lead(lead)
            if not _pf_ok:
                logger.debug(
                    f"[web] pre_filter rejected '{lead.get('name') or lead.get('email')}': "
                    f"{_pf_reason}"
                )
                continue

            # ── Pipeline Stage B: domain extraction ───────────────────────────
            # Ensure every lead carries its base domain so the pipeline can
            # cache Hunter/MX results and deduplicate by domain.
            website = (lead.get('website') or '').strip()
            if website:
                try:
                    _parsed_domain = urlparse(website).netloc.replace('www.', '')
                    if _parsed_domain:
                        dp = lead.setdefault('data_points', {})
                        dp['domain'] = _parsed_domain
                except Exception:
                    pass

            # ── Pipeline Stage C: intent detection ────────────────────────────
            # Scan page text / snippet for buying-intent signals and attach
            # intent metadata.  Used by the candidate_pipeline for scoring.
            if _PIPELINE_AVAILABLE:
                _raw_text = (
                    lead.get('data_points', {}).get('search_snippet', '')
                    or (lead.get('interests') or '')
                )
                if isinstance(_raw_text, list):
                    _raw_text = ' '.join(str(i) for i in _raw_text)
                _intent = _detect_intent(
                    str(_raw_text),
                    company=lead.get('company'),
                    industry=lead.get('industry'),
                )
                lead.setdefault('data_points', {})['intent'] = _intent

            # Patch city from search context if page extraction missed it
            if not lead.get('city') and url_info.get('city'):
                lead['city'] = url_info['city']
                lead['location'] = f"{url_info['city']}, {lead.get('country', '')}"

            # ── Deduplication ─────────────────────────────────────────────────
            if dedup is not None:
                is_dup, reason = dedup.is_duplicate(lead)
                if is_dup:
                    logger.debug(
                        f"[collector] duplicate skipped: "
                        f"{lead.get('company') or lead.get('email')} ({reason})"
                    )
                    continue
                dedup.register(lead)
            else:
                # Legacy set-based fallback
                email = (lead.get('email') or '').lower().strip()
                company = (lead.get('company') or '').lower().strip()
                if email and email in seen_emails:
                    continue
                if company and company in seen_companies:
                    continue
                if email:
                    seen_emails.add(email)
                if company:
                    seen_companies.add(company)

            leads.append(lead)

        logger.info(
            f"[collector] collect_by_country complete: "
            f"{len(leads)} unique leads from {country_code}"
        )
        return leads

    def search_people(self, query: str, country_code: str,
                      city: Optional[str] = None,
                      max_results: int = 20,
                      custom_queries: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Search for real professionals using Serper (Google) with LinkedIn-specific
        and team-page queries.  Falls back to DuckDuckGo when Serper quota is exhausted.

        When custom_queries is provided (from AI orchestrator), those queries are used
        directly instead of the built-in templates — they are already targeted to
        named decision-makers with country/industry context baked in.

        Priority order:
          1. LinkedIn profile search via Serper (real named individuals)
          2. Company team/leadership pages via Serper
          3. DuckDuckGo fallback (same queries, lower quality)
        """
        country_info = COUNTRY_SOURCES.get(country_code, {})
        country_name = country_info.get('name', country_code)
        # When using AI custom queries, run once (no city loop — queries already targeted).
        if custom_queries:
            cities = ['']
        else:
            cities = [city] if city else country_info.get('default_cities', [country_name])[:2]

        all_urls: List[Dict[str, Any]] = []
        seen_urls: set = set()

        skip_domains = [
            'duckduckgo.com', 'google.com', 'bing.com', 'yahoo.com',
            'youtube.com', 'reddit.com', 'wikipedia.org', 'wikimedia.org',
            'amazon.com', 'pinterest.com', 'tiktok.com', 'instagram.com',
            'facebook.com', 'twitter.com', 'x.com',
            'indeed.com', 'glassdoor.com', 'glassdoor.co',
            'ziprecruiter.com', 'monster.com', 'careerbuilder.com',
            'wellfound.com', 'lever.co', 'greenhouse.io', 'workday.com',
            'rocketreach.co', 'zoominfo.com', 'lusha.com', 'lusha.co',
            'apollo.io', 'hunter.io', 'leadiq.com', 'clearbit.com',
            'signalhire.com', 'snov.io', 'peopledatalabs.com',
            'theorg.com', 'crunchbase.com', 'pitchbook.com',
            'nytimes.com', 'forbes.com', 'bbc.', 'cnn.com',
            'medium.com', 'quora.com', 'slideshare.net',
        ]

        def _add_result(href: str, title: str, snippet: str,
                        target_city: str, is_li: bool) -> bool:
            """Validate and append a URL result. Returns True if added."""
            if not href or not href.startswith('http'):
                return False
            if href in seen_urls:
                return False
            domain = urlparse(href).netloc.lower()
            url_path = urlparse(href).path.lower()
            if any(sd in domain for sd in skip_domains):
                return False
            if any(kw in url_path for kw in ['/job/', '/jobs/', '/career',
                                              '/hiring', '/vacancy', '/apply']):
                return False
            if any(kw in domain for kw in ['careers.', 'jobs.', 'hiring.']):
                return False
            seen_urls.add(href)
            all_urls.append({
                'url':          href,
                'city':         target_city,
                'country_code': country_code,
                'title':        title,
                'snippet':      snippet,
                'is_linkedin':  is_li,
            })
            return True

        # ── Search strategy table ──────────────────────────────────────────────
        # When custom_queries come from the AI orchestrator, they are already
        # fully formed Google queries targeting named decision-makers.
        # Otherwise fall back to the built-in templates.
        if custom_queries:
            search_strategies = [
                (q, 'linkedin.com/in' in q.lower())
                for q in custom_queries
            ]
        else:
            search_strategies = [
                # 1. LinkedIn profile search (highest person signal)
                (
                    'site:linkedin.com/in "{query}" CEO OR founder OR CTO OR director '
                    '"{country}"',
                    True,
                ),
                (
                    'site:linkedin.com/in "{query}" owner OR president OR "head of" '
                    '"{city}" OR "{country}"',
                    True,
                ),
                # 2. Company team/leadership pages (personal contact emails)
                (
                    '"{query}" {city} {country} inurl:team OR inurl:about OR inurl:leadership '
                    '-inurl:jobs -site:linkedin.com',
                    False,
                ),
                # 3. Named executive contact pages
                (
                    '"{query}" {country} CEO OR founder OR owner "email" OR "contact" '
                    '-site:linkedin.com -inurl:jobs -inurl:news',
                    False,
                ),
            ]

        serper_key = (
            os.environ.get('SERPER_API_KEY') or os.environ.get('SERPER_KEY', '')
        ).strip()

        for target_city in cities:
            if len(all_urls) >= max_results:
                break

            for query_template, is_linkedin_q in search_strategies:
                if len(all_urls) >= max_results:
                    break

                # AI custom queries are already complete — use as-is.
                # Built-in templates need city/country substituted.
                if custom_queries:
                    search_query = query_template
                else:
                    search_query = query_template.format(
                        query=query,
                        city=target_city,
                        country=country_name,
                    )
                self._rate_limit_wait()

                # ── Primary: Serper (real Google) ──────────────────────────────
                serper_results: List[Dict[str, Any]] = []
                if serper_key:
                    try:
                        import json as _json
                        resp = requests.post(
                            'https://google.serper.dev/search',
                            headers={
                                'X-API-KEY': serper_key,
                                'Content-Type': 'application/json',
                            },
                            data=_json.dumps({
                                'q':   search_query,
                                'num': min(max_results, 10),
                                'gl':  country_code.lower() or 'us',
                            }),
                            timeout=10,
                            verify=False,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            for item in data.get('organic', []):
                                serper_results.append({
                                    'href':    item.get('link', ''),
                                    'title':   item.get('title', ''),
                                    'snippet': item.get('snippet', ''),
                                })
                    except Exception as _se:
                        logger.debug(f"[search_people] Serper error: {_se}")

                # ── Fallback 1: Bing (optional, requires BING_API_KEY) ──────────
                if not serper_results:
                    bing_raw = self._search_bing(search_query, n=min(max_results, 10))
                    for r in bing_raw:
                        serper_results.append({
                            'href':    r.get('href', ''),
                            'title':   r.get('title', ''),
                            'snippet': r.get('snippet', ''),
                        })

                # ── Fallback 2: DuckDuckGo ────────────────────────────────────
                if not serper_results:
                    try:
                        from ddgs import DDGS
                        ddg_raw = list(DDGS(timeout=6).text(
                            search_query.replace('site:linkedin.com/in ', ''),
                            max_results=min(max_results, 10),
                        ))
                        for r in ddg_raw:
                            serper_results.append({
                                'href':    r.get('href', ''),
                                'title':   r.get('title', ''),
                                'snippet': r.get('body', ''),
                            })
                    except Exception as _de:
                        logger.debug(f"[search_people] DuckDuckGo error: {_de}")

                for r in serper_results:
                    href = r.get('href', '')
                    is_li = is_linkedin_q or 'linkedin.com/in/' in href
                    _add_result(href, r.get('title', ''), r.get('snippet', ''),
                                target_city, is_li)
                    if len(all_urls) >= max_results:
                        break

        return all_urls[:max_results]

    def _collect_person_from_linkedin_snippet(self, url_info: Dict[str, Any],
                                               country_code: str) -> Optional[Dict[str, Any]]:
        """
        Build a person lead from a LinkedIn search snippet (without scraping LinkedIn).
        LinkedIn blocks scrapers, so we use the search title/snippet data.
        """
        title = url_info.get('title', '')
        snippet = url_info.get('snippet', '')
        url = url_info.get('url', '')

        # LinkedIn titles are like "John Smith - VP Marketing - Company Name | LinkedIn"
        # DuckDuckGo often concatenates multiple LinkedIn profiles in a single title:
        # "John Smith - CTO | LinkedInJane Doe - VP | LinkedIn"
        # So we split on "LinkedIn" first and take only the FIRST segment.
        title_segments = re.split(r'LinkedIn', title)
        title_first = title_segments[0].strip().rstrip('|').strip() if title_segments else title

        # Also remove trailing pipe
        title_clean = re.split(r'\s*\|\s*', title_first)[0].strip()

        # Normalize: ensure spaces around dashes that act as delimiters
        # A dash touching a capital letter is likely a delimiter, not a hyphen
        # e.g., "Name -CTO" -> "Name - CTO", but keep "Dorato-Hankins"
        title_clean = re.sub(r'\s*-([A-Z])', r' - \1', title_clean)
        title_clean = re.sub(r'([a-z])-\s', r'\1 - ', title_clean)

        # Fix DuckDuckGo stripped spaces in known patterns
        title_clean = re.sub(r'([a-z])([A-Z])', r'\1 \2', title_clean)

        # Split on " - " or " – " or " — " (with surrounding spaces)
        parts = re.split(r' [\-–—] ', title_clean)
        name = parts[0].strip() if parts else ''
        position = None
        company = None

        # Patterns that indicate a part is a LOCATION, not a position/company
        location_patterns = [
            'metropolitan area', 'metro area', 'greater', 'area',
            'region', 'county', 'state', 'province', 'district',
        ]

        # Work through parts[1:] to find position and company
        remaining_parts = []
        for part in parts[1:]:
            cleaned = part.strip()
            if not cleaned or cleaned.lower() in ('linkedin', ''):
                continue
            # Skip locations  
            if any(lp in cleaned.lower() for lp in location_patterns):
                continue
            remaining_parts.append(cleaned)

        if len(remaining_parts) >= 2:
            position = remaining_parts[0]
            company = remaining_parts[1]
        elif len(remaining_parts) == 1:
            # Could be position or company — check if it looks like a job title
            candidate = remaining_parts[0]
            title_indicators = [
                'ceo', 'cto', 'cfo', 'coo', 'cmo', 'vp ', 'vice president',
                'director', 'manager', 'head of', 'chief', 'lead', 'senior',
                'founder', 'co-founder', 'partner', 'president', 'officer',
                'engineer', 'developer', 'consultant', 'analyst', 'specialist',
                'advisor', 'architect', 'strategist',
            ]
            if any(ti in candidate.lower() for ti in title_indicators):
                position = candidate
            else:
                company = candidate

        # If position contains "at CompanyName", split it
        # Also handle "Directorat" (no space) - fix first
        if position:
            position = re.sub(r'(\w)(at\s+[A-Z])', r'\1 \2', position)
        if position and ' at ' in position:
            pos_parts = position.split(' at ', 1)
            position = pos_parts[0].strip()
            if not company:
                company = pos_parts[1].strip()

        # Reject names that end with just initials like "Nick M."
        if not name or len(name) < 4 or not self._is_person_name(name):
            return None
        # Reject abbreviated last names (e.g. "Nick M.")
        name_parts = name.split()
        if name_parts and len(name_parts[-1].strip('.')) <= 1:
            return None
        # Reject names with 3+ words that contain known business keywords
        # (e.g., "Dusit Thani Dubai" is a hotel, not a person)
        name_lower = name.lower()
        business_in_name = ['hotel', 'restaurant', 'group', 'dubai', 'center', 'centre',
                            'agency', 'studio', 'club', 'foundation', 'institute']
        if len(name_parts) >= 3 and any(bw in name_lower for bw in business_in_name):
            return None

        # Clean "LinkedIn" from fields (handles "LinkedIn", "Linked In", etc.)
        if company and re.search(r'linked\s*in', company, re.IGNORECASE):
            company = None
        if position and re.search(r'linked\s*in', position, re.IGNORECASE):
            position = None

        # Validate company name — reject if it looks like a page/tool description
        if company:
            bad_company_patterns = [
                'find email', 'phone number', 'search', 'lookup', 'database',
                'contact info', 'directory', 'addresses', 'free tool',
                'sign up', 'log in', 'register', 'subscribe',
            ]
            if any(bp in company.lower() for bp in bad_company_patterns):
                company = None

        # Also try to extract company from snippet if not in title
        if not company and snippet:
            # Fix DuckDuckGo space stripping in snippet for parsing
            snippet_fixed = re.sub(r'([a-z])([A-Z])', r'\1 \2', snippet)

            # Pattern 1: "Experience: CompanyName" (structured LinkedIn snippet)
            exp_match = re.search(r'Experience:\s*([A-Za-z][A-Za-z0-9\s&.,\'-]+?)(?:\s*·|\s*$)', snippet_fixed)
            if exp_match:
                candidate = exp_match.group(1).strip().rstrip('.')
                if 2 < len(candidate) < 100:
                    company = candidate[:255]
            # Pattern 2: "Title. CompanyName. Date" pattern (LinkedIn body)
            # e.g., "Chief Technology Officer. NYSE. Mar 2022"
            if not company:
                title_dot_match = re.search(
                    r'(?:Officer|CTO|CEO|CFO|COO|CIO|Director|VP|President|Founder|Manager|Lead)\s*\.\s*'
                    r'([A-Z][A-Za-z0-9\s&.,\'-]+?)\s*\.\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})',
                    snippet_fixed
                )
                if title_dot_match:
                    candidate = title_dot_match.group(1).strip().rstrip('.')
                    if 2 < len(candidate) < 100:
                        company = candidate[:255]
            # Pattern 3: "Position at CompanyName" in body
            if not company:
                at_match = re.search(r'(?:CTO|CEO|CFO|COO|CIO|Director|VP|Manager|Head|Chief|Officer|Founder)\s+(?:at|@)\s+([A-Z][A-Za-z0-9\s&.,\'-]+?)(?:\s*[·|•\-–,]|\.\s|$)', snippet_fixed)
                if at_match:
                    candidate = at_match.group(1).strip().rstrip('.')
                    if 2 < len(candidate) < 100:
                        company = candidate[:255]
            # Pattern 4: "Co-founder...and CTO. CompanyName, Inc." or "CTO. CompanyName"
            if not company:
                cto_dot = re.search(r'(?:CTO|CEO|CFO|COO)\s*\.\s*([A-Z][A-Za-z0-9\s&.,\'-]+?)(?:\s*\.\s*|\s*$)', snippet_fixed)
                if cto_dot:
                    candidate = cto_dot.group(1).strip().rstrip('.')
                    if 2 < len(candidate) < 100 and not any(d in candidate.lower() for d in ['month', 'year', 'present', 'jan', 'feb', 'mar', 'apr']):
                        company = candidate[:255]
            # Pattern 5: "Position · CompanyName is..." (LinkedIn body format)
            if not company:
                dot_match = re.search(r'(?:Officer|CTO|CEO|Director|VP|Founder|Manager|Engineer|Lead)\s*·\s*([A-Z][A-Za-z0-9\s&.,\'-]+?)(?:\s+is\b|\s+the\b|\s*·|\s*$)', snippet_fixed)
                if dot_match:
                    candidate = dot_match.group(1).strip().rstrip('.')
                    if 2 < len(candidate) < 100:
                        company = candidate[:255]
            # Pattern 6: Generic "at CompanyName" in any context
            # Stop at '·', '|', '•', '–', period+space, comma, or end-of-string
            # Cap at 50 chars to avoid capturing long snippet text bleed
            if not company:
                at_match2 = re.search(
                    r'\bat\s+([A-Z][A-Za-z0-9\s&\'-]{2,49})(?:\s*[·|•\-–,]|\.\s|$)',
                    snippet_fixed
                )
                if at_match2:
                    candidate = at_match2.group(1).strip().rstrip('.,')
                    if (2 < len(candidate) < 60
                            and not re.search(r'linked\s*in', candidate, re.IGNORECASE)
                            and '...' not in candidate):
                        company = candidate[:255]

        # Helper: fix DuckDuckGo stripped spaces (e.g., "ChiefTechnologyOfficer" -> "Chief Technology Officer")
        def _fix_camel_spaces(text: str) -> str:
            # Insert space before uppercase letters that follow lowercase
            # But preserve known acronyms like SaaS, IaaS, PaaS, etc.
            result = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
            # Fix broken acronyms: "Saa S" → "SaaS", "Iaa S" → "IaaS"
            result = re.sub(r'\b([A-Z])aa\s+S\b', r'\1aaS', result)
            result = re.sub(r'\bLin ked In\b', 'LinkedIn', result)
            return result

        # Clean position text
        if position:
            position = _fix_camel_spaces(position)
            position = re.sub(r'\.{2,}$', '', position).strip()
            position = re.sub(r',(\S)', r', \1', position)
            position = re.sub(r'&(\S)', r'& \1', position)
            position = re.sub(r'\((\w)', r'( \1', position)
            position = re.sub(r'\s*\(\s*', ' (', position)
            position = re.sub(r'\s*\)\s*', ') ', position).strip()
            # Remove trailing dashes/pipes
            position = re.sub(r'\s*[\-–—|]+\s*$', '', position).strip()
            # Truncate at "..." or if another person's name appears
            if '...' in position:
                position = position.split('...')[0].strip()
            # Limit position length and cut at suspicious breaks
            if len(position) > 80:
                position = position[:80].rsplit(' ', 1)[0].strip()
            # If position contains "at Company", extract company
            at_match = re.match(r'^(.+?)\s+at\s+(.+)$', position, re.IGNORECASE)
            if at_match and not company:
                position = at_match.group(1).strip()
                company = at_match.group(2).strip()
            # If position ends with ", CompanyName" where company looks like
            # an org (e.g., "Chief Technology Officer, NYSE"), extract it
            if not company and ', ' in position:
                pos_parts = position.rsplit(', ', 1)
                candidate_company = pos_parts[1].strip()
                # If the part after comma doesn't look like part of a title, it's a company
                title_words = [
                    'officer', 'director', 'manager', 'lead', 'head', 'senior',
                    'junior', 'vp', 'president', 'consultant', 'engineer',
                    'developer', 'analyst', 'specialist', 'strategy', 'operations',
                    'marketing', 'sales', 'product', 'technology', 'data',
                ]
                if not any(tw in candidate_company.lower() for tw in title_words):
                    # Looks like a company name
                    position = pos_parts[0].strip()
                    company = candidate_company

        # Clean company text
        if company:
            company = _fix_camel_spaces(company)
            # Fix spacing around & and , (e.g. "Marketing&Estrategia" → "Marketing & Estrategia")
            company = re.sub(r'&(\S)', r'& \1', company)
            company = re.sub(r',(\S)', r', \1', company)
            # Truncate at "..." — everything after is unreliable snippet overflow
            if '...' in company:
                company = company.split('...')[0].strip()
            company = re.sub(r'\.{2,}$', '', company).strip()
            # Remove trailing connector words left by truncation
            company = re.sub(r'\s+(and|or|the|&)\s*$', '', company, flags=re.IGNORECASE).strip()
            # Hard cap: real company names are rarely > 60 chars — truncate cleanly at word boundary
            if len(company) > 60:
                company = company[:60].rsplit(' ', 1)[0].strip()
            # Reject known placeholder / null-ish values
            _NULL_COMPANY = {'n/a', 'n/a.', 'na', 'none', 'unknown', 'null', '-', '—',
                             'not available', 'not specified', 'company', 'organization'}
            if company.lower().strip() in _NULL_COMPANY:
                company = None
            # Reject if company still contains "..." (bad parse)
            elif '...' in company or len(company) < 2:
                company = None

        if company:
            # Reject single-word companies that look like cities
            known_cities = [
                'albany', 'boston', 'chicago', 'dallas', 'denver', 'houston',
                'los angeles', 'miami', 'new york', 'philadelphia', 'phoenix',
                'san francisco', 'seattle', 'washington', 'london', 'paris',
                'berlin', 'tokyo', 'sydney', 'toronto', 'mumbai', 'dubai',
            ]
            if company.lower().strip() in known_cities:
                company = None

        # Reject company names that are really "Position + City" combos
        if company:
            title_words_in_company = [
                'director', 'manager', 'officer', 'cto', 'ceo', 'cfo',
                'marketing', 'engineering', 'founder', 'consultant',
            ]
            company_lower = company.lower()
            has_title = any(tw in company_lower for tw in title_words_in_company)
            has_city = any(c in company_lower for c in known_cities)
            if has_title and has_city:
                company = None

        # Reject company names that look like they contain a person's name after a comma or "and"
        # e.g. "Technology, Media and Andrew Trossman" — the "and FirstName LastName" is a giveaway
        if company and re.search(r'\band\s+[A-Z][a-z]+\s+[A-Z][a-z]+', company):
            # Strip the "and PersonName" tail and try to salvage the front
            company = re.sub(r'\s+and\s+[A-Z][a-z]+\s+[A-Z][a-z]+.*$', '', company).strip()
            if len(company) < 2:
                company = None

        # Try to extract email from snippet
        emails = self._extract_emails(snippet)

        country_info = COUNTRY_SOURCES.get(country_code, {})
        country_name = country_info.get('name', '')

        # Known large-enterprise company keywords — individual emails not findable publicly
        _LARGE_ENTERPRISE_KEYWORDS = {
            'microsoft', 'google', 'amazon', 'apple', 'meta', 'facebook',
            'ibm', 'oracle', 'sap', 'salesforce', 'akamai', 'dxc',
            'accenture', 'deloitte', 'pwc', 'kpmg', 'mckinsey', 'ey ',
            'capgemini', 'infosys', 'wipro', 'tata', 'cognizant', 'hp ',
            'dell', 'cisco', 'intel', 'qualcomm', 'broadcom', 'nvidia',
            'linkedin', 'twitter', 'x.com', 'youtube', 'netflix', 'uber',
            'airbnb', 'lyft', 'stripe', 'paypal', 'visa', 'mastercard',
        }
        company_lower = (company or '').lower()
        is_large_enterprise = any(kw in company_lower for kw in _LARGE_ENTERPRISE_KEYWORDS)

        # If no email found in snippet, use SocialMediaCollector's full enrichment pipeline:
        # domain cache → _find_company_domain → _scrape_website_contact (CF decode, obfuscation etc.)
        company_website = None
        email_is_generic = False
        if not emails and company and not is_large_enterprise:
            try:
                from app.services.social_media_collector import get_social_collector, _email_matches_person
                from urllib.parse import urlparse as _up
                social = get_social_collector()
                # _find_company_domain uses the shared domain cache (avoids repeat DDG calls)
                company_website = social._find_company_domain(company)
                if company_website:
                    scraped_email, _ = social._scrape_website_contact(company_website)
                    if scraped_email:
                        # Domain check: only accept emails whose domain matches the scraped site.
                        # Prevents press@pinterest.com / suscripciones@merca20.com on wrong leads.
                        site_domain = _up(company_website).netloc.replace('www.', '').lower()
                        email_domain = scraped_email.split('@')[-1].lower()
                        domain_ok = (email_domain == site_domain or site_domain.endswith('.' + email_domain))
                        if domain_ok:
                            # Fix 4 — wrong attribution: reject personal emails that clearly
                            # belong to a different employee (e.g. richard.mobbs@ for Zen Bahar).
                            # Generic emails (info@, contact@) are company-wide — always OK.
                            if self._is_generic_email(scraped_email) or _email_matches_person(scraped_email, name):
                                emails = [scraped_email]
                            else:
                                logger.debug(
                                    f"Rejected {scraped_email!r} — local part does not match person '{name}'"
                                )
                        else:
                            logger.debug(
                                f"Discarded email {scraped_email!r} — domain {email_domain!r} "
                                f"does not match site {site_domain!r}"
                            )

                # Fix 2 — Hunter.io fallback: find personal email when scraping yields nothing.
                if not emails and company_website:
                    _hunter_domain = _up(company_website).netloc.replace('www.', '')
                    _name_parts = name.strip().split()
                    if len(_name_parts) >= 2 and _hunter_domain:
                        hunter_email = social._find_email_via_hunter(
                            _name_parts[0], _name_parts[-1], _hunter_domain
                        )
                        if hunter_email:
                            emails = [hunter_email]
            except Exception as exc:
                logger.debug(f"Email enrichment error for '{name}': {exc}")

        # Fix 3 — company email fallback: allow generic emails but flag them as 'company' type.
        # (Previously _personal_email_only() dropped them entirely.)
        final_email = emails[0] if emails else None
        if final_email:
            email_is_generic = self._is_generic_email(final_email)

        lead = {
            'name': name[:255],
            # Fix 3: keep generic emails as company-contact fallback; tag via email_type in data_points.
            'email': final_email,
            'phone': None,
            'company': (company or '')[:255],
            'position': (position or '')[:255] if position else None,
            'country': country_name,
            'city': url_info.get('city', ''),
            'location': f"{url_info.get('city', '')}, {country_name}".strip(', '),
            'industry': self._classify_industry(title + ' ' + snippet),
            'website': company_website or None,
            'linkedin_url': url.split('?')[0],
            'interests': self._extract_interests(title + ' ' + snippet, self._classify_industry(title + ' ' + snippet)),
            'source': f'linkedin_search_{country_code.lower()}',
            'lead_type': 'person',
            'qualification_score': 0.0,
            'status': 'warm',
            'data_points': {
                'collected_at': datetime.utcnow().isoformat(),
                'source_url': url,
                'country_code': country_code,
                'search_title': title,
                'search_snippet': snippet[:300],
                'collection_type': 'people',
                'email_verified': bool(final_email) and not email_is_generic,
                'email_is_generic': email_is_generic,
                'email_type': 'company' if email_is_generic else ('personal' if final_email else None),
                'large_enterprise': is_large_enterprise,
            },
        }
        lead['qualification_score'] = self._calculate_initial_score(lead)
        return lead

    @staticmethod
    def _is_person_name(name: str) -> bool:
        """Check if a string looks like a real person name (not a company or title)."""
        if not name or len(name) < 3 or len(name) > 80:
            return False
        # Must have at least two words (first + last name)
        words = name.strip().split()
        if len(words) < 2 or len(words) > 5:
            return False
        # Each word should start with uppercase and be mostly alpha
        for w in words:
            clean = w.strip('.,()-')
            if not clean:
                continue
            if not clean[0].isupper():
                return False
            if not all(c.isalpha() or c in "'-." for c in clean):
                return False
        # Reject common non-person patterns
        lower = name.lower()
        non_person = [
            'company', 'group', 'inc', 'llc', 'ltd', 'corp', 'agency',
            'services', 'solutions', 'marketing', 'digital', 'global',
            'consulting', 'associates', 'partners', 'team', 'staff',
            'director', 'manager', 'associate', 'senior', 'junior',
            'what does', 'how to', 'about us', 'contact us', 'our team',
            'brand', 'hiring', 'job', 'career', 'position', 'role',
            'nothing found', 'not found', 'page not', 'error', 'sorry',
            'search results', 'no results', 'get started',
        ]
        if any(np in lower for np in non_person):
            return False
        # Reject names composed entirely of industry/tech keywords
        _kw = {
            'artificial', 'intelligence', 'machine', 'learning', 'deep',
            'software', 'technology', 'tech', 'digital', 'data', 'science',
            'cloud', 'cyber', 'security', 'automation', 'blockchain',
            'saas', 'fintech', 'startup', 'enterprise', 'platform',
            'analytics', 'developer', 'engineering', 'innovation',
            'smart', 'intelligent', 'advanced', 'professional',
        }
        words_lower = [w.strip('.,()-').lower() for w in words if w.strip('.,()-')]
        if words_lower and all(w in _kw for w in words_lower):
            return False
        return True

    def collect_people_from_url(self, url: str, country_code: str = '') -> List[Dict[str, Any]]:
        """
        Collect people/contacts from a single URL.
        Extracts multiple people from team pages, about pages, etc.
        Returns list of person leads.
        """
        html = self._safe_fetch(url)
        if not html:
            return []

        try:
            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)

            company = self._extract_company_name(soup, text)
            industry = self._classify_industry(text)
            address = self._extract_address(soup)
            page_linkedin = self._extract_linkedin_url(soup, html)

            country_info = COUNTRY_SOURCES.get(country_code, {})
            country_name = country_info.get('name', address.get('country', ''))

            # Extract multiple people from the page
            people = self._extract_people_from_page(soup, text, url)
            leads = []

            for person in people:
                # Validate person name
                if not self._is_person_name(person['name']):
                    continue

                # Also check for page-level emails/phones as fallback
                page_emails = self._extract_emails(text) if not person.get('email') else []

                # Determine email and verification status — person leads only get personal emails
                if person.get('email') and not self._is_generic_email(person['email']):
                    p_email, p_email_verified = person['email'], True
                elif page_emails:
                    # _extract_emails returns personal first, then generic — take first personal
                    personal_emails = [e for e in page_emails if not self._is_generic_email(e)]
                    if personal_emails:
                        p_email, p_email_verified = personal_emails[0], True
                    else:
                        p_email, p_email_verified = None, False
                else:
                    raw_email, verified = self._try_find_email(url, [], company)
                    p_email = self._personal_email_only(raw_email)
                    p_email_verified = verified and p_email is not None

                lead = {
                    'name': person['name'][:255],
                    'email': p_email,
                    'phone': person.get('phone'),
                    'company': (company or '')[:255],
                    'position': person.get('position'),
                    'country': country_name,
                    'city': address.get('city', ''),
                    'location': f"{address.get('city', '')}, {country_name}".strip(', '),
                    'industry': industry,
                    'website': url,
                    'linkedin_url': person.get('linkedin_url') or page_linkedin,
                    'interests': self._extract_interests(text, industry),
                    'source': f'web_people_{country_code.lower()}' if country_code else 'web_people',
                    'lead_type': 'person',
                    'qualification_score': 0.0,
                    'status': 'warm',
                    'data_points': {
                        'email_verified': p_email_verified,
                        'collected_at': datetime.utcnow().isoformat(),
                        'source_url': url,
                        'country_code': country_code,
                        'collection_type': 'people',
                        'company_name': company,
                    },
                }
                lead['qualification_score'] = self._calculate_initial_score(lead)
                leads.append(lead)

            # If no structured people found, fall back to single-contact extraction
            if not leads:
                person_name = self._extract_person_name(soup)
                emails = self._extract_emails(text)
                phones = self._extract_phones(text)
                position = self._extract_position(soup)

                if person_name and self._is_person_name(person_name):
                    raw_fb_email, fb_email_verified = self._try_find_email(url, emails, company)
                    fb_email = self._personal_email_only(raw_fb_email)
                    fb_email_verified = fb_email_verified and fb_email is not None
                    lead = {
                        'name': person_name[:255],
                        'email': fb_email,
                        'phone': phones[0] if phones else None,
                        'company': (company or '')[:255],
                        'position': position,
                        'country': country_name,
                        'city': address.get('city', ''),
                        'location': f"{address.get('city', '')}, {country_name}".strip(', '),
                        'industry': industry,
                        'website': url,
                        'linkedin_url': page_linkedin,
                        'interests': self._extract_interests(text, industry),
                        'source': f'web_people_{country_code.lower()}' if country_code else 'web_people',
                        'lead_type': 'person',
                        'qualification_score': 0.0,
                        'status': 'warm',
                        'data_points': {
                            'email_verified': fb_email_verified,
                            'collected_at': datetime.utcnow().isoformat(),
                            'source_url': url,
                            'country_code': country_code,
                            'collection_type': 'people',
                        },
                    }
                    lead['qualification_score'] = self._calculate_initial_score(lead)
                    leads.append(lead)

            return leads

        except Exception as e:
            logger.error(f"Error extracting people from {url}: {e}")
            return []

    def collect_people_by_country(self, query: str, country_code: str,
                                   city: Optional[str] = None,
                                   max_leads: int = 20,
                                   deadline: Optional[float] = None,
                                   on_progress=None,
                                   custom_queries: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Collect people/professional leads from a country.

        Pipeline per lead:
          1. LinkedIn snippet → named person from Google search result
          2. Team/about page scrape → named people with extracted contacts
          3. Hunter enrichment — for each person without a personal email,
             call Hunter domain-search to find the most likely work email
          4. Fallback sub-page scrape (/contact, /about) if still no email

        custom_queries: AI-generated Google search queries from CollectionOrchestrator.
          When provided, these replace the built-in search templates.
        """
        logger.info(f"Collecting people: query='{query}', country={country_code}, city={city}, "
                    f"ai_queries={len(custom_queries) if custom_queries else 0}")

        urls = self.search_people(query, country_code, city,
                                  max_results=max_leads * 2,
                                  custom_queries=custom_queries)
        logger.info(f"Found {len(urls)} candidate URLs for people search")

        # Load Hunter key once for enrichment pass
        _hunter_key = (
            os.environ.get('HUNTER_IO_API_KEY') or
            os.environ.get('HUNTER_API_KEY', '')
        ).strip()
        _hunter_configured = bool(_hunter_key and _hunter_key != 'test-key-123')

        _GENERIC_EMAIL_PREFIXES = frozenset({
            'info', 'contact', 'hello', 'support', 'sales', 'admin',
            'team', 'marketing', 'office', 'press', 'hr',
        })

        def _email_needs_enrichment(email: str) -> bool:
            """True when we should try Hunter to find a real personal email."""
            if not email:
                return True
            local = email.split('@')[0].lower() if '@' in email else email.lower()
            return local in _GENERIC_EMAIL_PREFIXES

        def _hunter_find_person_email(domain: str, first: str, last: str) -> Optional[str]:
            """Call Hunter to find a personal work email for a named individual."""
            if not _hunter_configured or not domain:
                return None
            try:
                endpoint = 'https://api.hunter.io/v2/email-finder'
                params: Dict[str, Any] = {'domain': domain, 'api_key': _hunter_key}
                if first and last:
                    params['first_name'] = first
                    params['last_name']  = last
                    resp = requests.get(endpoint, params=params, timeout=8)
                else:
                    # Domain search — pick first result with confidence ≥ 80
                    resp = requests.get(
                        'https://api.hunter.io/v2/domain-search',
                        params={'domain': domain, 'limit': 3, 'api_key': _hunter_key},
                        timeout=8,
                    )
                data = resp.json()
                if resp.status_code == 200 and 'data' in data:
                    ed = data['data']
                    if isinstance(ed, dict):
                        # email-finder response
                        em  = ed.get('email', '')
                        con = ed.get('score', 0)
                        if em and con >= 75:
                            return em
                        # domain-search emails list
                        for entry in ed.get('emails', []):
                            if entry.get('confidence', 0) >= 75:
                                return entry.get('value', '') or None
            except Exception as _he:
                logger.debug(f"[people] Hunter error for {domain}: {_he}")
            return None

        leads: List[Dict[str, Any]] = []
        seen_names: set = set()
        seen_emails: set = set()

        for url_idx, url_info in enumerate(urls):
            if len(leads) >= max_leads:
                break
            if deadline is not None and time.time() > deadline:
                logger.info(f"[collector] people deadline reached at {len(leads)}/{max_leads}")
                break
            if on_progress:
                on_progress(url_idx, len(urls))

            # ── 1. LinkedIn snippet → named person (no scraping needed) ─────────
            if url_info.get('is_linkedin'):
                lead = self._collect_person_from_linkedin_snippet(url_info, country_code)
                if lead:
                    name_key = lead['name'].lower().strip()
                    if name_key in seen_names:
                        continue
                    email_raw = (lead.get('email') or '').lower().strip()

                    # ── Hunter enrichment for LinkedIn leads without a personal email ──
                    if _email_needs_enrichment(email_raw) and lead.get('website'):
                        _domain = urlparse(lead['website']).netloc.replace('www.', '').lower()
                        _parts  = lead['name'].strip().split()
                        _first  = _parts[0] if _parts else ''
                        _last   = _parts[-1] if len(_parts) > 1 else ''
                        hunter_email = _hunter_find_person_email(_domain, _first, _last)
                        if hunter_email:
                            lead['email'] = hunter_email
                            lead.setdefault('data_points', {})['email_verified'] = True
                            lead['data_points']['email_source'] = 'hunter_api'
                            email_raw = hunter_email.lower().strip()
                            logger.info(f"[people] Hunter found email for {lead['name']}: {hunter_email}")

                    if not email_raw or email_raw in seen_emails:
                        if email_raw in seen_emails:
                            continue
                    seen_names.add(name_key)
                    if email_raw:
                        seen_emails.add(email_raw)
                    leads.append(lead)
                continue

            # ── 2. Team/about page scrape ─────────────────────────────────────
            page_leads = self.collect_people_from_url(url_info['url'], url_info['country_code'])

            for lead in page_leads:
                if len(leads) >= max_leads:
                    break

                name_key  = lead['name'].lower().strip()
                email_raw = (lead.get('email') or '').lower().strip()

                if name_key in seen_names:
                    continue
                if email_raw and email_raw in seen_emails:
                    continue

                # Override city if not extracted
                if not lead.get('city') and url_info.get('city'):
                    lead['city']     = url_info['city']
                    lead['location'] = f"{url_info['city']}, {lead.get('country', '')}"

                # ── 3. Hunter enrichment for leads without a personal email ────
                if _email_needs_enrichment(email_raw):
                    _website = lead.get('website') or url_info.get('url', '')
                    if _website:
                        _domain = urlparse(_website).netloc.replace('www.', '').lower()
                        _parts  = lead['name'].strip().split()
                        _first  = _parts[0] if _parts else ''
                        _last   = _parts[-1] if len(_parts) > 1 else ''
                        hunter_email = _hunter_find_person_email(_domain, _first, _last)
                        if hunter_email:
                            lead['email'] = hunter_email
                            lead.setdefault('data_points', {})['email_verified'] = True
                            lead['data_points']['email_source'] = 'hunter_api'
                            email_raw = hunter_email.lower().strip()
                            logger.info(
                                f"[people] Hunter found email for {lead['name']}: {hunter_email}"
                            )

                # ── 4. Fallback sub-page scrape if still no email ─────────────
                if _email_needs_enrichment(email_raw):
                    _website = lead.get('website') or url_info.get('url', '')
                    if _website:
                        try:
                            from app.services.lead_fallback import scrape_contact_pages
                            scraped_email, scraped_phone = scrape_contact_pages(_website)
                            # Only use if it's a personal-looking email
                            if scraped_email:
                                _local = scraped_email.split('@')[0].lower()
                                if _local not in _GENERIC_EMAIL_PREFIXES:
                                    lead['email'] = scraped_email
                                    email_raw = scraped_email.lower().strip()
                                    lead.setdefault('data_points', {})['email_source'] = (
                                        'contact_page_scrape'
                                    )
                            if scraped_phone and not lead.get('phone'):
                                lead['phone'] = scraped_phone
                        except Exception:
                            pass

                seen_names.add(name_key)
                if email_raw:
                    seen_emails.add(email_raw)
                leads.append(lead)

        logger.info(
            f"[people] Collected {len(leads)} people from {country_code} "
            f"(hunter_configured={_hunter_configured})"
        )
        return leads

    def collect_multi_country(self, query: str, country_codes: List[str],
                              max_per_country: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        """
        Collect leads from multiple countries.

        Args:
            query: Search query
            country_codes: List of country codes to search
            max_per_country: Max leads per country

        Returns:
            Dict mapping country_code -> list of leads
        """
        results = {}
        for code in country_codes:
            if code not in COUNTRY_SOURCES:
                logger.warning(f"Unknown country code: {code}")
                continue
            try:
                leads = self.collect_by_country(query, code, max_leads=max_per_country)
                results[code] = leads
            except Exception as e:
                logger.error(f"Error collecting from {code}: {e}")
                results[code] = []
        return results


def get_supported_countries() -> List[Dict[str, str]]:
    """Return list of supported countries with codes and names"""
    return [
        {'code': code, 'name': info['name']}
        for code, info in sorted(COUNTRY_SOURCES.items(), key=lambda x: x[1]['name'])
    ]


def get_collector() -> PublicWebCollector:
    """Get a configured collector instance"""
    return PublicWebCollector(rate_limit=0.8, timeout=7)
