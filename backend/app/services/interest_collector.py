"""
Interest-Based Lead Collector
==============================
Orchestrates category-aware lead collection end-to-end:

  1. Resolve category → get keywords, intent phrases, source types
  2. Generate targeted search queries via interest_query_generator
  3. Collect raw candidates — Places → Serper → DDG → URL visit (fallback)
  4. Run buying-intent detection on each candidate's snippet / title
  5. Apply quality gate (lead_quality_engine)
  6. Adjust score for intent signals (high → +10, medium → +5)
  7. ML-score every saved lead (XGBoost blend)
  8. Save to DB with 6 new interest fields populated
  9. Return a rich IntentQualityReport with intent breakdown

Usage
-----
    from app.services.interest_collector import collect_by_interest, IntentQualityReport

    result = collect_by_interest(
        category_name='laptops',
        country_name='Lebanon',
        city='Beirut',
        max_leads=50,
        sources=['web', 'directories', 'news'],
        db_session=db.session,
        progress_callback=lambda pct, msg: print(pct, msg),
    )
    print(result.to_dict())
"""

from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _has_internet(host: str = '8.8.8.8', port: int = 53, timeout: float = 3.0) -> bool:
    """Quick TCP connectivity check — resolves in <timeout s even when offline."""
    try:
        socket.setdefaulttimeout(timeout)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

# ---------------------------------------------------------------------------
# Country name → 2-letter code mapping (matches COUNTRY_SOURCES in public_web_collector)
# ---------------------------------------------------------------------------

_COUNTRY_NAME_TO_CODE: Dict[str, str] = {
    'united states': 'US', 'usa': 'US', 'us': 'US',
    'united kingdom': 'UK', 'uk': 'UK', 'great britain': 'UK',
    'germany': 'DE', 'france': 'FR',
    'united arab emirates': 'AE', 'uae': 'AE', 'emirates': 'AE',
    'saudi arabia': 'SA', 'ksa': 'SA',
    'india': 'IN',
    'canada': 'CA',
    'australia': 'AU',
    'japan': 'JP',
    'brazil': 'BR',
    'egypt': 'EG',
    'nigeria': 'NG',
    'south africa': 'ZA',
    'singapore': 'SG',
    'south korea': 'KR', 'korea': 'KR',
    'mexico': 'MX',
    'turkey': 'TR',
    'indonesia': 'ID',
    'thailand': 'TH',
    'philippines': 'PH',
    'malaysia': 'MY',
    'pakistan': 'PK',
    'kenya': 'KE',
    'ghana': 'GH',
    'morocco': 'MA',
    'colombia': 'CO',
    'chile': 'CL',
    'argentina': 'AR',
    'poland': 'PL',
    'netherlands': 'NL',
    'sweden': 'SE',
    'switzerland': 'CH',
    'italy': 'IT',
    'spain': 'ES',
    'qatar': 'QA',
    'kuwait': 'KW',
    'bahrain': 'BH',
    'oman': 'OM',
    'jordan': 'JO',
    'lebanon': 'LB',
    'new zealand': 'NZ',
    'ireland': 'IE',
    'israel': 'IL',
}


def _resolve_country_code(country: str) -> str:
    """Return 2-letter code for a country name or code. Falls back to 'US'."""
    normalized = country.strip().lower()
    if len(normalized) == 2:
        return normalized.upper()
    return _COUNTRY_NAME_TO_CODE.get(normalized, 'US')


# ---------------------------------------------------------------------------
# Intent-adjusted scoring
# ---------------------------------------------------------------------------

_INTENT_SCORE_BOOST   = {'high': 12.0, 'medium': 7.0, 'low': 3.0, 'none': -3.0}
_MIN_INTEREST_SCORE   = 30.0   # lower than web (30) — leads are pre-qualified by search query


def _adjust_score_for_intent(base_score: float, buying_intent: str, has_category: bool) -> float:
    boost = _INTENT_SCORE_BOOST.get(buying_intent, 0.0)
    if has_category:
        boost += 3.0   # clear category match
    return round(min(100.0, max(0.0, base_score + boost)), 1)


# ---------------------------------------------------------------------------
# IntentQualityReport
# ---------------------------------------------------------------------------

@dataclass
class IntentQualityReport:
    category_name:   str
    country:         str
    city:            Optional[str]
    sources:         List[str]
    queries_run:     int = 0
    raw_candidates:  int = 0
    saved:           int = 0
    rejected:        int = 0
    duplicates:      int = 0
    duration_s:      float = 0.0
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    intent_breakdown:  Dict[str, int] = field(default_factory=lambda: {
        'high': 0, 'medium': 0, 'low': 0, 'none': 0,
    })
    saved_lead_ids:  List[int] = field(default_factory=list, repr=False)
    _scores: List[float] = field(default_factory=list, repr=False)

    def record_score(self, score: float) -> None:
        self._scores.append(score)

    def record_intent(self, intent: str) -> None:
        key = intent if intent in self.intent_breakdown else 'none'
        self.intent_breakdown[key] = self.intent_breakdown.get(key, 0) + 1

    def record_rejection(self, reasons: List[str]) -> None:
        self.rejected += 1
        for r in reasons:
            self.rejection_reasons[r] = self.rejection_reasons.get(r, 0) + 1

    @property
    def average_quality_score(self) -> float:
        return round(sum(self._scores) / len(self._scores), 1) if self._scores else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'category':              self.category_name,
            'country':               self.country,
            'city':                  self.city,
            'sources':               self.sources,
            'queries_run':           self.queries_run,
            'raw_candidates':        self.raw_candidates,
            'saved':                 self.saved,
            'rejected':              self.rejected,
            'duplicates':            self.duplicates,
            'average_quality_score': self.average_quality_score,
            'duration_seconds':      round(self.duration_s, 2),
            'rejection_reasons':     dict(self.rejection_reasons),
            'intent_breakdown':      dict(self.intent_breakdown),
        }


# ---------------------------------------------------------------------------
# Main collection function
# ---------------------------------------------------------------------------

def collect_by_interest(
    category_name: str,
    country_name: str,
    city: Optional[str] = None,
    max_leads: int = 50,
    sources: Optional[List[str]] = None,
    db_session=None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    collected_by: Optional[int] = None,
) -> IntentQualityReport:
    """
    Collect and save leads for a given product/service category.

    Args:
        category_name:     Category slug or display name (e.g. 'laptops').
        country_name:      Country name or code (e.g. 'Lebanon' or 'LB').
        city:              Optional city for city-level query expansion.
        max_leads:         Hard cap on leads to save per run (1–200).
        sources:           Which collectors to use. Defaults to category source_types.
        db_session:        SQLAlchemy session. Required to save leads to DB.
        progress_callback: Optional fn(percent: int, message: str) for async updates.

    Returns:
        IntentQualityReport — summary of the collection run.
    """
    from config.lead_categories import get_category
    from app.services.interest_query_generator import generate_queries

    def _progress(pct: int, msg: str) -> None:
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    t0 = time.time()
    # Async-friendly budget — caller controls the thread lifetime
    _COLLECTION_BUDGET = 240.0
    deadline = t0 + _COLLECTION_BUDGET
    max_leads = max(1, min(max_leads, 200))

    cat = get_category(category_name)
    if cat is None:
        logger.warning("[InterestCollector] Unknown category: %r", category_name)
        return IntentQualityReport(
            category_name=category_name, country=country_name, city=city,
            sources=sources or [],
        )

    active_sources = list(sources or cat.source_types)
    country_code   = _resolve_country_code(country_name)

    # ── Connectivity check — fail fast if no internet ────────────────────────
    web_needed = bool(set(active_sources) & {'web', 'directories', 'news'})
    if web_needed and not _has_internet():
        logger.warning("[InterestCollector] No internet connectivity — aborting collection")
        raise RuntimeError(
            "No internet connection detected. The server cannot reach external websites. "
            "Please check your network connection and try again."
        )

    report = IntentQualityReport(
        category_name=cat.category_name,
        country=country_name,
        city=city,
        sources=active_sources,
    )

    # ════════════════════════════════════════════════════════════════════════
    # STAGE 1 — SEARCH DISCOVERY
    # ════════════════════════════════════════════════════════════════════════
    _progress(5, 'Generating search queries...')
    queries = generate_queries(
        category_name=category_name,
        country=country_name,
        city=city,
        sources=active_sources,
        max_keywords=4,
    )
    max_queries = min(len(queries), 8)
    queries = queries[:max_queries]
    report.queries_run = len(queries)

    logger.info(
        "[Pipeline] STAGE 1 — Search Discovery | %s | %s/%s | %d queries | sources=%s",
        cat.category_name, country_name, city or '*', len(queries), active_sources,
    )

    # ════════════════════════════════════════════════════════════════════════
    # STAGE 2 — CANDIDATE EXTRACTION
    # Priority: Places API → Serper → DDG → URL visit (only when short on leads)
    # ════════════════════════════════════════════════════════════════════════
    raw_leads: List[Dict[str, Any]] = []
    web_sources    = set(active_sources) & {'web', 'directories', 'news'}
    social_sources = set(active_sources) & {'social'}
    max_per_query  = max(2, max_leads // max(len(queries), 1))

    _progress(10, f'Searching {cat.category_name} companies in {country_name}...')
    logger.info("[Pipeline] STAGE 2 — Candidate Extraction | max_per_query=%d", max_per_query)

    if web_sources:
        try:
            from app.services.public_web_collector import get_collector
            collector = get_collector()

            # ── Stage 2a: Google Places — instant structured data ────────────
            for q in queries[:2]:
                if time.time() > deadline - 180:
                    break
                try:
                    places = collector._search_places(
                        query=q,
                        city=city or country_name,
                        country_name=country_name,
                        max_results=max_per_query,
                    )
                    for pl in places:
                        raw_leads.append({
                            'name':          pl.get('company', ''),
                            'company':       pl.get('company', ''),
                            'phone':         pl.get('phone'),
                            'website':       pl.get('_places_url') or pl.get('website'),
                            'country':       country_name,
                            'city':          city or '',
                            'location':      f"{city or ''} {country_name}".strip(),
                            'source':        'google_places',
                            'lead_type':     'company',
                            '_source_query': q,
                            'data_points':   {'phone_verified': bool(pl.get('phone'))},
                        })
                    report.raw_candidates += len(places)
                    logger.info("[Pipeline] Places returned %d results for %r", len(places), q)
                except Exception as e:
                    logger.debug("[Pipeline] Places query failed (%r): %s", q, e)

            # ── Stage 2b: Serper / DDG — search results with snippets ────────
            from app.services.public_web_collector import COUNTRY_SOURCES as _CS
            country_info = _CS.get(country_code, {})

            def _ddg_search(query_str: str, n: int) -> list:
                """DDG with retry: try full query first, then simplified keyword-only."""
                try:
                    from ddgs import DDGS as _DDGS
                    r = list(_DDGS(timeout=10).text(query_str, max_results=n))
                    if r:
                        return r
                except Exception:
                    pass
                # Simplify: strip boolean operators and site: modifiers → just keywords
                import re as _re
                simple = _re.sub(r'\b(OR|AND|NOT|site:\S+|inurl:\S+)\b', '', query_str)
                simple = _re.sub(r'"([^"]+)"', r'\1', simple).strip()
                simple = ' '.join(simple.split()[:6])  # max 6 words
                if not simple or simple == query_str:
                    return []
                try:
                    from ddgs import DDGS as _DDGS
                    return list(_DDGS(timeout=12).text(simple, max_results=n))
                except Exception as _e2:
                    logger.debug("[Pipeline] DDG retry also failed: %s", _e2)
                    return []

            import os as _os_ic, requests as _req_ic

            def _bing_search(query_str: str, n: int) -> list:
                """Bing Web Search API — optional 3rd engine (requires BING_API_KEY)."""
                _bkey = _os_ic.getenv('BING_API_KEY', '')
                if not _bkey:
                    return []
                try:
                    _br = _req_ic.get(
                        'https://api.bing.microsoft.com/v7.0/search',
                        headers={'Ocp-Apim-Subscription-Key': _bkey},
                        params={'q': query_str, 'count': n, 'responseFilter': 'Webpages'},
                        timeout=10,
                    )
                    if not _br.ok:
                        return []
                    return [
                        {'href': p.get('url'), 'title': p.get('name'), 'body': p.get('snippet')}
                        for p in _br.json().get('webPages', {}).get('value', [])
                    ]
                except Exception as _be:
                    logger.debug("[Pipeline] Bing search error: %s", _be)
                    return []

            for q in queries:
                if time.time() > deadline - 170:
                    break
                if len(raw_leads) >= max_leads * 3:
                    break
                try:
                    results = collector._search_serper(q, country_code=country_code,
                                                       num=max_per_query + 2)
                    if not results:
                        results = _bing_search(f"{q} {country_name}", max_per_query + 2)
                    if not results:
                        results = _ddg_search(f"{q} {country_name}", max_per_query + 2)

                    for r in results:
                        href    = r.get('href') or r.get('link', '')
                        title   = r.get('title', '')
                        snippet = r.get('body') or r.get('snippet', '')
                        if not href or not title:
                            continue

                        # LinkedIn profile — parse "Name - Title at Company | LinkedIn"
                        if 'linkedin.com/in/' in href.lower():
                            _li_clean = title.replace(' | LinkedIn', '').replace(' - LinkedIn', '').strip()
                            _li_segs  = _li_clean.split(' - ')
                            _li_name  = _li_segs[0].strip() if _li_segs else ''
                            _li_rest  = ' - '.join(_li_segs[1:]).strip() if len(_li_segs) > 1 else ''
                            _li_pos, _li_co = '', ''
                            if ' at ' in _li_rest:
                                _li_pos, _li_co = _li_rest.split(' at ', 1)
                                _li_co = _li_co.split(' | ')[0].strip()
                            elif _li_rest:
                                _li_pos = _li_rest.split(' | ')[0].strip()
                            if _li_name and len(_li_name.split()) >= 2:
                                raw_leads.append({
                                    'name':          _li_name[:255],
                                    'company':       _li_co[:255] if _li_co else '',
                                    'position':      _li_pos.strip()[:255],
                                    'website':       '',
                                    'linkedin_url':  href,
                                    'country':       country_name,
                                    'city':          city or country_info.get('name', country_name),
                                    'location':      f"{city or ''} {country_name}".strip(),
                                    'source':        'linkedin_search',
                                    'lead_type':     'person',
                                    '_source_query': q,
                                    'data_points':   {
                                        'snippet':                  snippet,
                                        'search_title':             title,
                                        'linkedin_url':             href,
                                        'email_source':             'missing',
                                        'email_verified':           False,
                                        'source_reliability_score': 72.0,
                                    },
                                })
                            continue

                        company = title.split(' - ')[0].split(' | ')[0].strip()[:255]
                        raw_leads.append({
                            'name':          company,
                            'company':       company,
                            'website':       href,
                            'country':       country_name,
                            'city':          city or country_info.get('name', country_name),
                            'location':      f"{city or ''} {country_name}".strip(),
                            'source':        'web_public',
                            'lead_type':     'company',
                            '_source_query': q,
                            'data_points':   {
                                'snippet':      snippet,
                                'search_title': title,
                            },
                        })
                    report.raw_candidates += len(results)
                except Exception as e:
                    logger.debug("[Pipeline] web query failed (%r): %s", q, e)

            # ── Stage 2c: Full URL visit — only when critically short AND well within budget ──
            # Fires when Serper+DDG both returned nothing; 90s guard prevents timeout.
            if time.time() < deadline - 90 and len(raw_leads) < 3:
                logger.info("[Pipeline] Stage 2c: no API results — trying URL visit fallback")
                try:
                    # Use a simplified keyword query (avoid complex boolean that scraper can't parse)
                    import re as _re
                    _simple_q = ' '.join(
                        w for w in _re.sub(r'["\']', '', queries[0]).split()
                        if w.lower() not in ('or', 'and', 'not', 'inurl:contact',
                                             'inurl:about-us', 'email', 'phone')
                    )[:80] if queries else category_name
                    leads = collector.collect_by_country(
                        query=_simple_q, country_code=country_code, city=city,
                        max_leads=min(max_per_query, 5), deadline=deadline - 70,
                    )
                    for ld in leads:
                        ld['_source_query'] = queries[0] if queries else category_name
                    raw_leads.extend(leads)
                    report.raw_candidates += len(leads)
                    logger.info("[Pipeline] URL-visit fallback: %d leads", len(leads))
                except Exception as e:
                    logger.debug("[Pipeline] URL-visit fallback failed: %s", e)

            if not raw_leads:
                logger.warning(
                    "[Pipeline] 0 raw candidates — no SERPER_API_KEY or GOOGLE_PLACES_API_KEY "
                    "configured and DDG returned nothing for %r in %s. "
                    "Add API keys in .env for reliable results.",
                    category_name, country_name,
                )
        except Exception as e:
            logger.warning("[Pipeline] web collector unavailable: %s", e)

    if social_sources:
        try:
            from app.services.social_media_collector import get_social_collector
            sc = get_social_collector()
            for q in queries[:2]:
                try:
                    # Use clean category+country query for Reddit — not the LinkedIn site: query
                    _reddit_q = f"{cat.category_name} {country_name}"
                    leads = sc._collect_from_reddit(_reddit_q, cat.category_name, max_per_query)
                    for ld in leads:
                        ld['_source_query'] = q
                        ld['source'] = 'reddit'
                    raw_leads.extend(leads)
                    report.raw_candidates += len(leads)
                except Exception as e:
                    logger.debug("[Pipeline] social query failed (%r): %s", q, e)
        except Exception as e:
            logger.warning("[Pipeline] social collector unavailable: %s", e)

    # Apollo B2B people search — personal emails directly from database
    try:
        from app.services.apollo_service import ApolloService
        _apollo = ApolloService()
        if _apollo.is_configured() and not _apollo.needs_upgrade():
            _apollo_leads = _apollo.search_people(
                keywords=category_name,
                locations=[country_name] + ([city] if city else []),
                titles=['CEO', 'Founder', 'Co-Founder', 'CTO', 'CMO',
                        'COO', 'Director', 'VP', 'Manager', 'Owner'],
                per_page=min(max_leads, 25),
            )
            if _apollo_leads:
                for _al in _apollo_leads:
                    _al['lead_type'] = 'person'
                    _al['source']    = 'apollo'
                    _al['_source_query'] = category_name
                    _al.setdefault('data_points', {})['email_verified'] = True
                    _al.setdefault('data_points', {})['email_source']   = 'apollo'
                raw_leads.extend(_apollo_leads)
                report.raw_candidates += len(_apollo_leads)
                logger.info("[Pipeline] Apollo added %d person leads", len(_apollo_leads))
    except Exception as _ae:
        logger.debug("[Pipeline] Apollo search skipped: %s", _ae)

    # ── Stage 2d: News collector — named executives from press releases/RSS ──
    # Pulls from BusinessWire, TechCrunch, PRNewswire, Google News funding feeds.
    # Returns name+company+position leads (no email) for Hunter enrichment.
    if 'news' in set(active_sources) and time.time() < deadline - 60:
        try:
            from app.services.news_collector import get_news_collector
            _nc = get_news_collector()
            _news_leads = _nc.collect(keywords=category_name,
                                      max_results=min(max_leads, 20))
            for _nl in _news_leads:
                _nl['_source_query'] = f"news:{category_name}"
                _nl.setdefault('country', country_name)
                _nl.setdefault('city', city or '')
                _nl.setdefault('location', f"{city or ''} {country_name}".strip())
            raw_leads.extend(_news_leads)
            report.raw_candidates += len(_news_leads)
            logger.info("[Pipeline] Stage 2d — News collector: %d leads", len(_news_leads))
        except Exception as _ne:
            logger.debug("[Pipeline] News collector skipped: %s", _ne)

    # ── Stage 2e: GitHub collector — founders / tech leads by location ────────
    # Uses GitHub Search API (free, unauthenticated 60 req/h; GITHUB_TOKEN lifts
    # it to 5 000 req/h). Returns self-reported name+company+email from profiles.
    if 'github' in set(active_sources) and time.time() < deadline - 60:
        try:
            from app.services.github_collector import get_github_collector
            _gc = get_github_collector()
            _gh_leads = _gc.collect(
                keywords=category_name,
                locations=[country_name] + ([city] if city else []),
                max_results=min(max_leads, 15),
            )
            for _gl in _gh_leads:
                _gl['_source_query'] = f"github:{category_name}"
                _gl.setdefault('country', country_name)
                _gl.setdefault('city', city or '')
                _gl.setdefault('location', f"{city or ''} {country_name}".strip())
            raw_leads.extend(_gh_leads)
            report.raw_candidates += len(_gh_leads)
            logger.info("[Pipeline] Stage 2e — GitHub collector: %d leads", len(_gh_leads))
        except Exception as _ghe:
            logger.debug("[Pipeline] GitHub collector skipped: %s", _ghe)

    logger.info("[Pipeline] STAGE 2 done — %d raw candidates", len(raw_leads))
    _progress(30, f'Found {len(raw_leads)} candidates — filtering...')

    # ════════════════════════════════════════════════════════════════════════
    # STAGE 3 — ENTITY NORMALIZATION
    # ════════════════════════════════════════════════════════════════════════
    _GENERIC_NAMES_IC = frozenset({
        'online', 'digital', 'global', 'solutions', 'services', 'technology',
        'tech', 'group', 'company', 'business', 'consulting', 'media',
        'network', 'networks', 'systems', 'software', 'data', 'startup',
        'startups', 'dictionary', 'thesaurus', 'directory', 'news',
        'blog', 'home', 'website', 'web', 'store', 'shop', 'market',
        'hub', 'center', 'platform', 'portal', 'analytics', 'cloud',
        'connect', 'smart', 'pro', 'plus', 'app', 'apps', 'ai', 'io',
    })
    _LEGAL_SUFFIXES = (' inc', ' llc', ' ltd', ' corp', ' co.', ' s.a.',
                       ' s.r.l', ' gmbh', ' pty', ' plc', ' nv', ' bv')

    def _normalize_entity(ld: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        company = (ld.get('company') or '').strip()
        if not company:
            return None
        co_check = company.lower()
        for sfx in _LEGAL_SUFFIXES:
            if co_check.endswith(sfx):
                co_check = co_check[: -len(sfx)].strip()
                break
        words = [w for w in co_check.split() if w.isalpha()]
        if len(words) == 1 and words[0] in _GENERIC_NAMES_IC:
            return None
        if len(company.split()) > 5:
            return None
        _TAGLINE_STARTERS = ('we ', 'i ', 'our ', 'my ', 'the ', 'a ', 'an ',
                             'helping ', 'building ', 'creating ', 'making ')
        if any(co_check.startswith(p) for p in _TAGLINE_STARTERS):
            return None
        return ld

    before_norm = len(raw_leads)
    raw_leads = [r for r in raw_leads if _normalize_entity(r) is not None]
    logger.info(
        "[Pipeline] STAGE 3 — Entity Normalization | dropped %d generic names | %d remain",
        before_norm - len(raw_leads), len(raw_leads),
    )

    # ════════════════════════════════════════════════════════════════════════
    # STAGE 3b — CANDIDATE FILTER (keyword + Gemini AI validation)
    # Runs BEFORE enrichment so we don't waste Hunter calls on junk.
    # ════════════════════════════════════════════════════════════════════════
    try:
        from app.services.lead_candidate_filter import filter_candidates as _cfilter
        _n_before_filter = len(raw_leads)
        raw_leads = _cfilter(raw_leads, query=category_name, location=country_name)
        if len(raw_leads) < _n_before_filter:
            _progress(32, f'Filtered to {len(raw_leads)} business candidates...')
            logger.info(
                "[Pipeline] STAGE 3b — Candidate filter: %d → %d leads",
                _n_before_filter, len(raw_leads),
            )
    except Exception as _cf_err:
        logger.debug("[Pipeline] candidate filter error: %s", _cf_err)

    # ════════════════════════════════════════════════════════════════════════
    # STAGE 3c — FAST INTELLIGENCE CHECK (anti-junk + business classifier)
    # No HTTP calls — runs in <1 ms per lead.
    # Rejects NGOs, universities, government, directories, parked domains,
    # URL names, @handles, and known aggregator domains BEFORE enrichment
    # so we don't waste Hunter API credits on junk.
    # ════════════════════════════════════════════════════════════════════════
    try:
        from app.intelligence.fast_check import batch_fast_check as _bfc
        _n_before_intel = len(raw_leads)
        raw_leads, _intel_rejected = _bfc(raw_leads)
        if _intel_rejected:
            _progress(35, f'Intelligence pre-check: {len(raw_leads)} real companies remain...')
            logger.info(
                "[Pipeline] STAGE 3c — Fast intelligence check: %d → %d leads "
                "(%d rejected as non-business)",
                _n_before_intel, len(raw_leads), _intel_rejected,
            )
    except Exception as _ic_err:
        logger.debug("[Pipeline] fast intelligence check skipped: %s", _ic_err)

    # ════════════════════════════════════════════════════════════════════════
    # STAGE 3d — CATEGORY RELEVANCE FILTER
    # Rejects leads that have no keywords from the searched category in any
    # of their text fields (company, industry, description, website).
    # Prevents off-topic leads (e.g. Henkel for "electrical appliances").
    # ════════════════════════════════════════════════════════════════════════
    def _cat_relevance_keywords(c) -> frozenset:
        """Extract meaningful keywords from category definition (min 5 chars)."""
        words: set = set()
        for kw in (getattr(c, 'keywords', None) or []):
            for w in kw.lower().split():
                if len(w) >= 5:
                    words.add(w)
        for w in (getattr(c, 'category_name', '') or '').lower().split():
            if len(w) >= 5:
                words.add(w)
        return frozenset(words)

    def _is_cat_relevant(lead: dict, kws: frozenset) -> bool:
        """Return True if at least one category keyword appears in the lead's text."""
        if not kws:
            return True
        dp = lead.get('data_points') or {}
        blob = ' '.join([
            lead.get('company')     or '',
            lead.get('name')        or '',
            lead.get('industry')    or '',
            lead.get('description') or '',
            lead.get('website')     or '',
            dp.get('snippet')       or '',
            dp.get('description')   or '',
        ]).lower()
        return any(kw in blob for kw in kws)

    _rel_kws = _cat_relevance_keywords(cat)
    if _rel_kws:
        _n_before_rel = len(raw_leads)
        raw_leads = [ld for ld in raw_leads if _is_cat_relevant(ld, _rel_kws)]
        _rel_dropped = _n_before_rel - len(raw_leads)
        if _rel_dropped:
            logger.info(
                "[Pipeline] STAGE 3d — Category relevance filter '%s': "
                "dropped %d off-topic leads, %d remain",
                cat.category_name, _rel_dropped, len(raw_leads),
            )
            _progress(38, f'Category filter: {len(raw_leads)} relevant candidates remain...')

    # ════════════════════════════════════════════════════════════════════════
    # STAGE 6 — ENRICHMENT
    # Hunter first; contact-page scrape only if Hunter exhausted AND time allows.
    # ════════════════════════════════════════════════════════════════════════
    _progress(40, f'Enriching {len(raw_leads)} candidates...')
    if deadline - time.time() > 15:
        try:
            from app.services.lead_fallback import enrich_lead_fallbacks
            from app.services.hunter_service import get_hunter_service as _get_hunter
            _hunter_ok = not _get_hunter()._rate_limited
            enriched: List[Dict[str, Any]] = []
            for ld in raw_leads:
                if time.time() > deadline - 10:
                    enriched.extend(raw_leads[len(enriched):])
                    break
                _has_website = bool(ld.get('website'))
                _scrape = _has_website and not _hunter_ok and deadline - time.time() > 15
                try:
                    enriched.append(enrich_lead_fallbacks(
                        ld,
                        scrape_contact=_scrape,
                        use_hunter=_hunter_ok,
                        generate_email=False,
                        debug=False,
                    ))
                except Exception:
                    enriched.append(ld)
            raw_leads = enriched
            logger.info("[Pipeline] STAGE 6 — Enrichment done (hunter=%s)", _hunter_ok)
        except Exception as e:
            logger.debug("[Pipeline] enrichment skipped: %s", e)

    # ════════════════════════════════════════════════════════════════════════
    # STAGE 7 — VERIFICATION
    # ════════════════════════════════════════════════════════════════════════
    with_email = [ld for ld in raw_leads if ld.get('email')]
    if with_email and deadline - time.time() > 10:
        try:
            from app.services.email_verifier import bulk_verify
            bulk_verify(with_email, max_to_verify=15)
            logger.info("[Pipeline] STAGE 7 — Verification done for %d emails", len(with_email))
        except Exception as e:
            logger.debug("[Pipeline] email verification skipped: %s", e)

    # ════════════════════════════════════════════════════════════════════════
    # STAGE 8 — COMPANY-FIRST INTELLIGENCE PIPELINE
    # Replaces the old quality-gate + ML + save loop.
    # All candidates must pass 7 hard gates before any contact is resolved
    # or the lead is saved.  Hunter / ZeroBounce run ONLY inside Stage 8
    # (ContactResolver) after the company passes all intelligence gates.
    # ════════════════════════════════════════════════════════════════════════
    _progress(60, 'Running intelligence pipeline...')

    if db_session is None:
        logger.warning("[InterestCollector] No db_session — leads will not be saved")
        report.duration_s = time.time() - t0
        return report

    from app.models.models import Lead

    # Tag every candidate with the button name and the interest category
    for _ld in raw_leads:
        _ld.setdefault('_button', 'interest_collect')
        _ld.setdefault('data_points', {})['interest_category'] = cat.category_name
        # Fill country fallback so intelligence country matching works
        if not _ld.get('country'):
            _ld['country'] = country_name

    # Build the interest-aware query for UserIntentContract parsing
    _interest_query = f"{cat.category_name} companies {country_name}"

    # Derive allowed_types from the category (fall back to b2b_saas / b2b_services)
    _cat_allowed: frozenset
    _cat_source_types = getattr(cat, 'source_types', [])
    if 'ecommerce' in (getattr(cat, 'category_name', '') or '').lower():
        _cat_allowed = frozenset({'b2b_saas', 'b2b_services', 'ecommerce', 'unknown'})
    else:
        # 'unknown' allows local/service businesses the classifier can't categorise as SaaS
        _cat_allowed = frozenset({'b2b_saas', 'b2b_services', 'unknown'})

    def _build_interests(lead_data: dict, category: str) -> list:
        """Always include the searched category as the first interest."""
        _cat = category.replace('_', ' ').strip()
        _existing = [str(i).strip() for i in (lead_data.get('interests') or []) if str(i).strip()]
        _deduped = [i for i in _existing if i.lower() != _cat.lower()]
        return [_cat] + _deduped if _cat else _existing

    def _interest_save_fn(lead_data: dict) -> bool:
        """Called by IntelligenceOrchestrator after company passes all 7 gates."""
        if report.saved >= max_leads:
            return False

        _co = (lead_data.get('company') or '').strip().rstrip('.')
        _ld_country  = lead_data.get('country') or country_name
        _ld_city     = lead_data.get('city') or city or ''
        # Don't store city when it equals the country — avoids "Germany Germany" in UI
        if _ld_city and _ld_country and _ld_city.strip().lower() == _ld_country.strip().lower():
            _ld_city = ''
        _ld_location = lead_data.get('location') or ''
        if not _ld_location and (_ld_country or _ld_city):
            _ld_location = ', '.join(p for p in [_ld_city, _ld_country] if p)

        # DB dedup
        try:
            _em = (lead_data.get('email') or '').strip().lower()
            if _em and Lead.query.filter_by(email=_em).first():
                report.duplicates += 1
                return False
            if _co and _ld_country and Lead.query.filter_by(
                company=_co, country=_ld_country
            ).first():
                report.duplicates += 1
                return False
        except Exception as _dde:
            logger.debug("[InterestCollector] DB dedup check failed: %s", _dde)

        # Reconstruct intent fields from data_points context
        _dp = lead_data.get('data_points') or {}
        _intent_meta = _dp.get('intent') or {}
        _buying_intent = _intent_meta.get('buying_intent', 'medium')
        _intent_conf   = float(_intent_meta.get('confidence', 0.5))

        # Use policy-tiered status set by IntelligenceOrchestrator
        _suggested_status = lead_data.get('_suggested_status', 'unvalidated')

        try:
            lead_obj = Lead(
                name=(lead_data.get('name') or _co or '')[:255] or None,
                email=lead_data.get('email'),
                phone=lead_data.get('phone'),
                company=(_co or '')[:255],
                position=(lead_data.get('position') or '')[:255] or None,
                location=_ld_location[:255] or None,
                country=_ld_country[:100] if _ld_country else None,
                city=_ld_city[:100] if _ld_city else None,
                industry=lead_data.get('industry'),
                website=lead_data.get('website'),
                linkedin_url=lead_data.get('linkedin_url'),
                interests=_build_interests(lead_data, cat.category_name),
                product=lead_data.get('product'),
                source=lead_data.get('source', 'web_public'),
                lead_type=lead_data.get('lead_type'),
                status=_suggested_status,
                qualification_score=round(
                    lead_data.get('final_company_score',
                    lead_data.get('qualification_score', _MIN_INTEREST_SCORE)), 1
                ),
                completeness_score=round(
                    lead_data.get('final_company_score',
                    lead_data.get('qualification_score', _MIN_INTEREST_SCORE)), 1
                ),
                email_type=lead_data.get('email_type') or _dp.get('email_type'),
                data_points={**_dp},
                interest_category=cat.category_name,
                buying_intent=_buying_intent,
                intent_confidence=_intent_conf,
                intent_source=lead_data.get('source', 'interest_collect'),
                collected_by=collected_by,
            )
            db_session.add(lead_obj)
            db_session.flush()
            if lead_obj.id:
                report.saved_lead_ids.append(lead_obj.id)
            report.saved += 1
            report.record_score(lead_obj.qualification_score)
            _progress(
                60 + min(35, int(35 * report.saved / max(max_leads, 1))),
                f'Saved {report.saved} leads...',
            )
            return True
        except Exception as _se:
            logger.warning("[InterestCollector] save failed: %s", _se)
            try:
                db_session.rollback()
            except Exception:
                pass
            return False

    try:
        from app.intelligence.intelligence_orchestrator import IntelligenceOrchestrator
        from app.services.collection_policy import BALANCED_INTELLIGENCE
        _ic_orch = IntelligenceOrchestrator(
            allowed_types=_cat_allowed,
            use_hunter=True,
            use_zerobounce=True,
            policy=BALANCED_INTELLIGENCE,
        )
        _ic_report = _ic_orch.run_pipeline(
            candidates=raw_leads[:max_leads * 4],  # generous upper cap for pre-filter
            query=_interest_query,
            location=country_name,
            save_lead_fn=_interest_save_fn,
            collection_button='interest_collect',
        )
        logger.info(
            "[InterestCollector] intelligence pipeline done — "
            "saved=%d rejected=%d skipped=%d needs_review=%d",
            _ic_report.n_saved, _ic_report.n_rejected,
            _ic_report.n_skipped, _ic_report.n_needs_review,
        )
        for reason, cnt in _ic_report.rejection_reasons.items():
            for _ in range(cnt):
                report.record_rejection([reason])
        # Count skipped (keyword filter) and needs_review as soft rejects so totals add up
        for _ in range(_ic_report.n_skipped):
            report.record_rejection(['keyword_filter_skipped'])
        for _ in range(_ic_report.n_needs_review):
            report.record_rejection(['needs_review'])
    except Exception as _ie:
        logger.error("[InterestCollector] intelligence pipeline error: %s", _ie, exc_info=True)

    # ── Commit all saves in one transaction ──────────────────────────────────
    if report.saved > 0:
        try:
            db_session.commit()
        except Exception as e:
            logger.error("[InterestCollector] Commit failed: %s", e)
            db_session.rollback()
            report.saved = 0

    report.duration_s = time.time() - t0
    _progress(100, f'Done — saved {report.saved} leads in {report.duration_s:.0f}s')
    logger.info(
        "[InterestCollector] COMPLETE | saved=%d rejected=%d dupes=%d time=%.1fs",
        report.saved, report.rejected, report.duplicates, report.duration_s,
    )
    return report
