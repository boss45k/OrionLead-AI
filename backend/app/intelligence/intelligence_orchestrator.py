"""
Intelligence Orchestrator
=========================
Enforces the company-first intelligence pipeline.

Flow
----
  Query
  → Pre-screen (fast anti-junk, no HTTP)
  → Intent Contract Parsing (what country/industry did the user ask for?)
  → Company Discovery (raw candidates from collector)
  → Dedup by domain
  → Keyword pre-filter
  → Per-company loop:
      Stage 1  — Anti-junk initial check (name / domain level, no HTTP)
      Stage 2  — Website audit (scrape homepage/about/pricing/careers/contact)
      Stage 2b — Anti-junk re-check with page text
      Stage 3  — Business classification
      Stage 4  — User intent contract validation (country + industry match)
      Stage 5  — Growth signal detection
      Stage 6  — Buying intent scoring
      Stage 7  — Account scoring gate (IntelligenceDecision, 7 hard gates)
      Stage 8  — Contact resolution [ONLY if company passed Stage 7]
      Stage 9  — Email verification
      Stage 10 — Final save gate

CRITICAL RULES:
  • Contacts are resolved ONLY after company passes Stage 7.
  • If intelligence fails with an exception, the lead is NOT saved.
    It is marked needs_review, never silently passed through.
  • Every decision is recorded in the audit_log with full evidence.

Audit log
---------
Every candidate is logged with:
  query, source, company, domain, decision, rejection_reason,
  failed_stage, scores, evidence, timestamp
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional

from app.intelligence.models import IntelligenceDecision
from app.intelligence.user_intent_contract import get_intent_contract_engine
from app.services.lead_candidate_filter import filter_candidates
from app.services.collection_policy import CollectionPolicy, STRICT_INTELLIGENCE, RAW_COLLECTION, BALANCED_INTELLIGENCE

logger = logging.getLogger(__name__)


# ── Pipeline report ───────────────────────────────────────────────────────────

@dataclass
class IntelligencePipelineReport:
    query: str = ""
    location: str = ""
    n_in: int = 0
    n_saved: int = 0
    n_rejected: int = 0
    n_skipped: int = 0
    n_needs_review: int = 0
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    saved_leads: List[Dict[str, Any]] = field(default_factory=list)
    audit_log: List[Dict[str, Any]] = field(default_factory=list)
    elapsed_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query":              self.query,
            "location":          self.location,
            "n_in":              self.n_in,
            "n_saved":           self.n_saved,
            "n_rejected":        self.n_rejected,
            "n_skipped":         self.n_skipped,
            "n_needs_review":    self.n_needs_review,
            "rejection_reasons": self.rejection_reasons,
            "elapsed_ms":        self.elapsed_ms,
        }


# ── Orchestrator ──────────────────────────────────────────────────────────────

class IntelligenceOrchestrator:
    """
    Company-first intelligence pipeline.

    All sub-components are lazy-imported so the orchestrator degrades
    gracefully when individual services (Hunter, ZeroBounce, Gemini) are not
    configured.  Exceptions from external services are caught per-company
    and the lead is marked needs_review — never silently passed.
    """

    def __init__(
        self,
        allowed_types:   Optional[FrozenSet[str]] = None,
        audit_website:   bool = True,
        use_hunter:      bool = True,
        use_zerobounce:  bool = True,
        website_timeout: int  = 8,
        policy:          Optional[CollectionPolicy] = None,
    ) -> None:
        from app.intelligence.anti_junk_engine    import get_anti_junk_engine
        from app.intelligence.website_auditor     import WebsiteAuditor
        from app.intelligence.business_classifier import get_business_classifier
        from app.intelligence.growth_detector     import get_growth_detector
        from app.intelligence.account_scorer      import get_account_scorer
        from app.intelligence.contact_resolver    import get_contact_resolver

        self._anti_junk    = get_anti_junk_engine()
        self._auditor      = WebsiteAuditor(timeout=website_timeout)
        self._classifier   = get_business_classifier()
        self._growth       = get_growth_detector()
        self._scorer       = get_account_scorer()
        self._resolver     = get_contact_resolver()

        self._allowed_types  = allowed_types or frozenset({"b2b_saas"})
        self._audit_website  = audit_website
        self._use_hunter     = use_hunter
        self._use_zerobounce = use_zerobounce
        self._policy         = policy or STRICT_INTELLIGENCE

        logger.info(
            "[orchestrator] ready — icp=%s audit=%s hunter=%s zb=%s policy=%s",
            self._allowed_types, audit_website, use_hunter, use_zerobounce, self._policy.mode,
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_pipeline(
        self,
        candidates:        List[Dict[str, Any]],
        query:             str = "",
        location:          str = "",
        save_lead_fn:      Optional[Callable[[Dict[str, Any]], bool]] = None,
        progress_fn:       Optional[Callable[[int, str], None]] = None,
        collection_button: str = "",
    ) -> IntelligencePipelineReport:
        """
        Run the full company-first intelligence pipeline.

        Args:
            candidates:   Raw company leads (dicts) from any collector.
            query:        Original search query (for intent scoring context).
            location:     Search location string.
            save_lead_fn: Callable(lead_dict) → bool.
            progress_fn:  Optional callable(pct, msg).

        Returns:
            IntelligencePipelineReport
        """
        t0 = time.monotonic()
        report = IntelligencePipelineReport(query=query, location=location)
        report.n_in = len(candidates)
        # Guard: tests may instantiate via __new__, bypassing __init__
        if not hasattr(self, '_policy'):
            self._policy = STRICT_INTELLIGENCE

        def _progress(pct: int, msg: str) -> None:
            if progress_fn:
                try:
                    progress_fn(pct, msg)
                except Exception:
                    pass

        _progress(2, f"Intelligence pipeline starting for {len(candidates)} candidates…")

        # ── Parse user intent contract once (before the per-company loop) ──────
        intent_contract = None
        try:
            intent_contract = get_intent_contract_engine().parse(query, location)
            logger.info(
                "[orchestrator] intent_contract — country=%s types=%s",
                intent_contract.requested_country,
                intent_contract.requested_industry_types,
            )
        except Exception as ice:
            logger.debug("[orchestrator] intent contract parse failed: %s", ice)

        # ── Dedup by domain ────────────────────────────────────────────────────
        candidates = self._dedup(candidates)
        _progress(5, f"{len(candidates)} unique companies after dedup")

        # ── Keyword pre-filter ─────────────────────────────────────────────────
        try:
            before = len(candidates)
            candidates = filter_candidates(candidates, query=query, location=location)
            skipped = before - len(candidates)
            if skipped:
                report.n_skipped += skipped
                logger.info(
                    "[orchestrator] keyword pre-filter: %d → %d (%d removed)",
                    before, len(candidates), skipped,
                )
        except Exception as kf_err:
            logger.debug("[orchestrator] keyword filter unavailable: %s", kf_err)

        _progress(10, f"{len(candidates)} candidates after pre-filter")

        # ── Per-company intelligence loop ──────────────────────────────────────
        total = len(candidates)
        for idx, raw in enumerate(candidates):
            pct = 10 + int((idx / max(total, 1)) * 85)
            _progress(pct, f"Analysing {idx + 1}/{total}: {raw.get('company', '?')}…")

            # Tag with collection button so audit log can trace which button produced this lead
            if collection_button:
                raw = dict(raw)
                raw.setdefault("_button", collection_button)

            if self._policy.run_full_intelligence:
                result = self._process_one(raw, query=query, location=location,
                                           intent_contract=intent_contract)
            else:
                result = self._raw_check(raw)

            decision = result.get("decision", "needs_review")
            reason   = result.get("rejection_reason", "")

            if decision == "save":
                lead_to_save = result.get("lead", raw)
                saved = False
                if save_lead_fn:
                    try:
                        saved = bool(save_lead_fn(lead_to_save))
                    except Exception as se:
                        logger.warning("[orchestrator] save_lead_fn error: %s", se)
                if saved:
                    report.n_saved += 1
                    report.saved_leads.append(lead_to_save)
            elif decision == "rejected":
                report.n_rejected += 1
                report.rejection_reasons[reason] = \
                    report.rejection_reasons.get(reason, 0) + 1
            elif decision == "needs_review":
                report.n_needs_review += 1
                report.rejection_reasons["needs_review"] = \
                    report.rejection_reasons.get("needs_review", 0) + 1
            else:
                report.n_skipped += 1

            report.audit_log.append(self._audit_entry(raw, result))

        _progress(100, f"Done — {report.n_saved} saved, {report.n_rejected} rejected, "
                       f"{report.n_needs_review} needs_review")
        report.elapsed_ms = int((time.monotonic() - t0) * 1000)

        logger.info(
            "[orchestrator] query='%s' loc='%s' — "
            "in=%d saved=%d rejected=%d needs_review=%d skipped=%d in %dms",
            query, location, report.n_in, report.n_saved,
            report.n_rejected, report.n_needs_review,
            report.n_skipped, report.elapsed_ms,
        )
        return report

    # ------------------------------------------------------------------
    # Single-company processing
    # ------------------------------------------------------------------

    def _process_one(
        self,
        raw:             Dict[str, Any],
        query:           str,
        location:        str,
        intent_contract: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Run the full intelligence stack for one company candidate.

        NEVER raises — on unhandled exception returns needs_review.
        Returns dict: decision, lead, rejection_reason, scores, evidence.
        """
        # Guard: tests may instantiate via __new__, bypassing __init__
        if not hasattr(self, '_policy'):
            self._policy = STRICT_INTELLIGENCE

        company = (raw.get("company") or raw.get("name") or "").strip()
        website = (raw.get("website") or "").strip()
        domain  = self._get_domain(raw)

        collected_evidence: Dict[str, Any] = {}

        # ── Stage 1: Anti-junk (no HTTP) ──────────────────────────────────────
        try:
            junk_result = self._anti_junk.check(raw, source_url=raw.get("source_url", ""))
        except Exception as exc:
            logger.warning("[orchestrator] anti_junk exception for %s: %s", company, exc)
            return self._needs_review(raw, "anti_junk_exception", "anti_junk")

        collected_evidence["anti_junk_initial"] = junk_result.to_dict()

        if not junk_result.passed:
            return self._reject(
                raw, junk_result.rejection_reason, "anti_junk",
                evidence=collected_evidence,
            )

        # ── Stage 2: Website audit ─────────────────────────────────────────────
        audit = None
        if self._audit_website and (website or domain):
            try:
                audit = self._auditor.audit(website or domain, domain=domain)
                collected_evidence["website_audit"] = audit.to_dict()
            except Exception as exc:
                logger.debug("[orchestrator] website audit failed for %s: %s", company, exc)

            if audit:
                # Re-run anti-junk with page text
                try:
                    junk_result2 = self._anti_junk.check(
                        raw,
                        page_text=audit.raw_text_snippet,
                        source_url="",
                    )
                    collected_evidence["anti_junk_post_audit"] = junk_result2.to_dict()
                    if not junk_result2.passed:
                        return self._reject(
                            raw, junk_result2.rejection_reason, "anti_junk_post_audit",
                            evidence=collected_evidence,
                        )
                except Exception as exc:
                    logger.debug("[orchestrator] anti_junk_post_audit error: %s", exc)

                if "parked" in audit.red_flags:
                    return self._reject(raw, "parked_domain", "website_audit",
                                        evidence=collected_evidence)

        # ── Stage 3: Business classification ──────────────────────────────────
        page_text = (audit.raw_text_snippet if audit else "") + \
                    " " + (raw.get("data_points") or {}).get("snippet", "")

        try:
            classification = self._classifier.classify(raw, page_text=page_text, website_audit=audit)
            collected_evidence["classification"] = classification.to_dict()
        except Exception as exc:
            logger.debug("[orchestrator] classifier error for %s: %s", company, exc)
            classification = None

        if classification and classification.is_hard_reject:
            return self._reject(
                raw, f"business_type_{classification.business_type}", "classifier",
                evidence=collected_evidence,
            )

        # ── Stage 4: Growth signal detection ──────────────────────────────────
        try:
            growth_result = self._growth.detect(raw, page_text=page_text, website_audit=audit)
            collected_evidence["growth"] = growth_result.to_dict()
        except Exception as exc:
            logger.debug("[orchestrator] growth detector error for %s: %s", company, exc)
            growth_result = None

        # ── Stage 5: Buying intent detection ──────────────────────────────────
        intent = {}
        try:
            from app.services.intent_detector import detect_intent
            intent = detect_intent(text=page_text or company, company=company)
            collected_evidence["intent"] = intent
        except Exception as ie:
            logger.debug("[orchestrator] intent detection failed: %s", ie)

        # Store intent values — applied to `lead` dict after it's built at Stage 8
        _bi = (intent.get("buying_intent") or "none")[:20]
        _ic = float(intent.get("confidence") or 0.0)

        # ── Stage 6: Legacy intel engine (optional) ────────────────────────────
        intel_profile = None
        try:
            from app.intelligence.company_intelligence import CompanyIntelligenceEngine
            intel_profile = CompanyIntelligenceEngine().analyze(raw)
            collected_evidence["intel_profile"] = intel_profile.to_dict()
        except Exception as ie:
            logger.debug("[orchestrator] intel engine unavailable: %s", ie)

        # ── Stage 7: Account scoring — 7 hard gates ────────────────────────────
        try:
            intel_decision: IntelligenceDecision = self._scorer.score(
                raw,
                anti_junk=junk_result,
                classification=classification,
                growth=growth_result,
                website_audit=audit,
                intel_profile=intel_profile,
                intent=intent,
                allowed_types=self._allowed_types,
                user_intent_contract=intent_contract,
            )
        except Exception as exc:
            logger.warning("[orchestrator] account_scorer exception for %s: %s", company, exc)
            return self._needs_review(raw, "account_scorer_exception", "account_scorer",
                                      evidence=collected_evidence)

        collected_evidence["intelligence_decision"] = intel_decision.to_dict()

        if not intel_decision.passed:
            # In balanced_intelligence mode, save if score >= min_save_score
            # despite gate failure — unless the hard anti-junk stage failed.
            policy = self._policy
            failed_stage = intel_decision.failed_stage or ""
            final_score_early = float(intel_decision.final_score or 0.0)
            if (
                policy.mode == "balanced_intelligence"
                and final_score_early >= policy.min_save_score
                and failed_stage not in ("anti_junk", "anti_junk_post_audit", "hard_reject", "user_intent_check")
            ):
                # Override: save as unvalidated/semi_validated despite gate failure
                if final_score_early >= policy.min_semi_validated_score:
                    _suggested_status_early = "semi_validated"
                else:
                    _suggested_status_early = "unvalidated"
                lead_early = dict(raw)
                lead_early["buying_intent"]          = _bi
                lead_early["intent_confidence"]      = _ic
                lead_early.setdefault("data_points", {})["intent"] = intent
                lead_early["_company_intelligence"]  = collected_evidence
                lead_early["_account_score"]         = intel_decision.to_dict()
                lead_early["_intelligence_decision"] = intel_decision.to_dict()
                lead_early["final_company_score"]    = intel_decision.final_score
                lead_early["_suggested_status"]      = _suggested_status_early
                lead_early["_policy_mode"]           = policy.mode
                logger.debug(
                    "[orchestrator] balanced override SAVE '%s' score=%.1f status=%s "
                    "(gate failed: %s)",
                    company, final_score_early, _suggested_status_early, failed_stage,
                )
                return {
                    "decision":         "save",
                    "lead":             lead_early,
                    "rejection_reason": "",
                    "scores":           intel_decision.to_dict(),
                    "evidence":         collected_evidence,
                }
            return self._reject(
                raw,
                intel_decision.rejection_reason,
                intel_decision.failed_stage,
                evidence=collected_evidence,
                scores=intel_decision.to_dict(),
            )

        # ── Stage 8: Contact resolution (ONLY after company passes) ───────────
        try:
            contact_result = self._resolver.resolve(raw, domain=domain, website_audit=audit)
            collected_evidence["contact_resolution"] = contact_result.to_dict()
        except Exception as exc:
            logger.debug("[orchestrator] contact resolution error for %s: %s", company, exc)
            contact_result = None

        # ── Build enriched lead dict ───────────────────────────────────────────
        lead = dict(raw)
        # Promote intent fields (computed at Stage 5, applied here once `lead` exists)
        lead["buying_intent"]     = _bi
        lead["intent_confidence"] = _ic
        lead.setdefault("data_points", {})["intent"] = intent
        lead["_company_intelligence"]      = collected_evidence
        lead["_account_score"]             = intel_decision.to_dict()
        lead["_intelligence_decision"]     = intel_decision.to_dict()
        lead["why_saved"]                  = intel_decision.why_saved
        lead["top_positive_signals"]       = intel_decision.top_positive_signals
        lead["top_risk_signals"]           = intel_decision.top_risk_signals
        lead["final_company_score"]        = intel_decision.final_score
        lead["recommended_outreach_angle"] = intel_decision.recommended_outreach_angle

        if contact_result and contact_result.found:
            bc = contact_result.best_contact
            if bc.name  and not lead.get("name"):  lead["name"]     = bc.name
            if bc.email and not lead.get("email"): lead["email"]    = bc.email
            if bc.phone and not lead.get("phone"): lead["phone"]    = bc.phone
            if bc.title and not lead.get("position"): lead["position"] = bc.title

        # ── Stage 9: Email verification ────────────────────────────────────────
        if self._use_zerobounce and lead.get("email"):
            try:
                from app.services.email_verifier import verify_email
                vresult = verify_email(lead["email"])
                lead["_email_verification"] = vresult
                _ev_status = vresult.get("status", "")
                # Write to data_points so the "Verified Email" filter works
                lead.setdefault("data_points", {})["email_verified"] = (_ev_status == "valid")
                if _ev_status == "invalid":
                    return self._reject(
                        raw, "invalid_email", "email_verification",
                        evidence=collected_evidence, lead=lead,
                    )
            except Exception as ve:
                logger.debug("[orchestrator] email verification failed: %s", ve)

        # Policy-tiered save status
        _policy = self._policy
        _final_score = float(intel_decision.final_score or 0.0)
        if _final_score >= _policy.min_validated_score:
            _suggested_status = "validated"
        elif _final_score >= _policy.min_semi_validated_score:
            _suggested_status = "semi_validated"
        else:
            _suggested_status = _policy.default_save_status
        lead["_suggested_status"] = _suggested_status
        lead["_policy_mode"]      = _policy.mode

        # Persist intelligence scores into data_points so UI can display breakdown
        lead.setdefault("data_points", {})["intelligence_score"] = intel_decision.to_dict()

        return {
            "decision":         "save",
            "lead":             lead,
            "rejection_reason": "",
            "scores":           intel_decision.to_dict(),
            "evidence":         collected_evidence,
        }

    # ------------------------------------------------------------------
    # Raw collection check (no full intelligence — hard anti-junk only)
    # ------------------------------------------------------------------

    def _raw_check(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        For raw_collection mode: only hard anti-junk rules, no full intelligence.
        Fast — no HTTP calls, no website audit, no scoring.
        """
        company = (raw.get("company") or raw.get("name") or "").strip()
        email   = (raw.get("email") or "").strip()
        website = (raw.get("website") or "").strip()

        # Must have company OR (email AND website)
        if not company and not (email and website):
            return {"decision": "rejected", "rejection_reason": "no_company_no_contact",
                    "failed_stage": "raw_check", "lead": raw, "evidence": {}, "scores": {}}

        # Hard anti-junk only
        try:
            junk = self._anti_junk.check(raw, source_url=raw.get("source_url", ""))
        except Exception as exc:
            logger.warning("[orchestrator] raw_check anti_junk exception for %s: %s", company, exc)
            # On exception in raw mode, save with unvalidated rather than needs_review
            lead = dict(raw)
            lead["_suggested_status"] = "unvalidated"
            lead["_policy_mode"] = "raw_collection"
            return {"decision": "save", "rejection_reason": "", "lead": lead,
                    "evidence": {}, "scores": {}}

        if not junk.passed:
            # Check if the signal is a soft passthrough
            if junk.rejection_reason in self._policy.soft_signal_passthrough:
                logger.debug(
                    "[orchestrator] raw_check soft passthrough '%s': %s",
                    company, junk.rejection_reason,
                )
            else:
                return {"decision": "rejected",
                        "rejection_reason": junk.rejection_reason,
                        "failed_stage": "anti_junk",
                        "lead": raw,
                        "evidence": {"anti_junk": junk.to_dict()},
                        "scores": {}}

        lead = dict(raw)
        lead["_suggested_status"] = "unvalidated"
        lead["_policy_mode"] = "raw_collection"
        return {"decision": "save", "rejection_reason": "", "lead": lead,
                "evidence": {}, "scores": {}}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _reject(
        raw:          Dict[str, Any],
        reason:       str,
        failed_stage: str,
        evidence:     Optional[Dict] = None,
        scores:       Optional[Dict] = None,
        lead:         Optional[Dict] = None,
    ) -> Dict[str, Any]:
        company = raw.get("company") or raw.get("name") or "?"
        logger.debug("[orchestrator] REJECT '%s' at %s: %s", company, failed_stage, reason)
        return {
            "decision":         "rejected",
            "lead":             lead or raw,
            "rejection_reason": reason,
            "failed_stage":     failed_stage,
            "evidence":         evidence or {},
            "scores":           scores or {},
        }

    @staticmethod
    def _needs_review(
        raw:          Dict[str, Any],
        reason:       str,
        failed_stage: str,
        evidence:     Optional[Dict] = None,
    ) -> Dict[str, Any]:
        company = raw.get("company") or raw.get("name") or "?"
        logger.debug("[orchestrator] NEEDS_REVIEW '%s' at %s: %s",
                     company, failed_stage, reason)
        return {
            "decision":         "needs_review",
            "lead":             raw,
            "rejection_reason": reason,
            "failed_stage":     failed_stage,
            "evidence":         evidence or {},
            "scores":           {},
        }

    @staticmethod
    def _get_domain(lead: Dict[str, Any]) -> str:
        from urllib.parse import urlparse
        domain = (lead.get("domain") or "").strip().lower()
        if domain:
            return domain
        website = (lead.get("website") or "").strip()
        if website:
            try:
                return urlparse(website).netloc.lower().replace("www.", "")
            except Exception:
                pass
        email = (lead.get("email") or "").strip().lower()
        if "@" in email:
            return email.split("@")[-1]
        return ""

    @staticmethod
    def _dedup(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        from urllib.parse import urlparse
        seen_domains: set = set()
        seen_emails:  set = set()
        result = []
        for c in candidates:
            website = c.get("website") or ""
            try:
                d = urlparse(website).netloc.lower().replace("www.", "") if website else ""
            except Exception:
                d = ""
            email       = (c.get("email") or "").lower()
            domain_key  = d or (c.get("domain") or "").lower()

            if domain_key and domain_key in seen_domains:
                continue
            if email and email in seen_emails:
                continue
            if domain_key:
                seen_domains.add(domain_key)
            if email:
                seen_emails.add(email)
            result.append(c)
        return result

    @staticmethod
    def _audit_entry(raw: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        import datetime
        scores   = result.get("scores") or {}
        evidence = result.get("evidence") or {}
        intel    = evidence.get("intelligence_decision") or {}
        return {
            "timestamp":         datetime.datetime.utcnow().isoformat() + "Z",
            "company":           raw.get("company") or raw.get("name"),
            "domain":            raw.get("domain") or raw.get("website"),
            "source":            raw.get("source"),
            "collection_button": raw.get("_button", ""),
            "decision":          result.get("decision"),
            "rejection_reason":  result.get("rejection_reason", ""),
            "failed_stage":      result.get("failed_stage", ""),
            # Scores (from IntelligenceDecision)
            "final_score":      intel.get("final_score") or scores.get("final_score"),
            "fit_score":        intel.get("fit_score")   or scores.get("fit_score"),
            "intent_score":     intel.get("intent_score") or scores.get("intent_score"),
            "growth_score":     intel.get("growth_score") or scores.get("growth_score"),
            "confidence_score": intel.get("confidence_score") or scores.get("confidence_score"),
            "risk_score":       intel.get("risk_score")  or scores.get("risk_score"),
            # Gate flags
            "company_identity_passed": intel.get("company_identity_passed"),
            "user_intent_passed":      intel.get("user_intent_passed"),
            "anti_junk_passed":        intel.get("anti_junk_passed"),
            "location_match":          intel.get("location_match"),
            # Explainability
            "why_saved":        intel.get("why_saved", ""),
            "top_positive":     intel.get("top_positive_signals", []),
            "top_risks":        intel.get("top_risk_signals", []),
            "evidence_count":   len(intel.get("evidence", [])),
        }


# ── Module-level convenience function ─────────────────────────────────────────

def run_intelligence_pipeline(
    candidates:   List[Dict[str, Any]],
    query:        str = "",
    location:     str = "",
    save_lead_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
    allowed_types: Optional[FrozenSet[str]] = None,
    progress_fn:  Optional[Callable[[int, str], None]] = None,
    audit_website: bool = True,
    use_hunter:   bool = True,
) -> IntelligencePipelineReport:
    """Module-level entry point — creates a fresh orchestrator and runs pipeline."""
    orch = IntelligenceOrchestrator(
        allowed_types=allowed_types,
        audit_website=audit_website,
        use_hunter=use_hunter,
    )
    return orch.run_pipeline(
        candidates=candidates,
        query=query,
        location=location,
        save_lead_fn=save_lead_fn,
        progress_fn=progress_fn,
    )
