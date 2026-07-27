"""
Intent Detector
===============
Detects B2B buying intent signals from raw text (post body, page excerpt,
job description, news mention, etc.).

Output schema
-------------
{
    'product_interest':  str,   # best-guess product/service category
    'interest_category': str,   # canonical category label
    'buying_intent':     str,   # 'high' | 'medium' | 'low' | 'none'
    'intent_reason':     str,   # human-readable explanation
    'intent_confidence': float, # 0.0 – 1.0
    'matched_phrases':   list,  # raw phrases that triggered detection
}

Usage
-----
    from app.services.intent_detector import detect_intent

    result = detect_intent(
        text="We are looking for a wholesale supplier of AI software tools.",
        company="Acme Corp",
        industry="Technology",
    )
    # → {'buying_intent': 'high', 'interest_category': 'ai_software', ...}
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Phrase banks — ordered from most specific (high intent) to least (low)
# ---------------------------------------------------------------------------

_HIGH_INTENT_PHRASES: List[str] = [
    # Direct purchase / vendor signals
    'request a quote', 'request quote', 'get a quote', 'get quote',
    'looking for a supplier', 'looking for supplier', 'seeking vendor',
    'seeking a vendor', 'need a vendor', 'vendor evaluation',
    'where to buy', 'where can i buy', 'how to purchase',
    'wholesale pricing', 'wholesale price', 'bulk pricing', 'bulk order',
    'bulk purchase', 'reseller program', 'partner program',
    'accept demos', 'book a demo', 'request demo', 'schedule demo',
    'evaluate solutions', 'evaluating solutions', 'evaluating vendors',
    'comparing providers', 'comparing solutions', 'shortlisting vendors',
    'rfp', 'rfq', 'request for proposal', 'request for quotation',
    'looking to switch', 'replace our current', 'migrate from',
    # Urgency signals
    'urgent need', 'need immediately', 'asap', 'immediate requirement',
    'need by', 'deadline', 'launch date', 'go-live',
    # Budget signals
    'budget approved', 'budget available', 'have budget', 'allocated budget',
]

_MEDIUM_INTENT_PHRASES: List[str] = [
    # Research / discovery signals
    'looking for', 'looking to', 'need a', 'need an', 'need to find',
    'trying to find', 'searching for', 'in search of',
    'recommend', 'recommendations', 'can anyone recommend',
    'best tool for', 'best software for', 'best platform for',
    'supplier', 'vendors', 'provider', 'providers',
    'wholesale', 'distributor', 'reseller', 'partner',
    'integrate with', 'integration with', 'connect to',
    'automate', 'automation', 'streamline', 'scale',
    # Hiring → company growth signal
    'hiring', 'we are hiring', "we're hiring", 'join our team',
    'open position', 'job opening', 'expanding team',
    # Pain-point signals
    'struggling with', 'problem with', 'issue with', 'pain point',
    'bottleneck', 'manual process', 'time-consuming',
    'replace excel', 'spreadsheet solution', 'outgrown',
    # Competitor awareness
    'alternative to', 'vs ', 'versus', 'compared to', 'comparison',
]

_LOW_INTENT_PHRASES: List[str] = [
    'interested in', 'curious about', 'exploring options', 'learning about',
    'researching', 'considering', 'thinking about', 'wondering if',
    'would be nice', 'might need', 'eventually', 'in the future',
    'nice to have', 'looking into',
]

# ---------------------------------------------------------------------------
# Product / interest category mapping
# Maps detected keywords → canonical interest_category label
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    'ai_software':       ['ai', 'artificial intelligence', 'machine learning', 'llm', 'gpt', 'generative ai', 'nlp'],
    'automation':        ['automation', 'automate', 'workflow', 'rpa', 'bot', 'robotic process'],
    'crm_sales':         ['crm', 'sales software', 'sales tool', 'lead management', 'pipeline'],
    'marketing_tools':   ['marketing', 'email marketing', 'seo', 'advertising', 'content marketing'],
    'analytics':         ['analytics', 'dashboard', 'reporting', 'business intelligence', 'bi tool', 'data visualization'],
    'cloud_saas':        ['saas', 'cloud', 'subscription software', 'software as a service'],
    'security':          ['security', 'cybersecurity', 'soc', 'siem', 'endpoint protection', 'compliance'],
    'erp_finance':       ['erp', 'accounting', 'finance software', 'invoicing', 'billing', 'payroll'],
    'ecommerce':         ['ecommerce', 'e-commerce', 'online store', 'shopify', 'woocommerce', 'marketplace'],
    'logistics':         ['logistics', 'supply chain', 'shipping', 'freight', 'inventory', 'warehouse'],
    'wholesale_trade':   ['wholesale', 'wholesale supplier', 'distributor', 'bulk order', 'reseller'],
    'hr_recruiting':     ['hr software', 'ats', 'applicant tracking', 'recruitment', 'payroll'],
    'dev_tools':         ['api', 'sdk', 'developer tools', 'devops', 'ci/cd', 'monitoring'],
    'data_integration':  ['data integration', 'etl', 'data pipeline', 'sync', 'connector'],
    'customer_support':  ['helpdesk', 'ticketing', 'customer support', 'live chat', 'chatbot'],
    'general_b2b':       ['b2b', 'business software', 'enterprise software', 'platform'],
}


def _detect_category(text_lower: str) -> Tuple[str, str]:
    """Return (interest_category, product_interest_label)."""
    best_cat   = 'general_b2b'
    best_label = 'B2B software'
    best_count = 0

    for category, keywords in _CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > best_count:
            best_count = count
            best_cat   = category
            best_label = keywords[0].title()

    return best_cat, best_label


def _find_matched_phrases(text_lower: str, phrases: List[str]) -> List[str]:
    return [p for p in phrases if p in text_lower]


def detect_intent(
    text: str,
    company: Optional[str] = None,
    industry: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyse ``text`` for B2B buying intent signals.

    Args:
        text:     Raw text (post body, page excerpt, job posting, etc.)
        company:  Optional company name (boosts context weighting)
        industry: Optional industry string (used for category inference)

    Returns:
        Intent dict — see module docstring for schema.
    """
    if not text:
        return _empty_intent()

    text_lower = text.lower()

    # --- phase 1: phrase matching ---
    high_matches   = _find_matched_phrases(text_lower, _HIGH_INTENT_PHRASES)
    medium_matches = _find_matched_phrases(text_lower, _MEDIUM_INTENT_PHRASES)
    low_matches    = _find_matched_phrases(text_lower, _LOW_INTENT_PHRASES)

    matched_phrases = high_matches + medium_matches + low_matches

    # --- phase 2: buying_intent level ---
    if high_matches:
        buying_intent = 'high'
        base_confidence = 0.85
        reason_phrases  = high_matches[:3]
    elif len(medium_matches) >= 2:
        buying_intent = 'medium'
        base_confidence = 0.60
        reason_phrases  = medium_matches[:3]
    elif medium_matches or low_matches:
        buying_intent = 'low'
        base_confidence = 0.35
        reason_phrases  = (medium_matches or low_matches)[:2]
    else:
        return _empty_intent()

    # --- phase 3: category detection ---
    interest_category, product_interest = _detect_category(text_lower)

    # Industry hint: if we know the industry, prefer the matching category
    if industry:
        industry_lower = industry.lower()
        for cat, keywords in _CATEGORY_KEYWORDS.items():
            if any(kw in industry_lower for kw in keywords):
                interest_category = cat
                product_interest  = keywords[0].title()
                break

    # --- phase 4: confidence adjustment ---
    # More matched phrases → higher confidence (diminishing returns)
    confidence = min(1.0, base_confidence + len(matched_phrases) * 0.02)

    # Company name present → more confident (not anonymous post)
    if company and len(company) > 2:
        confidence = min(1.0, confidence + 0.05)

    intent_reason = (
        f"Detected {buying_intent}-intent signal{'s' if len(reason_phrases) > 1 else ''}: "
        f"{', '.join(repr(p) for p in reason_phrases)}"
    )

    return {
        'product_interest':  product_interest,
        'interest_category': interest_category,
        'buying_intent':     buying_intent,
        'intent_reason':     intent_reason,
        'intent_confidence': round(confidence, 2),
        'matched_phrases':   matched_phrases[:10],   # cap payload size
    }


def _empty_intent() -> Dict[str, Any]:
    return {
        'product_interest':  '',
        'interest_category': '',
        'buying_intent':     'none',
        'intent_reason':     '',
        'intent_confidence': 0.0,
        'matched_phrases':   [],
    }


def intent_quality_boost(intent: Dict[str, Any]) -> float:
    """
    Return a score boost (0–15) to add to a lead's quality score
    based on detected buying intent.  Called by the candidate pipeline.
    """
    level = intent.get('buying_intent', 'none')
    conf  = float(intent.get('intent_confidence', 0.0))
    if level == 'high':
        return 15.0 * conf
    if level == 'medium':
        return 7.0 * conf
    if level == 'low':
        return 3.0 * conf
    return 0.0
