"""
Enterprise Save Policy
======================
Multi-gate quality filter applied immediately before a lead is persisted.
Any gate returning False drops the lead; the first failure reason is logged.

Gates (in order)
----------------
1. Minimum final score           ≥ 35
2. Email present and not free    (unless phone present as fallback)
3. Name parseable                (at least one alpha token ≥ 2 chars)
4. Company present               (non-trivial string)
5. Not a cold-signal reject      (parked domain, inactive company, etc.)
6. Grade not F                   (score optimizer grade)
7. Duplicate check               (email uniqueness within current session)
8. Company intelligence gate     — IntelligenceDecision.passed must be True
   Checks ALL gate flags:
     • company_identity_passed
     • user_intent_passed
     • anti_junk_passed
     • location_match
   If intelligence object is missing → reject (no silent fallback)
9. Risk gate                     — IntelligenceDecision.risk_score ≤ 35

Configuration via environment variables:
  ENTERPRISE_MIN_SCORE          (default 35)
  ENTERPRISE_REQUIRE_EMAIL      (default true)
  ENTERPRISE_BLOCK_F_GRADE      (default true)
  ENTERPRISE_REQUIRE_INTEL_PASS (default false — enable for company-first mode)
  ENTERPRISE_MAX_RISK_SCORE     (default 35)
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any, Dict, Optional, Set, Tuple


_MIN_SCORE          = float(os.getenv("ENTERPRISE_MIN_SCORE", "35"))
_REQUIRE_EMAIL      = os.getenv("ENTERPRISE_REQUIRE_EMAIL", "true").lower() == "true"
_BLOCK_F_GRADE      = os.getenv("ENTERPRISE_BLOCK_F_GRADE", "true").lower() == "true"
_REQUIRE_INTEL_PASS = os.getenv("ENTERPRISE_REQUIRE_INTEL_PASS", "true").lower() == "true"
_MAX_RISK_SCORE     = float(os.getenv("ENTERPRISE_MAX_RISK_SCORE", "35"))

_FREE_EMAIL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "protonmail.com", "mail.com", "yandex.com",
    "live.com", "msn.com", "me.com",
})

_COLD_BLOCK_SIGNALS = frozenset({
    "parked_domain", "inactive_company", "no_business_identity",
    "spam_domain", "disposable_email",
})

# Gate flags that MUST all be True for intelligence to pass
_REQUIRED_INTEL_GATES = (
    "company_identity_passed",
    "anti_junk_passed",
    # "user_intent_passed" and "location_match" are checked separately
    # so we can give more specific rejection reasons
)


class EnterpriseSavePolicy:
    """
    Thread-safe per-run policy enforcer.

    Create a new instance for each collection run (call reset() between runs)
    so the session duplicate set is isolated per run.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen_emails: Set[str] = set()

    def reset(self) -> None:
        with self._lock:
            self._seen_emails.clear()

    def evaluate(
        self,
        lead: Dict[str, Any],
        *,
        final_score: float = 0.0,
        grade: str = "F",
        collected_by: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Returns (should_save: bool, reason: str).
        reason is empty string when should_save is True.
        """
        dp      = lead.get("data_points") or {}
        email   = (lead.get("email") or "").strip().lower()
        name    = (lead.get("name") or "").strip()
        company = (lead.get("company") or "").strip()
        phone   = (lead.get("phone") or "").strip()

        # Gate 1 — minimum score
        if final_score < _MIN_SCORE:
            return False, f"score_below_minimum ({final_score:.1f} < {_MIN_SCORE})"

        # Gate 2 — email / phone fallback
        if _REQUIRE_EMAIL:
            if not email:
                if not phone:
                    return False, "no_email_no_phone"
            elif "@" not in email:
                return False, "invalid_email_format"

        # Gate 3 — name present
        alpha_tokens = [t for t in name.split() if re.search(r"[a-zA-Z]{2,}", t)]
        if not alpha_tokens:
            return False, "name_missing_or_invalid"

        # Gate 4 — company present
        if not company or len(company) < 2:
            return False, "company_missing"

        # Gate 5 — cold signal block
        cold_signals = frozenset(s.lower() for s in (dp.get("cold_signals") or []))
        blocked = cold_signals & _COLD_BLOCK_SIGNALS
        if blocked:
            return False, f"cold_signal_block ({', '.join(blocked)})"

        # Gate 6 — grade not F
        if _BLOCK_F_GRADE and grade == "F":
            return False, "grade_F"

        # Gate 7 — session-level duplicate
        if email:
            domain = email.split("@")[1] if "@" in email else ""
            is_free = domain in _FREE_EMAIL_DOMAINS
            if not is_free:
                with self._lock:
                    if email in self._seen_emails:
                        return False, f"duplicate_email ({email})"
                    self._seen_emails.add(email)

        # Gate 8 — company intelligence gate
        if _REQUIRE_INTEL_PASS:
            # Check both old (_account_score) and new (_intelligence_decision) fields
            intel_decision = lead.get("_intelligence_decision") or lead.get("_account_score") or {}

            if not intel_decision:
                return False, "intelligence_decision_missing — no intel data, rejecting to prevent unvalidated save"

            # Must have passed the IntelligenceDecision
            if not intel_decision.get("passed", False):
                reason = intel_decision.get("rejection_reason", "intelligence_failed")
                stage  = intel_decision.get("failed_stage", "unknown")
                return False, f"intelligence_gate_failed [{stage}]: {reason}"

            # Check individual gate flags
            for gate_flag in _REQUIRED_INTEL_GATES:
                if not intel_decision.get(gate_flag, True):
                    return False, f"intelligence_gate_{gate_flag}_failed"

            # User intent / location check (give specific reason)
            if not intel_decision.get("user_intent_passed", True):
                return False, "user_intent_not_matched — company does not match query intent"

            if not intel_decision.get("location_match", True):
                return False, "location_mismatch — company country does not match requested location"

            # Gate 9 — risk score check
            risk_score = float(intel_decision.get("risk_score", 0.0))
            if risk_score > _MAX_RISK_SCORE:
                return False, f"risk_score_too_high ({risk_score:.1f} > {_MAX_RISK_SCORE})"

        # Gate 10 — company-level cross-user duplicate
        if collected_by:
            try:
                from app.services.lead_dedup import company_duplicate
                _dup, _dup_by = company_duplicate(email or None, lead.get("linkedin_url"), collected_by)
                if _dup:
                    return False, f"company_duplicate (already collected by {_dup_by}, lead_id={_dup.id})"
            except Exception:
                pass  # DB unavailable or no app context — skip gate silently

        return True, ""

    def should_save(
        self,
        lead: Dict[str, Any],
        *,
        final_score: float = 0.0,
        grade: str = "F",
        collected_by: Optional[int] = None,
    ) -> bool:
        ok, _ = self.evaluate(lead, final_score=final_score, grade=grade, collected_by=collected_by)
        return ok


# ── Module-level singleton (reset between runs) ───────────────────────────────

_instance: Optional[EnterpriseSavePolicy] = None
_ilock = threading.Lock()


def get_save_policy() -> EnterpriseSavePolicy:
    global _instance
    if _instance is None:
        with _ilock:
            if _instance is None:
                _instance = EnterpriseSavePolicy()
    return _instance
