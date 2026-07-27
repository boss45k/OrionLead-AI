"""
Fast Intelligence Check
=======================
Instant (no HTTP) gate that runs anti-junk + business classification
on a lead dict.  Used inside per-lead loops in all three collectors
(interest, social, web) to drop junk BEFORE spending Hunter/enrichment
API credits.

Usage
-----
    from app.intelligence.fast_check import fast_intelligence_check

    ok, reason = fast_intelligence_check(lead)
    if not ok:
        continue   # skip this lead — it's a directory, NGO, parked, etc.

Returns
-------
    (passed: bool, rejection_reason: str)
    reason is '' when passed is True.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Module-level singletons (imported lazily so the module loads fast)
_anti_junk_engine = None
_business_classifier = None


def _get_anti_junk():
    global _anti_junk_engine
    if _anti_junk_engine is None:
        from app.intelligence.anti_junk_engine import get_anti_junk_engine
        _anti_junk_engine = get_anti_junk_engine()
    return _anti_junk_engine


def _get_classifier():
    global _business_classifier
    if _business_classifier is None:
        from app.intelligence.business_classifier import get_business_classifier
        _business_classifier = get_business_classifier()
    return _business_classifier


def fast_intelligence_check(
    lead: Dict[str, Any],
    allowed_types: Optional[frozenset] = None,
    source_url: str = "",
) -> Tuple[bool, str]:
    """
    Instant company intelligence gate — no network calls.

    Runs:
      1. Anti-junk engine  (name/domain/URL hard rules)
      2. Business classifier  (NGO / university / government / directory hard rejects)
      3. ICP type check  (is the company in the allowed business types?)

    Args:
        lead:          Lead dict with at minimum: name, company, email, website/domain.
        allowed_types: frozenset of allowed business_type values.
                       None = skip ICP check (only hard rejects enforced).
        source_url:    URL the lead was scraped from (for aggregator detection).

    Returns:
        (True, '') if passed
        (False, rejection_reason) if rejected
    """
    try:
        # ── Gate 1: Anti-junk (name / URL / domain / keyword rules) ───────────
        junk = _get_anti_junk().check(lead, source_url=source_url)
        if not junk.passed:
            logger.debug(
                "[fast_check] REJECT '%s' anti_junk=%s",
                lead.get("company") or lead.get("name"), junk.rejection_reason,
            )
            return False, junk.rejection_reason

        # ── Gate 2: Business classifier (hard-reject types only) ───────────────
        clf = _get_classifier()
        dp = lead.get("data_points") or {}
        page_text = dp.get("snippet", "") + " " + dp.get("description", "")
        classification = clf.classify(lead, page_text=page_text)

        if classification.is_hard_reject:
            reason = f"business_type_{classification.business_type}"
            logger.debug(
                "[fast_check] REJECT '%s' hard_reject=%s",
                lead.get("company") or lead.get("name"), reason,
            )
            return False, reason

        # ── Gate 3: ICP type check (optional) ────────────────────────────────
        if allowed_types and not clf.is_icp_match(classification, allowed_types):
            reason = f"not_in_icp ({classification.business_type})"
            logger.debug(
                "[fast_check] REJECT '%s' icp_miss=%s",
                lead.get("company") or lead.get("name"), reason,
            )
            return False, reason

        return True, ""

    except Exception as exc:
        # Fail-open: never block a lead on a check error
        logger.debug("[fast_check] error (fail-open): %s", exc)
        return True, ""


def batch_fast_check(
    leads: list,
    allowed_types: Optional[frozenset] = None,
    source_url: str = "",
) -> Tuple[list, int]:
    """
    Run fast_intelligence_check on a batch of leads.

    Returns (passed_leads, n_rejected).
    """
    passed = []
    rejected = 0
    for lead in leads:
        ok, reason = fast_intelligence_check(
            lead, allowed_types=allowed_types, source_url=source_url,
        )
        if ok:
            passed.append(lead)
        else:
            rejected += 1
            logger.debug("[fast_check] batch reject: %s — %s",
                         lead.get("company") or lead.get("name"), reason)
    return passed, rejected
