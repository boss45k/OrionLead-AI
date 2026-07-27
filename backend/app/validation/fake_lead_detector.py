"""
Fake Lead Detector
==================
Detects demo, test, placeholder, and synthetic lead data before save.

Returns a FakeLeadResult:
  is_fake:  True if lead is detected as fake/test/synthetic
  reason:   Rule key that triggered (used as rejection_reason in audit log)
  severity: 'hard' = reject outright | 'soft' = downgrade to needs_review

Hard rejects:
  - Fake/reserved emails (test@, demo@, example.com, disposable providers)
  - Demo/test/placeholder company names
  - Placeholder contact names (John Doe, Test Person, lorem ipsum)

Soft downgrades:
  - Suspiciously minimal company names that aren't caught by anti_junk
  - All-numeric or all-symbol company names
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict

# ── Fake name patterns ────────────────────────────────────────────────────────

_FAKE_NAME_RE = [
    re.compile(p, re.I) for p in [
        # Explicit test/demo prefix names
        r'^(test|demo|sample|example|placeholder|fake|dummy|temp|null|none)\b',
        r'\b(test lead|demo lead|sample lead|fake lead|dummy lead)\b',
        # Universal legal placeholder names (RFC/legal standard — NOT real people names)
        r'^john\s+doe$|^jane\s+doe$',
        # Bot-generated user IDs masquerading as names
        r'^(user\d+|admin\d+|test\d+|demo\d+|lead\d+)$',
        r'lorem\s+ipsum',
        r'^test\s+person$|^sample\s+person$|^demo\s+person$',
    ]
]

# ── Fake company patterns ─────────────────────────────────────────────────────

_FAKE_COMPANY_RE = [
    re.compile(p, re.I) for p in [
        # Explicit placeholder names (including Hunter.io / API demo data)
        r'^(test company|demo company|sample company|example corp|fake corp|acme corp)$',
        r'^acme\s+(inc\.?|corp\.?|corporation|company|co\.?|ltd\.?)$',
        r'^(example company|example business|sample business|demo business)$',
        r'^(widget corp|widget company|widgets inc|widgets corp)$',
        r'^(my company|your company|client company|company name here|company name)$',
        r'^(foo|bar|baz|foobar|test123|demo123|sample123)(\s+\w+)?$',
        # Testing / demo prefix
        r'^\s*(test|demo|sample|fake|dummy)\s+(company|corp|inc|llc|ltd|business|firm)\b',
        # Common data-entry filler
        r'^(n/?a|na|tbd|tba|xxx|yyy|zzz|aaa|bbb)$',
        # Placeholder brackets
        r'^\[?(company name|your company|insert company)\]?$',
    ]
]

# ── Fake / disposable email patterns ─────────────────────────────────────────

_FAKE_EMAIL_RE = [
    re.compile(p, re.I) for p in [
        # Explicit test prefixes
        r'^(test|demo|sample|fake|noreply|no[-_]reply|donotreply|do[-_]not[-_]reply|null|admin123|user123|lead123|contact123)@',
        # Reserved domains (RFC 2606)
        r'@(example|test|invalid|localhost)\.(com|org|net|io|local)$',
        # Disposable / throwaway providers
        r'@(mailinator|guerrillamail|throwam|tempmail|yopmail|sharklasers|'
        r'guerrillamailblock|trashmail|dispostable|fakeinbox|'
        r'maildrop|spamgourmet|spamex|mailnesia|discard\.email|mailnull)\.',
        # Numeric-only local part (bot-generated)
        r'^[0-9]+@',
    ]
]


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class FakeLeadResult:
    is_fake: bool
    reason: str = ""
    severity: str = "hard"  # 'hard' = reject, 'soft' = needs_review


# ── Detector ──────────────────────────────────────────────────────────────────

def detect_fake_lead(lead: Dict[str, Any]) -> FakeLeadResult:
    """
    Check a lead dict for fake / test / placeholder data.

    Args:
        lead: Dict with keys name, company, email (all optional).

    Returns:
        FakeLeadResult — check .is_fake before using the lead.
    """
    name    = (lead.get("name")    or "").strip()
    company = (lead.get("company") or "").strip()
    email   = (lead.get("email")   or "").strip().lower()

    # ── Fake email (hard reject) ──────────────────────────────────────────────
    if email:
        for pat in _FAKE_EMAIL_RE:
            if pat.search(email):
                return FakeLeadResult(True, "fake_email_detected", "hard")

    # ── Fake contact name (hard reject) ──────────────────────────────────────
    if name:
        for pat in _FAKE_NAME_RE:
            if pat.search(name):
                return FakeLeadResult(True, "fake_name_detected", "hard")

    # ── Fake company name (hard reject) ──────────────────────────────────────
    if company:
        for pat in _FAKE_COMPANY_RE:
            if pat.search(company):
                return FakeLeadResult(True, "fake_company_detected", "hard")

    # ── Suspiciously minimal company (soft downgrade) ─────────────────────────
    # Catches "X", "AB", "12", etc. not already caught by anti_junk length check
    co_alpha = re.sub(r"[^a-zA-Z]", "", company)
    if company and len(co_alpha) < 2 and len(company) < 4:
        return FakeLeadResult(True, "company_name_suspicious", "soft")

    return FakeLeadResult(False)
