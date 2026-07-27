"""
Relationship Mapper
===================
Maps raw lead data into graph entities and infers implicit relationships
that are not directly stated in the lead dict.

Examples of inferred relationships:
  - email local-part matches person name → high-confidence identity
  - two leads share same domain → same company, different contacts
  - LinkedIn slug matches company name → corroborate entity
  - Multiple people from same company → company is real and active

All inference is heuristic — no external API calls.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse


# ── Name ↔ email matching ─────────────────────────────────────────────────────

def _normalize_for_match(s: str) -> str:
    """Lowercase, remove non-alpha, collapse whitespace."""
    return re.sub(r"[^a-z]", "", s.lower())


def email_matches_name(email: str, name: str) -> Tuple[bool, float]:
    """
    Check whether an email address plausibly belongs to a named person.

    Returns (matches, confidence) where confidence is 0.0-1.0.

    Examples:
      john.smith@acme.com + "John Smith" → (True, 0.95)
      jsmith@acme.com    + "John Smith" → (True, 0.75)
      info@acme.com      + "John Smith" → (False, 0.0)
    """
    if not email or not name or "@" not in email:
        return False, 0.0

    local = email.split("@")[0].lower()
    # Generic addresses — no personal match possible
    _GENERIC = frozenset({
        "info", "contact", "hello", "support", "sales", "admin",
        "team", "marketing", "office", "hr", "press", "media",
        "enquiries", "enquiry", "noreply", "no-reply",
    })
    if local in _GENERIC:
        return False, 0.0

    parts = name.strip().lower().split()
    if len(parts) < 2:
        return False, 0.0

    first, last = _normalize_for_match(parts[0]), _normalize_for_match(parts[-1])
    local_clean = re.sub(r"[^a-z]", "", local)

    # Exact "firstlast" or "lastfirst"
    if local_clean == first + last or local_clean == last + first:
        return True, 0.95

    # first.last or last.first with separator
    sep_local = re.sub(r"[._\-]", "", local_clean)
    if sep_local == first + last:
        return True, 0.95

    # first initial + last (jsmith)
    if len(first) > 0 and local_clean == first[0] + last:
        return True, 0.80

    # First name only
    if local_clean == first:
        return True, 0.55

    # Fuzzy match
    ratio = SequenceMatcher(None, local_clean, first + last).ratio()
    if ratio >= 0.80:
        return True, ratio * 0.85

    return False, 0.0


class RelationshipMapper:
    """
    Infers and returns implicit relationships for a lead before graph insertion.
    """

    def map(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Augment lead's data_points with inferred relationship metadata.

        Returns the (possibly modified) lead dict.
        """
        lead = dict(lead)
        dp   = dict(lead.get("data_points") or {})

        email = (lead.get("email") or "").strip().lower()
        name  = (lead.get("name")  or "").strip()

        # ── 1. Email ↔ name corroboration ─────────────────────────────────
        if email and name:
            matches, confidence = email_matches_name(email, name)
            dp["email_name_match"]       = matches
            dp["email_name_confidence"]  = round(confidence, 3)

        # ── 2. Domain extraction ──────────────────────────────────────────
        domain = ""
        website = (lead.get("website") or "").strip()
        if website:
            try:
                domain = urlparse(website).netloc.lower().replace("www.", "")
            except Exception:
                pass
        if not domain and "@" in email:
            domain = email.split("@")[1]

        if domain:
            dp["resolved_domain"] = domain

            # Check if email domain matches website domain
            if email and "@" in email:
                email_domain = email.split("@")[1].lower()
                dp["email_domain_matches_website"] = (email_domain == domain)

        # ── 3. LinkedIn slug → company corroboration ──────────────────────
        linkedin = (lead.get("linkedin_url") or "").strip()
        if linkedin:
            company = (lead.get("company") or "").strip().lower()
            company_slug = re.sub(r"[^a-z0-9]", "", company)
            li_slug = re.sub(r"[^a-z0-9]", "", linkedin.lower().split("/")[-1].rstrip("/"))
            if company_slug and li_slug and (
                company_slug in li_slug or li_slug in company_slug
            ):
                dp["linkedin_company_corroborated"] = True

        lead["data_points"] = dp
        return lead

    def get_domain(self, lead: Dict[str, Any]) -> str:
        return (lead.get("data_points") or {}).get("resolved_domain", "")
