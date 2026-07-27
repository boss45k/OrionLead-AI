"""
Lead Candidate Filter — Two-stage pre-save validation
=====================================================
Stage 1 (instant): keyword filter — rejects page titles, course names,
                   blog posts, and content masquerading as company leads.
Stage 2 (AI):      Gemini/Groq batch validation — confirms remaining
                   candidates are real business entities matching the query.

Usage:
    from app.services.lead_candidate_filter import filter_candidates

    platform_leads = filter_candidates(
        platform_leads,
        query='e-learning companies',
        location='Oman',
    )
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage 1 — keyword filter
# ---------------------------------------------------------------------------

# Patterns that reliably identify page titles and content, not companies.
_CONTENT_PATTERNS: list = [
    re.compile(r'\bbest\s+[\w\s&-]{2,50}\s+(?:in|for|of)\b', re.IGNORECASE),  # "Best X in Y"
    re.compile(r'\btop\s+\d+\b', re.IGNORECASE),                               # "Top 10"
    re.compile(r'\b\d+\s+(best|top|free|ways?|tips?)\b', re.IGNORECASE),       # "10 Best"
    re.compile(r'\bhow\s+to\b', re.IGNORECASE),
    re.compile(r'\bvs\.?\s+\w', re.IGNORECASE),
    re.compile(r'\bguide\s+to\b', re.IGNORECASE),
    re.compile(r'\b(training|online|free)\s+course\b', re.IGNORECASE),
    re.compile(r'\b(complete|ultimate|definitive)\s+(guide|course|tutorial)\b', re.IGNORECASE),
    re.compile(r'@[a-zA-Z0-9_]{3,}', re.IGNORECASE),  # Twitter handle embedded in name
]

# If a name is composed ONLY of these words (after stripping stop-words), it is
# a category label — not a company name.
_CATEGORY_ONLY_WORDS = frozenset({
    'course', 'courses', 'tutorial', 'tutorials', 'training', 'lesson', 'lessons',
    'bootcamp', 'certification', 'certificate', 'masterclass', 'workshop', 'webinar',
    'seminar', 'lecture', 'class', 'classes', 'module', 'curriculum',
    'guide', 'guides', 'review', 'reviews', 'comparison', 'checklist', 'overview',
    'platform', 'platforms', 'tool', 'tools', 'app', 'apps',
    'education', 'learning', 'elearning', 'e-learning',
    'blog', 'article', 'post', 'news', 'newsletter',
    'list', 'directory', 'database', 'catalog',
})

_STOP_WORDS = frozenset({'the', 'and', 'for', 'in', 'of', 'to', 'a', 'an', 'or',
                          'with', 'at', 'by', 'on', 'is', 'are', 'from', 'into'})


def _is_content_not_company(text: str) -> bool:
    """Return True if the text looks like a page title / content category."""
    if not text:
        return False
    t = text.strip()

    for pat in _CONTENT_PATTERNS:
        if pat.search(t):
            return True

    words = re.findall(r'\b[a-z]{3,}\b', t.lower())
    meaningful = [w for w in words if w not in _STOP_WORDS]
    if meaningful and all(w in _CATEGORY_ONLY_WORDS for w in meaningful):
        return True

    return False


def _name_equals_company(lead: Dict[str, Any]) -> bool:
    name    = (lead.get('name')    or '').strip().lower()
    company = (lead.get('company') or '').strip().lower()
    return bool(name and company and name == company)


def keyword_filter(leads: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    Instant keyword-based pre-filter.
    Returns (passed_leads, n_rejected).
    """
    passed: List[Dict[str, Any]] = []
    rejected = 0

    for lead in leads:
        name    = lead.get('name',    '') or ''
        company = lead.get('company', '') or ''

        if _is_content_not_company(name) or _is_content_not_company(company):
            logger.debug("[candidate_filter] kw-reject (content): '%s'", name or company)
            rejected += 1
            continue

        passed.append(lead)

    return passed, rejected


# ---------------------------------------------------------------------------
# Stage 2 — Gemini/Groq batch validation
# ---------------------------------------------------------------------------

_BATCH_SIZE = 10

_SYSTEM = (
    "You are a B2B lead quality validator. You decide which candidates are real, "
    "contactable business entities vs. content artifacts (course titles, blog posts, "
    "aggregator pages, generic categories, or scraped page titles)."
)

_PROMPT_TMPL = """\
User searched for: "{query}" in "{location}"

Evaluate these {n} candidates. Return ONLY a JSON array of 0-based indices for candidates \
that are REAL BUSINESS ENTITIES (companies or named professionals) relevant to the search.

Reject a candidate if ANY of the following is true:
• The name is a course / article / blog post title
• The name is a generic category (e.g. "Online Education", "E-Learning Platforms")
• The name duplicates the search query verbatim
• The name contains a social-media handle (@username) or is a username
• There is no recognisable company or person name at all

Candidates:
{candidates}

Respond with ONLY valid JSON — e.g. [0, 2, 5] or []. No explanation."""


def _gemini_validate_batch(
    leads: List[Dict[str, Any]],
    query: str,
    location: str,
    ai_svc: Any,
) -> Tuple[List[Dict[str, Any]], int]:
    """Send one batch to Gemini/Groq. Returns (kept, n_rejected)."""
    lines = []
    for j, lead in enumerate(leads):
        name    = lead.get('name', '') or 'Unknown'
        company = lead.get('company', '') or ''
        website = lead.get('website', '') or ''
        label   = name
        if company and company.lower() != name.lower():
            label += f" | {company}"
        if website:
            label += f"  <{website}>"
        lines.append(f"{j}: {label}")

    prompt = _PROMPT_TMPL.format(
        query=query or 'companies',
        location=location or 'unknown',
        n=len(leads),
        candidates='\n'.join(lines),
    )

    try:
        raw = ai_svc._generate(
            prompt=prompt,
            system=_SYSTEM,
            temperature=0.0,
            max_tokens=64,
        )
        if not raw:
            return leads, 0

        m = re.search(r'\[[\d,\s]*\]', raw)
        if not m:
            return leads, 0

        valid_indices = set(json.loads(m.group()))
        kept, rejected = [], 0
        for j, lead in enumerate(leads):
            if j in valid_indices:
                kept.append(lead)
            else:
                rejected += 1
                logger.debug(
                    "[candidate_filter] Gemini-reject: '%s'",
                    lead.get('name') or lead.get('company'),
                )
        return kept, rejected

    except Exception as exc:
        logger.debug("[candidate_filter] Gemini batch error: %s", exc)
        return leads, 0  # fail-open


def gemini_validate(
    leads: List[Dict[str, Any]],
    query: str,
    location: str,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Stage 2: AI batch validation.
    Skips gracefully if no Gemini/Groq key is configured.
    Returns (passed_leads, n_rejected).
    """
    if not leads:
        return leads, 0

    try:
        from app.services.gemini_service import get_ai_service
        ai_svc = get_ai_service()
        if not (ai_svc._gemini_key or ai_svc._groq_key):
            return leads, 0
    except Exception:
        return leads, 0

    kept_all: List[Dict[str, Any]] = []
    total_rejected = 0

    for i in range(0, len(leads), _BATCH_SIZE):
        batch = leads[i : i + _BATCH_SIZE]
        kept, n_rej = _gemini_validate_batch(batch, query, location, ai_svc)
        kept_all.extend(kept)
        total_rejected += n_rej

    return kept_all, total_rejected


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def filter_candidates(
    leads: List[Dict[str, Any]],
    query: str = '',
    location: str = '',
    require_contact: bool = False,
) -> List[Dict[str, Any]]:
    """
    Apply both filter stages.

    Args:
        leads:           Raw candidate leads from any collector.
        query:           User's original search query (Gemini context).
        location:        User's location string (Gemini context).
        require_contact: Drop leads with neither email nor phone (default: False —
                         website / LinkedIn still allow outreach).

    Returns:
        Filtered list of candidates ready for the quality gate.
    """
    if not leads:
        return leads

    n_in = len(leads)

    # Stage 1: keyword filter (< 1 ms)
    after_kw, kw_rej = keyword_filter(leads)
    if kw_rej:
        logger.info(
            "[candidate_filter] Stage 1 (keywords): %d → %d  (%d rejected as content)",
            n_in, len(after_kw), kw_rej,
        )

    # Stage 1b: optional hard contact requirement
    if require_contact and after_kw:
        no_contact = [l for l in after_kw if not l.get('email') and not l.get('phone')]
        after_kw   = [l for l in after_kw if l.get('email') or l.get('phone')]
        if no_contact:
            logger.info(
                "[candidate_filter] Stage 1b (contact gate): %d leads removed (no email+phone)",
                len(no_contact),
            )

    if not after_kw:
        logger.info("[candidate_filter] 0 candidates remain after Stage 1 — skipping Gemini")
        return []

    # Stage 2: Gemini/Groq AI validation
    after_gem, gem_rej = gemini_validate(after_kw, query, location)
    if gem_rej:
        logger.info(
            "[candidate_filter] Stage 2 (Gemini): %d → %d  (%d rejected as non-business)",
            len(after_kw), len(after_gem), gem_rej,
        )

    return after_gem
