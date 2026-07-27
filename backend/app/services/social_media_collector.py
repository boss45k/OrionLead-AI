"""
Social Media Public Group Collector
Collects lead data from public social media groups and communities.
Sources: Reddit (public API), Telegram (public channels), X/Twitter & Facebook (via search).
Uses ethical scraping with rate limiting — only public, indexable content.
"""

import re
import time
import logging
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timezone
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

# ── Production modules ────────────────────────────────────────────────────────
try:
    from app.services.lead_extractor import _email_type
    from app.services.lead_validator import validate_and_score, DuplicateFilter
    from app.services.lead_fallback import enrich_lead_fallbacks
    _MODULES_AVAILABLE = True
except ImportError as _imp_err:
    logger.warning(f"[social] lead modules not available: {_imp_err}")
    _MODULES_AVAILABLE = False

# ── Smart pipeline helpers ────────────────────────────────────────────────────
try:
    from app.services.name_validator import pre_filter_lead as _pre_filter_lead
    from app.services.intent_detector import detect_intent as _detect_intent, intent_quality_boost
    _SOCIAL_PIPELINE = True
except ImportError:
    _SOCIAL_PIPELINE = False

    def _pre_filter_lead(lead: dict) -> "tuple[bool, str]":  # type: ignore[misc]
        return True, ''

    def _detect_intent(*a, **kw) -> dict:       # type: ignore[misc]
        return {'buying_intent': 'none', 'intent_confidence': 0.0}

    def intent_quality_boost(intent: dict) -> float:  # type: ignore[misc]
        return 0.0

# ============================================================================
# Platform configs & popular business subreddits / channels
# ============================================================================

REDDIT_SUBREDDITS = {
    'startups': ['r/startups', 'r/Entrepreneur', 'r/smallbusiness', 'r/SaaS', 'r/startup'],
    'technology': ['r/technology', 'r/programming', 'r/webdev', 'r/devops', 'r/artificial'],
    'marketing': ['r/marketing', 'r/digital_marketing', 'r/socialmedia', 'r/SEO', 'r/PPC'],
    'finance': ['r/fintech', 'r/investing', 'r/CryptoCurrency', 'r/personalfinance'],
    'ecommerce': ['r/ecommerce', 'r/shopify', 'r/FulfillmentByAmazon', 'r/dropship'],
    'design': ['r/design', 'r/graphic_design', 'r/UI_Design', 'r/UXDesign'],
    'sales': ['r/sales', 'r/Entrepreneur', 'r/leadgeneration'],
    'realestate': ['r/realestate', 'r/RealEstateInvesting', 'r/CommercialRealEstate'],
    'health': ['r/HealthIT', 'r/digitalhealth', 'r/biotech'],
    'ai': ['r/MachineLearning', 'r/artificial', 'r/OpenAI', 'r/LocalLLaMA'],
    'consulting': ['r/consulting', 'r/freelance', 'r/Upwork'],
    'education': ['r/edtech', 'r/OnlineEducation', 'r/education'],
    'logistics': ['r/supplychain', 'r/logistics', 'r/freight'],
}

PLATFORM_TYPES = ['reddit', 'telegram', 'twitter', 'facebook', 'linkedin']

# Generic email prefixes — catch-all addresses, not personal contacts
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


def _is_generic_email(email: str) -> bool:
    """Check if an email is a generic catch-all address."""
    if not email or '@' not in email:
        return False
    local = email.lower().split('@')[0]
    return local in GENERIC_EMAIL_PREFIXES


_PERSONAL_DOMAINS = frozenset({
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com',
    'protonmail.com', 'icloud.com', 'me.com', 'msn.com', 'aol.com',
})

_COMPANY_STOPWORDS = frozenset({
    'the', 'and', 'inc', 'llc', 'ltd', 'corp', 'company', 'group',
    'holding', 'holdings', 'international', 'global', 'solutions',
    'services', 'technology', 'technologies',
})

# Known rebrands: if company name contains key, also check alias domains
_COMPANY_ALIASES: Dict[str, List[str]] = {
    'meta': ['facebook', 'fb', 'instagram', 'whatsapp'],
    'alphabet': ['google', 'deepmind', 'waymo'],
    'twitter': ['x.com', 'xcom'],
}


def _email_domain_matches_company(email: str, company: str) -> bool:
    """
    Return False when a generic email clearly belongs to a different company.

    Example: hello@windsor.ai saved under company='Meta' → False.
    Personal free emails (gmail etc.) are always allowed.
    Non-generic emails are let through — the person may freelance/consult.
    Only blocks generic catch-alls (hello@, info@, contact@…) whose domain
    shares no word with the company name.
    """
    if not email or '@' not in email or not company:
        return True

    domain = email.split('@')[1].lower()

    # Personal free email → always fine regardless of company
    if domain in _PERSONAL_DOMAINS:
        return True

    # Only apply domain-company check to generic/catch-all emails
    if not _is_generic_email(email):
        return True

    # Strip TLD noise and split domain into words
    bare = re.sub(r'\.(com|io|ai|net|org|co|uk|de|fr|us|biz|app|tech|info)$', '', domain)
    bare = re.sub(r'[^a-z0-9]', ' ', bare)

    # Extract meaningful words from the company name
    company_words = [
        re.sub(r'[^a-z]', '', w)
        for w in company.lower().split()
        if len(w) > 3 and w.lower() not in _COMPANY_STOPWORDS
    ]
    if not company_words:
        return True  # Company name too short/generic to check

    # Direct word match
    if any(word in bare for word in company_words):
        return True

    # Check known rebrands/aliases
    for alias_key, alias_words in _COMPANY_ALIASES.items():
        if alias_key in company.lower():
            if any(a in bare for a in alias_words):
                return True

    # Generic email domain doesn't match company at all → mis-attributed
    return False


def _email_matches_person(email: str, person_name: str) -> bool:
    """Return True if the email could plausibly belong to this person, False if it clearly belongs to someone else.

    Used to prevent wrong attribution — e.g. richard.mobbs@itp.com being stored
    for Zen Bahar's lead just because the scraper found it on her company's page.

    Logic:
    - Generic emails (info@, contact@) are company-wide — not mis-attributed, always OK.
    - For personal emails, the local part must contain at least one significant name part.
      'zen.bahar@...' → local 'zenbahar' contains 'zen' ✓
      'richard.mobbs@...' → local 'richardmobbs' contains neither 'zen' nor 'bahar' ✗
    - Returns True when we can't tell (no usable name parts, or very short name).
    """
    if not email or '@' not in email or not person_name:
        return True
    # Generic emails belong to the company, not mis-attributed to a specific person
    if _is_generic_email(email):
        return True
    local = re.sub(r'[._\-]', '', email.split('@')[0].lower())
    parts = [re.sub(r'[^a-z]', '', p) for p in person_name.lower().strip().split()]
    # Keep only parts long enough to be meaningful (≥3 chars avoids false positives)
    parts = [p for p in parts if len(p) >= 3]
    if not parts:
        return True  # No usable name parts — allow it
    return any(part in local for part in parts)


def _validate_email(email: str) -> bool:
    """Basic email validation beyond just regex matching."""
    if not email or '@' not in email:
        return False
    # Strip trailing punctuation that regex often captures (period, comma, bracket)
    e = email.strip().rstrip('.,;:!?)>]}"\'').lower()
    if '@' not in e:
        return False
    local, domain = e.split('@', 1)
    if len(local) < 2 or len(domain) < 4:
        return False
    if '..' in local or '..' in domain:
        return False
    # Reject all-numeric local parts (e.g. 123@domain.com — usually tracking IDs)
    if local.replace('.', '').replace('-', '').replace('_', '').isdigit():
        return False
    # Reject locals that are too long (often obfuscation artifacts)
    if len(local) > 64:
        return False
    reject_prefixes = ('noreply', 'no-reply', 'mailer-daemon', 'postmaster',
                       'donotreply', 'bounce', 'unsubscribe', 'webmaster',
                       'notifications', 'automated', 'system', 'robot',
                       'newsletter', 'updates', 'alerts', 'digest')
    if any(local.startswith(rp) for rp in reject_prefixes):
        return False
    reject_domains = ('example.com', 'example.org', 'example.net',
                      'sentry.io', 'gravatar.com', 'w3.org',
                      'schema.org', 'wordpress.org', 'wixpress.com',
                      'googleusercontent.com', 'cloudflare.com',
                      'amazonaws.com', 'sendgrid.net', 'mailchimp.com',
                      'hubspotfree.net', 'test.com', 'placeholder.com',
                      'yourdomain.com', 'company.com', 'domain.com',
                      'email.com', 'yourcompany.com')
    if any(rd in domain for rd in reject_domains):
        return False
    if e.endswith(('.png', '.jpg', '.gif', '.css', '.js', '.svg', '.ico', '.woff')):
        return False
    # Must have a valid TLD (at least 2 chars after last dot)
    if '.' not in domain or len(domain.rsplit('.', 1)[-1]) < 2:
        return False
    return True


class SocialMediaCollector:
    """Collects business leads from public social media groups & communities."""

    def __init__(self, rate_limit: float = 0.8, timeout: int = 10):
        self.rate_limit = rate_limit
        self.timeout = timeout
        self.session = requests.Session()
        try:
            import certifi
            self.session.verify = certifi.where()
            self._ssl_verify = certifi.where()
        except ImportError:
            self._ssl_verify = True
        self._user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
        ]
        self._ua_index = 0
        self.session.headers.update({
            'User-Agent': self._user_agents[0],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        self._last_request_time = 0
        # Domain cache: company_key → (domain_url, timestamp) — avoids repeat DDG lookups
        self._domain_cache: Dict[str, tuple] = {}
        self._domain_cache_ttl = 3600  # 1 hour TTL

    def _rate_limit_wait(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request_time = time.time()

    def _rotate_ua(self):
        self._ua_index = (self._ua_index + 1) % len(self._user_agents)
        self.session.headers['User-Agent'] = self._user_agents[self._ua_index]

    # ========================================================================
    # DOMAIN CACHE — avoid repeat DDG lookups for the same company
    # ========================================================================

    @staticmethod
    def _normalize_company_key(company: str) -> str:
        """Normalize a company name to a cache key.
        Strips legal suffixes, punctuation, and extra whitespace.
        e.g. 'Acme Corp, Inc.' → 'acme corp'
        """
        key = company.lower().strip()
        # Remove common legal suffixes
        key = re.sub(
            r'\b(inc\.?|llc\.?|ltd\.?|corp\.?|co\.?|gmbh|s\.a\.?|b\.v\.?|plc\.?|'
            r'limited|incorporated|group|holdings?|international|intl\.?)\b',
            '', key
        )
        # Strip punctuation and collapse whitespace
        key = re.sub(r'[^\w\s]', '', key)
        key = re.sub(r'\s+', ' ', key).strip()
        return key

    @staticmethod
    def _company_is_duplicate(company_a: str, company_b: str) -> bool:
        """Fuzzy match: true if two company names refer to the same entity."""
        if not company_a or not company_b:
            return False
        a = SocialMediaCollector._normalize_company_key(company_a)
        b = SocialMediaCollector._normalize_company_key(company_b)
        if a == b:
            return True
        # Prefix match: one starts with the other (catches "Acme" vs "Acme Digital")
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        if len(shorter) >= 4 and longer.startswith(shorter):
            return True
        return False

    def _get_cached_domain(self, company: str) -> Optional[str]:
        """Return cached domain URL for company if still fresh, else None."""
        key = self._normalize_company_key(company)
        entry = self._domain_cache.get(key)
        if entry:
            domain_url, ts = entry
            if time.time() - ts < self._domain_cache_ttl:
                return domain_url
            # Expired — remove
            del self._domain_cache[key]
        return None

    def _cache_domain(self, company: str, domain_url: str):
        """Store a resolved domain URL for a company."""
        key = self._normalize_company_key(company)
        self._domain_cache[key] = (domain_url, time.time())

    _DOMAIN_SKIP = frozenset({
        'linkedin.com', 'facebook.com', 'twitter.com', 'x.com',
        'youtube.com', 'instagram.com', 'wikipedia.org', 'crunchbase.com',
        'glassdoor.com', 'indeed.com', 'zoominfo.com', 'apollo.io',
        'bloomberg.com', 'reuters.com', 'forbes.com', 'techcrunch.com',
        'clutch.co', 'g2.com', 'capterra.com', 'trustpilot.com',
        # Search engines — their URLs are search result pages, not company sites
        'yandex.com', 'yandex.ru', 'baidu.com', 'ask.com', 'bing.com',
        'google.com', 'yahoo.com', 'duckduckgo.com', 'ecosia.org',
        'search.yahoo.com', 'sogou.com',
    })

    def _find_company_domain(self, company: str) -> Optional[str]:
        """Find the official website URL for a company.
        Uses domain cache first, falls back to DDG search.
        Returns a full URL (https://...) or None.
        """
        if not company or len(company) < 2:
            return None

        # Check cache first
        cached = self._get_cached_domain(company)
        if cached:
            return cached

        # Build a targeted search query
        # Split CamelCase / slug words before stripping symbols so
        # "AlManamaCompanies" → "Al Manama Companies" not "AlManamaCompanies"
        expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', company)
        expanded = re.sub(r'([A-Z]{2,})([A-Z][a-z])', r'\1 \2', expanded)
        clean = re.sub(r'[^\w\s]', ' ', expanded).strip()
        clean = re.sub(r'\s+', ' ', clean)
        query = f'"{clean}" official site'
        results = self._search_duckduckgo(query, max_results=5)
        # If quoted search returned nothing, fall back to unquoted
        if not results and clean:
            results = self._search_duckduckgo(f'{clean} official website', max_results=5)

        company_words = [
            w for w in re.split(r'[\s&.,]+', company.lower()) if len(w) > 2
        ]

        for r in results:
            url = r.get('url', '')
            if not url:
                continue
            try:
                from urllib.parse import urlparse as _up
                domain = _up(url).netloc.replace('www.', '').lower()
            except Exception:
                continue
            # Skip known aggregator/social domains
            if any(s in domain for s in self._DOMAIN_SKIP):
                continue
            # Prefer domain that shares a word with the company name
            if any(w in domain for w in company_words):
                self._cache_domain(company, url)
                return url
            # Accept first non-skip hit as fallback (only if we had no word match)

        # Second pass: accept first non-skip hit
        for r in results:
            url = r.get('url', '')
            if not url:
                continue
            try:
                from urllib.parse import urlparse as _up
                domain = _up(url).netloc.replace('www.', '').lower()
            except Exception:
                continue
            if not any(s in domain for s in self._DOMAIN_SKIP):
                self._cache_domain(company, url)
                return url

        return None

    def _fetch(self, url: str, headers: Optional[Dict] = None) -> Optional[str]:
        """Fetch URL with rate limiting."""
        self._rate_limit_wait()
        self._rotate_ua()
        try:
            resp = self.session.get(url, timeout=self.timeout, headers=headers or {}, allow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.warning(f"Fetch failed {url}: {e}")
            return None

    def _fast_fetch(self, url: str) -> tuple:
        """Fetch a single page quickly without rate limiting.
        Used for contact-page scraping where we hit many different domains.
        Returns (html_or_None, status_code).
        """
        self._rotate_ua()
        try:
            resp = self.session.get(url, timeout=3, allow_redirects=True)
            if resp.status_code == 200:
                return (resp.text, 200)
            return (None, resp.status_code)
        except Exception:
            return (None, 0)

    def _fetch_json(self, url: str, headers: Optional[Dict] = None) -> Optional[Any]:
        """Fetch URL and parse JSON."""
        self._rate_limit_wait()
        self._rotate_ua()
        try:
            resp = self.session.get(url, timeout=self.timeout, headers=headers or {}, allow_redirects=True)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"JSON fetch failed {url}: {e}")
            return None

    # ========================================================================
    # MAIN ENTRY POINT
    # ========================================================================

    def collect_from_social(
        self,
        query: str,
        platforms: List[str],
        industry: str = '',
        max_per_platform: int = 10,
        on_platform_start: Optional[Callable] = None,
        on_platform_done: Optional[Callable] = None,
    ) -> List[Dict[str, Any]]:
        """
        Collect leads from specified social media platforms.

        Args:
            query: Search topic / keyword
            platforms: List of platform names ('reddit', 'telegram', 'twitter', 'facebook', 'linkedin')
            industry: Industry category for subreddit matching
            max_per_platform: Max leads per platform
            on_platform_start: callback(platform_name) called before each platform
            on_platform_done: callback(platform_name, leads_count) called after each platform

        Returns:
            List of scored, deduped lead dicts ready for DB insertion
        """
        import concurrent.futures
        PLATFORM_TIMEOUT = 60  # seconds max per platform

        all_leads: List[Dict[str, Any]] = []

        # Use smart DuplicateFilter when modules are available
        dedup_filter = DuplicateFilter() if _MODULES_AVAILABLE else None
        # Legacy fallback sets
        seen_emails: set = set()
        seen_websites: set = set()

        for platform in platforms:
            platform = platform.lower().strip()
            logger.info(f"[social] starting platform='{platform}' query='{query}'")
            try:
                if on_platform_start:
                    try:
                        on_platform_start(platform)
                    except Exception:
                        pass

                def _run_platform(p=platform):
                    if p == 'reddit':
                        return self._collect_from_reddit(query, industry, max_per_platform)
                    elif p == 'telegram':
                        return self._collect_from_telegram(query, max_per_platform)
                    elif p in ('twitter', 'x'):
                        return self._collect_from_twitter(query, industry, max_per_platform)
                    elif p == 'facebook':
                        return self._collect_from_facebook(query, industry, max_per_platform)
                    elif p == 'linkedin':
                        return self._collect_from_linkedin(query, industry, max_per_platform)
                    logger.warning(f"[social] unknown platform '{p}' — skipping")
                    return []

                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(_run_platform)
                        leads = future.result(timeout=PLATFORM_TIMEOUT)
                except concurrent.futures.TimeoutError:
                    logger.warning(
                        f"[social] platform '{platform}' timed out after {PLATFORM_TIMEOUT}s"
                    )
                    leads = []

                logger.info(
                    f"[social] platform '{platform}' raw leads: {len(leads)}"
                )

                deduped: List[Dict[str, Any]] = []
                for lead in leads:
                    # ── Pipeline Stage 0: hard pre-filter ────────────────────
                    # Reject CDN emails, URL-shaped names, and no-anchor leads
                    # before spending any API quota on them.
                    _pf_ok, _pf_reason = _pre_filter_lead(lead)
                    if not _pf_ok:
                        logger.debug(
                            f"[social] pre_filter rejected '{lead.get('name') or lead.get('email')}': "
                            f"{_pf_reason}"
                        )
                        continue

                    # ── Pipeline Stage 0b: substance check ───────────────────
                    # Social leads MUST have company + email, OR phone, OR website.
                    # Username-only leads are discarded here before enrichment.
                    _has_company  = bool(lead.get('company'))
                    _has_email    = bool(lead.get('email'))
                    _has_phone    = bool(lead.get('phone'))
                    _has_website  = bool(lead.get('website'))
                    _has_linkedin = bool(lead.get('linkedin_url'))
                    _social_substance = (
                        (_has_company and _has_email)
                        or _has_phone
                        or _has_website
                        or _has_linkedin
                    )
                    if not _social_substance:
                        logger.debug(
                            f"[social] no-substance lead dropped: "
                            f"name='{lead.get('name')}' platform='{platform}'"
                        )
                        continue

                    # ── Pipeline Stage 0c: intent detection ──────────────────
                    # Scan raw post text for buying-intent signals.
                    # Intent data is stored in data_points and used for scoring.
                    _raw_text = (
                        lead.get('data_points', {}).get('raw_text', '')
                        or lead.get('data_points', {}).get('post_text', '')
                        or ''
                    )
                    if _SOCIAL_PIPELINE and _raw_text:
                        _intent = _detect_intent(
                            _raw_text,
                            company=lead.get('company'),
                            industry=lead.get('industry'),
                        )
                        lead.setdefault('data_points', {})['intent'] = _intent
                        # High-intent posts get a quality boost stored in data_points
                        _boost = intent_quality_boost(_intent)
                        if _boost > 0:
                            dp = lead.setdefault('data_points', {})
                            dp['intent_quality_boost'] = round(_boost, 1)
                            logger.debug(
                                f"[social] intent boost +{_boost:.0f} for "
                                f"'{lead.get('company') or lead.get('name')}': "
                                f"{_intent.get('buying_intent')} — "
                                f"{_intent.get('intent_reason', '')[:60]}"
                            )

                    # ── Classify lead type ───────────────────────────────────
                    if 'lead_type' not in lead:
                        lead['lead_type'] = self._classify_lead_type(lead)

                    # ── Fallback enrichment (fill missing fields) ────────────
                    if _MODULES_AVAILABLE:
                        try:
                            lead = enrich_lead_fallbacks(
                                lead,
                                scrape_contact=True,
                                use_hunter=True,
                                generate_email=False,  # never invent emails — only real ones
                                debug=False,
                            )
                        except Exception as enrich_exc:
                            logger.debug(
                                f"[social] enrich_lead_fallbacks error: {enrich_exc}"
                            )

                    # ── Scoring & status assignment ──────────────────────────
                    if _MODULES_AVAILABLE:
                        try:
                            lead, should_save, rejection_reason = validate_and_score(
                                lead, debug=False
                            )
                            if not should_save:
                                logger.debug(
                                    f"[social] lead dropped by validator: "
                                    f"name='{lead.get('name')}' reason={rejection_reason}"
                                )
                                continue
                            # Social media sources are noisy — require at least
                            # "pending" quality (score ≥ 40) to keep a lead.
                            if (lead.get('qualification_score') or 0) < 40:
                                logger.debug(
                                    f"[social] lead dropped (score too low): "
                                    f"name='{lead.get('name')}' score={lead.get('qualification_score')}"
                                )
                                continue
                            # Tag email type
                            if lead.get('email') and not lead.get('email_type'):
                                lead['email_type'] = _email_type(lead['email'])
                        except Exception as val_exc:
                            logger.debug(f"[social] validate_and_score error: {val_exc}")
                    else:
                        # Legacy: drop leads with ONLY an unverified inferred email
                        dp = lead.get('data_points') or {}
                        email_key = (lead.get('email') or '').lower().strip()
                        email_verified = dp.get('email_verified', True)
                        phone = (lead.get('phone') or '').strip()
                        linkedin = (lead.get('linkedin_url') or '').strip()
                        website = (lead.get('website') or '').strip()
                        if (email_key and not email_verified
                                and not phone and not linkedin and not website):
                            logger.debug(
                                f"[social] legacy-drop low-quality lead: {lead.get('name')}"
                            )
                            continue

                    # ── Deduplication ────────────────────────────────────────
                    if dedup_filter is not None:
                        is_dup, dup_reason = dedup_filter.is_duplicate(lead)
                        if is_dup:
                            logger.debug(
                                f"[social] duplicate skipped: "
                                f"{lead.get('email') or lead.get('name')} ({dup_reason})"
                            )
                            continue
                        dedup_filter.register(lead)
                    else:
                        # Legacy set-based dedup
                        email_key = (lead.get('email') or '').lower().strip()
                        website = (lead.get('website') or '').lower().strip()
                        website_domain = ''
                        if website:
                            try:
                                from urllib.parse import urlparse as _up
                                website_domain = _up(website).netloc.replace('www.', '')
                            except Exception:
                                pass
                        if email_key and email_key in seen_emails:
                            continue
                        if website_domain and website_domain in seen_websites:
                            continue
                        if email_key:
                            seen_emails.add(email_key)
                        if website_domain:
                            seen_websites.add(website_domain)

                    deduped.append(lead)

                dropped = len(leads) - len(deduped)
                logger.info(
                    f"[social] platform='{platform}' query='{query}': "
                    f"{len(deduped)} accepted, {dropped} dropped (dup/low-quality)"
                )
                all_leads.extend(deduped)

                if on_platform_done:
                    try:
                        on_platform_done(platform, len(deduped))
                    except Exception:
                        pass

            except Exception as exc:
                logger.error(f"[social] error collecting from '{platform}': {exc}", exc_info=True)

        logger.info(
            f"[social] collect_from_social complete: "
            f"{len(all_leads)} total leads across {len(platforms)} platforms"
        )
        return all_leads

    # ========================================================================
    # REDDIT — Public JSON API (no key needed)
    # ========================================================================

    def _collect_from_reddit(self, query: str, industry: str = '', max_leads: int = 10) -> List[Dict[str, Any]]:
        """Collect leads from Reddit public subreddits via JSON API."""
        leads = []
        seen_authors = set()

        # Pick relevant subreddits based on industry/query
        subreddits = self._pick_subreddits(query, industry)
        logger.info(f"Reddit: Searching {len(subreddits)} subreddits for '{query}'")

        for sub in subreddits:
            if len(leads) >= max_leads:
                break

            sub_name = sub.lstrip('r/')
            # Append business-signal keywords to surface posts by actual business owners
            business_query = f"{query} founder OR owner OR CEO OR 'my company' OR 'our product'"
            url = f"https://www.reddit.com/r/{sub_name}/search.json?q={quote_plus(business_query)}&restrict_sr=1&sort=relevance&limit=25&t=year"
            data = self._fetch_json(url, headers={'User-Agent': 'LeadCollector/1.0'})

            if not data or 'data' not in data:
                # Fallback: search plain query
                url = f"https://www.reddit.com/r/{sub_name}/search.json?q={quote_plus(query)}&restrict_sr=1&sort=new&limit=25&t=month"
                data = self._fetch_json(url, headers={'User-Agent': 'LeadCollector/1.0'})

            if not data or 'data' not in data:
                continue

            posts = data['data'].get('children', [])
            for post in posts:
                if len(leads) >= max_leads:
                    break

                pdata = post.get('data', {})
                author = pdata.get('author', '')
                if not author or author in ('[deleted]', 'AutoModerator') or author in seen_authors:
                    continue
                # Skip bot/spam usernames
                author_lower = author.lower()
                if any(p in author_lower for p in ('bot', '_bot', 'bot_', 'spam', 'auto_', 'moderator', 'test_', '_test')):
                    continue

                title = pdata.get('title', '')
                selftext = pdata.get('selftext', '')
                full_text = f"{title} {selftext}"

                # Extract business-relevant info
                lead = self._extract_lead_from_reddit_post(pdata, sub_name, full_text)
                if lead:
                    seen_authors.add(author)
                    leads.append(lead)

        return leads

    def _pick_subreddits(self, query: str, industry: str = '') -> List[str]:
        """Pick the most relevant subreddits based on query and industry."""
        query_lower = query.lower()
        industry_lower = industry.lower() if industry else ''
        matched = []

        # Match by industry first
        for category, subs in REDDIT_SUBREDDITS.items():
            if category in industry_lower or category in query_lower:
                matched.extend(subs)

        # Keyword matching
        keyword_map = {
            'startup': 'startups', 'saas': 'startups', 'founder': 'startups',
            'tech': 'technology', 'software': 'technology', 'developer': 'technology', 'programming': 'technology',
            'market': 'marketing', 'seo': 'marketing', 'ads': 'marketing', 'growth': 'marketing',
            'finance': 'finance', 'fintech': 'finance', 'crypto': 'finance', 'invest': 'finance',
            'shop': 'ecommerce', 'ecommerce': 'ecommerce', 'amazon': 'ecommerce', 'dropship': 'ecommerce',
            'design': 'design', 'ui': 'design', 'ux': 'design',
            'sales': 'sales', 'b2b': 'sales', 'lead': 'sales',
            'real estate': 'realestate', 'property': 'realestate',
            'health': 'health', 'medical': 'health', 'biotech': 'health',
            'ai': 'ai', 'machine learning': 'ai', 'llm': 'ai', 'gpt': 'ai',
        }

        for keyword, category in keyword_map.items():
            if keyword in query_lower or keyword in industry_lower:
                matched.extend(REDDIT_SUBREDDITS.get(category, []))

        # Default: general business subreddits
        if not matched:
            matched = ['r/Entrepreneur', 'r/startups', 'r/smallbusiness', 'r/sales']

        # Deduplicate and limit
        seen = set()
        unique = []
        for s in matched:
            if s not in seen:
                seen.add(s)
                unique.append(s)
        return unique[:6]  # Max 6 subreddits

    def _extract_lead_from_reddit_post(self, pdata: Dict, subreddit: str, full_text: str) -> Optional[Dict[str, Any]]:
        """Extract a lead from a Reddit post."""
        author = pdata.get('author', 'Unknown')
        title = pdata.get('title', '')
        selftext = pdata.get('selftext', '')
        permalink = pdata.get('permalink', '')
        score = pdata.get('score', 0)
        num_comments = pdata.get('num_comments', 0)

        # Extract emails from post text
        emails = [e for e in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', full_text) if _validate_email(e)]
        emails = [e for e in emails if not e.endswith(('.png', '.jpg', '.gif'))]

        # Extract URLs/websites from post — skip all non-company domains
        _SKIP_WEBSITE_DOMAINS = {
            # Reddit/social
            'reddit.com', 'imgur.com', 'i.redd.it', 'v.redd.it', 'preview.redd.it',
            'redd.it', 'youtube.com', 'youtu.be', 'twitter.com', 'x.com',
            'facebook.com', 'instagram.com', 'tiktok.com', 'pinterest.com',
            'linkedin.com', 'threads.net', 'mastodon.social', 'tumblr.com',
            # Search/content
            'google.com', 'docs.google.com', 'drive.google.com', 'forms.google.com',
            'bing.com', 'duckduckgo.com', 'yahoo.com', 'wikipedia.org',
            'medium.com', 'substack.com', 'quora.com', 'producthunt.com',
            # Dev/code hosting
            'github.com', 'gist.github.com', 'gitlab.com', 'bitbucket.org',
            'stackoverflow.com', 'npmjs.com', 'pypi.org', 'crates.io',
            # URL shorteners
            'bit.ly', 'tinyurl.com', 'ow.ly', 'buff.ly', 't.co', 'lnkd.in',
            'linktr.ee', 'pastebin.com',
            # Messaging
            'discord.gg', 'discord.com', 't.me', 'slack.com', 'telegram.org',
            # Major tech companies (posts reference them, they're not company leads)
            'microsoft.com', 'apple.com', 'amazon.com', 'aws.amazon.com',
            'azure.microsoft.com', 'cloud.google.com', 'salesforce.com',
            'hubspot.com', 'notion.so', 'airtable.com', 'zapier.com',
            'netlify.com', 'vercel.com', 'heroku.com', 'digitalocean.com',
            # Classifieds/marketplaces
            'craigslist.org', 'craigslist.com', 'ebay.com', 'etsy.com',
            'fiverr.com', 'upwork.com', 'freelancer.com', 'toptal.com',
            # Payments
            'paypal.com', 'stripe.com', 'gumroad.com', 'paddle.com',
            # News/blogs
            'techcrunch.com', 'forbes.com', 'wired.com', 'theverge.com',
            'hacker.news', 'news.ycombinator.com',
        }
        websites = re.findall(r'https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', full_text)
        websites = [w for w in websites if w not in _SKIP_WEBSITE_DOMAINS
                    and not any(w.endswith('.' + skip) for skip in _SKIP_WEBSITE_DOMAINS)]

        # Extract company name from post
        company = self._extract_company_from_text(full_text)

        # Extract position/role mentions
        position = self._extract_role_from_text(full_text)

        # Extract LinkedIn URLs
        linkedin = ''
        li_match = re.findall(r'(?:https?://)?(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+', full_text)
        if li_match:
            linkedin = li_match[0] if li_match[0].startswith('http') else f'https://{li_match[0]}'

        # STRICT filter: must have at least one REAL contact data point
        # Company name alone is unreliable (extracts garbage like "CEO", "US")
        # Require email, website, or LinkedIn for actionable leads
        has_real_contact = bool(emails or websites or linkedin)
        if not has_real_contact:
            return None  # Skip — no verifiable contact info

        # FILTER: clean up Reddit username-style handles
        # (e.g. "Ok_Cartoonist2006", "Many_Breadfruit9359")
        def _looks_like_username(n: str) -> bool:
            if not n:
                return False
            import re as _re
            return bool(_re.search(r'\d', n)) and (' ' not in n) and (len(n) < 30)

        if _looks_like_username(author):
            if not company and not position:
                return None  # No business context at all — skip
            # Use the company name as the lead name so it's a real identifier
            author = company if company else position

        # Determine interests from subreddit and content
        interests = self._extract_interests(subreddit, title, selftext)

        # Build lead
        website = f'https://{websites[0]}' if websites else ''
        found_email, email_verified = self._infer_email_from_website(emails[0] if emails else None)
        found_phone = None

        # If we have a website but no real email, scrape the website for contact info
        if website and (not found_email or not email_verified or _is_generic_email(found_email or '')):
            try:
                scraped_email, scraped_phone = self._scrape_website_contact(website)
                if scraped_email and (not found_email or _is_generic_email(found_email)):
                    found_email = scraped_email
                    email_verified = False  # scraped from HTML, not SMTP-confirmed
                if scraped_phone:
                    found_phone = scraped_phone
            except Exception as e:
                logger.debug(f"Website scrape failed for {website}: {e}")

        # Drop email if its domain belongs to a different company (e.g. hello@windsor.ai ≠ Meta)
        if found_email and not _email_domain_matches_company(found_email, company or ''):
            logger.debug(f"[reddit] email domain mismatch — clearing {found_email} for company='{company}'")
            found_email = None
            email_verified = False

        loc_country, loc_city = self._extract_location(full_text, website)
        lead = {
            'name': author,
            'email': found_email,
            'phone': found_phone,
            'company': company or '',
            'position': position or '',
            'industry': self._subreddit_to_industry(subreddit),
            'country': loc_country,
            'city': loc_city,
            'website': website,
            'linkedin_url': linkedin,
            'interests': interests,
            'source': f'reddit_r/{subreddit}',
            'status': 'pending',
            'qualification_score': self._calculate_social_score({
                'email': emails[0] if emails else None,
                'website': websites[0] if websites else None,
                'company': company,
                'position': position,
                'linkedin_url': linkedin,
                'reddit_score': score,
                'num_comments': num_comments,
            }),
            'data_points': {
                'reddit_username': author,
                'reddit_post_title': title[:200],
                'reddit_subreddit': subreddit,
                'reddit_post_url': f'https://reddit.com{permalink}' if permalink else '',
                'reddit_karma': score,
                'reddit_comments': num_comments,
                'email_verified': email_verified,
                'collected_at': datetime.now(timezone.utc).isoformat(),
                'platform': 'reddit',
            },
        }
        return lead

    # ========================================================================
    # TELEGRAM — Public Channel Web Preview
    # ========================================================================

    def _collect_from_telegram(self, query: str, max_leads: int = 10) -> List[Dict[str, Any]]:
        """Collect leads from Telegram public channels via web preview."""
        leads = []
        seen = set()

        # Telegram business channels with real contact signals
        search_queries = [
            f'site:t.me "{query}" business channel email OR phone OR WhatsApp',
            f'"{query}" telegram channel owner OR admin "contact us" OR "email" OR "DM"',
        ]

        for sq in search_queries:
            if len(leads) >= max_leads:
                break

            channels = self._search_duckduckgo(sq, max_results=10)
            for result in channels:
                if len(leads) >= max_leads:
                    break

                url = result.get('url', '')
                if 't.me/' not in url:
                    continue

                # Extract channel name
                channel_match = re.search(r't\.me/(?:s/)?([a-zA-Z0-9_]+)', url)
                if not channel_match:
                    continue
                channel_name = channel_match.group(1)
                if channel_name in seen or channel_name in ('share', 'addstickers', 'joinchat', 'proxy', 'socks'):
                    continue
                seen.add(channel_name)

                # Fetch public channel preview
                channel_leads = self._scrape_telegram_channel(channel_name)
                leads.extend(channel_leads[:max(1, max_leads - len(leads))])

        return leads[:max_leads]

    def _scrape_telegram_channel(self, channel_name: str) -> List[Dict[str, Any]]:
        """Scrape a public Telegram channel's web preview for leads."""
        url = f'https://t.me/s/{channel_name}'
        html = self._fetch(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # Get channel info
        channel_title = ''
        title_el = soup.select_one('.tgme_channel_info_header_title')
        if title_el:
            channel_title = title_el.get_text(strip=True)

        members_text = ''
        members_el = soup.select_one('.tgme_channel_info_counter .counter_value')
        if members_el:
            members_text = members_el.get_text(strip=True)

        # Scrape messages for contact info
        messages = soup.select('.tgme_widget_message_text')
        all_emails = set()
        all_websites = set()
        all_text = ''

        for msg in messages[:30]:  # Check last 30 messages
            text = msg.get_text(separator=' ', strip=True)
            all_text += ' ' + text

            # Extract emails — use full validation to reject noreply@, image URLs, etc.
            for email in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text):
                if _validate_email(email):
                    all_emails.add(email)

            # Extract websites
            for link in msg.find_all('a', href=True):
                href = link['href']
                if href.startswith('http') and 't.me' not in href and 'telegram' not in href:
                    domain = re.search(r'https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', href)
                    if domain:
                        all_websites.add(domain.group(1))

        # Build lead from channel
        if all_emails or all_websites or channel_title:
            tg_website = f'https://{list(all_websites)[0]}' if all_websites else ''
            tg_email, tg_email_verified = self._infer_email_from_website(list(all_emails)[0] if all_emails else None)
            tg_phone = None

            # If we have a website but no real email, scrape it for contact info
            if tg_website and (not tg_email or not tg_email_verified or _is_generic_email(tg_email or '')):
                try:
                    scraped_email, scraped_phone = self._scrape_website_contact(tg_website)
                    if scraped_email and (not tg_email or _is_generic_email(tg_email)):
                        tg_email = scraped_email
                        tg_email_verified = False  # scraped from HTML, not SMTP-confirmed
                    if scraped_phone:
                        tg_phone = scraped_phone
                except Exception as e:
                    logger.debug(f"Website scrape failed for {tg_website}: {e}")

            # Drop email if domain doesn't match the channel/company
            if tg_email and not _email_domain_matches_company(tg_email, channel_title or ''):
                logger.debug(f"[telegram] email domain mismatch — clearing {tg_email} for channel='{channel_title}'")
                tg_email = None
                tg_email_verified = False

            tg_country, tg_city = self._extract_location(f"{channel_title} {all_text[:500]}", tg_website)
            lead = {
                'name': channel_title or channel_name,
                'email': tg_email,
                'phone': tg_phone,
                'company': channel_title or '',
                'position': '',
                'industry': self._guess_industry_from_text(all_text[:500]),
                'country': tg_country,
                'city': tg_city,
                'website': tg_website,
                'linkedin_url': '',
                'interests': self._extract_interests_from_text(all_text[:500]),
                'source': f'telegram_{channel_name}',
                'status': 'pending',
                'qualification_score': self._calculate_social_score({
                    'email': list(all_emails)[0] if all_emails else None,
                    'website': list(all_websites)[0] if all_websites else None,
                    'company': channel_title,
                    'members': members_text,
                }),
                'data_points': {
                    'telegram_channel': channel_name,
                    'telegram_url': f'https://t.me/{channel_name}',
                    'telegram_title': channel_title,
                    'telegram_members': members_text,
                    'emails_found': list(all_emails)[:5],
                    'websites_found': list(all_websites)[:5],
                    'email_verified': tg_email_verified,
                    'collected_at': datetime.now(timezone.utc).isoformat(),
                    'platform': 'telegram',
                },
            }
            return [lead]

        return []

    # ========================================================================
    # TWITTER/X — via DuckDuckGo search
    # ========================================================================

    def _collect_from_twitter(self, query: str, industry: str = '', max_leads: int = 10) -> List[Dict[str, Any]]:
        """Collect leads from Twitter/X profiles via DuckDuckGo search."""
        leads = []
        seen = set()
        candidates_scraped = 0
        max_candidates = max_leads * 2  # Scrape at most 2× desired leads to stay within timeout

        ind = industry.strip()
        _q = re.sub(r'["\']', '', query).strip()
        search_queries = [
            # Profiles with explicit contact info in bio — highest signal
            f'site:twitter.com {_q} {ind} founder OR CEO OR owner "email" OR "DM for" -inurl:status'.strip(),
            # X.com equivalent
            f'site:x.com {_q} {ind} founder OR CEO OR owner "contact" OR "email" -inurl:status'.strip(),
            # Broader: business accounts promoting services / products
            f'site:twitter.com {_q} {ind} "my company" OR "we help" OR "our product" OR "book a call" -inurl:status'.strip(),
        ]

        for sq in search_queries:
            if len(leads) >= max_leads or candidates_scraped >= max_candidates:
                break

            results = self._search_duckduckgo(sq, max_results=10)
            for result in results:
                if len(leads) >= max_leads or candidates_scraped >= max_candidates:
                    break

                url = result.get('url', '')
                title = result.get('title', '')
                snippet = result.get('snippet', '')

                # Skip tweet URLs and non-profile pages
                if '/status/' in url:
                    continue
                if any(p in url for p in ('/with_replies', '/likes', '/followers',
                                          '/following', '/lists', '/moments',
                                          '/media', '/topics', '/communities')):
                    continue

                # Match twitter profile URLs (including mobile.twitter.com)
                profile_match = re.search(r'(?:mobile\.)?(?:twitter|x)\.com/([a-zA-Z0-9_]+)(?:\?|$|/)', url)
                if not profile_match:
                    continue

                handle = profile_match.group(1).lower()
                if handle in seen or handle in ('search', 'hashtag', 'explore', 'home', 'i', 'settings', 'login', 'signup'):
                    continue
                seen.add(handle)

                candidates_scraped += 1
                lead = self._parse_twitter_result(handle, title, snippet, url)
                if lead:
                    leads.append(lead)

        return leads[:max_leads]

    def _parse_twitter_result(self, handle: str, title: str, snippet: str, url: str) -> Optional[Dict[str, Any]]:
        """Parse Twitter profile info from search result."""
        full_text = f"{title} {snippet}"

        # Try to extract name from title
        # Common formats:
        #   "Name (@handle) / X"
        #   "Name (@handle) on X"
        #   "Name - Twitter"
        #   "Tweets with replies by Name (@handle) / X"  (non-profile page that slipped through)
        name = handle

        # Clean up "Tweets with replies by" or similar prefixes
        cleaned_title = re.sub(r'^(?:Tweets\s+(?:with\s+replies\s+)?by|Likes\s+by|Media\s+by)\s+', '', title, flags=re.IGNORECASE).strip()

        name_match = re.match(r'^(.+?)\s*[\(@]', cleaned_title)
        if name_match:
            name = name_match.group(1).strip()
        elif ' / X' in cleaned_title or ' on X' in cleaned_title:
            name = re.sub(r'\s*(?:/|on)\s*X.*$', '', cleaned_title).strip()
        elif ' - Twitter' in cleaned_title:
            name = re.sub(r'\s*-\s*Twitter.*$', '', cleaned_title).strip()

        # Skip if name still looks like a page title (too long or has noise words)
        if len(name) > 60:
            name = handle

        # Extract position from bio/snippet
        position = self._extract_role_from_text(full_text)

        # Extract company from bio
        company = self._extract_company_from_text(full_text)

        # Extract website from bio
        websites = re.findall(r'https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', full_text)
        skip_website_domains = ('twitter.com', 'x.com', 't.co', 'pic.twitter.com',
                                'tinyurl.com', 'bit.ly', 'goo.gl', 'ow.ly', 'buff.ly',
                                'linktr.ee', 'lnkd.in', 'youtu.be', 'amzn.to')
        websites = [w for w in websites if w not in skip_website_domains]

        # Extract email from bio
        emails = [e for e in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', full_text) if _validate_email(e)]

        tw_website = f'https://{websites[0]}' if websites else ''

        # Enrich: if no website found but we have a company name, try DDG search
        # Only do this for companies (not personal handles) to avoid excessive DDG calls
        if not tw_website and company:
            search_name = company or name
            site_results = self._search_duckduckgo(f'{search_name} official website contact', max_results=3)
            skip = ['wikipedia.org', 'twitter.com', 'x.com', 'facebook.com',
                     'linkedin.com', 'youtube.com', 'crunchbase.com', 'glassdoor.com',
                     'instagram.com', 'reddit.com', 'bloomberg.com', 'forbes.com',
                     'eventbrite.com', 'meetup.com', 'medium.com',
                     'rocketreach.co', 'zoominfo.com', 'apollo.io', 'lusha.com',
                     'hunter.io', 'leadiq.com', 'signalhire.com', 'contactout.com',
                     'techcrunch.com', 'venturebeat.com', 'inc.com', 'entrepreneur.com',
                     'pitchbook.com', 'cbinsights.com', 'saas.gov.uk', '.gov',
                     'tinyurl.com', 'bit.ly', 'linktr.ee', 'youtu.be']
            for sr in site_results:
                sr_url = sr.get('url', '')
                if sr_url:
                    from urllib.parse import urlparse as _urlparse
                    sr_domain = _urlparse(sr_url).netloc.replace('www.', '')
                    if not any(sr_domain.endswith(sd) for sd in skip):
                        if self._is_relevant_website(sr_domain, sr.get('title', ''), search_name):
                            tw_website = sr_url
                            websites = [sr_domain]
                            break

        # Scrape website for real contact info (snippet-only — no extra DDG per result)
        scraped_email, scraped_phone = None, None
        if tw_website:
            scraped_email, scraped_phone = self._scrape_website_contact(tw_website)

        if scraped_email:
            emails = [scraped_email]

        tw_email, tw_email_verified = self._infer_email_from_website(emails[0] if emails else None)
        if scraped_email and tw_email == scraped_email:
            tw_email_verified = False  # scraped from HTML, not SMTP-confirmed
        tw_generic = _is_generic_email(tw_email) if tw_email else False

        # Drop email if domain belongs to a different company
        if tw_email and not _email_domain_matches_company(tw_email, company or ''):
            logger.debug(f"[twitter] email domain mismatch — clearing {tw_email} for company='{company}'")
            tw_email = None
            tw_email_verified = False

        tw_country, tw_city = self._extract_location(full_text, tw_website)
        lead = {
            'name': name if name != handle else handle,
            'email': tw_email,
            'phone': scraped_phone or None,
            'company': company or '',
            'position': position or '',
            'industry': self._guess_industry_from_text(full_text),
            'country': tw_country,
            'city': tw_city,
            'website': tw_website,
            'linkedin_url': '',
            'interests': self._extract_interests_from_text(full_text),
            'source': 'twitter',
            'status': 'pending',
            'qualification_score': self._calculate_social_score({
                'email': tw_email,
                'website': websites[0] if websites else None,
                'company': company,
                'position': position,
            }),
            'data_points': {
                'twitter_handle': f'@{handle}',
                'twitter_url': url,
                'twitter_bio': snippet[:300] if snippet else '',
                'email_verified': tw_email_verified and not tw_generic,
                'email_is_generic': tw_generic,
                'collected_at': datetime.now(timezone.utc).isoformat(),
                'platform': 'twitter',
            },
        }
        # Require at least one real contact data point — same rule as Reddit collector
        has_real_contact = bool(tw_email or tw_website or lead.get('linkedin_url') or scraped_phone)
        if not has_real_contact:
            return None
        return lead

    # ========================================================================
    # FACEBOOK — via DuckDuckGo search for public pages/groups
    # ========================================================================

    def _collect_from_facebook(self, query: str, industry: str = '', max_leads: int = 10) -> List[Dict[str, Any]]:
        """Collect leads from Facebook public pages/groups via search."""
        leads = []
        seen = set()
        candidates_scraped = 0
        max_candidates = max_leads * 2  # Scrape at most 2× desired leads to stay within timeout

        ind = industry.strip()
        search_queries = [
            # Business pages with visible contact info (not group/post URLs)
            f'site:facebook.com "{query}" {ind} "email" OR "contact" business -inurl:posts -inurl:photos'.strip(),
            # Owner/founder pages — filters out generic pages, targets real decision-makers
            f'site:facebook.com "{query}" {ind} owner OR founder "WhatsApp" OR "email us" OR "contact us"'.strip(),
        ]

        for sq in search_queries:
            if len(leads) >= max_leads or candidates_scraped >= max_candidates:
                break

            results = self._search_duckduckgo(sq, max_results=10)
            for result in results:
                if len(leads) >= max_leads or candidates_scraped >= max_candidates:
                    break

                url = result.get('url', '')
                title = result.get('title', '')
                snippet = result.get('snippet', '')

                if 'facebook.com' not in url:
                    continue

                # Skip individual post URLs — we want group/page home pages
                if '/posts/' in url or '/permalink/' in url or '/photos/' in url or '/videos/' in url or '/reel/' in url:
                    continue

                # Extract page/group name
                fb_match = re.search(r'facebook\.com/(?:groups/)?([a-zA-Z0-9._-]+)', url)
                if not fb_match:
                    continue
                fb_id = fb_match.group(1).lower()
                if fb_id in seen or fb_id in ('login', 'marketplace', 'watch', 'events', 'groups', 'pages', 'help', 'settings', 'profile.php'):
                    continue
                seen.add(fb_id)

                candidates_scraped += 1
                lead = self._parse_facebook_result(fb_id, title, snippet, url)
                if lead:
                    leads.append(lead)

        return leads[:max_leads]

    def _parse_facebook_result(self, fb_id: str, title: str, snippet: str, url: str) -> Optional[Dict[str, Any]]:
        """Parse Facebook page/group info from search result."""
        full_text = f"{title} {snippet}"

        # Clean name from title
        name = re.sub(r'\s*[-|]\s*Facebook.*$', '', title, flags=re.IGNORECASE).strip()
        # If name is still a URL, empty, or a DDG placeholder, build from fb_id
        if not name or 'facebook.com' in name.lower() or 'site owner hides' in name.lower():
            # Try first sentence of snippet as name
            first_sent = snippet.split('.')[0].strip() if snippet else ''
            if first_sent and len(first_sent) < 80 and 'facebook.com' not in first_sent.lower() and 'site owner' not in first_sent.lower():
                name = first_sent
            else:
                name = fb_id.replace('.', ' ').replace('-', ' ').replace('_', ' ').title()

        company = self._extract_company_from_text(full_text) or name
        position = self._extract_role_from_text(full_text)
        emails = [e for e in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', full_text) if _validate_email(e)]

        websites = re.findall(r'https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', full_text)
        websites = [w for w in websites if 'facebook.com' not in w and 'fbcdn' not in w]

        is_group = '/groups/' in url

        fb_website = f'https://{websites[0]}' if websites else ''

        # Scrape website for real contact info (snippet-only — no extra DDG per result)
        scraped_email, scraped_phone = None, None
        if fb_website:
            scraped_email, scraped_phone = self._scrape_website_contact(fb_website)
        if scraped_email:
            emails = [scraped_email]

        fb_email, fb_email_verified = self._infer_email_from_website(emails[0] if emails else None)
        if scraped_email and fb_email == scraped_email:
            fb_email_verified = False  # scraped from HTML, not SMTP-confirmed
        fb_generic = _is_generic_email(fb_email) if fb_email else False

        # Drop email if domain belongs to a different company
        if fb_email and not _email_domain_matches_company(fb_email, company or ''):
            logger.debug(f"[facebook] email domain mismatch — clearing {fb_email} for company='{company}'")
            fb_email = None
            fb_email_verified = False

        fb_country, fb_city = self._extract_location(full_text, fb_website)

        # Require at least one real contact data point before saving
        has_real_contact = bool(fb_email or fb_website or scraped_phone)
        if not has_real_contact:
            return None

        lead = {
            'name': name,
            'email': fb_email,
            'phone': scraped_phone or None,
            'company': company if not is_group else '',
            'position': position or ('Group Admin' if is_group else ''),
            'industry': self._guess_industry_from_text(full_text),
            'country': fb_country,
            'city': fb_city,
            'website': fb_website,
            'linkedin_url': '',
            'interests': self._extract_interests_from_text(full_text),
            'source': 'facebook_group' if is_group else 'facebook_page',
            'status': 'pending',
            'qualification_score': self._calculate_social_score({
                'email': fb_email,
                'website': websites[0] if websites else None,
                'company': company,
                'position': position,
            }),
            'data_points': {
                'facebook_url': url,
                'facebook_type': 'group' if is_group else 'page',
                'facebook_name': name,
                'description': snippet[:300] if snippet else '',
                'email_verified': fb_email_verified and not fb_generic,
                'email_is_generic': fb_generic,
                'collected_at': datetime.now(timezone.utc).isoformat(),
                'platform': 'facebook',
            },
        }
        return lead

    # ========================================================================
    # LINKEDIN — via DuckDuckGo search for company/people profiles
    # ========================================================================

    def _collect_from_linkedin(
        self,
        query: str,
        industry: str = '',
        max_leads: int = 10,
        custom_queries: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Collect leads from LinkedIn profiles/companies via DuckDuckGo search.

        custom_queries: QueryPlanner-generated LinkedIn queries.  When provided
        they replace the built-in templates for more targeted results.
        """
        leads = []
        seen_ids = set()
        seen_websites = set()
        seen_emails = set()
        seen_names = set()

        # Strip any existing quotes — exact-phrase matching on multi-word queries
        # kills DDG recall; separate keyword matching works much better.
        _q = re.sub(r'["\']', '', query).strip()
        _ind = industry.strip()

        # Use QueryPlanner custom queries when provided; fall back to built-in templates.
        _using_custom = bool(custom_queries)
        if _using_custom:
            search_queries = list(custom_queries)  # type: ignore[arg-type]
        else:
            search_queries = [
                # Company pages — broadest signal, good for brand-name companies
                f'site:linkedin.com/company {_q} {_ind}'.strip(),
                # C-suite decision makers — highest authority contacts
                f'site:linkedin.com/in {_q} CEO OR founder OR "co-founder" OR owner {_ind}'.strip(),
                # Mid-level decision makers — also frequently drive purchasing
                f'site:linkedin.com/in {_q} director OR VP OR "managing director" OR president {_ind}'.strip(),
                # Manager-level — often the hands-on buyer in SMBs
                f'site:linkedin.com/in {_q} manager OR "head of" OR partner {_ind}'.strip(),
                # No site: restriction — catches profiles where linkedin.com/in appears in URL
                f'linkedin.com/in/ {_q} {_ind} professional profile'.strip(),
                # Broader fallback: non-LinkedIn results with strong business signals
                f'{_q} {_ind} CEO founder email contact phone'.strip(),
            ]

        _domain_lookups_done = 0  # cap domain lookups per collection run

        for sq_idx, sq in enumerate(search_queries):
            if len(leads) >= max_leads:
                break

            # Determine query type dynamically when using custom queries;
            # fall back to index-based detection for the built-in template list.
            if _using_custom:
                _is_broad_fallback = 'linkedin.com' not in sq
                _is_linkedin_keyword = (
                    'linkedin.com/in' in sq and 'site:linkedin.com/in' not in sq
                )
            else:
                _is_broad_fallback = sq_idx == 5   # last query has no site:linkedin filter
                _is_linkedin_keyword = sq_idx == 4  # linkedin.com/in without site:

            results = self._search_duckduckgo(sq, max_results=8 if _is_broad_fallback else 6)

            for result in results:
                if len(leads) >= max_leads:
                    break

                url = result.get('url', '')
                title = result.get('title', '')
                snippet = result.get('snippet', '')

                if _is_broad_fallback:
                    # For non-LinkedIn results: try person extraction first, then company
                    if 'linkedin.com' in url:
                        continue  # LinkedIn results handled by other queries
                    # Try to extract a person lead from "Name - Title at Company | Site" titles
                    _person_lead = self._try_parse_person_from_web(url, title, snippet)
                    lead = _person_lead or self._parse_web_company_result(url, title, snippet)
                    if not lead:
                        continue
                else:
                    # Both site:linkedin.com queries (sq 0-3) AND keyword query (sq 4)
                    # require a LinkedIn URL in the result
                    if 'linkedin.com' not in url:
                        # sq 4 (linkedin keyword): also accept non-LinkedIn URLs if person-parseable
                        if not _is_linkedin_keyword:
                            continue
                        _person_lead = self._try_parse_person_from_web(url, title, snippet)
                        if not _person_lead:
                            continue
                        lead = _person_lead
                    else:
                        is_company = '/company/' in url
                        is_person = '/in/' in url
                        if not is_company and not is_person:
                            continue

                        li_match = re.search(r'linkedin\.com/(?:company|in)/([a-zA-Z0-9_-]+)', url)
                        if not li_match:
                            continue
                        li_id = li_match.group(1).lower()
                        if li_id in seen_ids or li_id in ('login', 'signup', 'feed', 'mynetwork', 'jobs', 'messaging'):
                            continue
                        seen_ids.add(li_id)

                        lead = self._parse_linkedin_result(li_id, title, snippet, url, is_company)
                        if not lead:
                            continue

                    # For company leads with no website found in the snippet, try a
                    # domain lookup so the background Hunter enrichment has a domain to use.
                    if lead.get('source') in ('linkedin_company',) and not lead.get('website') and lead.get('company') and _domain_lookups_done < 4:
                        try:
                            _resolved = self._find_company_domain(lead['company'])
                            if _resolved:
                                lead['website'] = _resolved
                                _domain_lookups_done += 1
                                # Scrape the resolved website for email/phone
                                _sc_email, _sc_phone = self._scrape_website_contact(_resolved)
                                if _sc_email and not lead.get('email'):
                                    lead['email'] = _sc_email
                                    lead['data_points']['email_verified'] = False
                                    lead['data_points']['email_source'] = 'contact_page_scrape'
                                if _sc_phone and not lead.get('phone'):
                                    lead['phone'] = _sc_phone
                        except Exception:
                            pass

                # Deduplicate by website domain
                website = (lead.get('website') or '').lower().strip()
                if website:
                    try:
                        from urllib.parse import urlparse as _up
                        domain = _up(website).netloc.replace('www.', '') or website
                    except Exception:
                        domain = website
                    if domain and domain in seen_websites:
                        logger.debug(f"Skipping LinkedIn duplicate by website domain: {domain}")
                        continue
                    if domain:
                        seen_websites.add(domain)

                # Deduplicate by email
                email = (lead.get('email') or '').lower().strip()
                if email:
                    if email in seen_emails:
                        logger.debug(f"Skipping LinkedIn duplicate by email: {email}")
                        continue
                    seen_emails.add(email)

                # Deduplicate by normalized name when no website or email to key on
                norm_name = re.sub(r'\s+', '', (lead.get('name') or '').lower())
                if norm_name and not website and not email:
                    if norm_name in seen_names:
                        logger.debug(f"Skipping LinkedIn duplicate by name: {lead.get('name')}")
                        continue
                    seen_names.add(norm_name)
                elif norm_name:
                    seen_names.add(norm_name)

                leads.append(lead)

        return leads[:max_leads]

    def _parse_web_company_result(self, url: str, title: str, snippet: str) -> Optional[Dict[str, Any]]:
        """Parse a generic web search result into a minimal company lead.
        Used as fallback when site:linkedin.com search returns no results.
        """
        from urllib.parse import urlparse as _up
        try:
            domain = _up(url).netloc.replace('www.', '').lower()
        except Exception:
            domain = ''
        if not domain or any(s in domain for s in self._DOMAIN_SKIP):
            return None

        full_text = f"{title} {snippet}"
        full_text_fixed = re.sub(r'([a-z])([A-Z])', r'\1 \2', full_text)

        # Extract name from title (strip common suffixes)
        name = re.sub(r'\s*[-|].*$', '', title).strip()[:120]
        if not name or len(name) < 3:
            name = domain.split('.')[0].replace('-', ' ').title()

        emails = [e for e in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', full_text) if _validate_email(e)]
        phones = re.findall(r'(?:\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', full_text)
        industry = self._guess_industry_from_text(full_text_fixed)
        country, city = self._extract_location(full_text_fixed, url)

        email = emails[0] if emails else None
        email_verified = False
        email_source = 'web_snippet'

        if not email and url:
            # Quick contact-page scrape
            sc_email, sc_phone = self._scrape_website_contact(url)
            if sc_email:
                email = sc_email
                email_source = 'contact_page_scrape'
            if sc_phone and not phones:
                phones = [sc_phone]

        li_email, li_email_verified = self._infer_email_from_website(email)
        if li_email_verified and email:
            email_verified = True

        return {
            'name': name,
            'email': email,
            'phone': phones[0] if phones else None,
            'company': name,
            'position': self._extract_role_from_text(full_text_fixed) or '',
            'industry': industry,
            'country': country,
            'city': city,
            'website': f'https://{domain}' if domain else '',
            'linkedin_url': '',
            'interests': [],
            'source': 'linkedin_web',
            'status': 'pending',
            'qualification_score': self._calculate_social_score({
                'email': email, 'website': url, 'company': name, 'linkedin_url': '',
            }),
            'data_points': {
                'linkedin_type': 'web_company',
                'description': snippet[:300] if snippet else '',
                'email_verified': email_verified,
                'email_source': email_source,
                'collected_at': datetime.now(timezone.utc).isoformat(),
                'platform': 'linkedin',
            },
        }

    # Person-name patterns: "First Last - Title" or "First Last | Title" or "First Last at Company"
    _PERSON_TITLE_RE = re.compile(
        r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*[-–|]\s*(.+)',
        re.UNICODE,
    )
    _TITLE_KEYWORDS = frozenset({
        'ceo', 'cto', 'coo', 'cmo', 'cpo', 'vp', 'vice president', 'director',
        'manager', 'head of', 'founder', 'co-founder', 'partner', 'president',
        'officer', 'lead', 'senior', 'engineer', 'developer', 'consultant',
        'analyst', 'specialist', 'architect', 'designer', 'scientist',
    })

    def _try_parse_person_from_web(self, url: str, title: str, snippet: str) -> Optional[Dict[str, Any]]:
        """Return a person lead dict if the title matches 'Name - Title [at Company]', else None."""
        if not title:
            return None
        m = self._PERSON_TITLE_RE.match(title.strip())
        if not m:
            return None
        name = m.group(1).strip()
        rest = m.group(2).strip()
        rest_lower = rest.lower()
        if not any(kw in rest_lower for kw in self._TITLE_KEYWORDS):
            return None  # title segment doesn't look like a job title
        # Split "Title at Company | Site"
        position, company = rest, ''
        if ' at ' in rest:
            _parts = rest.split(' at ', 1)
            position = _parts[0].strip()
            company = re.sub(r'\s*[|–—].*$', '', _parts[1]).strip()
        else:
            position = re.sub(r'\s*[|–—].*$', '', rest).strip()
        if not name or len(name.split()) < 2:
            return None
        from urllib.parse import urlparse as _up_p
        try:
            domain = _up_p(url).netloc.replace('www.', '').lower()
        except Exception:
            domain = ''
        country, city = self._extract_location(f"{title} {snippet}", url)
        return {
            'name':      name[:255],
            'company':   company[:255],
            'position':  position[:255],
            'email':     None,
            'phone':     None,
            'website':   f'https://{domain}' if domain else '',
            'linkedin_url': url if 'linkedin.com' in url else '',
            'country':   country,
            'city':      city,
            'industry':  self._guess_industry_from_text(f"{title} {snippet}"),
            'interests': [],
            'source':    'web_person',
            'lead_type': 'person',
            'status':    'pending',
            'qualification_score': self._calculate_social_score({
                'email': None, 'website': url, 'company': company, 'position': position,
                'linkedin_url': url if 'linkedin.com' in url else '',
            }),
            'data_points': {
                'linkedin_type': 'person',
                'description':   snippet[:300] if snippet else '',
                'email_source':  'missing',
                'email_verified': False,
                'collected_at':  datetime.now(timezone.utc).isoformat(),
                'platform':      'linkedin',
            },
        }

    def _parse_linkedin_result(self, li_id: str, title: str, snippet: str, url: str, is_company: bool) -> Optional[Dict[str, Any]]:
        """Parse LinkedIn profile/company info from search result."""
        full_text = f"{title} {snippet}"
        # Fix DuckDuckGo stripped spaces
        full_text_fixed = re.sub(r'([a-z])([A-Z])', r'\1 \2', full_text)

        if is_company:
            # Company: title is like "CompanyName | LinkedIn" or "CompanyName - Overview | LinkedIn"
            name = re.sub(r'\s*[-|].*(?:LinkedIn|Overview).*$', '', title, flags=re.IGNORECASE).strip()
            if not name:
                name = li_id.replace('-', ' ').title()

            # Try to extract industry and employee count from snippet
            industry = self._guess_industry_from_text(full_text_fixed)
            employees = ''
            emp_match = re.search(r'(\d[\d,]+)\s*(?:employees|followers)', snippet, re.IGNORECASE)
            if emp_match:
                employees = emp_match.group(1)

            # Extract website from snippet
            websites = re.findall(r'https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', full_text)
            websites = [w for w in websites if 'linkedin.com' not in w]
            li_website = f'https://{websites[0]}' if websites else ''
            emails = [e for e in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', full_text) if _validate_email(e)]

            # Only scrape website if it was already found in the snippet — no extra DDG per result
            scraped_email, scraped_phone = None, None
            if li_website:
                scraped_email, scraped_phone = self._scrape_website_contact(li_website)

            if scraped_email:
                emails = [scraped_email]

            li_email, li_email_verified = self._infer_email_from_website(emails[0] if emails else None)
            if scraped_email and li_email == scraped_email:
                li_email_verified = False  # scraped from HTML, not SMTP-confirmed
            li_generic = _is_generic_email(li_email) if li_email else False

            # Drop email if domain belongs to a different company
            if li_email and not _email_domain_matches_company(li_email, name or ''):
                logger.debug(f"[linkedin] email domain mismatch — clearing {li_email} for company='{name}'")
                li_email = None
                li_email_verified = False

            li_co_country, li_co_city = self._extract_location(full_text_fixed, li_website)

            # Require at least one real contact data point (LinkedIn URL alone counts)
            has_real_contact = bool(li_email or li_website or scraped_phone or url)
            if not has_real_contact:
                return None

            lead = {
                'name': name,
                'email': li_email,
                'phone': scraped_phone or None,
                'company': name,
                'position': '',
                'industry': industry,
                'country': li_co_country,
                'city': li_co_city,
                'website': li_website,
                'linkedin_url': url,
                'interests': self._extract_interests_from_text(full_text_fixed),
                'source': 'linkedin_company',
                'status': 'pending',
                'qualification_score': self._calculate_social_score({
                    'email': li_email,
                    'website': websites[0] if websites else None,
                    'company': name,
                    'linkedin_url': url,
                }),
                'data_points': {
                    'linkedin_url': url,
                    'linkedin_type': 'company',
                    'linkedin_name': name,
                    'employees': employees,
                    'description': snippet[:300] if snippet else '',
                    'email_verified': li_email_verified and not li_generic,
                    'email_is_generic': li_generic,
                    'collected_at': datetime.now(timezone.utc).isoformat(),
                    'platform': 'linkedin',
                },
            }
            return lead
        else:
            # Person: title is like "John Smith - CTO - CompanyName | LinkedIn"
            title_clean = re.sub(r'\s*\|\s*LinkedIn.*$', '', title).strip()
            title_clean = re.sub(r'([a-z])([A-Z])', r'\1 \2', title_clean)
            parts = re.split(r'\s*[\-–—]\s*', title_clean)

            name = parts[0].strip() if parts else li_id
            position = ''
            company = ''

            for part in parts[1:]:
                part = part.strip()
                if not part:
                    continue
                title_indicators = [
                    'ceo', 'cto', 'cfo', 'coo', 'cmo', 'vp', 'vice president',
                    'director', 'manager', 'head', 'chief', 'lead', 'senior',
                    'founder', 'co-founder', 'partner', 'president', 'officer',
                    'engineer', 'developer', 'consultant', 'analyst', 'specialist',
                ]
                if any(ti in part.lower() for ti in title_indicators):
                    position = part
                elif not company:
                    company = part

            # Extract from snippet if not in title
            if not position:
                position = self._extract_role_from_text(full_text_fixed)
            if not company:
                company = self._extract_company_from_text(full_text_fixed)

            emails = [e for e in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', full_text) if _validate_email(e)]
            websites = re.findall(r'https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', full_text)
            websites = [w for w in websites if 'linkedin.com' not in w]
            li_website = f'https://{websites[0]}' if websites else ''

            li_p_email_raw, li_p_email_verified = self._infer_email_from_website(emails[0] if emails else None)

            # Fix 4 — wrong attribution: reject personal emails whose local part doesn't match the person's name.
            # e.g. richard.mobbs@itp.com found on Zen Bahar's company page → rejected.
            if li_p_email_raw and not _is_generic_email(li_p_email_raw) and not _email_matches_person(li_p_email_raw, name):
                logger.debug(f"Person email mismatch: {li_p_email_raw!r} rejected for '{name}'")
                li_p_email_raw = None
                li_p_email_verified = False

            # Fix 2 — Hunter.io fallback: try to find email when scraping/snippet yields nothing personal.
            if (not li_p_email_raw or _is_generic_email(li_p_email_raw)) and li_website:
                from urllib.parse import urlparse as _up_h
                _hunter_domain = _up_h(li_website).netloc.replace('www.', '')
                _name_parts = name.strip().split()
                if len(_name_parts) >= 2 and _hunter_domain:
                    hunter_email = self._find_email_via_hunter(_name_parts[0], _name_parts[-1], _hunter_domain)
                    if hunter_email:
                        li_p_email_raw = hunter_email
                        li_p_email_verified = True

            # Fix 3 — company email fallback: allow generic emails but flag them as company contact.
            li_p_email_is_generic = _is_generic_email(li_p_email_raw or '')
            li_p_email = li_p_email_raw  # keep both types; UI uses email_type flag to distinguish
            li_p_email_verified = li_p_email_verified and bool(li_p_email) and not li_p_email_is_generic

            li_p_country, li_p_city = self._extract_location(full_text_fixed, li_website)

            # Require at least one real contact data point (LinkedIn URL counts)
            has_real_contact = bool(li_p_email or li_website or url)
            if not has_real_contact:
                return None

            lead = {
                'name': name if len(name) > 2 else li_id,
                'email': li_p_email,
                'phone': None,
                'company': company or '',
                'position': position or '',
                'industry': self._guess_industry_from_text(full_text_fixed),
                'country': li_p_country,
                'city': li_p_city,
                'website': li_website,
                'linkedin_url': url,
                'interests': self._extract_interests_from_text(full_text_fixed),
                'source': 'linkedin_person',
                'status': 'pending',
                'qualification_score': self._calculate_social_score({
                    'email': li_p_email,
                    'website': websites[0] if websites else None,
                    'company': company,
                    'position': position,
                    'linkedin_url': url,
                }),
                'data_points': {
                    'linkedin_url': url,
                    'linkedin_type': 'person',
                    'linkedin_name': name,
                    'description': snippet[:300] if snippet else '',
                    'email_verified': li_p_email_verified,
                    'email_is_generic': li_p_email_is_generic,
                    'email_type': 'company' if li_p_email_is_generic else ('personal' if li_p_email else None),
                    'collected_at': datetime.now(timezone.utc).isoformat(),
                    'platform': 'linkedin',
                },
            }
            return lead

    # ========================================================================
    # WEBSITE SCRAPING HELPER — extract real contact info from company sites
    # ========================================================================

    def _scrape_website_contact(self, website_url: str) -> tuple:
        """Visit a company website and extract real email + phone.
        Returns (email, phone) tuple — both may be None.
        Prefers personal emails over generic ones (info@, contact@, etc).
        Sources tried (in order):
          1. JSON-LD structured data (schema.org)
          2. itemProp / microformat attributes + class="email"
          3. mailto: links + raw email regex scan
          4. Cloudflare CF-email decode (/cdn-cgi/l/email-protection#<hex>)
          5. Obfuscated patterns: [at]/[dot], HTML entities, data-user/domain, Unicode
          6. Footer link discovery → fetch best contact subpage
          7. tel: links and phone regex
        """
        best_personal_email = None
        best_generic_email = None
        best_phone = None

        import json as _json
        import html as _html_mod
        from urllib.parse import urlparse as _urlparse, urljoin as _urljoin

        parsed = _urlparse(website_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        def _register_email(candidate: str) -> bool:
            """Validate and slot email into best_personal / best_generic.
            Returns True if a personal email was found."""
            nonlocal best_personal_email, best_generic_email
            candidate = candidate.strip().rstrip('.,;:!?)>]}"\'').lower()
            if not _validate_email(candidate):
                return False
            if _is_generic_email(candidate):
                best_generic_email = best_generic_email or candidate
            else:
                best_personal_email = best_personal_email or candidate
                return True
            return False

        def _cf_decode(hex_str: str) -> Optional[str]:
            """Decode a Cloudflare-protected email (XOR with first byte as key)."""
            try:
                data = bytes.fromhex(hex_str)
                key = data[0]
                decoded = ''.join(chr(b ^ key) for b in data[1:])
                return decoded if '@' in decoded else None
            except Exception:
                return None

        def _find_footer_contact_links(page_html: str) -> List[str]:
            """Parse footer / nav for contact/about links and return up to 3 URLs."""
            links = []
            seen = set()
            # Look specifically inside footer, nav, or anywhere near 'contact'
            for m in re.finditer(
                r'href=["\']([^"\'#?][^"\']*)["\'][^>]*>[^<]{0,40}(?:contact|about|reach|email|touch)[^<]{0,40}<',
                page_html, re.IGNORECASE
            ):
                href = m.group(1).strip()
                if href.startswith('mailto:') or href.startswith('tel:'):
                    continue
                full = href if href.startswith('http') else _urljoin(base, href)
                if full not in seen:
                    seen.add(full)
                    links.append(full)
                if len(links) >= 3:
                    break
            return links

        # Fixed candidate subpages: /contact and /about are most productive
        static_subpages = [f"{base}/contact", f"{base}/about"]

        main_html, status = self._fast_fetch(website_url)
        if status == 403:
            return (None, None)

        # Discover extra contact links from footer of main page (before iterating)
        footer_links: List[str] = []
        if main_html:
            footer_links = _find_footer_contact_links(main_html)

        def _pages():
            """Yield pages to scan, stopping as soon as a personal email is found."""
            if main_html:
                yield main_html
            visited = set(static_subpages)
            for p in static_subpages + footer_links:
                if best_personal_email:
                    return
                if p in visited and p not in static_subpages:
                    continue
                visited.add(p)
                page_html, _ = self._fast_fetch(p)
                if page_html:
                    yield page_html

        for page_html in _pages():
            if best_personal_email:
                break

            visible_text = re.sub(r'<[^>]+>', ' ', page_html)
            # Decode HTML entities in visible text (&#64; → @, &#46; → .)
            visible_decoded = _html_mod.unescape(visible_text)

            # ── 1. JSON-LD structured data (schema.org) ──
            if not best_personal_email or not best_phone:
                for ld_block in re.findall(
                    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                    page_html, re.DOTALL | re.IGNORECASE
                ):
                    try:
                        obj = _json.loads(ld_block)
                        items = obj if isinstance(obj, list) else [obj]
                        for item in items:
                            if isinstance(item, dict):
                                ld_email = item.get('email', '')
                                ld_phone = item.get('telephone', '') or item.get('phone', '')
                                if ld_email:
                                    _register_email(ld_email)
                                if ld_phone and not best_phone:
                                    digits = re.sub(r'[^\d]', '', ld_phone)
                                    if 7 <= len(digits) <= 15:
                                        best_phone = ld_phone.strip()
                    except Exception:
                        pass

            # ── 2. itemProp / hCard microformat + class="email" ──
            if not best_personal_email or not best_phone:
                for m in re.finditer(
                    r'itemprop=["\']email["\'][^>]*(?:content=["\']([^"\']+)["\']|>([^<]+)<)',
                    page_html, re.IGNORECASE
                ):
                    candidate = (m.group(1) or m.group(2) or '').strip()
                    if _register_email(candidate):
                        break

                for m in re.finditer(
                    r'itemprop=["\']telephone["\'][^>]*(?:content=["\']([^"\']+)["\']|>([^<]+)<)',
                    page_html, re.IGNORECASE
                ):
                    candidate = (m.group(1) or m.group(2) or '').strip()
                    digits = re.sub(r'[^\d]', '', candidate)
                    if 7 <= len(digits) <= 15 and not best_phone:
                        best_phone = candidate
                        break

                for m in re.finditer(
                    r'class=["\'][^"\']*\bemail\b[^"\']*["\'][^>]*>([^<]{4,80})<',
                    page_html, re.IGNORECASE
                ):
                    _register_email(m.group(1).strip())
                    if best_personal_email:
                        break

                if not best_phone:
                    for m in re.finditer(
                        r'class=["\'][^"\']*\btel\b[^"\']*["\'][^>]*>([^<]{5,25})<',
                        page_html, re.IGNORECASE
                    ):
                        candidate = m.group(1).strip()
                        digits = re.sub(r'[^\d]', '', candidate)
                        if 7 <= len(digits) <= 15:
                            best_phone = candidate
                            break

            # ── 3. mailto: links + raw email scan ──
            mailto_emails = re.findall(
                r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', page_html
            )
            raw_emails = re.findall(
                r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', page_html
            )
            for e in list(dict.fromkeys(mailto_emails + raw_emails)):
                e = e.replace('%20', '').replace('%40', '@')
                if _register_email(e) and best_personal_email:
                    break

            # ── 4. Cloudflare CF-email decode ──
            # Handles: /cdn-cgi/l/email-protection#<hexdata>
            if not best_personal_email and not best_generic_email:
                for cf_match in re.finditer(
                    r'/cdn-cgi/l/email-protection#([0-9a-fA-F]+)', page_html
                ):
                    decoded = _cf_decode(cf_match.group(1))
                    if decoded and _register_email(decoded):
                        break
                # Also look for data-cfemail attribute pattern
                if not best_personal_email and not best_generic_email:
                    for cf_match in re.finditer(
                        r'data-cfemail=["\']([0-9a-fA-F]+)["\']', page_html
                    ):
                        decoded = _cf_decode(cf_match.group(1))
                        if decoded:
                            _register_email(decoded)
                            break

            # ── 5. Obfuscated email patterns (extended) ──
            if not best_personal_email and not best_generic_email:
                # 5a. [at] / (at) / [dot] / (dot) in visible text
                obf = re.sub(
                    r'\s*[\[\(](?:at|AT)[\]\)]\s*', '@',
                    re.sub(r'\s*[\[\(](?:dot|DOT)[\]\)]\s*', '.', visible_decoded)
                )
                for e in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', obf):
                    if _register_email(e) and best_personal_email:
                        break

                # 5b. HTML entities in raw HTML: &#64; → @, &#46; → .
                if not best_personal_email and not best_generic_email:
                    entity_decoded = _html_mod.unescape(page_html)
                    for e in re.findall(
                        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', entity_decoded
                    ):
                        if _register_email(e) and best_personal_email:
                            break

                # 5c. data-user + data-domain split attributes
                # e.g. <span data-user="john" data-domain="acme.com">
                if not best_personal_email and not best_generic_email:
                    for m in re.finditer(
                        r'data-user=["\']([^"\']+)["\'][^>]*data-domain=["\']([^"\']+)["\']',
                        page_html, re.IGNORECASE
                    ):
                        candidate = f"{m.group(1)}@{m.group(2)}"
                        if _register_email(candidate):
                            break
                    # Also reverse order: data-domain before data-user
                    if not best_personal_email and not best_generic_email:
                        for m in re.finditer(
                            r'data-domain=["\']([^"\']+)["\'][^>]*data-user=["\']([^"\']+)["\']',
                            page_html, re.IGNORECASE
                        ):
                            candidate = f"{m.group(2)}@{m.group(1)}"
                            if _register_email(candidate):
                                break

                # 5d. Unicode lookalike @ (＠ U+FF20) and . (．U+FF0E)
                if not best_personal_email and not best_generic_email:
                    unicode_norm = visible_decoded.replace('\uff20', '@').replace('\uff0e', '.')
                    for e in re.findall(
                        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', unicode_norm
                    ):
                        if _register_email(e) and best_personal_email:
                            break

                # 5e. "user (at) domain (dot) tld" spelled-out pattern
                if not best_personal_email and not best_generic_email:
                    spelled = re.sub(
                        r'\s+at\s+', '@',
                        re.sub(r'\s+dot\s+', '.', visible_decoded),
                        flags=re.IGNORECASE
                    )
                    for e in re.findall(
                        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', spelled
                    ):
                        if _register_email(e) and best_personal_email:
                            break

            # ── 6. tel: links and phone regex ──
            if not best_phone:
                for tp in re.findall(r'href=["\']tel:([+\d\s\-().]+)["\']', page_html):
                    digits = re.sub(r'[^\d]', '', tp)
                    if 7 <= len(digits) <= 15 and len(set(digits)) > 2:
                        best_phone = tp.strip()
                        break

            if not best_phone:
                phone_patterns = [
                    r'\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}',
                    r'\(\d{3}\)\s?\d{3}[\-\s]?\d{4}',
                    r'\b\d{3}[\-.\s]\d{3}[\-.\s]\d{4}\b',
                    r'\b\d{2,4}[\s\-]\d{3,4}[\s\-]\d{3,4}\b',
                ]
                for pattern in phone_patterns:
                    for p in re.findall(pattern, visible_decoded):
                        digits = re.sub(r'[^\d]', '', p)
                        if 7 <= len(digits) <= 15 and len(set(digits)) > 2:
                            if not (digits.startswith('555') and len(digits) == 10):
                                best_phone = p.strip()
                                break
                    if best_phone:
                        break

        best_email = best_personal_email or best_generic_email
        return (best_email, best_phone)

    def _search_contact_via_ddg(self, company_name: str, domain: str = '') -> tuple:
        """Last-resort DDG search for a company's email and phone when website scraping fails.
        Tries website scraping first (using domain cache), then DDG snippet scan.
        Returns (email, phone) tuple — both may be None.
        """
        import html as _html_mod

        # If no domain given, try to resolve via domain cache / DDG
        if not domain and company_name:
            resolved_url = self._find_company_domain(company_name)
            if resolved_url:
                from urllib.parse import urlparse as _up
                domain = _up(resolved_url).netloc.replace('www.', '')
                # Attempt full website scrape first — much higher yield than snippet scan
                email, phone = self._scrape_website_contact(resolved_url)
                if email:
                    return (email, phone)

        # Clean company name: add spaces to CamelCase, strip special chars
        clean_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', company_name)
        clean_name = re.sub(r'[^\w\s]', ' ', clean_name).strip()

        # Build queries — one attempt only to stay fast
        queries = []
        if domain:
            queries.append(f'site:{domain} email contact')
        if clean_name:
            queries.append(f'"{clean_name}" email contact')

        for query in queries:
            results = self._search_duckduckgo(query, max_results=5)
            for r in results:
                text = f"{r.get('title', '')} {r.get('snippet', '')}"
                # Decode HTML entities and obfuscated patterns before scanning
                text = _html_mod.unescape(text)
                text_decoded = re.sub(
                    r'\s*[\[\(](?:at|AT)[\]\)]\s*', '@',
                    re.sub(r'\s*[\[\(](?:dot|DOT)[\]\)]\s*', '.', text)
                )
                for e in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text_decoded):
                    e = e.strip().rstrip('.,;:').lower()
                    if _validate_email(e):
                        phone = None
                        for p in re.findall(r'\+?\d[\d\s\-().]{6,18}\d', text):
                            digits = re.sub(r'[^\d]', '', p)
                            if 7 <= len(digits) <= 15 and len(set(digits)) > 2:
                                phone = p.strip()
                                break
                        return (e, phone)
        return (None, None)

    # ========================================================================
    # EMAIL CONFIDENCE SCORING
    # ========================================================================

    @staticmethod
    def _email_confidence(email: str, source: str) -> float:
        """Return a 0.0–1.0 confidence score for an extracted email address.
        Higher = more trustworthy.

        Sources (highest → lowest):
          json_ld        0.90  — schema.org structured data, very intentional
          itemprop       0.85  — microformat attribute, still structured
          mailto         0.80  — explicit clickable link, very reliable
          cf_decoded     0.80  — Cloudflare-protected email successfully decoded
          class_email    0.75  — class="email" visible element
          text_scan      0.60  — regex scan of visible page text
          obfuscated     0.55  — [at]/[dot] pattern decoded from text
          data_attr      0.55  — data-user / data-domain HTML attribute
          ddg_snippet    0.45  — found in DuckDuckGo search snippet
          inferred       0.20  — info@domain guessed from website URL
        """
        source_scores = {
            'json_ld':     0.90,
            'itemprop':    0.85,
            'mailto':      0.80,
            'cf_decoded':  0.80,
            'class_email': 0.75,
            'text_scan':   0.60,
            'obfuscated':  0.55,
            'data_attr':   0.55,
            'ddg_snippet': 0.45,
            'inferred':    0.20,
        }
        base = source_scores.get(source, 0.50)

        # Boost personal emails over generic ones
        if email and '@' in email:
            local = email.split('@')[0].lower()
            if local in GENERIC_EMAIL_PREFIXES:
                base = max(0.10, base - 0.20)

        return round(base, 2)

    def _find_email_via_hunter(self, first_name: str, last_name: str, domain: str) -> Optional[str]:
        """Find a personal email via Hunter.io Email Finder API.

        Requires HUNTER_IO_API_KEY in environment. Free tier: 25 searches/month.
        Only called as a last resort when website scraping yields nothing.
        Returns a validated email with ≥50% confidence, or None.
        """
        import os
        api_key = os.environ.get('HUNTER_IO_API_KEY', '').strip()
        if not api_key or not first_name or not last_name or not domain:
            return None
        try:
            resp = self.session.get(
                'https://api.hunter.io/v2/email-finder',
                params={
                    'domain': domain,
                    'first_name': first_name,
                    'last_name': last_name,
                    'api_key': api_key,
                },
                timeout=15,
            )
            if resp.status_code != 200:
                logger.debug(f"Hunter.io returned {resp.status_code} for {first_name} {last_name} @ {domain}")
                return None
            data = resp.json()
            email = (data.get('data') or {}).get('email', '')
            confidence = (data.get('data') or {}).get('confidence', 0)
            if email and _validate_email(email) and confidence >= 50:
                logger.info(f"Hunter.io: {email} (confidence {confidence}%) for {first_name} {last_name}")
                return email
        except Exception as e:
            logger.warning(f"Hunter.io lookup failed for {first_name} {last_name} @ {domain}: {e}")
        return None

    # ========================================================================
    # DUCKDUCKGO SEARCH HELPER (uses ddgs library to avoid CAPTCHA)
    # ========================================================================

    def _search_duckduckgo(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
        """Search via Serper.dev → Bing → DuckDuckGo (3-engine fallback chain)."""
        self._rate_limit_wait()
        results = self._search_serper(query, num=max_results)
        if results:
            return results
        # Bing fallback (optional — only runs when BING_API_KEY is set)
        results = self._search_bing(query, num=max_results)
        if results:
            return results
        # DDG final fallback
        for attempt in range(2):
            try:
                from ddgs import DDGS
                raw = list(DDGS(timeout=6).text(query, max_results=max_results))
                for r in raw:
                    results.append({
                        'url': r.get('href', ''),
                        'title': r.get('title', ''),
                        'snippet': r.get('body', ''),
                    })
                break
            except Exception as e:
                logger.warning(f"DDG search attempt {attempt+1} failed for '{query}': {e}")
                if attempt < 1:
                    time.sleep(1)
        return results

    def _search_serper(self, query: str, num: int = 10) -> List[Dict[str, str]]:
        """Search via Serper.dev and return results in the same format as _search_duckduckgo."""
        import os, json as _json
        api_key = os.environ.get('SERPER_API_KEY', '')
        if not api_key:
            return []
        try:
            resp = requests.post(
                'https://google.serper.dev/search',
                headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'},
                data=_json.dumps({'q': query, 'num': num}),
                timeout=10,
                verify=False,
            )
            if resp.status_code != 200:
                logger.warning("[serper] HTTP %s for query %r", resp.status_code, query[:60])
                return []
            return [
                {'url': item.get('link', ''), 'title': item.get('title', ''), 'snippet': item.get('snippet', '')}
                for item in resp.json().get('organic', [])
            ]
        except Exception as exc:
            logger.warning("[serper] error: %s", exc)
            return []

    def _search_bing(self, query: str, num: int = 10) -> List[Dict[str, str]]:
        """Bing Web Search API — optional 3rd engine (requires BING_API_KEY env var)."""
        import os as _os
        _bkey = _os.getenv('BING_API_KEY', '').strip()
        if not _bkey:
            return []
        try:
            resp = requests.get(
                'https://api.bing.microsoft.com/v7.0/search',
                headers={'Ocp-Apim-Subscription-Key': _bkey},
                params={'q': query, 'count': num, 'responseFilter': 'Webpages'},
                timeout=10,
            )
            if not resp.ok:
                return []
            return [
                {'url': p.get('url', ''), 'title': p.get('name', ''), 'snippet': p.get('snippet', '')}
                for p in resp.json().get('webPages', {}).get('value', [])
            ]
        except Exception as _be:
            logger.debug("[social] Bing search error: %s", _be)
            return []

    # ========================================================================
    # EMAIL INFERENCE
    # ========================================================================

    @staticmethod
    def _infer_email_from_website(email: Optional[str]) -> tuple:
        """Return (email, is_verified) from post content, or (None, False) if none.
        Does not generate info@domain guesses."""
        if email:
            return (email, True)
        return (None, False)

    @staticmethod
    def _is_relevant_website(domain: str, title: str, search_name: str) -> bool:
        """Check if a DDG search result is likely the actual website for the entity.
        Prevents matching unrelated domains like science.org for 'Digital Marketing Group'."""
        if not search_name or not domain:
            return False
        # Normalize
        domain_lower = domain.lower().replace('www.', '')
        title_lower = title.lower()
        name_lower = search_name.lower().strip()
        # Extract significant words (skip very short/common words)
        skip_words = {'the', 'and', 'or', 'of', 'in', 'for', 'at', 'by', 'a', 'an',
                      'inc', 'llc', 'ltd', 'co', 'corp', 'group', 'pro', 'official',
                      'website', 'contact', 'company', 'page'}
        name_words = [w for w in re.split(r'[\s|,./&-]+', name_lower) if len(w) > 2 and w not in skip_words]
        if not name_words:
            return True  # Can't validate, allow it

        # Check if domain contains any significant word from the name
        domain_base = domain_lower.split('.')[0]
        for word in name_words:
            if word in domain_base:
                return True
        # Check if search result title contains significant words
        matches = sum(1 for w in name_words if w in title_lower)
        if matches >= max(1, len(name_words) // 2):
            return True
        return False

    # ========================================================================
    # TEXT EXTRACTION HELPERS
    # ========================================================================

    def _extract_company_from_text(self, text: str) -> str:
        """Try to extract a company name from text."""
        patterns = [
            r'(?:at|@|from|with|building|co-?founded?|founded?)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,3})',
            r'(?:CEO|CTO|CFO|COO|founder|co-founder|director)\s+(?:of|at)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,3})',
            r'(?:my company|our company|my startup|our startup)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                company = match.group(1).strip()
                # Filter out common non-company words
                noise = {'I', 'We', 'My', 'The', 'This', 'That', 'And', 'But', 'Not', 'Just', 'Been', 'With',
                         'JavaScript', 'Python', 'React', 'Angular', 'Vue', 'Node', 'Java', 'Ruby',
                         'PHP', 'HTML', 'CSS', 'SQL', 'Linux', 'Windows', 'Mac', 'Google', 'Apple',
                         'Facebook', 'Twitter', 'Reddit', 'Telegram', 'San', 'New', 'Los',
                         'CEO', 'CTO', 'CFO', 'COO', 'VP', 'Director', 'Manager',
                         'US', 'UK', 'USA', 'EU', 'Team', 'Company', 'Business',
                         'Senior', 'Junior', 'Lead', 'Head', 'Chief',
                         'January', 'February', 'March', 'April', 'May', 'June',
                         'July', 'August', 'September', 'October', 'November', 'December',
                         'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
                         }
                noise_lower = {n.lower() for n in noise}
                if company.lower() not in noise_lower and len(company) > 1:
                    return company[:100]
        return ''

    def _extract_role_from_text(self, text: str) -> str:
        """Extract a job role/position from text."""
        patterns = [
            r'\b((?:co-?)?(?:CEO|CTO|CFO|COO|CMO|CPO|VP|SVP|EVP|Director|Manager|Head|Lead|Chief|President|Founder|Partner|Owner)(?:\s+of\s+[A-Za-z]+(?:\s+[A-Za-z]+){0,2})?)\b',
            r'\b((?:Software|Senior|Junior|Staff|Principal)\s+(?:Engineer|Developer|Designer|Architect|Analyst|Manager|Consultant))\b',
            r'\b((?:Marketing|Sales|Product|Growth|Data|DevOps|Full[- ]?Stack|Back[- ]?end|Front[- ]?end)\s+(?:Manager|Director|Lead|Engineer|Developer|Specialist|Head))\b',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:100]
        return ''

    def _extract_interests(self, subreddit: str, title: str, selftext: str) -> List[str]:
        """Extract interests from subreddit and post content."""
        interests = set()

        # Map subreddit to interest
        sub_interests = {
            'startups': 'Startups', 'Entrepreneur': 'Entrepreneurship', 'smallbusiness': 'Small Business',
            'SaaS': 'SaaS', 'technology': 'Technology', 'programming': 'Software Development',
            'webdev': 'Web Development', 'devops': 'DevOps', 'marketing': 'Marketing',
            'digital_marketing': 'Digital Marketing', 'SEO': 'SEO', 'PPC': 'Advertising',
            'fintech': 'Fintech', 'CryptoCurrency': 'Crypto', 'ecommerce': 'E-commerce',
            'shopify': 'E-commerce', 'design': 'Design', 'UI_Design': 'UI Design',
            'UXDesign': 'UX Design', 'sales': 'Sales', 'B2B': 'B2B',
            'MachineLearning': 'Machine Learning', 'artificial': 'AI',
            'realestate': 'Real Estate', 'biotech': 'Biotech',
        }
        if subreddit in sub_interests:
            interests.add(sub_interests[subreddit])

        # Check content for keyword interests
        text = f"{title} {selftext}".lower()
        keyword_interests = {
            'ai': 'AI', 'machine learning': 'Machine Learning', 'saas': 'SaaS',
            'ecommerce': 'E-commerce', 'marketing': 'Marketing', 'sales': 'Sales',
            'automation': 'Automation', 'cloud': 'Cloud', 'data': 'Data Analytics',
            'blockchain': 'Blockchain', 'fintech': 'Fintech', 'cybersecurity': 'Cybersecurity',
        }
        for kw, interest in keyword_interests.items():
            if kw in text:
                interests.add(interest)

        return list(interests)[:5]

    def _extract_interests_from_text(self, text: str) -> List[str]:
        """Extract interests from generic text."""
        text_lower = text.lower()
        interests = set()
        keyword_map = {
            'startup': 'Startups', 'saas': 'SaaS', 'ai': 'AI', 'marketing': 'Marketing',
            'ecommerce': 'E-commerce', 'fintech': 'Fintech', 'crypto': 'Crypto',
            'real estate': 'Real Estate', 'technology': 'Technology', 'software': 'Software',
            'design': 'Design', 'sales': 'Sales', 'automation': 'Automation',
            'cloud': 'Cloud', 'data': 'Data', 'consulting': 'Consulting',
            'education': 'Education', 'health': 'Health', 'invest': 'Investment',
        }
        for kw, interest in keyword_map.items():
            if kw in text_lower:
                interests.add(interest)
        return list(interests)[:5]

    def _subreddit_to_industry(self, subreddit: str) -> str:
        """Map subreddit to industry."""
        mapping = {
            'startups': 'Technology', 'Entrepreneur': 'Business', 'smallbusiness': 'Business',
            'SaaS': 'Software', 'technology': 'Technology', 'programming': 'Software',
            'webdev': 'Web Development', 'devops': 'Technology', 'marketing': 'Marketing',
            'digital_marketing': 'Marketing', 'SEO': 'Marketing', 'PPC': 'Advertising',
            'fintech': 'Finance', 'CryptoCurrency': 'Finance', 'investing': 'Finance',
            'ecommerce': 'E-commerce', 'shopify': 'E-commerce', 'FulfillmentByAmazon': 'E-commerce',
            'design': 'Design', 'UI_Design': 'Design', 'UXDesign': 'Design',
            'sales': 'Sales', 'B2B': 'B2B Services',
            'MachineLearning': 'AI/ML', 'artificial': 'AI/ML', 'OpenAI': 'AI/ML',
            'realestate': 'Real Estate', 'HealthIT': 'Healthcare', 'biotech': 'Biotech',
        }
        return mapping.get(subreddit, 'Business')

    def _guess_industry_from_text(self, text: str) -> str:
        """Guess industry from text content."""
        text_lower = text.lower()
        industry_keywords = {
            'Technology': ['tech', 'software', 'app', 'digital', 'platform', 'code'],
            'Marketing': ['marketing', 'seo', 'ads', 'advertising', 'branding', 'social media'],
            'Finance': ['finance', 'fintech', 'banking', 'invest', 'crypto', 'trading'],
            'E-commerce': ['ecommerce', 'shop', 'retail', 'amazon', 'store', 'dropship'],
            'Healthcare': ['health', 'medical', 'biotech', 'pharma', 'clinic'],
            'Real Estate': ['real estate', 'property', 'housing', 'rent'],
            'Education': ['education', 'learning', 'course', 'training', 'teach'],
            'AI/ML': ['ai', 'machine learning', 'llm', 'gpt', 'neural', 'deep learning'],
            'SaaS': ['saas', 'subscription', 'b2b software'],
        }
        for industry, keywords in industry_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return industry
        return 'Business'

    def _calculate_social_score(self, data: Dict[str, Any]) -> float:
        """Calculate initial lead score based on available data."""
        score = 15  # Base

        if data.get('email'):
            email = data['email']
            is_generic = _is_generic_email(email)
            if '@' in email:
                domain = email.split('@')[-1]
                is_free = domain in ('gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
                                     'live.com', 'msn.com', 'aol.com', 'protonmail.com',
                                     'icloud.com', 'mail.com', 'zoho.com', 'yandex.com')
                if is_generic:
                    score += 5    # Generic catch-all (info@, contact@) — low value
                elif is_free:
                    score += 12   # Personal free email (gmail etc.) — at least it's personal
                else:
                    score += 25   # Personal business email — highest value
            else:
                score += 5

        if data.get('website'):
            score += 15

        if data.get('company'):
            score += 10

        if data.get('position'):
            pos_lower = str(data['position']).lower()
            if any(t in pos_lower for t in ['ceo', 'cto', 'founder', 'director', 'vp', 'head', 'chief']):
                score += 15
            else:
                score += 5

        if data.get('linkedin_url'):
            score += 10

        # Reddit-specific boosts
        reddit_score = data.get('reddit_score', 0)
        if reddit_score >= 50:
            score += 10
        elif reddit_score >= 10:
            score += 5

        num_comments = data.get('num_comments', 0)
        if num_comments >= 10:
            score += 5

        # Telegram member count
        members = data.get('members', '')
        if members:
            try:
                member_count = int(re.sub(r'[^\d]', '', str(members)))
                if member_count >= 10000:
                    score += 10
                elif member_count >= 1000:
                    score += 5
            except (ValueError, TypeError):
                pass

        return min(score, 100)

    # ========================================================================
    # LOCATION EXTRACTION
    # ========================================================================

    # Major countries and common abbreviations
    _COUNTRIES = {
        'united states': 'United States', 'usa': 'United States', 'us': 'United States',
        'united kingdom': 'United Kingdom', 'uk': 'United Kingdom', 'england': 'United Kingdom',
        'canada': 'Canada', 'australia': 'Australia', 'germany': 'Germany', 'deutschland': 'Germany',
        'france': 'France', 'india': 'India', 'brazil': 'Brazil', 'japan': 'Japan',
        'china': 'China', 'south korea': 'South Korea', 'korea': 'South Korea',
        'netherlands': 'Netherlands', 'holland': 'Netherlands', 'spain': 'Spain',
        'italy': 'Italy', 'sweden': 'Sweden', 'norway': 'Norway', 'denmark': 'Denmark',
        'finland': 'Finland', 'switzerland': 'Switzerland', 'austria': 'Austria',
        'ireland': 'Ireland', 'portugal': 'Portugal', 'poland': 'Poland',
        'belgium': 'Belgium', 'singapore': 'Singapore', 'israel': 'Israel',
        'uae': 'UAE', 'united arab emirates': 'UAE', 'dubai': 'UAE',
        'saudi arabia': 'Saudi Arabia', 'ksa': 'Saudi Arabia',
        'kuwait': 'Kuwait', 'state of kuwait': 'Kuwait',
        'qatar': 'Qatar', 'bahrain': 'Bahrain', 'oman': 'Oman',
        'jordan': 'Jordan', 'lebanon': 'Lebanon', 'iraq': 'Iraq',
        'mexico': 'Mexico', 'argentina': 'Argentina',
        'colombia': 'Colombia', 'chile': 'Chile', 'nigeria': 'Nigeria',
        'south africa': 'South Africa', 'egypt': 'Egypt', 'turkey': 'Turkey',
        'russia': 'Russia', 'ukraine': 'Ukraine', 'indonesia': 'Indonesia',
        'malaysia': 'Malaysia', 'thailand': 'Thailand', 'vietnam': 'Vietnam',
        'philippines': 'Philippines', 'pakistan': 'Pakistan', 'bangladesh': 'Bangladesh',
        'new zealand': 'New Zealand', 'czech republic': 'Czech Republic',
        'romania': 'Romania', 'hungary': 'Hungary', 'greece': 'Greece',
        'taiwan': 'Taiwan', 'hong kong': 'Hong Kong',
        'kenya': 'Kenya', 'ghana': 'Ghana', 'ethiopia': 'Ethiopia',
        'peru': 'Peru', 'venezuela': 'Venezuela', 'ecuador': 'Ecuador',
    }

    # US state abbreviations
    _US_STATES = {
        'al': 'Alabama', 'ak': 'Alaska', 'az': 'Arizona', 'ar': 'Arkansas',
        'ca': 'California', 'co': 'Colorado', 'ct': 'Connecticut', 'de': 'Delaware',
        'fl': 'Florida', 'ga': 'Georgia', 'hi': 'Hawaii', 'id': 'Idaho',
        'il': 'Illinois', 'in': 'Indiana', 'ia': 'Iowa', 'ks': 'Kansas',
        'ky': 'Kentucky', 'la': 'Louisiana', 'me': 'Maine', 'md': 'Maryland',
        'ma': 'Massachusetts', 'mi': 'Michigan', 'mn': 'Minnesota', 'ms': 'Mississippi',
        'mo': 'Missouri', 'mt': 'Montana', 'ne': 'Nebraska', 'nv': 'Nevada',
        'nh': 'New Hampshire', 'nj': 'New Jersey', 'nm': 'New Mexico', 'ny': 'New York',
        'nc': 'North Carolina', 'nd': 'North Dakota', 'oh': 'Ohio', 'ok': 'Oklahoma',
        'or': 'Oregon', 'pa': 'Pennsylvania', 'ri': 'Rhode Island', 'sc': 'South Carolina',
        'sd': 'South Dakota', 'tn': 'Tennessee', 'tx': 'Texas', 'ut': 'Utah',
        'vt': 'Vermont', 'va': 'Virginia', 'wa': 'Washington', 'wv': 'West Virginia',
        'wi': 'Wisconsin', 'wy': 'Wyoming', 'dc': 'Washington DC',
    }

    # Major cities → country mapping
    _CITY_COUNTRY = {
        'san francisco': 'United States', 'new york': 'United States', 'los angeles': 'United States',
        'chicago': 'United States', 'seattle': 'United States', 'austin': 'United States',
        'boston': 'United States', 'denver': 'United States', 'miami': 'United States',
        'atlanta': 'United States', 'dallas': 'United States', 'houston': 'United States',
        'phoenix': 'United States', 'san diego': 'United States', 'san jose': 'United States',
        'portland': 'United States', 'nashville': 'United States', 'raleigh': 'United States',
        'charlotte': 'United States', 'minneapolis': 'United States', 'detroit': 'United States',
        'philadelphia': 'United States', 'silicon valley': 'United States',
        'sf bay area': 'United States', 'bay area': 'United States',
        'nyc': 'United States', 'sf': 'United States', 'dc': 'United States',
        'atl': 'United States', 'phx': 'United States', 'philly': 'United States',
        'vegas': 'United States', 'las vegas': 'United States', 'salt lake city': 'United States',
        'san antonio': 'United States', 'columbus': 'United States', 'indianapolis': 'United States',
        'jacksonville': 'United States', 'memphis': 'United States', 'oklahoma city': 'United States',
        'pittsburgh': 'United States', 'st louis': 'United States', 'new orleans': 'United States',
        'washington dc': 'United States', 'washington d.c.': 'United States',
        'new york city': 'United States', 'brooklyn': 'United States', 'manhattan': 'United States',
        'greater new york': 'United States', 'greater los angeles': 'United States',
        'greater chicago': 'United States', 'greater seattle': 'United States',
        'greater boston': 'United States', 'greater denver': 'United States',
        'london': 'United Kingdom', 'manchester': 'United Kingdom', 'birmingham': 'United Kingdom',
        'glasgow': 'United Kingdom', 'liverpool': 'United Kingdom', 'cambridge': 'United Kingdom',
        'oxford': 'United Kingdom',
        'edinburgh': 'United Kingdom', 'bristol': 'United Kingdom', 'leeds': 'United Kingdom',
        'toronto': 'Canada', 'vancouver': 'Canada', 'montreal': 'Canada', 'ottawa': 'Canada',
        'calgary': 'Canada', 'edmonton': 'Canada', 'winnipeg': 'Canada',
        'sydney': 'Australia', 'melbourne': 'Australia', 'brisbane': 'Australia', 'perth': 'Australia',
        'berlin': 'Germany', 'munich': 'Germany', 'hamburg': 'Germany', 'frankfurt': 'Germany',
        'paris': 'France', 'lyon': 'France', 'marseille': 'France',
        'amsterdam': 'Netherlands', 'rotterdam': 'Netherlands',
        'stockholm': 'Sweden', 'oslo': 'Norway', 'copenhagen': 'Denmark', 'helsinki': 'Finland',
        'zurich': 'Switzerland', 'geneva': 'Switzerland', 'dublin': 'Ireland',
        'lisbon': 'Portugal', 'barcelona': 'Spain', 'madrid': 'Spain', 'milan': 'Italy', 'rome': 'Italy',
        'warsaw': 'Poland', 'brussels': 'Belgium', 'vienna': 'Austria', 'prague': 'Czech Republic',
        'budapest': 'Hungary', 'bucharest': 'Romania', 'athens': 'Greece',
        'tel aviv': 'Israel', 'singapore': 'Singapore', 'tokyo': 'Japan', 'osaka': 'Japan',
        'seoul': 'South Korea', 'beijing': 'China', 'shanghai': 'China', 'shenzhen': 'China',
        'bangalore': 'India', 'mumbai': 'India', 'delhi': 'India', 'hyderabad': 'India',
        'chennai': 'India', 'pune': 'India',
        'dubai': 'UAE', 'abu dhabi': 'UAE', 'sharjah': 'UAE', 'ajman': 'UAE',
        'kuwait city': 'Kuwait', 'kuwait': 'Kuwait',
        'doha': 'Qatar', 'manama': 'Bahrain', 'muscat': 'Oman',
        'amman': 'Jordan', 'beirut': 'Lebanon', 'baghdad': 'Iraq',
        'riyadh': 'Saudi Arabia', 'jeddah': 'Saudi Arabia', 'mecca': 'Saudi Arabia',
        'dammam': 'Saudi Arabia', 'medina': 'Saudi Arabia',
        'cairo': 'Egypt', 'alexandria': 'Egypt', 'ankara': 'Turkey', 'istanbul': 'Turkey',
        'lagos': 'Nigeria', 'nairobi': 'Kenya', 'cape town': 'South Africa',
        'johannesburg': 'South Africa', 'mexico city': 'Mexico',
        'sao paulo': 'Brazil', 'rio de janeiro': 'Brazil', 'buenos aires': 'Argentina',
        'bogota': 'Colombia', 'santiago': 'Chile', 'lima': 'Peru',
        'bangkok': 'Thailand', 'jakarta': 'Indonesia', 'kuala lumpur': 'Malaysia',
        'ho chi minh': 'Vietnam', 'manila': 'Philippines', 'taipei': 'Taiwan',
        'hong kong': 'Hong Kong', 'auckland': 'New Zealand',
    }

    def _extract_location(self, text: str, website: str = '') -> tuple:
        """Extract (country, city) from text. Returns ('', '') if not found."""
        if not text:
            return ('', '')

        text_clean = text.replace('\n', ' ').replace('\r', ' ')

        # 1) Try "City, State" pattern (US) - e.g. "San Francisco, CA"
        state_match = re.search(
            r'\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s*,\s*([A-Z]{2})\b', text_clean
        )
        if state_match:
            city_candidate = state_match.group(1).strip()
            state_abbr = state_match.group(2).lower()
            if state_abbr in self._US_STATES and len(city_candidate) < 40:
                return ('United States', city_candidate)

        # 2) Try "City, State, Country" (LinkedIn) - e.g. "San Francisco, California, United States"
        csco_match = re.search(
            r'\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})\s*,\s*[A-Z][a-zA-Z]+(?:\s+[A-Za-z]+){0,2}\s*,\s*([A-Z][a-zA-Z]+(?:\s+[A-Za-z]+){0,3})\b',
            text_clean
        )
        if csco_match:
            city_part = csco_match.group(1).strip()
            country_part = csco_match.group(2).strip()
            country_lower = country_part.lower()
            if country_lower in self._COUNTRIES and len(city_part) < 40:
                return (self._COUNTRIES[country_lower], city_part)

        # 3) Try "City, Country" pattern
        city_country_match = re.search(
            r'\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})\s*,\s*([A-Z][a-zA-Z]+(?:\s+[A-Za-z]+){0,3})\b',
            text_clean
        )
        if city_country_match:
            city_part = city_country_match.group(1).strip()
            country_part = city_country_match.group(2).strip()
            country_lower = country_part.lower()
            if country_lower in self._COUNTRIES and len(city_part) < 40:
                return (self._COUNTRIES[country_lower], city_part)

        # 4) "Based in/Located in/From [City]" pattern
        based_in = re.search(
            r'(?:based\s+in|located\s+in|headquartered\s+in|hq\s+in|from)\s+([A-Z][a-zA-Z]+(?:[\s-][A-Z][a-zA-Z]+){0,3})',
            text_clean, re.IGNORECASE
        )
        if based_in:
            place = based_in.group(1).strip().lower()
            if place in self._CITY_COUNTRY:
                return (self._CITY_COUNTRY[place], place.title())
            if place in self._COUNTRIES:
                return (self._COUNTRIES[place], '')

        # 5) Emoji location marker: "📍 City" or "📍City"
        pin_match = re.search(r'📍\s*([A-Za-z]+(?:[\s-][A-Za-z]+){0,3})', text_clean)
        if pin_match:
            place = pin_match.group(1).strip().lower()
            if place in self._CITY_COUNTRY:
                return (self._CITY_COUNTRY[place], place.title())
            if place in self._COUNTRIES:
                return (self._COUNTRIES[place], '')

        # 6) LinkedIn-specific: "Location Area" patterns in titles
        #    e.g. "San Francisco Bay Area", "Greater New York City Area"
        area_match = re.search(r'(?:Greater\s+)?([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})\s+(?:Bay\s+)?Area', text_clean)
        if area_match:
            area_city = area_match.group(1).strip()
            area_lower = area_city.lower()
            if area_lower in self._CITY_COUNTRY or f'{area_lower} bay area' in self._CITY_COUNTRY:
                for k, v in self._CITY_COUNTRY.items():
                    if area_lower in k:
                        return (v, area_city)

        # 7) Search for known cities in text (case-insensitive)
        text_lower = text_clean.lower()
        # Try longer city names first to avoid partial matches
        sorted_cities = sorted(self._CITY_COUNTRY.keys(), key=len, reverse=True)
        for city in sorted_cities:
            # Skip very short abbreviations (2 chars) to avoid false positives
            if len(city) <= 2:
                continue
            pattern = r'\b' + re.escape(city) + r'\b'
            if re.search(pattern, text_lower):
                return (self._CITY_COUNTRY[city], city.title())

        # 8) Search for country names in text
        sorted_countries = sorted(self._COUNTRIES.keys(), key=len, reverse=True)
        for country_key in sorted_countries:
            if len(country_key) <= 2:
                continue  # Skip short abbreviations to avoid false positives
            pattern = r'\b' + re.escape(country_key) + r'\b'
            if re.search(pattern, text_lower):
                return (self._COUNTRIES[country_key], '')

        # 9) US state full names in text (e.g. "California", "Texas")
        us_state_names = {v.lower(): v for v in self._US_STATES.values()}
        for state_lower, state_name in sorted(us_state_names.items(), key=lambda x: len(x[0]), reverse=True):
            if len(state_lower) <= 4:
                continue
            pattern = r'\b' + re.escape(state_lower) + r'\b'
            if re.search(pattern, text_lower):
                return ('United States', state_name)

        # 10) Try domain TLD-based country detection from website
        if website:
            country = self._country_from_tld(website)
            if country:
                return (country, '')

        return ('', '')

    # Domain TLD → country mapping
    _TLD_COUNTRY = {
        '.co.uk': 'United Kingdom', '.uk': 'United Kingdom',
        '.de': 'Germany', '.fr': 'France', '.es': 'Spain', '.it': 'Italy',
        '.nl': 'Netherlands', '.be': 'Belgium', '.at': 'Austria', '.ch': 'Switzerland',
        '.se': 'Sweden', '.no': 'Norway', '.dk': 'Denmark', '.fi': 'Finland',
        '.pt': 'Portugal', '.pl': 'Poland', '.cz': 'Czech Republic', '.ie': 'Ireland',
        '.ro': 'Romania', '.hu': 'Hungary', '.gr': 'Greece',
        '.ca': 'Canada', '.au': 'Australia', '.nz': 'New Zealand',
        '.in': 'India', '.jp': 'Japan', '.kr': 'South Korea', '.cn': 'China',
        '.sg': 'Singapore', '.my': 'Malaysia', '.th': 'Thailand', '.ph': 'Philippines',
        '.id': 'Indonesia', '.vn': 'Vietnam', '.tw': 'Taiwan', '.hk': 'Hong Kong',
        '.il': 'Israel', '.ae': 'UAE', '.sa': 'Saudi Arabia',
        '.br': 'Brazil', '.mx': 'Mexico', '.ar': 'Argentina', '.co': 'Colombia',
        '.cl': 'Chile', '.za': 'South Africa', '.ng': 'Nigeria', '.ke': 'Kenya',
        '.eg': 'Egypt', '.tr': 'Turkey', '.ru': 'Russia', '.ua': 'Ukraine',
    }

    @classmethod
    def _country_from_tld(cls, url: str) -> str:
        """Extract country from website domain TLD."""
        if not url:
            return ''
        try:
            from urllib.parse import urlparse
            domain = urlparse(url if '://' in url else f'https://{url}').netloc.lower()
            domain = domain.lstrip('www.')
            # Check compound TLDs first (co.uk, com.au, etc.), then single
            for tld, country in sorted(cls._TLD_COUNTRY.items(), key=lambda x: len(x[0]), reverse=True):
                if domain.endswith(tld):
                    return country
        except Exception:
            pass
        return ''

    # ========================================================================
    # LEAD TYPE CLASSIFICATION
    # ========================================================================

    def _classify_lead_type(self, lead: Dict[str, Any]) -> str:
        """Classify lead as 'company' or 'person' based on available signals."""
        source = lead.get('source', '')
        data_points = lead.get('data_points', {})
        name = lead.get('name', '')
        company = lead.get('company', '')
        position = lead.get('position', '')

        # LinkedIn explicitly distinguishes
        if data_points.get('linkedin_type') == 'company' or source == 'linkedin_company':
            return 'company'
        if data_points.get('linkedin_type') == 'person' or source == 'linkedin_person':
            return 'person'

        # Facebook pages are companies, groups are communities (person-like)
        if source == 'facebook_page':
            return 'company'
        if source == 'facebook_group':
            return 'company'

        # Telegram channels are company/org
        if 'telegram' in source:
            return 'company'

        # Reddit authors are people
        if 'reddit' in source:
            return 'person'

        # Twitter: check if name looks like a person (first+last)
        if 'twitter' in source:
            # If has a position like CEO, Founder, etc → person
            if position:
                return 'person'
            # If company field is set and name == company → company
            if company and name.lower() == company.lower():
                return 'company'
            # Check name pattern: "FirstName LastName"
            name_parts = name.strip().split()
            if len(name_parts) >= 2 and all(p[0].isupper() for p in name_parts if p):
                return 'person'
            return 'person'

        # Fallback: if has position (CEO, Founder, etc) → person
        if position:
            return 'person'
        # If company == name → company
        if company and name and company.lower() == name.lower():
            return 'company'

        return 'person'


# ============================================================================
# SINGLETON
# ============================================================================

_collector_instance = None


def get_social_collector() -> SocialMediaCollector:
    """Get or create singleton collector instance."""
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = SocialMediaCollector()
    return _collector_instance
