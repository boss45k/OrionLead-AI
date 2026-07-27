"""
Candidate Pipeline
==================
8-stage orchestrator for smart lead collection.

Flow:
  Stage 1  discover_candidates()  — collect broadly from all enabled sources
  Stage 2  deduplicate()          — in-memory session dedup (email + domain)
  Stage 3  pre_filter()           — fast name/CDN/anchor check (no API)
  Stage 4  enrich()               — contact-page scrape → Hunter → PDL/Apollo
  Stage 5  detect_intent()        — buying-intent phrase detection
  Stage 6  verify_contact()       — ZeroBounce SMTP / MX fallback
  Stage 7  evaluate_quality()     — full lead_quality_engine scoring
  Stage 8  save_or_reject()       — source-specific hard rules + DB write

Core principle:
  Collect many candidates broadly, save only those that pass strict gates.
  Expensive APIs (Hunter, ZeroBounce) are called only when the candidate's
  pre-filter score is high enough to justify the cost.

Usage (from a background task)
------------------------------
    pipeline = CandidatePipeline()
    report = pipeline.run(
        query='SaaS companies hiring',
        sources=['web', 'social', 'github'],
        options={'max_candidates': 100, 'countries': ['US', 'UK']},
        save_lead_fn=save_to_db,
    )
    print(report.to_dict())
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — each import is guarded so the pipeline degrades gracefully
# if a module is unavailable.
# ---------------------------------------------------------------------------

def _import_quality_engine():
    from app.services.lead_quality_engine import (
        evaluate_lead_quality, CollectionQualityReport,
    )
    return evaluate_lead_quality, CollectionQualityReport

def _import_name_validator():
    from app.services.name_validator import pre_filter_lead
    return pre_filter_lead

def _import_intent_detector():
    from app.services.intent_detector import detect_intent, intent_quality_boost
    return detect_intent, intent_quality_boost

def _import_cache():
    from app.services.candidate_cache import get_candidate_cache
    return get_candidate_cache()

def _import_lead_fallback():
    from app.services.lead_fallback import enrich_lead_fallbacks
    return enrich_lead_fallbacks

def _import_email_verifier():
    from app.services.email_verifier import verify_email
    return verify_email

def _import_hunter():
    from app.services.hunter_service import HunterService
    return HunterService()

def _import_ml_model():
    from app.services.ml_model import XGBLeadScoringModel, extract_features
    return XGBLeadScoringModel, extract_features

def _import_ai_service():
    from app.services.gemini_service import get_ai_service
    return get_ai_service()

def _import_orchestrator_agent():
    from app.agents.orchestrator_agent import run_enterprise_pipeline
    return run_enterprise_pipeline

def _import_enterprise_save_policy():
    from app.services.enterprise_save_policy import get_save_policy
    return get_save_policy()

def _import_graph_agent():
    from app.agents import graph_agent
    return graph_agent

def _import_audit_log():
    from app.monitoring import audit_lead, get_metrics
    return audit_lead, get_metrics()


# ---------------------------------------------------------------------------
# Source-specific save rules
# ---------------------------------------------------------------------------

# Minimum pre-filter score to spend API quota on a candidate.
# Scored 0-100 by _estimate_pre_score() before any enrichment.
_API_CALL_THRESHOLD = 40

# Minimum final quality score before save (source-specific overrides below).
_DEFAULT_MIN_SCORE = 35

_SOURCE_MIN_SCORES: Dict[str, float] = {
    'hunter':      50.0,  # Hunter data is strong — accept pending tier
    'hunter_api':  50.0,
    'pdl':         50.0,
    'apollo':      50.0,
    'clearbit':    45.0,
    'crunchbase':  45.0,
    'github':      40.0,
    'news':        35.0,
    'web':         35.0,
    'public_web':  35.0,
    'reddit':      50.0,  # Social sources need more signals
    'twitter':     50.0,
    'facebook':    50.0,
    'telegram':    50.0,
    'social_media':50.0,
    'generated':   999.0,  # Never save generated leads
    'inferred':    999.0,
}

# Email type hard rules (source → allowed email types → min score)
_REJECT_EMAIL_COMBOS = {
    # Generated emails are never saved regardless of source
    frozenset({'generated', 'generated_personal', 'generated_generic'}): 999.0,
}


# ---------------------------------------------------------------------------
# CandidateDict — internal representation before DB write
# ---------------------------------------------------------------------------

@dataclass
class CandidateDict:
    """
    Carries a raw lead through the pipeline.
    Each stage may add / modify fields.
    The original lead dict is in `data`.
    """
    data: Dict[str, Any]
    source: str

    # Set by pipeline stages:
    domain: str = ''
    pre_filter_passed: bool = False
    pre_filter_reason: str = ''
    enriched: bool = False
    intent: Dict[str, Any] = field(default_factory=dict)
    contact_verified: bool = False
    quality_score: float = 0.0
    quality_tier: str = ''
    ml_score: Optional[float] = None       # XGBoost prediction (0-100)
    intel_action: str = ''                 # 'SAVE' | 'REVIEW' | 'DISCARD'
    save_decision: str = 'pending'   # 'save' | 'reject' | 'pending' | 'enrich'
    rejection_reason: str = ''
    stage_times: Dict[str, float] = field(default_factory=dict)

    @property
    def email(self) -> str:
        return (self.data.get('email') or '').strip().lower()

    @property
    def name(self) -> str:
        return (self.data.get('name') or '').strip()

    @property
    def company(self) -> str:
        return (self.data.get('company') or '').strip()


# ---------------------------------------------------------------------------
# CandidatePipeline
# ---------------------------------------------------------------------------

class CandidatePipeline:
    """
    Runs candidates through the 8-stage quality pipeline.

    The pipeline is stateless — create a new instance per collection run,
    or reuse across runs (the CandidateCache singleton persists).
    """

    def __init__(self) -> None:
        try:
            self._cache = _import_cache()
        except Exception:
            self._cache = None
            logger.warning('[pipeline] CandidateCache unavailable — caching disabled')

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        candidates: List[Dict[str, Any]],
        source: str,
        save_lead_fn: Callable[[Dict[str, Any]], bool],
        report: Optional[Any] = None,   # CollectionQualityReport
        options: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Process a list of raw candidate dicts through the full 9-stage pipeline.

        Stages:
          2. Dedup          — in-memory email+domain dedup
          3. Pre-filter     — fast name/CDN/anchor check (no API)
          4. Enrichment     — Hunter email-finder (conditional)
          5. Intent         — buying-intent phrase detection
          6. Verification   — ZeroBounce email check (conditional)
          7. Quality Gate   — lead_quality_engine full scoring
          8. ML Qualify     — XGBoost score (conditional, pre-save)
          9. Intelligence   — rule-based B2B reality check
         10. Save           — DB write if all gates pass

        Stage 1 (AI Orchestrator) runs in the caller before collecting candidates.

        Args:
            candidates:    Raw lead dicts from any collector.
            source:        Source name ('hunter', 'reddit', 'web', …).
            save_lead_fn:  Callable(lead_dict) → bool. Called for each
                           accepted lead; returns True on successful save.
            report:        Optional CollectionQualityReport to accumulate stats.
            options:       Optional dict: {'min_score': 40, 'use_hunter': True,
                           'use_verify': True, 'use_ml': True,
                           'use_intelligence': True, 'collection_type': 'people',
                           'strategy': CollectionStrategy}

        Returns:
            The report (or a lightweight summary dict if report was None).
        """
        opts = options or {}
        min_score           = float(opts.get('min_score', _DEFAULT_MIN_SCORE))
        use_hunter          = bool(opts.get('use_hunter', True))
        use_verify          = bool(opts.get('use_verify', True))
        use_ml              = bool(opts.get('use_ml', True))
        use_intelligence    = bool(opts.get('use_intelligence', True))
        company_first_mode  = bool(opts.get('company_first_mode', False))
        collection_type     = str(opts.get('collection_type', 'people'))
        strategy            = opts.get('strategy')   # CollectionStrategy or None
        stage_callback      = opts.get('stage_callback')  # callable(stage_num, stage_name, counts)
        intent_label        = str(opts.get('intent', 'other'))
        region              = str(opts.get('region', 'unknown'))
        query               = str(opts.get('query', ''))
        location            = str(opts.get('location', ''))
        allowed_types       = opts.get('allowed_types')   # frozenset or None
        policy              = opts.get('policy')          # CollectionPolicy or None

        # ── Company-first intelligence mode — delegates to IntelligenceOrchestrator ──
        if company_first_mode:
            return self._run_company_first(
                candidates=candidates,
                source=source,
                save_lead_fn=save_lead_fn,
                report=report,
                query=query,
                location=location,
                allowed_types=allowed_types,
                use_hunter=use_hunter,
                stage_callback=stage_callback,
                policy=policy,
            )

        # Enterprise save policy — fresh instance per run (session dedup)
        _save_policy = None
        try:
            _save_policy = _import_enterprise_save_policy()
            _save_policy.reset()
        except Exception as _sp_err:
            logger.debug(f'[pipeline] enterprise save policy unavailable: {_sp_err}')

        # Reset entity graph between runs so domain counts don't bleed across queries
        try:
            _import_graph_agent().reset_graph()
        except Exception:
            pass

        # Monitoring
        _audit_lead = None
        _metrics = None
        try:
            _audit_lead, _metrics = _import_audit_log()
        except Exception:
            pass

        def _stage_cb(num, name, counts=None):
            if stage_callback:
                try:
                    stage_callback(num, name, counts)
                except Exception:
                    pass

        # Use existing report or create a lightweight one
        if report is None:
            try:
                _, CollectionQualityReport = _import_quality_engine()
                report = CollectionQualityReport(source=source)
            except Exception:
                report = _FallbackReport(source=source)

        report.raw_candidates += len(candidates)

        # Pre-load ML model once (avoid reloading per candidate)
        _ml_model = None
        _extract_features = None
        if use_ml:
            try:
                XGBLeadScoringModel, extract_features = _import_ml_model()
                _ml_model_inst = XGBLeadScoringModel()
                _ml_model_inst.load_model()
                if _ml_model_inst.model is not None:
                    _ml_model = _ml_model_inst
                    _extract_features = extract_features
            except Exception as _me:
                logger.debug(f'[pipeline] ML model unavailable: {_me}')

        # ── Stage loop: one candidate at a time ─────────────────────────
        seen_emails: set  = set()
        seen_domains: set = set()
        _reported_stages: set = set()   # fire each stage callback exactly once

        def _once(stage_num: int, stage_name: str) -> None:
            if stage_num not in _reported_stages:
                _reported_stages.add(stage_num)
                _stage_cb(stage_num, stage_name)

        for raw in candidates:
            t_start = time.monotonic()
            c = CandidateDict(data=dict(raw), source=source)

            # ── Stage 3: In-memory dedup ─────────────────────────────────
            _once(3, 'Normalization + Dedup')
            if not self._stage_dedup(c, seen_emails, seen_domains):
                report.duplicates += 1
                continue

            # ── Stage 4: Pre-filter ──────────────────────────────────────
            _once(4, 'Pre-filter + Strategy Check')
            if not self._stage_pre_filter(c):
                report.rejected += 1
                report.rejection_reasons[c.pre_filter_reason] = (
                    report.rejection_reasons.get(c.pre_filter_reason, 0) + 1
                )
                continue

            # AI strategy rejection signals — fast string check, no API
            if strategy and not self._stage_strategy_check(c, strategy, collection_type):
                report.rejected += 1
                report.rejection_reasons['strategy_rejection'] = (
                    report.rejection_reasons.get('strategy_rejection', 0) + 1
                )
                continue

            # Estimate pre-score to gate API calls
            pre_score = self._estimate_pre_score(c)

            # ── Stage 5: Enrichment ──────────────────────────────────────
            if pre_score >= _API_CALL_THRESHOLD:
                _once(5, 'Enrichment')
                self._stage_enrich(c, use_hunter=use_hunter, report=report)
                report.enriched_candidates += 1

            # ── Stage 5b: Intent detection ───────────────────────────────
            self._stage_detect_intent(c)
            if c.intent.get('buying_intent', 'none') != 'none':
                report.intent_detected += 1

            # ── Stage 6: Contact verification (ZeroBounce) ───────────────
            if use_verify and c.email:
                _once(6, 'Verification (ZeroBounce)')
                self._stage_verify_contact(c)

            # ── Stage 7: Quality Gate ────────────────────────────────────
            _once(7, 'Quality Gate')
            decision = self._stage_evaluate(c, source=source, report=report)
            c.save_decision = decision.decision
            c.quality_score = decision.quality_score
            c.quality_tier  = decision.tier

            _boost = 0.0
            if c.intent:
                try:
                    _, intent_quality_boost = _import_intent_detector()
                    _boost = intent_quality_boost(c.intent)
                except Exception:
                    pass
            effective_score = min(100.0, c.quality_score + _boost)
            source_min = _SOURCE_MIN_SCORES.get(source.lower(), min_score)

            if not decision.should_save or effective_score < source_min:
                reason = c.rejection_reason or 'below_min_score'
                report.rejected += 1
                report.rejection_reasons[reason] = (
                    report.rejection_reasons.get(reason, 0) + 1
                )
                c.stage_times['total'] = round(time.monotonic() - t_start, 3)
                continue

            # ── Stage 8: ML Qualification ────────────────────────────────
            if use_ml and _ml_model is not None:
                _once(8, 'ML Qualification (XGBoost)')
                ml_passed = self._stage_ml_qualify(c, _ml_model, _extract_features)
                if not ml_passed:
                    report.rejected += 1
                    report.rejection_reasons['ml_discard'] = (
                        report.rejection_reasons.get('ml_discard', 0) + 1
                    )
                    c.stage_times['total'] = round(time.monotonic() - t_start, 3)
                    continue
                # Blend ML score into effective_score, but never drop below the gate that admitted it
                if c.ml_score is not None:
                    blended = min(100.0, effective_score * 0.6 + c.ml_score * 0.4)
                    effective_score = max(blended, source_min)
                    c.data['qualification_score'] = round(effective_score)

            # ── Stage 9: Intelligence + Enterprise Enrichment ────────────
            _once(9, 'Intelligence Check')
            enterprise_result: Dict[str, Any] = {}
            if use_intelligence:
                intel_ok = self._stage_intelligence_check(c)
                if not intel_ok:
                    if _audit_lead:
                        _audit_lead(c.data, final_score=effective_score, grade='F',
                                    saved=False, drop_reason=c.rejection_reason,
                                    source=source, intent=intent_label)
                    report.rejected += 1
                    report.rejection_reasons['intelligence_discard'] = (
                        report.rejection_reasons.get('intelligence_discard', 0) + 1
                    )
                    c.stage_times['total'] = round(time.monotonic() - t_start, 3)
                    continue

                # Enterprise graph pass — enriches data_points with identity signals.
                # Does NOT override effective_score (quality gate score is authoritative);
                # enterprise score is stored as metadata only so saves are not blocked
                # when ML or intelligence components return 0.
                try:
                    _run_enterprise = _import_orchestrator_agent()
                    enterprise_result = _run_enterprise(
                        c.data,
                        ml_score=c.ml_score or 0.0,
                        intent=intent_label,
                        source=source,
                        region=region,
                        run_intelligence=False,   # intel already done inline above
                        run_graph=True,
                    )
                    # Promote augmented lead (enriched data_points from graph pass)
                    if enterprise_result.get('augmented_lead'):
                        c.data = enterprise_result['augmented_lead']
                    # Store enterprise intelligence as metadata — never replace quality score
                    c.data.setdefault('data_points', {}).update({
                        'enterprise_final_score': enterprise_result.get('final_score'),
                        'enterprise_grade':       enterprise_result.get('grade'),
                        'enterprise_breakdown':   enterprise_result.get('context_breakdown', {}),
                        'graph_confidence':       enterprise_result.get('graph_confidence'),
                    })
                    if _metrics:
                        _metrics.observe('enterprise_final_score',
                                         enterprise_result.get('final_score', 0))
                except Exception as _ent_err:
                    logger.debug(f'[pipeline] enterprise enrichment error: {_ent_err}')

                # Cold-signal block only — email/score gates already enforced above
                if _save_policy:
                    cold_signals = frozenset(
                        s.lower() for s in (
                            (c.data.get('data_points') or {}).get('cold_signals') or []
                        )
                    )
                    _COLD_BLOCK = frozenset({
                        'parked_domain', 'inactive_company',
                        'no_business_identity', 'spam_domain',
                    })
                    blocked = cold_signals & _COLD_BLOCK
                    if blocked:
                        reason = f"cold_signal ({', '.join(blocked)})"
                        if _audit_lead:
                            _audit_lead(c.data, final_score=effective_score, grade='F',
                                        saved=False, drop_reason=reason,
                                        source=source, intent=intent_label)
                        report.rejected += 1
                        report.rejection_reasons[reason] = (
                            report.rejection_reasons.get(reason, 0) + 1
                        )
                        c.stage_times['total'] = round(time.monotonic() - t_start, 3)
                        continue

            # ── Stage 10: Save ───────────────────────────────────────────
            _once(10, 'Save')
            self._apply_intent_to_lead(c)
            saved = save_lead_fn(c.data)
            _ent_grade = enterprise_result.get('grade', 'C') if enterprise_result else 'C'
            if saved:
                report.saved += 1
                report.record_source(source)
                report.record_score(effective_score)
                if _audit_lead:
                    _audit_lead(c.data, final_score=effective_score, grade=_ent_grade,
                                saved=True, source=source, intent=intent_label,
                                score_breakdown=enterprise_result.get('context_breakdown'))
                if _metrics:
                    _metrics.increment('leads_saved')
                if decision.metadata.get('email_type') == 'personal_business' \
                        and decision.metadata.get('email_verified'):
                    report.verified_personal += 1
                elif decision.metadata.get('email_type') == 'generic':
                    report.company_generic += 1
                else:
                    report.unverified += 1
                if c.email:
                    seen_emails.add(c.email)
                if c.domain:
                    seen_domains.add(c.domain)
            else:
                if _audit_lead:
                    _audit_lead(c.data, final_score=effective_score, grade=_ent_grade,
                                saved=False, drop_reason='save_failed',
                                source=source, intent=intent_label)
                report.rejected += 1
                report.rejection_reasons['save_failed'] = (
                    report.rejection_reasons.get('save_failed', 0) + 1
                )

            c.stage_times['total'] = round(time.monotonic() - t_start, 3)

        report.log_summary()
        return report

    # ------------------------------------------------------------------
    # Company-first intelligence mode (replaces person-first stages)
    # ------------------------------------------------------------------

    def _run_company_first(
        self,
        candidates: List[Dict[str, Any]],
        source: str,
        save_lead_fn: Callable[[Dict[str, Any]], bool],
        report: Optional[Any],
        query: str,
        location: str,
        allowed_types: Optional[Any],
        use_hunter: bool,
        stage_callback: Optional[Callable],
        policy: Optional[Any] = None,
    ) -> Any:
        """
        Company-first intelligence pipeline:
        discover companies → intelligence qualification → contact resolution
        → verification → final save gate.

        Contacts are NEVER found before the company passes intelligence checks.
        Delegates to IntelligenceOrchestrator which enforces the strict gate order.
        """
        logger.info(
            "[pipeline] company_first_mode=True — delegating to IntelligenceOrchestrator"
        )

        def _stage_cb(pct, msg):
            if stage_callback:
                try:
                    stage_callback(pct, msg)
                except Exception:
                    pass

        try:
            from app.intelligence.intelligence_orchestrator import IntelligenceOrchestrator
        except ImportError as ie:
            logger.error("[pipeline] IntelligenceOrchestrator unavailable: %s — falling back to standard pipeline", ie)
            # Fallback: run standard pipeline without company-first mode
            return self.run(candidates, source, save_lead_fn, report=report,
                            options={'use_hunter': use_hunter})

        from app.services.collection_policy import STRICT_INTELLIGENCE as _DEFAULT_POLICY
        orch = IntelligenceOrchestrator(
            allowed_types=allowed_types,
            use_hunter=use_hunter,
            audit_website=True,
            policy=policy or _DEFAULT_POLICY,
        )

        intel_report = orch.run_pipeline(
            candidates=candidates,
            query=query,
            location=location,
            save_lead_fn=save_lead_fn,
            progress_fn=_stage_cb,
        )

        # Map IntelligencePipelineReport back to CollectionQualityReport format
        if report is not None:
            report.raw_candidates += intel_report.n_in
            report.saved           = getattr(report, 'saved', 0) + intel_report.n_saved
            report.rejected       += intel_report.n_rejected
            for reason, cnt in intel_report.rejection_reasons.items():
                report.rejection_reasons[reason] = (
                    report.rejection_reasons.get(reason, 0) + cnt
                )
        else:
            report = intel_report

        logger.info(
            "[pipeline] company_first done — saved=%d rejected=%d skipped=%d in %dms",
            intel_report.n_saved, intel_report.n_rejected,
            intel_report.n_skipped, intel_report.elapsed_ms,
        )
        return report

    # ------------------------------------------------------------------
    # Stage 2: in-memory dedup
    # ------------------------------------------------------------------

    def _stage_dedup(
        self,
        c: CandidateDict,
        seen_emails: set,
        seen_domains: set,
    ) -> bool:
        """Return False (skip) if candidate is already seen this run."""
        if c.email and c.email in seen_emails:
            return False
        # Extract domain
        website = (c.data.get('website') or '').strip()
        if website:
            try:
                c.domain = urlparse(website).netloc.replace('www.', '')
            except Exception:
                pass
        if not c.domain:
            email_domain = c.email.split('@')[1] if '@' in c.email else ''
            c.domain = email_domain

        if c.domain and c.domain in seen_domains:
            # Same domain — still allow if person name differs (different contacts)
            existing_key = f"{c.name.lower()}|{c.domain}"
            if existing_key in seen_emails:   # reuse set as name+domain store
                return False
        return True

    # ------------------------------------------------------------------
    # Stage 3: pre-filter (no API)
    # ------------------------------------------------------------------

    def _stage_pre_filter(self, c: CandidateDict) -> bool:
        """
        Fast, free checks: CDN email, URL-as-name, no anchor data.
        Returns False if the candidate should be hard-rejected.
        """
        try:
            pre_filter_lead = _import_name_validator()
            ok, reason = pre_filter_lead(c.data)
            c.pre_filter_passed = ok
            c.pre_filter_reason = reason
            if not ok:
                c.rejection_reason = reason
            return ok
        except Exception as e:
            logger.debug(f'[pipeline] pre_filter error: {e}')
            c.pre_filter_passed = True
            return True

    # ------------------------------------------------------------------
    # Stage 4: enrichment
    # ------------------------------------------------------------------

    def _stage_enrich(
        self,
        c: CandidateDict,
        use_hunter: bool = True,
        report: Optional[Any] = None,
    ) -> None:
        """
        Progressive enrichment:
        1. Contact-page scrape (free, uses CandidateCache)
        2. Hunter domain search (if domain known, score >= threshold)
        3. lead_fallback strategies
        """
        # Check domain cache first
        if self._cache and c.domain:
            cached_emails = self._cache.get_domain_emails(c.domain)
            if cached_emails is not None:
                if report:
                    report.cache_hits += 1
                if cached_emails and not c.email:
                    c.data['email'] = cached_emails[0]
                    c.data.setdefault('data_points', {})['email_source'] = 'domain_cache'
                c.enriched = True
                return

            if self._cache.is_failed_domain(c.domain):
                if report:
                    report.cache_hits += 1
                return

        # Hunter domain search
        if use_hunter and c.domain and not c.email:
            try:
                hunter = _import_hunter()
                if report:
                    report.record_api_call('hunter')
                results = hunter.domain_search(c.domain)
                if results:
                    if self._cache:
                        emails_found = [r.get('email', '') for r in results if r.get('email')]
                        self._cache.set_hunter_results(c.domain, results)
                        self._cache.set_domain_emails(c.domain, emails_found)
                    # Pick the best result (personal email preferred)
                    best = results[0]
                    if not c.email and best.get('email'):
                        c.data['email'] = best['email']
                        dp = c.data.setdefault('data_points', {})
                        dp['email_source']   = 'hunter'
                        dp['email_verified'] = True
                        # Merge other fields if missing
                        for fld in ('name', 'company', 'position', 'linkedin_url'):
                            if not c.data.get(fld) and best.get(fld):
                                c.data[fld] = best[fld]
                else:
                    if self._cache:
                        self._cache.mark_failed(c.domain)
            except Exception as e:
                logger.debug(f'[pipeline] Hunter enrich error for {c.domain}: {e}')

        # lead_fallback strategies (contact page scrape, name inference)
        try:
            enrich_lead_fallbacks = _import_lead_fallback()
            c.data = enrich_lead_fallbacks(
                c.data,
                scrape_contact=True,
                use_hunter=False,     # already called above
                generate_email=False, # never invent emails
                debug=False,
            )
            c.enriched = True
        except Exception as e:
            logger.debug(f'[pipeline] lead_fallback error: {e}')

    # ------------------------------------------------------------------
    # Stage 5: intent detection
    # ------------------------------------------------------------------

    def _stage_detect_intent(self, c: CandidateDict) -> None:
        raw_text = (
            c.data.get('data_points', {}).get('raw_text', '')
            or c.data.get('data_points', {}).get('post_text', '')
            or c.data.get('data_points', {}).get('search_snippet', '')
            or ''
        )
        if not raw_text:
            c.intent = {'buying_intent': 'none', 'intent_confidence': 0.0}
            return
        try:
            detect_intent, _ = _import_intent_detector()
            c.intent = detect_intent(
                str(raw_text),
                company=c.company,
                industry=c.data.get('industry'),
            )
        except Exception as e:
            logger.debug(f'[pipeline] intent detection error: {e}')
            c.intent = {'buying_intent': 'none', 'intent_confidence': 0.0}

    # ------------------------------------------------------------------
    # Stage 6: contact verification
    # ------------------------------------------------------------------

    def _stage_verify_contact(self, c: CandidateDict) -> None:
        if not c.email:
            return
        # MX cache check (free)
        if self._cache and c.domain:
            cached_mx = self._cache.get_mx(c.domain)
            if cached_mx is False:
                c.data.setdefault('data_points', {})['email_mx_valid'] = False
                return

        try:
            verify_email = _import_email_verifier()
            result = verify_email(c.email)
            dp = c.data.setdefault('data_points', {})
            if result.status == 'valid':
                dp['email_verified'] = True
                c.contact_verified = True
            elif result.status in ('invalid', 'spamtrap', 'abuse', 'do_not_mail'):
                dp['email_verified'] = False
                dp['zerobounce_status'] = result.status
            if self._cache and c.domain:
                self._cache.set_mx(c.domain, result.mx_valid)
        except Exception as e:
            logger.debug(f'[pipeline] email verify error: {e}')

    # ------------------------------------------------------------------
    # Stage 7: quality evaluation
    # ------------------------------------------------------------------

    def _stage_evaluate(self, c: CandidateDict, source: str, report: Any) -> Any:
        try:
            evaluate_lead_quality, _ = _import_quality_engine()
            return evaluate_lead_quality(c.data, source=source, report=None)
        except Exception as e:
            logger.warning(f'[pipeline] evaluate_lead_quality error: {e}')
            # Return a minimal fallback decision so the pipeline can continue
            return _FallbackDecision()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _estimate_pre_score(self, c: CandidateDict) -> float:
        """
        Cheap 0-100 estimate of a candidate's worth before any API calls.
        Used to gate whether enrichment API calls are worth making.
        """
        score = 0.0
        if c.email:
            score += 30.0
        if c.company:
            score += 20.0
        if c.name and ' ' in c.name:
            score += 15.0
        if c.data.get('phone'):
            score += 15.0
        if c.data.get('website'):
            score += 10.0
        if c.domain:
            score += 10.0
        return min(score, 100.0)

    # ------------------------------------------------------------------
    # Stage: AI strategy rejection signal check (no API)
    # ------------------------------------------------------------------

    def _stage_strategy_check(
        self,
        c: CandidateDict,
        strategy: Any,
        collection_type: str,
    ) -> bool:
        """
        Check candidate against CollectionStrategy rejection signals.
        No API call — all in memory.
        Returns True (keep) or False (drop).
        """
        from app.services.ai_collection_orchestrator import is_valid_candidate
        ok, reason = is_valid_candidate(c.data, strategy, collection_type=collection_type)
        if not ok:
            c.rejection_reason = reason
        return ok

    # ------------------------------------------------------------------
    # Stage 8: ML Qualification
    # ------------------------------------------------------------------

    def _stage_ml_qualify(
        self,
        c: CandidateDict,
        model: Any,
        extract_features: Any,
    ) -> bool:
        """
        Run XGBoost on the candidate BEFORE saving.
        Returns True (keep) or False (ML says discard).
        Only drops if BOTH quality score and ML score are very low.
        """
        try:
            features = extract_features(c.data)
            ml_score = model.predict(features)
            if ml_score is None:
                return True   # model can't score → pass through

            c.ml_score = float(ml_score)
            c.data.setdefault('data_points', {})['ml_score'] = ml_score

            # Hard discard only when both gates fail — don't over-trust ML alone
            combined = c.quality_score * 0.6 + ml_score * 0.4
            if combined < 12:
                c.rejection_reason = 'ml_discard'
                logger.debug(
                    f'[pipeline] ML discard: name={c.name} '
                    f'quality={c.quality_score:.0f} ml={ml_score:.0f} combined={combined:.0f}'
                )
                return False

            return True
        except Exception as e:
            logger.debug(f'[pipeline] ML qualify error: {e}')
            return True   # fail open

    # ------------------------------------------------------------------
    # Stage 9: Intelligence quick-check (rule-based, no LLM)
    # ------------------------------------------------------------------

    _B2B_NEGATIVE_SIGNALS = frozenset({
        'university', 'polytechnic', 'ministry', 'government', 'municipality',
        'embassy', 'consulate', 'parliament', 'public school', 'secondary school',
        'charity', 'ngo', 'humanitarian', 'non-profit', 'nonprofit',
        'national institute', 'public hospital', 'health authority',
    })
    _DIRECTORY_SIGNALS = frozenset({
        'yellow pages', 'yellowpages', 'white pages', 'whitepages',
        'directory', 'listings', 'yelp.com', 'google maps', 'tripadvisor',
    })

    def _stage_intelligence_check(self, c: CandidateDict) -> bool:
        """
        Fast rule-based intelligence check — no LLM, runs in memory.
        Uses anti_junk_engine + business_classifier for immediate hard rejects.
        Returns True (keep) or False (discard now).

        On exception, marks the lead needs_review and rejects (no unsafe fallback).
        """
        company_lower = c.company.lower()

        # Hard signal: company name matches known non-B2B patterns
        if any(sig in company_lower for sig in self._B2B_NEGATIVE_SIGNALS):
            if not c.name or ' ' not in c.name:
                c.rejection_reason = 'non_b2b_intelligence'
                return False

        # Hard signal: directory listing / aggregator website
        website = (c.data.get('website') or '').lower()
        if any(sig in website for sig in self._DIRECTORY_SIGNALS):
            c.rejection_reason = 'directory_listing'
            return False

        # People collection: must have a real person name
        if c.data.get('lead_type') == 'person' or c.data.get('source', '').startswith('web_people'):
            if not c.name or ' ' not in c.name:
                c.rejection_reason = 'no_person_name_people_collection'
                return False

        # Fast anti-junk check (no HTTP)
        try:
            from app.intelligence.anti_junk_engine import get_anti_junk_engine
            junk_result = get_anti_junk_engine().check(c.data)
            if not junk_result.passed:
                c.rejection_reason = f'anti_junk_{junk_result.rejection_reason}'
                c.data.setdefault('data_points', {})['intel_rejection'] = {
                    'stage': 'anti_junk_inline',
                    'reason': junk_result.rejection_reason,
                    'junk_score': junk_result.junk_score,
                }
                return False
        except Exception as exc:
            logger.debug('[pipeline] inline anti_junk check error: %s', exc)
            # On exception → needs_review, do NOT silently pass through
            c.rejection_reason = 'anti_junk_check_failed_needs_review'
            c.intel_action = 'REVIEW'
            c.data.setdefault('data_points', {})['intel_action_inline'] = 'REVIEW'
            return False

        c.intel_action = 'SAVE' if c.quality_score >= 35 else 'REVIEW'
        c.data.setdefault('data_points', {})['intel_action_inline'] = c.intel_action
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply_intent_to_lead(self, c: CandidateDict) -> None:
        """Write intent metadata back into the lead dict before saving."""
        if c.intent and c.intent.get('buying_intent', 'none') != 'none':
            dp = c.data.setdefault('data_points', {})
            dp['intent'] = c.intent
            # Merge interest_category into interests list
            cat = c.intent.get('interest_category', '')
            if cat:
                existing = c.data.get('interests') or []
                if isinstance(existing, str):
                    existing = [existing]
                if cat not in existing:
                    c.data['interests'] = existing + [cat]


# ---------------------------------------------------------------------------
# Minimal fallbacks used when imports fail at runtime
# ---------------------------------------------------------------------------

class _FallbackReport:
    """Minimal no-op report used when CollectionQualityReport can't be imported."""
    def __init__(self, source: str) -> None:
        self.source = source
        self.raw_candidates = 0
        self.enriched_candidates = 0
        self.rejected = 0
        self.saved = 0
        self.duplicates = 0
        self.intent_detected = 0
        self.cache_hits = 0
        self.rejection_reasons: Dict[str, int] = {}
        self._scores: List[float] = []
        self.verified_personal = 0
        self.company_generic = 0
        self.unverified = 0

    def record_api_call(self, _: str) -> None: pass
    def record_source(self, _: str) -> None: pass
    def record_score(self, s: float) -> None: self._scores.append(s)
    def log_summary(self) -> None:
        logger.info(
            f'[pipeline] source={self.source} raw={self.raw_candidates} '
            f'saved={self.saved} rejected={self.rejected}'
        )

    def to_dict(self) -> Dict[str, Any]:
        avg = round(sum(self._scores) / len(self._scores), 1) if self._scores else 0.0
        return {
            'source': self.source, 'raw_candidates': self.raw_candidates,
            'saved': self.saved, 'rejected': self.rejected,
            'duplicates': self.duplicates, 'average_quality_score': avg,
            'rejection_reasons': self.rejection_reasons,
        }


class _FallbackDecision:
    """Minimal decision object returned when evaluate_lead_quality fails."""
    decision     = 'reject'
    quality_score = 0.0
    tier         = 'rejected'
    reasons: List[str] = ['evaluation_error']
    metadata: Dict[str, Any] = {}
    should_save  = False
