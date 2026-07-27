"""
Lead Candidate Merger
=====================
When the same person surfaces from multiple sources (GitHub + news +
web scrape + Apollo), merge them into one richer record instead of
saving duplicates or losing data.

Algorithm:
  1. Group candidates by email (normalised) — strongest signal.
  2. Within email groups, also group by normalised name+company.
  3. Within each group, apply "best field wins" merge:
       • For each field, pick the value from the highest-reliability source.
       • data_points are merged: all sources contribute metadata.
  4. Track source_count and source_names — used by quality engine to
     give a bonus for multi-source agreement.

Source reliability order (higher = wins a field contest):
  pdl > hunter > clearbit > apollo > crunchbase > github > web > news > reddit

Rules:
  • Never overwrite a verified email (email_verified=True) with an unverified one.
  • Never overwrite a non-empty field with an empty one.
  • LinkedIn URL from a higher-reliability source wins.
  • Phone from any source is kept if valid.
"""

from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Source reliability ranking for field arbitration (higher wins)
_SOURCE_RANK: Dict[str, int] = {
    'pdl':         100,
    'hunter':       90,
    'clearbit':     80,
    'apollo':       78,
    'crunchbase':   75,
    'github':       65,
    'linkedin':     65,
    'web':          55,
    'public_web':   55,
    'news':         50,
    'reddit':       25,
    'twitter':      25,
    'facebook':     25,
    'telegram':     20,
    'unknown':      10,
}

_LEGAL_SUFFIXES = re.compile(
    r'\b(Inc\.?|LLC\.?|Ltd\.?|Corp\.?|Co\.?|GmbH|S\.A\.?|B\.V\.?|'
    r'PLC\.?|AG|SE|SAS|NV|AB|OY|AS|Oy|Pte\.?|Pvt\.?|'
    r'Holdings?|Ventures?|Technologies|Solutions|Services|Systems|'
    r'Group|Labs?|Digital|Global|International)\b\.?$',
    re.IGNORECASE,
)

_GMAIL_DOTS = re.compile(r'(?<=@gmail\.com$)|(?<=@googlemail\.com$)')


def _norm_email(email: str) -> str:
    """Canonical email for grouping: lowercase, remove Gmail dots before @."""
    e = (email or '').strip().lower()
    if not e or '@' not in e:
        return ''
    local, domain = e.rsplit('@', 1)
    if domain in ('gmail.com', 'googlemail.com'):
        local = local.replace('.', '')
    return f"{local}@{domain}"


def _norm_name(name: str) -> str:
    return re.sub(r'\s+', ' ', (name or '').strip().lower())


def _norm_company(company: str) -> str:
    c = re.sub(r'\s+', ' ', (company or '').strip().lower())
    c = _LEGAL_SUFFIXES.sub('', c).strip().rstrip(',.')
    return c


def _source_rank(lead: Dict[str, Any]) -> int:
    src = (lead.get('source') or lead.get('data_points', {}).get('enrichment_source') or 'unknown').lower()
    # Handle composite sources like 'news_techcrunch'
    for key in _SOURCE_RANK:
        if key in src:
            return _SOURCE_RANK[key]
    return _SOURCE_RANK['unknown']


def _is_verified(lead: Dict[str, Any]) -> bool:
    return bool(lead.get('data_points', {}).get('email_verified'))


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------

def _merge_group(group: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge a group of leads representing the same person into one record."""
    if len(group) == 1:
        return _annotate_merged(group[0], group)

    # Sort: highest-reliability first
    ranked = sorted(group, key=_source_rank, reverse=True)

    # Start with the highest-rank lead as the base
    merged = {k: v for k, v in ranked[0].items() if k != 'data_points'}
    merged_dp: Dict[str, Any] = dict(ranked[0].get('data_points') or {})

    # Priority for email: prefer verified over unverified
    verified_leads = [ld for ld in ranked if _is_verified(ld) and ld.get('email')]
    if verified_leads:
        best_email_lead = verified_leads[0]
        merged['email'] = best_email_lead['email']
        merged_dp.update(best_email_lead.get('data_points') or {})

    # Fill empty fields from lower-rank sources
    _scalar_fields = [
        'name', 'email', 'company', 'position', 'industry',
        'website', 'linkedin_url', 'location', 'country', 'city',
        'phone', 'company_size', 'company_size_int',
    ]
    for lead in ranked[1:]:
        for field in _scalar_fields:
            if not merged.get(field) and lead.get(field):
                merged[field] = lead[field]
        # Merge data_points: lower-rank can contribute fields the winner lacks
        for dp_key, dp_val in (lead.get('data_points') or {}).items():
            if dp_key not in merged_dp or not merged_dp[dp_key]:
                merged_dp[dp_key] = dp_val

    # Phone: keep first non-empty across all sources
    for lead in ranked:
        if lead.get('phone') and not merged.get('phone'):
            merged['phone'] = lead['phone']

    return _annotate_merged(merged, group, merged_dp)


def _annotate_merged(
    lead: Dict[str, Any],
    group: List[Dict[str, Any]],
    dp: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Add source_count / source_names metadata to a merged lead."""
    base_dp  = dp if dp is not None else dict(lead.get('data_points') or {})
    sources  = list(dict.fromkeys(
        ld.get('source', 'unknown') for ld in group
    ))
    base_dp['source_count'] = len(group)
    base_dp['source_names'] = sources

    # Multi-source agreement bonus hint for quality engine
    if len(group) >= 3:
        base_dp['multi_source_agreement'] = 'high'
    elif len(group) == 2:
        base_dp['multi_source_agreement'] = 'medium'

    lead = dict(lead)
    lead['data_points'] = base_dp
    return lead


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def _group_candidates(
    candidates: List[Dict[str, Any]]
) -> List[List[Dict[str, Any]]]:
    """
    Group candidates that represent the same person.
    Primary key: normalised email.
    Secondary key: normalised name + company (for email-less leads).
    """
    # Pass 1: bucket by normalised email
    email_groups: Dict[str, List] = {}
    no_email:     List[Dict]      = []

    for lead in candidates:
        email = _norm_email(lead.get('email', ''))
        if email:
            email_groups.setdefault(email, []).append(lead)
        else:
            no_email.append(lead)

    # Build a name+company → email_key index so email-less leads
    # can be merged into an existing email group for the same person.
    nc_to_email_key: Dict[str, str] = {}
    for email_key, grp in email_groups.items():
        for ld in grp:
            n = _norm_name(ld.get('name', ''))
            c = _norm_company(ld.get('company', ''))
            if n and c:
                nc_to_email_key[f"{n}|{c}"] = email_key

    # Pass 2: route no-email leads into email groups or name-only groups
    name_groups: Dict[str, List] = {}
    ungrouped:   List[Dict]      = []

    for lead in no_email:
        n = _norm_name(lead.get('name', ''))
        c = _norm_company(lead.get('company', ''))
        nc_key = f"{n}|{c}" if n and c else ''

        if nc_key and nc_key in nc_to_email_key:
            # Same person already seen with an email — merge them
            email_groups[nc_to_email_key[nc_key]].append(lead)
        elif nc_key:
            name_groups.setdefault(nc_key, []).append(lead)
        else:
            ungrouped.append(lead)

    groups = list(email_groups.values()) + list(name_groups.values())
    groups += [[ld] for ld in ungrouped]
    return groups


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def merge_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge a flat list of raw candidate leads into de-duplicated, enriched records.

    Input:  N leads, possibly many representing the same person from different sources.
    Output: M leads (M ≤ N) where each person appears once, with the richest data.

    Call this BEFORE evaluate_lead_quality() so the quality engine sees the
    best possible data for each person.
    """
    if not candidates:
        return []

    groups  = _group_candidates(candidates)
    merged  = [_merge_group(grp) for grp in groups]

    logger.info(
        f"[Merger] {len(candidates)} candidates → {len(merged)} merged "
        f"({len(candidates) - len(merged)} duplicates collapsed)"
    )
    return merged
