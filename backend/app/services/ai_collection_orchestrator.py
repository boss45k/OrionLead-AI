"""
AI Collection Orchestrator
==========================
Every collection request passes through here before a single API call is made.

Gemini analyzes the query and returns a CollectionStrategy — which sources to
use, custom Google search queries targeting named decision-makers (not
directories), DM titles for Apollo, and rejection signals to drop bad results
before they reach the quality gate.

Fallback: rule-based strategy when Gemini is unavailable.

Usage
-----
    from app.services.ai_collection_orchestrator import get_orchestrator

    orch = get_orchestrator()
    strategy = orch.analyze_query(
        query="SaaS companies",
        country_name="Nigeria",
        country_code="NG",
        collection_type="people",
    )
    # strategy.search_queries  → AI-generated Google queries
    # strategy.sources         → ordered source list
    # strategy.dm_titles       → Apollo title filter
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GROQ_API_URL   = "https://api.groq.com/openai/v1/chat/completions"


# ---------------------------------------------------------------------------
# CollectionStrategy — output of analyze_query()
# ---------------------------------------------------------------------------

@dataclass
class CollectionStrategy:
    # What kind of business/person the user is hunting for
    intent: str = 'other'                   # tech_startup | fintech | saas | local_sme | …
    persona: str = 'any_dm'                 # founder_ceo | vp_director | owner | …
    company_size: str = 'any'               # startup | sme | enterprise | any
    is_b2b: bool = True

    # Ordered source list — try in this order, stop when quota or deadline hit
    sources: List[str] = field(default_factory=lambda: ['apollo', 'serper_linkedin', 'hunter'])

    # Custom Google queries that target NAMED PEOPLE, not directories
    search_queries: List[str] = field(default_factory=list)

    # Apollo people-search title filter
    dm_titles: List[str] = field(default_factory=lambda: [
        'CEO', 'Founder', 'Co-Founder', 'CTO', 'CMO', 'COO',
        'Director', 'VP', 'Owner', 'President', 'Head of',
    ])

    # Industry keywords for better LinkedIn snippet matching
    industry_keywords: List[str] = field(default_factory=list)

    # Words in a company name that should trigger immediate rejection
    rejection_signals: List[str] = field(default_factory=lambda: [
        'university', 'polytechnic', 'ministry', 'government',
        'hospital', 'school', 'charity', 'ngo', 'embassy',
    ])

    # How confident we are in the AI analysis (0–1)
    confidence: float = 0.5

    # Provider that generated this strategy
    provider: str = 'rules'


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class CollectionOrchestrator:
    def __init__(self) -> None:
        self._gemini_key = os.getenv('GEMINI_API_KEY', '').strip()
        self._groq_key   = os.getenv('GROQ_API_KEY', '').strip()
        self._timeout    = int(os.getenv('GEMINI_TIMEOUT', 30))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_query(
        self,
        query: str,
        country_name: str,
        country_code: str = '',
        collection_type: str = 'people',
    ) -> CollectionStrategy:
        """
        Analyze a collection query with Gemini and return an optimized strategy.
        Falls back to rule-based strategy if AI is unavailable.
        """
        if not query:
            return self._rule_based_strategy(query, country_name, collection_type)

        try:
            strategy = self._gemini_analyze(query, country_name, country_code, collection_type)
            if strategy and strategy.confidence >= 0.4:
                logger.info(
                    f"[orchestrator] Gemini strategy: intent={strategy.intent} "
                    f"persona={strategy.persona} sources={strategy.sources} "
                    f"queries={len(strategy.search_queries)}"
                )
                return strategy
        except Exception as e:
            logger.debug(f"[orchestrator] Gemini failed: {e}")

        try:
            strategy = self._groq_analyze(query, country_name, country_code, collection_type)
            if strategy and strategy.confidence >= 0.4:
                logger.info(
                    f"[orchestrator] Groq strategy: intent={strategy.intent} "
                    f"sources={strategy.sources}"
                )
                return strategy
        except Exception as e:
            logger.debug(f"[orchestrator] Groq failed: {e}")

        logger.info("[orchestrator] Using rule-based strategy")
        return self._rule_based_strategy(query, country_name, collection_type)

    # ------------------------------------------------------------------
    # AI providers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        query: str,
        country_name: str,
        country_code: str,
        collection_type: str,
    ) -> str:
        return f"""You are a B2B lead intelligence engine. Analyze this lead collection request.

QUERY: "{query}"
TARGET COUNTRY: {country_name} ({country_code})
COLLECTION TYPE: {collection_type}

Respond with ONLY valid JSON (no markdown, no explanation):
{{
  "intent": "tech_startup|fintech|saas|ecommerce|healthcare_b2b|real_estate|consulting|manufacturing|local_sme|other",
  "persona": "founder_ceo|c_suite|vp_director|manager|owner|technical_lead|any_dm",
  "company_size": "startup|sme|enterprise|any",
  "is_b2b": true,
  "sources": ["apollo", "serper_linkedin", "hunter", "google_places"],
  "dm_titles": ["CEO", "Founder", "CTO"],
  "industry_keywords": ["keyword1", "keyword2"],
  "search_queries": [
    "site:linkedin.com/in QUERY CEO OR founder COUNTRY",
    "QUERY COUNTRY CEO OR founder email contact -site:linkedin.com inurl:about OR inurl:team",
    "QUERY COUNTRY CTO OR director OR owner email -inurl:jobs -site:linkedin.com"
  ],
  "rejection_signals": ["university", "government", "ngo"],
  "confidence": 0.85
}}

STRICT RULES:
1. search_queries: generate exactly 3 Google search queries that find NAMED PEOPLE with contact info.
   - Query 1 MUST use site:linkedin.com/in with relevant titles and country
   - Query 2: team/about pages with email signals, exclude job boards
   - Query 3: named executives + contact/email signals, exclude news/directories
   - Replace QUERY with the actual search terms from the query
   - Replace COUNTRY with {country_name}
   - NEVER include job boards (indeed, glassdoor, linkedin/jobs)
   - NEVER target directories (yellowpages, yelp, crunchbase)
   - Target actual people with emails

2. sources (ordered by expected yield, highest quality first):
   - Include "apollo" if collection_type=people (real B2B verified emails)
   - Include "google_places" if intent is local_sme or real_estate or healthcare_b2b
   - Include "serper_linkedin" for tech_startup, fintech, saas, consulting
   - Include "hunter" when company websites are likely available
   - Max 3 sources

3. dm_titles: 5-8 titles most relevant to this specific query (no generic list)

4. rejection_signals: words in company names that indicate non-B2B (universities, NGOs, govt)

5. is_b2b: set false only if clearly consumer/B2C (retail store, restaurant, etc.)"""

    def _parse_strategy(self, raw: str, provider: str) -> Optional[CollectionStrategy]:
        """Parse AI JSON response into a CollectionStrategy."""
        raw = raw.strip()
        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
        # Find the first JSON object
        m = re.search(r'\{[\s\S]*\}', raw)
        if not m:
            return None
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return None

        # Validate and sanitize sources
        valid_sources = {'apollo', 'serper_linkedin', 'hunter', 'google_places'}
        sources = [s for s in (data.get('sources') or []) if s in valid_sources]
        if not sources:
            sources = ['apollo', 'serper_linkedin', 'hunter']

        # Ensure search_queries are real strings
        raw_queries = data.get('search_queries') or []
        search_queries = [q for q in raw_queries if isinstance(q, str) and len(q) > 20]

        dm_titles = data.get('dm_titles') or [
            'CEO', 'Founder', 'CTO', 'Director', 'VP', 'Owner',
        ]

        return CollectionStrategy(
            intent=str(data.get('intent', 'other')),
            persona=str(data.get('persona', 'any_dm')),
            company_size=str(data.get('company_size', 'any')),
            is_b2b=bool(data.get('is_b2b', True)),
            sources=sources,
            search_queries=search_queries,
            dm_titles=dm_titles[:10],
            industry_keywords=data.get('industry_keywords') or [],
            rejection_signals=data.get('rejection_signals') or [],
            confidence=float(data.get('confidence', 0.5)),
            provider=provider,
        )

    def _gemini_analyze(
        self,
        query: str,
        country_name: str,
        country_code: str,
        collection_type: str,
    ) -> Optional[CollectionStrategy]:
        if not self._gemini_key:
            return None

        prompt = self._build_prompt(query, country_name, country_code, collection_type)
        url = (
            f"{GEMINI_API_URL}/gemini-2.5-flash"
            f":generateContent?key={self._gemini_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 600,
                "responseMimeType": "application/json",
            },
        }
        resp = requests.post(url, json=payload, timeout=self._timeout)
        resp.raise_for_status()
        candidates = resp.json().get("candidates", [])
        if not candidates:
            return None
        text = candidates[0]["content"]["parts"][0]["text"]
        return self._parse_strategy(text, provider='gemini')

    def _groq_analyze(
        self,
        query: str,
        country_name: str,
        country_code: str,
        collection_type: str,
    ) -> Optional[CollectionStrategy]:
        if not self._groq_key:
            return None

        prompt = self._build_prompt(query, country_name, country_code, collection_type)
        headers = {
            "Authorization": f"Bearer {self._groq_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 600,
            "response_format": {"type": "json_object"},
        }
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return self._parse_strategy(text, provider='groq')

    # ------------------------------------------------------------------
    # Rule-based fallback — always works, no API needed
    # ------------------------------------------------------------------

    _TECH_KEYWORDS = frozenset({
        'saas', 'software', 'tech', 'startup', 'app', 'platform', 'digital',
        'cloud', 'ai', 'fintech', 'data', 'developer', 'engineering', 'mobile',
        'cyber', 'blockchain', 'api', 'devops', 'web',
    })
    _FINANCE_KEYWORDS = frozenset({
        'fintech', 'finance', 'investment', 'bank', 'insurance', 'trading',
        'capital', 'fund', 'lending', 'payment', 'forex',
    })
    _LOCAL_KEYWORDS = frozenset({
        'restaurant', 'clinic', 'hotel', 'shop', 'store', 'salon', 'gym',
        'dental', 'pharmacy', 'real estate', 'property', 'agent', 'broker',
    })
    _HEALTH_KEYWORDS = frozenset({
        'health', 'medical', 'pharma', 'biotech', 'hospital', 'clinic',
        'wellness', 'healthcare',
    })
    _CONSULT_KEYWORDS = frozenset({
        'consult', 'advisory', 'agency', 'marketing', 'pr', 'legal', 'law',
        'accounting', 'audit', 'hr', 'recruitment', 'staffing',
    })

    def _rule_based_strategy(
        self,
        query: str,
        country_name: str,
        collection_type: str,
    ) -> CollectionStrategy:
        q = query.lower()
        words = set(re.findall(r'\b\w+\b', q))

        # Intent detection
        if words & self._TECH_KEYWORDS:
            intent = 'tech_startup' if 'startup' in words else 'saas'
            dm_titles = ['CEO', 'CTO', 'Founder', 'Co-Founder', 'Head of Engineering',
                         'VP Engineering', 'Director', 'Owner']
            sources = ['apollo', 'serper_linkedin', 'hunter']
        elif words & self._FINANCE_KEYWORDS:
            intent = 'fintech'
            dm_titles = ['CEO', 'CFO', 'Founder', 'Managing Director', 'COO',
                         'VP Finance', 'Head of Payments', 'Director']
            sources = ['apollo', 'serper_linkedin', 'hunter']
        elif words & self._LOCAL_KEYWORDS:
            intent = 'local_sme'
            dm_titles = ['Owner', 'Manager', 'Director', 'Founder', 'CEO', 'Partner']
            sources = ['google_places', 'serper_linkedin', 'hunter']
        elif words & self._HEALTH_KEYWORDS:
            intent = 'healthcare_b2b'
            dm_titles = ['CEO', 'CMO', 'Director', 'Head of', 'Founder', 'CTO',
                         'VP Operations', 'COO']
            sources = ['apollo', 'serper_linkedin', 'hunter']
        elif words & self._CONSULT_KEYWORDS:
            intent = 'consulting'
            dm_titles = ['Partner', 'Managing Director', 'CEO', 'Founder',
                         'Director', 'Principal', 'Head of', 'VP']
            sources = ['apollo', 'serper_linkedin', 'hunter']
        else:
            intent = 'other'
            dm_titles = ['CEO', 'Founder', 'Director', 'Owner', 'Managing Director',
                         'VP', 'Head of', 'Partner']
            sources = ['apollo', 'serper_linkedin', 'hunter']

        # Generate 3 targeted Google search queries
        titles_str = ' OR '.join(f'"{t}"' for t in dm_titles[:4])
        search_queries = [
            # 1. LinkedIn profiles — named people
            f'site:linkedin.com/in "{query}" {titles_str} "{country_name}"',
            # 2. Team/about pages — personal emails
            f'"{query}" "{country_name}" {" OR ".join(dm_titles[:3])} '
            f'inurl:team OR inurl:about OR inurl:leadership -inurl:jobs',
            # 3. Contact pages — named executives
            f'"{query}" "{country_name}" CEO OR founder OR director '
            f'"email" OR "contact" -site:linkedin.com -inurl:jobs -inurl:news',
        ]

        return CollectionStrategy(
            intent=intent,
            persona='any_dm',
            company_size='any',
            is_b2b=True,
            sources=sources,
            search_queries=search_queries,
            dm_titles=dm_titles,
            industry_keywords=[query],
            rejection_signals=[
                'university', 'polytechnic', 'ministry', 'government',
                'hospital', 'school', 'charity', 'ngo', 'embassy',
            ],
            confidence=0.6,
            provider='rules',
        )


# ---------------------------------------------------------------------------
# Candidate validator — fast in-memory check before hitting quality engine
# ---------------------------------------------------------------------------

def is_valid_candidate(
    raw: Dict[str, Any],
    strategy: CollectionStrategy,
    collection_type: str = 'people',
) -> tuple[bool, str]:
    """
    Quick binary check on a raw collector result.
    Returns (True, '') to accept or (False, reason) to discard immediately.

    Runs BEFORE evaluate_lead_quality() to drop obvious junk early.
    """
    company = (raw.get('company') or '').strip()
    name    = (raw.get('name') or '').strip()
    email   = (raw.get('email') or '').lower().strip()
    website = (raw.get('website') or '').strip()

    # Must have at least company name or personal name
    if not company and not name:
        return False, 'no_identity'

    # People collection: require a name
    if collection_type == 'people' and not name:
        return False, 'no_person_name'

    # Reject if company matches any rejection signal from the strategy
    company_lower = company.lower()
    for sig in strategy.rejection_signals:
        if sig in company_lower:
            return False, f'rejection_signal:{sig}'

    # Reject bot/generated emails immediately
    _GEN_SOURCES = frozenset({'generated', 'generated_personal', 'generated_generic', 'inferred'})
    email_src = (raw.get('data_points') or {}).get('email_source', '')
    if email_src in _GEN_SOURCES:
        return False, 'generated_email'

    # For people collection: generic-only email with no name → reject now
    if collection_type == 'people' and email:
        _GENERIC = frozenset({
            'info', 'contact', 'hello', 'support', 'sales', 'admin',
            'team', 'marketing', 'office', 'hr', 'press',
        })
        local = email.split('@')[0] if '@' in email else email
        if local in _GENERIC and not name:
            return False, 'generic_email_no_person'

    # Must have at least one contact signal
    has_contact = bool(email or website or raw.get('phone') or raw.get('linkedin_url'))
    if not has_contact:
        return False, 'no_contact_signal'

    return True, ''


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_orchestrator: Optional[CollectionOrchestrator] = None


def get_orchestrator() -> CollectionOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = CollectionOrchestrator()
    return _orchestrator
