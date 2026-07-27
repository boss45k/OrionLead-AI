"""
Account Scorer
==============
Computes the final company-level IntelligenceDecision used as the SAVE gate.

Formula
-------
    raw_score =
        fit_score        * 0.30   (ICP match + business type + website signals)
      + intent_score     * 0.30   (pricing, demo, hiring sales, CRM tools)
      + growth_score     * 0.20   (hiring, funding, activity)
      + confidence_score * 0.20   (data completeness, cross-source agreement)

    final_score = raw_score - (risk_score * 0.25)

Hard pass gates (ALL must pass — checked in order):
  1. company_identity_passed   — not a person-name / URL / generic company
  2. anti_junk_passed          — junk_score ≤ 30
  3. business_type_allowed     — business type is in the ICP allow-list
  4. user_intent_passed        — country + industry match user query
  5. final_score ≥ 70
  6. confidence_score ≥ 70
  7. risk_score ≤ 35

Risk signals that increase risk_score (0-100):
  +20 — missing domain
  +15 — website not reachable
  +20 — unknown country
  +15 — source-country disagreement (e.g. Apollo=Nigeria, website=Turkey)
  +10 — generic company name (soft signal from anti-junk)
  +15 — no product page evidence
  +10 — no contact evidence
  +15 — social-only lead (no real website)
  +15 — scraped from directory/listing
  +10 — free email only

Output
------
IntelligenceDecision (from app.intelligence.models) with:
  passed, final_score, confidence_score, risk_score,
  fit_score, intent_score, growth_score,
  company_identity_passed, user_intent_passed, anti_junk_passed,
  business_type_allowed, location_match,
  rejection_reason, failed_stage, decision_log,
  evidence, why_saved, recommended_outreach_angle,
  top_positive_signals, top_risk_signals
"""

from __future__ import annotations

import logging
from typing import Any, Dict, FrozenSet, List, Optional

from app.intelligence.models import EvidenceItem, IntelligenceDecision

logger = logging.getLogger(__name__)

# ── Thresholds (overridable via env vars) ────────────────────────────────────

import os as _os
_MIN_FINAL_SCORE = float(_os.getenv("INTELLIGENCE_MIN_FINAL_SCORE", "60"))
_MIN_CONFIDENCE  = float(_os.getenv("INTELLIGENCE_MIN_CONFIDENCE",  "50"))
_MAX_RISK_SCORE  = float(_os.getenv("INTELLIGENCE_MAX_RISK_SCORE",  "40"))
_MAX_JUNK_SCORE  = 30

_WEIGHTS = {
    "fit":        0.30,
    "intent":     0.30,
    "growth":     0.20,
    "confidence": 0.20,
    "risk_penalty": 0.25,  # subtracted from raw_score
}


# ── Scorer ────────────────────────────────────────────────────────────────────

class AccountScorer:
    """
    Combines all intelligence sub-scores into a final account-level gate.
    Returns IntelligenceDecision — never the old AccountScoreResult.

    Usage:
        scorer = AccountScorer()
        decision = scorer.score(
            lead=lead_dict,
            anti_junk=anti_junk_result,
            classification=biz_class,
            growth=growth_result,
            website_audit=audit_result,
            intent=intent_dict,
            allowed_types=frozenset({'b2b_saas'}),
            user_intent_contract=contract,
        )
    """

    def score(
        self,
        lead:            Dict[str, Any],
        *,
        anti_junk:       Optional[Any] = None,        # AntiJunkResult
        classification:  Optional[Any] = None,        # BusinessClassification
        growth:          Optional[Any] = None,         # GrowthResult
        website_audit:   Optional[Any] = None,         # WebsiteAuditResult
        intel_profile:   Optional[Any] = None,         # CompanyProfile (legacy)
        intent:          Optional[Dict[str, Any]] = None,
        allowed_types:   Optional[FrozenSet[str]] = None,
        user_intent_contract: Optional[Any] = None,   # IntentContract
    ) -> IntelligenceDecision:

        decision = IntelligenceDecision()
        log      = decision.decision_log
        evidence = decision.evidence
        positives: List[str] = []
        risks:     List[str] = []

        company = (lead.get("company") or lead.get("name") or "").strip()

        def _add_ev(source, fld, value, conf, reason):
            evidence.append(EvidenceItem(source, fld, str(value), conf, reason))

        # ══ Gate 1: Company identity ══════════════════════════════════════════
        # Check that the company is a real entity, not a person name / URL / generic
        identity_ok, identity_reason = self._check_company_identity(lead, anti_junk)
        decision.company_identity_passed = identity_ok
        _add_ev(
            "anti_junk", "company_identity", company,
            0.9 if identity_ok else 0.1,
            identity_reason,
        )
        if not identity_ok:
            log.append(f"GATE 1 FAIL: company_identity — {identity_reason}")
            return decision.reject(
                f"company_identity_failed ({identity_reason})",
                "company_identity",
                identity_reason,
            )
        log.append(f"Gate 1 PASS: company_identity — {identity_reason}")

        # ══ Gate 2: Anti-junk score ═══════════════════════════════════════════
        if anti_junk is not None and not anti_junk.passed:
            decision.anti_junk_passed = False
            _add_ev("anti_junk", "junk_check", anti_junk.rejection_reason, 0.95,
                    f"Hard-reject: {anti_junk.rejection_reason}")
            log.append(f"GATE 2 FAIL: anti_junk — {anti_junk.rejection_reason}")
            decision.top_risk_signals = list(anti_junk.junk_signals)
            return decision.reject(anti_junk.rejection_reason, "anti_junk")

        if anti_junk is not None:
            junk_score = anti_junk.junk_score
            if junk_score > _MAX_JUNK_SCORE:
                decision.anti_junk_passed = False
                _add_ev("anti_junk", "junk_score", str(junk_score), 0.9,
                        f"Junk score {junk_score} > max {_MAX_JUNK_SCORE}")
                log.append(f"GATE 2 FAIL: junk_score={junk_score} > {_MAX_JUNK_SCORE}")
                decision.top_risk_signals = list(anti_junk.junk_signals)
                return decision.reject(
                    f"high_junk_score ({junk_score})",
                    "anti_junk_threshold",
                    f"junk_score={junk_score}",
                )
            decision.anti_junk_passed = True
            _add_ev("anti_junk", "junk_score", str(junk_score), 0.9,
                    f"Junk score {junk_score} ≤ {_MAX_JUNK_SCORE} — clean")
            if anti_junk.junk_signals:
                risks.extend(anti_junk.junk_signals)
            log.append(f"Gate 2 PASS: junk_score={junk_score}")
        else:
            decision.anti_junk_passed = True
            log.append("Gate 2 PASS: anti_junk not run — allowed")

        # ══ Gate 3: Business type in ICP ══════════════════════════════════════
        if classification is not None:
            if classification.is_hard_reject:
                decision.business_type_allowed = False
                _add_ev("business_classifier", "business_type",
                        classification.business_type, 0.95,
                        f"Hard-reject business type: {classification.business_type}")
                log.append(f"GATE 3 FAIL: hard-reject type={classification.business_type}")
                return decision.reject(
                    f"business_type_{classification.business_type}",
                    "business_classifier",
                    f"type={classification.business_type} is hard-rejected",
                )

            from app.intelligence.business_classifier import BusinessClassifier
            icp_match = BusinessClassifier().is_icp_match(classification, allowed_types)
            decision.business_type_allowed = icp_match
            _add_ev("business_classifier", "business_type",
                    classification.business_type,
                    classification.confidence,
                    f"type={classification.business_type} {'in' if icp_match else 'NOT in'} ICP")
            if not icp_match:
                log.append(f"GATE 3 FAIL: {classification.business_type} not in ICP")
                # Compute score anyway so balanced_intelligence override can evaluate it
                _f = self._compute_fit(lead, classification, website_audit, allowed_types)
                _i = self._compute_intent(intent, website_audit, growth)
                _g = growth.growth_score if growth else 0.0
                _c = self._compute_confidence(lead, website_audit, intel_profile, classification)
                _r = self._compute_risk(lead, anti_junk, website_audit, classification, intent)
                _raw = (_f * _WEIGHTS["fit"] + _i * _WEIGHTS["intent"] +
                        _g * _WEIGHTS["growth"] + _c * _WEIGHTS["confidence"])
                decision.final_score = round(max(0.0, _raw - _r * _WEIGHTS["risk_penalty"]), 1)
                decision.fit_score = _f; decision.intent_score = _i
                decision.growth_score = _g; decision.confidence_score = _c
                decision.risk_score = _r
                return decision.reject(
                    f"business_type_not_in_icp ({classification.business_type})",
                    "icp_check",
                    f"type={classification.business_type}",
                )
            positives.append(f"icp_match ({classification.business_type})")
            log.append(f"Gate 3 PASS: type={classification.business_type} in ICP")
        else:
            decision.business_type_allowed = True
            log.append("Gate 3 PASS: classifier not run")

        # ══ Gate 4: User intent match (country + industry) ═══════════════════
        if user_intent_contract is not None:
            try:
                from app.intelligence.user_intent_contract import get_intent_contract_engine
                engine = get_intent_contract_engine()
                passed_intent, intent_reason, intent_conf, intent_evidence = engine.validate(
                    lead,
                    user_intent_contract,
                    website_audit=website_audit,
                    classification=classification,
                )
                evidence.extend(intent_evidence)
                decision.user_intent_passed = passed_intent
                decision.location_match = passed_intent  # location is part of intent

                if not passed_intent:
                    log.append(f"GATE 4 FAIL: user_intent — {intent_reason}")
                    return decision.reject(
                        intent_reason,
                        "user_intent_check",
                        intent_reason,
                    )
                positives.append("user_intent_match")
                log.append(f"Gate 4 PASS: user_intent (conf={intent_conf:.2f})")
            except Exception as ie:
                logger.debug("[account_scorer] intent contract validation error: %s", ie)
                decision.user_intent_passed = True
                log.append("Gate 4 PASS: intent check skipped (error)")
        else:
            decision.user_intent_passed = True
            log.append("Gate 4 PASS: no intent contract — unrestricted")

        # ══ Compute component scores ══════════════════════════════════════════

        fit_score        = self._compute_fit(lead, classification, website_audit, allowed_types)
        intent_score     = self._compute_intent(intent, website_audit, growth)
        growth_score_val = growth.growth_score if growth else 0.0
        confidence_score = self._compute_confidence(lead, website_audit, intel_profile, classification)
        risk_score       = self._compute_risk(lead, anti_junk, website_audit, classification, intent)

        decision.fit_score        = fit_score
        decision.intent_score     = intent_score
        decision.growth_score     = growth_score_val
        decision.confidence_score = confidence_score
        decision.risk_score       = risk_score

        raw_score   = (
            fit_score        * _WEIGHTS["fit"] +
            intent_score     * _WEIGHTS["intent"] +
            growth_score_val * _WEIGHTS["growth"] +
            confidence_score * _WEIGHTS["confidence"]
        )
        final_score = max(0.0, raw_score - risk_score * _WEIGHTS["risk_penalty"])
        decision.final_score = round(final_score, 1)

        _add_ev("account_scorer", "score_calculation",
                f"fit={fit_score:.1f} intent={intent_score:.1f} "
                f"growth={growth_score_val:.1f} conf={confidence_score:.1f} "
                f"risk={risk_score:.1f} → final={final_score:.1f}",
                0.95,
                f"raw={raw_score:.1f} - risk_penalty={risk_score * _WEIGHTS['risk_penalty']:.1f} = {final_score:.1f}")
        log.append(
            f"Scores — fit={fit_score:.1f} intent={intent_score:.1f} "
            f"growth={growth_score_val:.1f} conf={confidence_score:.1f} "
            f"risk={risk_score:.1f} → final={final_score:.1f}"
        )

        # ══ Gate 5: final_score ≥ threshold ══════════════════════════════════
        if final_score < _MIN_FINAL_SCORE:
            log.append(f"GATE 5 FAIL: final_score={final_score:.1f} < {_MIN_FINAL_SCORE}")
            return decision.reject(
                f"final_score_below_threshold ({final_score:.1f} < {_MIN_FINAL_SCORE})",
                "account_score",
                f"final={final_score:.1f}",
            )
        log.append(f"Gate 5 PASS: final_score={final_score:.1f}")

        # ══ Gate 6: confidence_score ≥ threshold ═════════════════════════════
        if confidence_score < _MIN_CONFIDENCE:
            log.append(f"GATE 6 FAIL: confidence={confidence_score:.1f} < {_MIN_CONFIDENCE}")
            return decision.reject(
                f"low_confidence ({confidence_score:.1f} < {_MIN_CONFIDENCE})",
                "data_confidence",
                f"confidence={confidence_score:.1f}",
            )
        log.append(f"Gate 6 PASS: confidence={confidence_score:.1f}")

        # ══ Gate 7: risk_score ≤ ceiling ═════════════════════════════════════
        if risk_score > _MAX_RISK_SCORE:
            log.append(f"GATE 7 FAIL: risk_score={risk_score:.1f} > {_MAX_RISK_SCORE}")
            decision.top_risk_signals = risks[:5]
            return decision.reject(
                f"risk_too_high ({risk_score:.1f} > {_MAX_RISK_SCORE})",
                "risk_gate",
                f"risk={risk_score:.1f}",
            )
        log.append(f"Gate 7 PASS: risk_score={risk_score:.1f}")

        # ══ All gates passed ══════════════════════════════════════════════════
        decision.passed = True
        log.append("PASSED all 7 gates")

        # Collect positive signals for explainability
        if growth is not None:
            positives.extend(growth.growth_signals[:3])
        if website_audit is not None:
            positives.extend(website_audit.trust_signals[:3])
        if intel_profile is not None:
            positives.extend((getattr(intel_profile, "hot_signals", None) or [])[:2])

        decision.top_positive_signals = positives[:8]
        decision.top_risk_signals     = risks[:5]
        decision.why_saved            = self._build_why_saved(decision, company)
        decision.recommended_outreach_angle = self._recommend_angle(
            intent, growth, classification, website_audit,
        )

        # Confidence sub-score breakdown for UI display
        decision.confidence_breakdown = {
            "identity": self._identity_confidence(lead, anti_junk),
            "company":  round(fit_score, 1),
            "email":    self._email_confidence(lead, website_audit),
            "source":   self._source_confidence(lead, anti_junk),
            "intent":   round(intent_score, 1),
        }

        logger.info(
            "[account_scorer] %s — PASS final=%.1f fit=%.1f intent=%.1f "
            "growth=%.1f conf=%.1f risk=%.1f",
            company, final_score, fit_score, intent_score,
            growth_score_val, confidence_score, risk_score,
        )
        return decision

    # ------------------------------------------------------------------
    # Company identity gate
    # ------------------------------------------------------------------

    @staticmethod
    def _check_company_identity(
        lead: Dict[str, Any],
        anti_junk: Optional[Any],
    ) -> tuple:
        """
        Returns (passed: bool, reason: str).
        Checks that the company has a real, non-person business identity.
        """
        company = (lead.get("company") or lead.get("name") or "").strip()

        if not company:
            return False, "company_name_empty"

        if len(company) < 2:
            return False, f"company_name_too_short ({len(company)} chars)"

        # If anti-junk already failed with identity-related reasons, honour that
        if anti_junk and not anti_junk.passed:
            identity_reasons = {
                "company_is_person_name", "company_name_too_short",
                "company_name_generic", "name_is_url", "name_is_social_handle",
            }
            if anti_junk.rejection_reason in identity_reasons:
                return False, anti_junk.rejection_reason

        # Check if company name looks like a person name (redundant safety check)
        from app.intelligence.anti_junk_engine import AntiJunkEngine
        if AntiJunkEngine._is_person_name(company):
            return False, f"company_is_person_name ({company})"

        return True, f"company_name_valid ({company})"

    # ------------------------------------------------------------------
    # Component score calculators
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_fit(
        lead:          Dict[str, Any],
        classification: Optional[Any],
        website_audit:  Optional[Any],
        allowed_types:  Optional[FrozenSet[str]],
    ) -> float:
        score = 35.0  # base for having a company + domain

        if classification:
            if not classification.is_hard_reject:
                score += 20.0
            score += classification.confidence * 20.0

        if website_audit:
            if website_audit.business_model == "b2b":
                score += 15.0
            elif website_audit.business_model == "both":
                score += 7.0
            if website_audit.saas_signals:
                score += min(10.0, len(website_audit.saas_signals) * 3.0)

        dp = lead.get("data_points") or {}
        if dp.get("is_b2b"):
            score += 10.0
        if lead.get("linkedin_url"):
            score += 5.0

        return min(100.0, score)

    @staticmethod
    def _compute_intent(
        intent:        Optional[Dict[str, Any]],
        website_audit: Optional[Any],
        growth:        Optional[Any],
    ) -> float:
        score = 15.0  # base — company exists at all

        if intent:
            level = intent.get("buying_intent", "none")
            score += {"high": 50.0, "medium": 30.0, "low": 10.0, "none": 0.0}.get(level, 0.0)
            score += float(intent.get("intent_confidence", 0.0)) * 15.0

        if website_audit:
            if website_audit.pricing_exists:
                score += 12.0
            if website_audit.demo_or_trial_exists:
                score += 10.0
            if website_audit.signup_exists:
                score += 8.0
            # CRM / sales tooling = strong intent signal
            saas_tools = {"HubSpot", "Salesforce", "Intercom", "Drift", "Calendly"}
            if any(t in website_audit.tech_stack_hints for t in saas_tools):
                score += 8.0

        if growth and growth.hiring_detected:
            score += 10.0

        return min(100.0, score)

    @staticmethod
    def _compute_confidence(
        lead:          Dict[str, Any],
        website_audit: Optional[Any],
        intel_profile: Optional[Any],
        classification: Optional[Any],
    ) -> float:
        score = 0.0
        sources = 0

        # Field completeness — each present field adds up
        field_weights = {
            "company": 8.0, "website": 8.0, "domain": 6.0,
            "email": 7.0,   "phone": 5.0,   "location": 5.0,
            "country": 5.0, "industry": 4.0, "linkedin_url": 4.0,
        }
        for fld, weight in field_weights.items():
            if lead.get(fld):
                score += weight

        sources += 1

        # Website audit
        if website_audit and website_audit.homepage_fetched:
            score += 15.0
            sources += 1
            if website_audit.contact_email:
                score += 5.0
            if website_audit.tech_stack_hints:
                score += min(5.0, len(website_audit.tech_stack_hints) * 1.5)
            if website_audit.location_signals:
                score += 5.0  # location evidence increases confidence
            # Red flags reduce confidence
            score -= len(website_audit.red_flags) * 3.0

        # Intelligence engine
        if intel_profile:
            score += min(10.0, getattr(intel_profile, "hot_score", 0) * 0.10)
            sources += 1

        # Classification confidence
        if classification:
            score += classification.confidence * 10.0
            sources += 1

        # Multi-source agreement bonus
        if sources >= 3:
            score += 12.0
        elif sources >= 2:
            score += 6.0

        return min(100.0, max(0.0, score))

    @staticmethod
    def _compute_risk(
        lead:           Dict[str, Any],
        anti_junk:      Optional[Any],
        website_audit:  Optional[Any],
        classification: Optional[Any],
        intent:         Optional[Dict[str, Any]],
    ) -> float:
        """Compute risk score 0-100. Higher = riskier. Gate rejects if > 35."""
        risk = 0.0

        domain  = lead.get("domain") or lead.get("website") or ""
        email   = (lead.get("email") or "").lower()
        country = lead.get("country") or lead.get("location") or ""

        # Missing domain — no verifiable business presence
        if not domain:
            risk += 20.0

        # Website not reachable
        if website_audit and not website_audit.homepage_fetched:
            risk += 15.0

        # Unknown country when country should be known
        if not country and not (website_audit and website_audit.location_signals):
            risk += 20.0

        # No product page evidence
        if website_audit and "no_product_signal" in website_audit.red_flags:
            risk += 15.0
        elif not website_audit and not domain:
            risk += 10.0  # no website evidence at all

        # No contact evidence
        if not email and not lead.get("phone"):
            if not (website_audit and website_audit.contact_email):
                risk += 10.0

        # Social-only lead
        source = (lead.get("source") or "").lower()
        if source in ("twitter", "facebook", "instagram", "telegram", "social_media"):
            if not domain:
                risk += 15.0

        # Scraped from directory / listing
        if anti_junk and "source_url_is_listing_page" in (anti_junk.junk_signals or []):
            risk += 15.0
        if source in ("crunchbase", "apollo", "zoominfo", "directory"):
            risk += 10.0

        # Free email only, no business domain
        if email:
            _FREE = frozenset({"gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                               "aol.com", "icloud.com", "protonmail.com"})
            email_domain = email.split("@")[-1] if "@" in email else ""
            if email_domain in _FREE and not domain:
                risk += 10.0

        # Generic / weak company name soft signals
        if anti_junk and "name_equals_company" in (anti_junk.junk_signals or []):
            risk += 5.0
        if anti_junk and "company_equals_contact_name" in (anti_junk.junk_signals or []):
            risk += 8.0

        return min(100.0, risk)

    # ------------------------------------------------------------------
    # Explainability helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _identity_confidence(lead: Dict[str, Any], anti_junk: Optional[Any]) -> float:
        """How confident we are that this is a real, named business entity."""
        score = 0.0
        company = (lead.get("company") or "").strip()
        if len(company) >= 3:
            score += 40.0
        if len(company) >= 8:
            score += 15.0
        if lead.get("website"):
            score += 20.0
        if lead.get("linkedin_url"):
            score += 15.0
        if lead.get("industry"):
            score += 10.0
        if anti_junk and anti_junk.passed and anti_junk.junk_score == 0:
            score += 10.0  # extra bonus for zero-junk signals
        elif anti_junk and anti_junk.junk_score > 0:
            score -= min(20.0, anti_junk.junk_score * 0.4)
        return min(100.0, max(0.0, round(score, 1)))

    @staticmethod
    def _email_confidence(lead: Dict[str, Any], website_audit: Optional[Any]) -> float:
        """Quality and verification confidence of the email address."""
        email = (lead.get("email") or "").strip().lower()
        if not email:
            return 0.0
        score = 30.0  # has any email
        _FREE = frozenset({
            "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
            "aol.com", "icloud.com", "protonmail.com", "live.com",
        })
        email_domain = email.split("@")[-1] if "@" in email else ""
        if email_domain and email_domain not in _FREE:
            score += 40.0  # business domain email
        dp = lead.get("data_points") or {}
        if dp.get("email_verified"):
            score += 30.0
        elif website_audit and website_audit.contact_email:
            score += 15.0  # email found on company website
        return min(100.0, round(score, 1))

    @staticmethod
    def _source_confidence(lead: Dict[str, Any], anti_junk: Optional[Any]) -> float:
        """Reliability of the data source that produced this lead."""
        source = (lead.get("source") or "").lower()
        base = {
            "apollo":           85.0,
            "pdl":              80.0,
            "clearbit":         80.0,
            "hunter":           75.0,
            "zerobounce":       70.0,
            "google_places":    60.0,
            "github_profile":   68.0,
            "linkedin_search":  72.0,
            "news":             60.0,
            "crunchbase":       78.0,
            "web_public":       40.0,
            "reddit":           30.0,
            "directory":        25.0,
        }.get(source, 35.0)
        # Degrade if the source URL was a listing/aggregator page
        if anti_junk and "source_url_is_listing_page" in (anti_junk.junk_signals or []):
            base -= 20.0
        if anti_junk and "aggregator_source" in (anti_junk.junk_signals or []):
            base -= 15.0
        return min(100.0, max(0.0, round(base, 1)))

    @staticmethod
    def _build_why_saved(decision: IntelligenceDecision, company: str) -> str:
        parts = [f"{company} passed all 7 intelligence gates."]
        if decision.fit_score >= 70:
            parts.append("Strong ICP fit.")
        if decision.intent_score >= 70:
            parts.append("High buying intent signals detected.")
        if decision.growth_score >= 60:
            parts.append("Active growth momentum.")
        if decision.confidence_score >= 80:
            parts.append("High data confidence across sources.")
        if decision.risk_score <= 15:
            parts.append("Low risk profile.")
        return " ".join(parts)

    @staticmethod
    def _recommend_angle(
        intent:         Optional[Dict[str, Any]],
        growth:         Optional[Any],
        classification: Optional[Any],
        website_audit:  Optional[Any],
    ) -> str:
        angles = []
        if growth and growth.hiring_detected:
            angles.append("actively hiring — reach out re: scaling tools")
        if growth and growth.funding_detected:
            angles.append("recently funded — positioned to invest in new tools")
        if website_audit and website_audit.pricing_exists:
            angles.append("already has pricing page — familiar with SaaS purchasing")
        if intent:
            level = intent.get("buying_intent", "none")
            if level == "high":
                angles.append("showing active research signals — high urgency")
            elif level == "medium":
                angles.append("in discovery phase — educational content recommended")
        if not angles:
            return "general awareness campaign"
        return "; ".join(angles[:2])


# ── Singleton ─────────────────────────────────────────────────────────────────

_scorer: Optional[AccountScorer] = None


def get_account_scorer() -> AccountScorer:
    global _scorer
    if _scorer is None:
        _scorer = AccountScorer()
    return _scorer
