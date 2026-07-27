"""
Interest Query Generator
========================
Generates targeted search queries for a given lead category,
and detects buying intent signals in collected text.

Usage
-----
    from app.services.interest_query_generator import generate_queries, detect_buying_intent

    queries = generate_queries('laptops', country='Lebanon', city='Beirut')
    # → ['laptop supplier Lebanon', 'laptop store contact email Lebanon', ...]

    result = detect_buying_intent(
        text="I'm looking for a laptop supplier in Beirut, need 50 units urgently.",
        category_name='laptops',
    )
    # → {'buying_intent': 'high', 'confidence': 0.8, ...}
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from config.lead_categories import CATEGORIES, LeadCategory, get_category
except ImportError:
    # Fallback for scripts run from the backend root
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    from config.lead_categories import CATEGORIES, LeadCategory, get_category  # type: ignore


# ---------------------------------------------------------------------------
# Query templates — targeting actual company pages, not directories
# ---------------------------------------------------------------------------

# LinkedIn profile/company search — direct named-person discovery (HIGHEST PRIORITY)
# site: operator works with both DDG and Serper; titles come back as
# "Name - Title at Company | LinkedIn" which interest_collector parses into leads.
_LINKEDIN_TEMPLATES: List[str] = [
    "site:linkedin.com/in/ {keyword} {country} CEO OR founder OR owner",
    "site:linkedin.com/in/ {keyword} director OR manager {country}",
    "site:linkedin.com/company/ {keyword} {country}",
]

# People-first discovery — decision makers, founders, owners (HIGH PRIORITY)
# Simple syntax without quotes/booleans so DDG + Serper handle them reliably
_PEOPLE_FIRST_TEMPLATES: List[str] = [
    "{keyword} owner {country} contact email",
    "{keyword} founder {country} email contact",
    "{keyword} company CEO {country} email",
    "{keyword} business owner {country} email phone",
    "{keyword} startup founder {country} contact",
    "{keyword} managing director {country} email",
    "{keyword} company director {country} contact email",
    "{keyword} entrepreneur {country} email",
]

# Contact-page queries — surfaces real company sites with emails/phones
_COMPANY_TEMPLATES: List[str] = [
    '"{keyword}" {country} inurl:contact OR inurl:about-us email',
    '"{keyword}" supplier {country} contact email phone',
    '"{keyword}" {country} CEO OR founder OR owner "contact us"',
    '"{keyword}" manufacturer {country} contact email',
    '"{keyword}" {country} dealer distributor email phone',
    '"{keyword}" services {country} "contact" "@"',
]

# City-level queries — same principle, city-scoped
_CITY_TEMPLATES: List[str] = [
    "{keyword} owner {city} contact email",
    '"{keyword}" {city} contact email phone',
    '"{keyword}" supplier {city} CEO founder contact',
    '"{keyword}" company {city} inurl:contact email',
    '"{keyword}" {city} owner manager "contact us"',
]

# Buyer-intent social queries — surfaces threads from actual buyers/businesses
_SOCIAL_INTENT_TEMPLATES: List[str] = [
    '"looking for" "{keyword}" supplier OR vendor OR service',
    '"need" "{keyword}" contact email site:reddit.com OR site:quora.com',
    '"recommend" "{keyword}" company OR provider',
    '"where to buy" "{keyword}"',
    '"seeking" "{keyword}" supplier OR manufacturer',
]

# News queries — executive moves and company growth signals
_NEWS_TEMPLATES: List[str] = [
    '"{keyword}" company {country} CEO founder appointed',
    '"{keyword}" {country} business expansion contact',
    '"{keyword}" industry {country} new contract deal',
]

# Decision-maker direct search — named executives at companies in this space
_DECISION_MAKER_TEMPLATES: List[str] = [
    '"{keyword}" CEO OR founder OR director email contact {country}',
    '"{keyword}" owner manager "contact us" email {country}',
    '"{keyword}" procurement buyer {country} email contact',
]

_GITHUB_TEMPLATES: List[str] = [
    'site:github.com "{keyword}" email contact',
    'site:github.com "{keyword}" readme "contact" email',
]


# ---------------------------------------------------------------------------
# Intent signal phrase sets
# ---------------------------------------------------------------------------

_HIGH_INTENT_PHRASES = frozenset({
    'looking for', 'need', 'want to buy', 'where to buy', 'how to buy',
    'purchase', 'order', 'price', 'quote', 'supplier needed', 'urgent',
    'seeking supplier', 'sourcing', 'procurement', 'bulk order',
    'buy now', 'get a quote', 'request quote', 'rfp', 'tender',
    'immediate need', 'interested in buying',
})

_MEDIUM_INTENT_PHRASES = frozenset({
    'recommend', 'best', 'compare', 'review', 'alternative', 'options',
    'suggestions', 'interested in', 'considering', 'evaluating',
    'thinking about', 'planning to buy', 'what do you think',
    'which is better', 'pros and cons',
})

_LOW_INTENT_PHRASES = frozenset({
    'information', 'learn about', 'what is', 'how does', 'explain',
    'tutorial', 'guide', 'overview', 'introduction to',
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_queries(
    category_name: str,
    country: str,
    city: Optional[str] = None,
    sources: Optional[List[str]] = None,
    max_keywords: int = 5,
) -> List[str]:
    """Generate targeted search queries for a lead category.

    Args:
        category_name: Category slug (e.g. 'laptops') or display name.
        country:       Target country name (e.g. 'Lebanon').
        city:          Optional city for city-level templates (e.g. 'Beirut').
        sources:       Collector types to activate. Defaults to category's source_types.
                       Valid values: 'web', 'social', 'news', 'directories', 'github'.
        max_keywords:  Max keywords to expand per template group (caps query count).

    Returns:
        Deduplicated list of search query strings, ordered by template priority.
    """
    cat = get_category(category_name)
    if cat is None:
        logger.warning("[QueryGen] Unknown category: %r — returning empty query list", category_name)
        return []

    active_sources = set(sources if sources is not None else cat.source_types)
    keywords = cat.keywords[:max_keywords]
    queries: List[str] = []

    # ── PRIORITY 0: LinkedIn profile/company search (direct person discovery) ─
    # Top keyword only — LinkedIn results are rich so one keyword gives enough
    # variety; the parser in interest_collector extracts name/title/company.
    if active_sources & {'web', 'directories'}:
        for kw in keywords[:1]:
            for tmpl in _LINKEDIN_TEMPLATES:
                queries.append(tmpl.format(keyword=kw, country=country, city=city or country))

    # ── PRIORITY 1: People-first discovery (decision makers come first) ─────
    # Uses top 2 keywords so queries stay focused; these fill the first N slots
    # so the 8-query cap in interest_collector gives targeted DM discovery.
    if active_sources & {'web', 'directories'}:
        for kw in keywords[:2]:
            for tmpl in _PEOPLE_FIRST_TEMPLATES:
                queries.append(tmpl.format(keyword=kw, country=country, city=city or country))

    # ── PRIORITY 2: Company contact-page queries ────────────────────────────
    if active_sources & {'web', 'directories'}:
        for kw in keywords:
            for tmpl in _COMPANY_TEMPLATES:
                queries.append(tmpl.format(keyword=kw, country=country, city=city or country))

    # ── PRIORITY 3: Decision-maker direct search ─────────────────────────────
    if active_sources & {'web', 'directories'}:
        for kw in keywords:
            for tmpl in _DECISION_MAKER_TEMPLATES:
                queries.append(tmpl.format(keyword=kw, country=country, city=city or country))

    # ── City-specific queries (only when a city is supplied) ────────────────
    if city and active_sources & {'web', 'directories'}:
        for kw in keywords:
            for tmpl in _CITY_TEMPLATES:
                queries.append(tmpl.format(keyword=kw, city=city, country=country))

    # ── News queries ────────────────────────────────────────────────────────
    if 'news' in active_sources:
        for kw in keywords:
            for tmpl in _NEWS_TEMPLATES:
                queries.append(tmpl.format(keyword=kw, country=country))

    # ── Social intent queries ────────────────────────────────────────────────
    if 'social' in active_sources:
        for kw in keywords:
            for tmpl in _SOCIAL_INTENT_TEMPLATES:
                queries.append(tmpl.format(keyword=kw))

    # ── GitHub queries (developer / software categories) ─────────────────────
    if 'github' in active_sources:
        for kw in keywords:
            for tmpl in _GITHUB_TEMPLATES:
                queries.append(tmpl.format(keyword=kw))

    # ── Deduplicate while preserving order ───────────────────────────────────
    seen: set = set()
    result: List[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            result.append(q)

    logger.debug("[QueryGen] %r → %d queries (country=%s, city=%s, sources=%s)",
                 category_name, len(result), country, city, sorted(active_sources))
    return result


def detect_buying_intent(
    text: str,
    category_name: str,
) -> Dict[str, Any]:
    """Detect buying intent signals in a text snippet.

    Scores the text using:
      - Category keywords (product_interest signals)
      - High/medium/low intent phrase sets
      - Category-specific intent_phrases from the category config

    Args:
        text:          Raw text (post title, snippet, page excerpt, etc.)
        category_name: Category slug or display name.

    Returns:
        Dict with keys:
            buying_intent    — 'high' | 'medium' | 'low' | 'none'
            confidence       — 0.0 – 1.0
            intent_reason    — human-readable explanation
            matched_phrases  — list of matched signal phrases
            category         — input category_name
            product_interest — list of category keywords found in text
    """
    if not text or not text.strip():
        return _intent_result('none', 0.0, 'Empty text', [], category_name, [])

    cat = get_category(category_name)
    text_lower = text.lower()

    # ── 1. Product keyword match ─────────────────────────────────────────────
    product_interest = [
        kw for kw in (cat.keywords if cat else [])
        if kw.lower() in text_lower
    ]

    # ── 2. Generic intent phrase matching ────────────────────────────────────
    matched_high   = [p for p in _HIGH_INTENT_PHRASES   if p in text_lower]
    matched_medium = [p for p in _MEDIUM_INTENT_PHRASES if p in text_lower]
    matched_low    = [p for p in _LOW_INTENT_PHRASES    if p in text_lower]

    # ── 3. Category-specific intent_phrases ─────────────────────────────────
    cat_matches: List[str] = []
    if cat:
        cat_matches = [p for p in cat.intent_phrases if p.lower() in text_lower]

    # ── 4. Weighted score ────────────────────────────────────────────────────
    score = 0.0
    score += len(matched_high)            * 3.0
    score += len(matched_medium)          * 1.5
    score += len(matched_low)             * 0.5
    score += len(cat_matches)             * 2.0
    score += min(len(product_interest), 3) * 1.0   # keyword hits cap at 3 pts

    all_matched = list(set(matched_high + matched_medium + matched_low + cat_matches))

    # Early exit: no relevant signals at all
    if not product_interest and not all_matched:
        return _intent_result(
            'none', 0.0,
            'No category keywords or intent phrases found',
            [], category_name, [],
        )

    # ── 5. Normalize confidence to [0, 1] ────────────────────────────────────
    confidence = round(min(score / 15.0, 1.0), 2)

    # ── 6. Classify intent level ─────────────────────────────────────────────
    # Require actual signal phrases for high/medium — numeric score alone from
    # keyword hits can inflate the tier for purely informational text.
    top_high   = (matched_high   or cat_matches)[:3]
    top_medium = (matched_medium or cat_matches)[:3]

    if matched_high or score >= 6.0:
        level  = 'high'
        reason = f"High-intent signals detected: {', '.join(top_high)}"
    elif matched_medium or (cat_matches and not matched_low):
        level  = 'medium'
        reason = f"Research/comparison signals: {', '.join(top_medium)}"
    elif product_interest or score > 0:
        level  = 'low'
        reason = 'Category keyword found but no clear buying action phrase'
    else:
        level  = 'none'
        reason = 'No intent signals detected'

    return _intent_result(level, confidence, reason, all_matched, category_name, product_interest)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _intent_result(
    buying_intent: str,
    confidence: float,
    intent_reason: str,
    matched_phrases: List[str],
    category: str,
    product_interest: List[str],
) -> Dict[str, Any]:
    return {
        'buying_intent':    buying_intent,
        'confidence':       confidence,
        'intent_reason':    intent_reason,
        'matched_phrases':  matched_phrases,
        'category':         category,
        'product_interest': product_interest,
    }
