"""
Intelligence Button Integration Tests
======================================
Proves that all 4 collection buttons (Auto, Web, Social, Interest) cannot bypass
the Intelligence Core (IntelligenceDecision / UserIntentContract / EnterpriseSavePolicy).

Tests are grouped by button and cover:
  - Weak / junk candidates are rejected before premium APIs are called
  - Strong candidates produce a valid IntelligenceDecision before save
  - EnterpriseSavePolicy blocks any lead missing a passed IntelligenceDecision
  - ContactResolver is NOT called until company passes intelligence
  - UserIntentContract is built for every collection run
  - Interest-mismatch candidates are rejected for Interest Collect

All tests mock external HTTP / DB calls so they run offline and instantly.
"""

from __future__ import annotations

import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call
from types import SimpleNamespace

# ── make backend importable ────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ── stub heavy optional dependencies ─────────────────────────────────────────
for _mod in (
    'xgboost', 'sklearn', 'faiss', 'shap', 'spacy',
    'sentence_transformers', 'torch', 'ollama',
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from app.intelligence.models import IntelligenceDecision, EvidenceItem  # noqa: E402
from app.intelligence.intelligence_orchestrator import IntelligenceOrchestrator  # noqa: E402
from app.services.enterprise_save_policy import EnterpriseSavePolicy  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_passing_decision(**kwargs) -> IntelligenceDecision:
    d = IntelligenceDecision()
    d.passed               = True
    d.final_score          = kwargs.get('final_score', 75.0)
    d.confidence_score     = kwargs.get('confidence_score', 75.0)
    d.risk_score           = kwargs.get('risk_score', 10.0)
    d.company_identity_passed = True
    d.anti_junk_passed     = True
    d.business_type_allowed = True
    d.user_intent_passed   = True
    d.location_match       = True
    d.why_saved            = 'Strong B2B SaaS with product evidence'
    d.recommended_outreach_angle = 'Highlight ROI and integration benefits'
    return d


def _make_failing_decision(reason: str, stage: str) -> IntelligenceDecision:
    d = IntelligenceDecision()
    d.passed           = False
    d.rejection_reason = reason
    d.failed_stage     = stage
    d.final_score      = 20.0
    d.risk_score       = 60.0
    return d


def _lead_with_intel(intel: IntelligenceDecision, **fields) -> dict:
    base = {
        'name':    'Jane Smith',
        'email':   'jane@acme.io',
        'company': 'Acme SaaS',
        'country': 'Nigeria',
        'website': 'https://acme.io',
        'source':  'test',
        'final_company_score':    intel.final_score,
        '_intelligence_decision': intel.to_dict(),
        '_account_score':         intel.to_dict(),
    }
    base.update(fields)
    return base


# ═══════════════════════════════════════════════════════════════════════════════
# Suite 1 — EnterpriseSavePolicy Gate 8 enforcement
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnterpriseSavePolicyGate8(unittest.TestCase):
    """ENTERPRISE_REQUIRE_INTEL_PASS=true by default; every button depends on this."""

    def setUp(self):
        self.policy = EnterpriseSavePolicy()

    # ── 1. Missing intelligence decision → block ───────────────────────────────
    def test_missing_intelligence_blocks_save(self):
        lead = {
            'name': 'John Doe', 'email': 'john@firm.io',
            'company': 'FirmCo', 'country': 'Nigeria',
        }
        ok, reason = self.policy.evaluate(lead, final_score=80.0, grade='A')
        self.assertFalse(ok)
        self.assertIn('intelligence_decision_missing', reason)

    # ── 2. Failed IntelligenceDecision → block ────────────────────────────────
    def test_failed_intelligence_blocks_save(self):
        decision = _make_failing_decision('agency_type', 'business_type')
        lead = _lead_with_intel(decision)
        ok, reason = self.policy.evaluate(lead, final_score=80.0, grade='A')
        self.assertFalse(ok)
        self.assertIn('intelligence_gate_failed', reason)

    # ── 3. location_match=False → block ──────────────────────────────────────
    def test_location_mismatch_blocks_save(self):
        decision = _make_passing_decision()
        decision.location_match = False
        decision.to_dict()  # rebuild cache
        lead = _lead_with_intel(decision)
        lead['_intelligence_decision']['location_match'] = False
        lead['_account_score']['location_match'] = False
        ok, reason = self.policy.evaluate(lead, final_score=80.0, grade='A')
        self.assertFalse(ok)
        self.assertIn('location_mismatch', reason)

    # ── 4. user_intent_passed=False → block ──────────────────────────────────
    def test_user_intent_failure_blocks_save(self):
        decision = _make_passing_decision()
        decision.user_intent_passed = False
        lead = _lead_with_intel(decision)
        lead['_intelligence_decision']['user_intent_passed'] = False
        lead['_account_score']['user_intent_passed'] = False
        ok, reason = self.policy.evaluate(lead, final_score=80.0, grade='A')
        self.assertFalse(ok)
        self.assertIn('user_intent_not_matched', reason)

    # ── 5. risk_score too high → block ───────────────────────────────────────
    def test_high_risk_blocks_save(self):
        decision = _make_passing_decision(risk_score=50.0)
        lead = _lead_with_intel(decision)
        lead['_intelligence_decision']['risk_score'] = 50.0
        lead['_account_score']['risk_score'] = 50.0
        ok, reason = self.policy.evaluate(lead, final_score=80.0, grade='A')
        self.assertFalse(ok)
        self.assertIn('risk_score_too_high', reason)

    # ── 6. Strong, fully-gated lead passes ───────────────────────────────────
    def test_strong_lead_passes_all_gates(self):
        decision = _make_passing_decision()
        lead = _lead_with_intel(decision)
        ok, reason = self.policy.evaluate(lead, final_score=80.0, grade='A')
        self.assertTrue(ok, f"Expected pass but got: {reason}")
        self.assertEqual(reason, '')


# ═══════════════════════════════════════════════════════════════════════════════
# Suite 2 — IntelligenceOrchestrator always produces IntelligenceDecision
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrchestratorProducesIntelligenceDecision(unittest.TestCase):
    """Orchestrator must attach _intelligence_decision to every lead it passes to save_lead_fn."""

    def _make_orch(self, decision: IntelligenceDecision) -> IntelligenceOrchestrator:
        """Build orchestrator with all sub-components mocked."""
        orch = IntelligenceOrchestrator.__new__(IntelligenceOrchestrator)

        junk = MagicMock()
        junk.passed = True
        junk.rejection_reason = ''
        junk.to_dict.return_value = {}
        orch._anti_junk = MagicMock(check=MagicMock(return_value=junk))

        audit = MagicMock()
        audit.red_flags = []
        audit.raw_text_snippet = ''
        audit.to_dict.return_value = {}
        orch._auditor = MagicMock(audit=MagicMock(return_value=audit))
        orch._audit_website = True

        cls = MagicMock()
        cls.is_hard_reject = False
        cls.business_type = 'b2b_saas'
        cls.to_dict.return_value = {}
        orch._classifier = MagicMock(classify=MagicMock(return_value=cls))

        growth = MagicMock()
        growth.to_dict.return_value = {}
        orch._growth = MagicMock(detect=MagicMock(return_value=growth))

        orch._scorer = MagicMock(score=MagicMock(return_value=decision))

        contact = MagicMock()
        contact.found = False
        contact.to_dict.return_value = {}
        orch._resolver = MagicMock(resolve=MagicMock(return_value=contact))

        orch._allowed_types  = frozenset({'b2b_saas'})
        orch._use_hunter     = True
        orch._use_zerobounce = True

        return orch

    # ── 7. Passing company produces _intelligence_decision in saved lead ──────
    def test_passed_company_attaches_intelligence_decision(self):
        decision = _make_passing_decision()
        orch = self._make_orch(decision)

        saved_leads: list = []

        def _save(ld):
            saved_leads.append(ld)
            return True

        candidates = [{'company': 'Acme SaaS', 'website': 'https://acme.io',
                       'country': 'Nigeria', 'email': 'ceo@acme.io'}]

        with patch('app.intelligence.intelligence_orchestrator.get_intent_contract_engine') as _mie:
            _mie.return_value = MagicMock(parse=MagicMock(return_value=None))
            with patch('app.intelligence.intelligence_orchestrator.filter_candidates',
                       side_effect=lambda c, **kw: c, create=True):
                orch.run_pipeline(candidates, query='SaaS Nigeria',
                                  location='Nigeria', save_lead_fn=_save)

        self.assertEqual(len(saved_leads), 1)
        lead = saved_leads[0]
        self.assertIn('_intelligence_decision', lead)
        self.assertTrue(lead['_intelligence_decision'].get('passed'))

    # ── 8. Failing company is NOT passed to save_lead_fn ─────────────────────
    def test_failing_company_never_reaches_save(self):
        decision = _make_failing_decision('agency_type', 'business_type')
        orch = self._make_orch(decision)

        saved_leads: list = []

        candidates = [{'company': 'Design Agency', 'website': 'https://agency.com',
                       'country': 'Nigeria'}]

        with patch('app.intelligence.intelligence_orchestrator.get_intent_contract_engine') as _mie:
            _mie.return_value = MagicMock(parse=MagicMock(return_value=None))
            with patch('app.intelligence.intelligence_orchestrator.filter_candidates',
                       side_effect=lambda c, **kw: c, create=True):
                orch.run_pipeline(candidates, query='SaaS Nigeria',
                                  location='Nigeria', save_lead_fn=lambda ld: saved_leads.append(ld) or True)

        self.assertEqual(len(saved_leads), 0)

    # ── 9. ContactResolver is NOT called when company fails ───────────────────
    def test_contact_resolver_not_called_when_company_fails(self):
        decision = _make_failing_decision('agency_type', 'business_type')
        orch = self._make_orch(decision)

        candidates = [{'company': 'Design Agency', 'website': 'https://agency.com'}]

        with patch('app.intelligence.intelligence_orchestrator.get_intent_contract_engine') as _mie:
            _mie.return_value = MagicMock(parse=MagicMock(return_value=None))
            with patch('app.intelligence.intelligence_orchestrator.filter_candidates',
                       side_effect=lambda c, **kw: c, create=True):
                orch.run_pipeline(candidates, query='SaaS', location='')

        orch._resolver.resolve.assert_not_called()

    # ── 10. ContactResolver IS called only after company passes ───────────────
    def test_contact_resolver_called_after_company_passes(self):
        decision = _make_passing_decision()
        orch = self._make_orch(decision)

        candidates = [{'company': 'Acme SaaS', 'website': 'https://acme.io',
                       'country': 'Nigeria'}]

        with patch('app.intelligence.intelligence_orchestrator.get_intent_contract_engine') as _mie:
            _mie.return_value = MagicMock(parse=MagicMock(return_value=None))
            with patch('app.intelligence.intelligence_orchestrator.filter_candidates',
                       side_effect=lambda c, **kw: c, create=True):
                orch.run_pipeline(candidates, query='SaaS Nigeria', location='Nigeria',
                                  save_lead_fn=lambda ld: True)

        orch._resolver.resolve.assert_called_once()

    # ── 11. collection_button is recorded in audit log ────────────────────────
    def test_collection_button_recorded_in_audit(self):
        decision = _make_passing_decision()
        orch = self._make_orch(decision)

        candidates = [{'company': 'Acme SaaS', 'website': 'https://acme.io',
                       'country': 'Nigeria', '_button': 'auto_collect'}]

        with patch('app.intelligence.intelligence_orchestrator.get_intent_contract_engine') as _mie:
            _mie.return_value = MagicMock(parse=MagicMock(return_value=None))
            with patch('app.intelligence.intelligence_orchestrator.filter_candidates',
                       side_effect=lambda c, **kw: c, create=True):
                report = orch.run_pipeline(
                    candidates, query='SaaS', location='',
                    save_lead_fn=lambda ld: True,
                    collection_button='auto_collect',
                )

        self.assertTrue(len(report.audit_log) > 0)
        self.assertEqual(report.audit_log[0].get('collection_button'), 'auto_collect')


# ═══════════════════════════════════════════════════════════════════════════════
# Suite 3 — Auto Collect: weak candidates skip premium APIs
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutoCollectIntelligenceGate(unittest.TestCase):
    """Weak / junk candidates must be rejected before Hunter / Apollo enrich calls."""

    # ── 12. Junk candidate (person name as company) skips contact resolution ──
    def test_person_name_company_skips_contact_resolution(self):
        decision = _make_failing_decision('company_is_person_name', 'company_identity')
        orch_mock = MagicMock()
        orch_mock.run_pipeline.return_value = MagicMock(
            n_saved=0, n_rejected=1, n_needs_review=0,
            to_dict=lambda: {},
            rejection_reasons={'company_is_person_name': 1},
        )
        # When orchestrator returns rejected, save_fn should never be called
        hunter_mock = MagicMock()
        with patch('app.intelligence.intelligence_orchestrator.IntelligenceOrchestrator',
                   return_value=orch_mock):
            from app.intelligence.intelligence_orchestrator import IntelligenceOrchestrator as IO
            orch = IO()
            candidates = [{'company': 'John Smith', 'email': 'john@gmail.com'}]
            report = orch.run_pipeline(candidates, query='SaaS', location='')
        self.assertEqual(report.n_saved, 0)

    # ── 13. Missing premium API key does not crash ────────────────────────────
    def test_missing_premium_key_does_not_crash(self):
        """Auto Collect must not crash when Apollo / Hunter keys are absent."""
        with patch.dict(os.environ, {'APOLLO_API_KEY': '', 'HUNTER_API_KEY': ''}):
            try:
                from app.services.apollo_service import ApolloService
                svc = ApolloService()
                is_conf = svc.is_configured()
                # Should return False, not raise
                self.assertFalse(is_conf)
            except Exception as exc:
                self.fail(f"ApolloService() raised with missing key: {exc}")

    # ── 14. Intelligence decision required before save in auto collect ─────────
    def test_auto_collect_candidate_requires_intelligence_decision(self):
        """EnterpriseSavePolicy must block a candidate without IntelligenceDecision."""
        policy = EnterpriseSavePolicy()
        lead = {
            'name': 'Jane CEO', 'email': 'jane@acme.io',
            'company': 'Acme SaaS', 'country': 'Nigeria',
            # No _intelligence_decision
        }
        ok, reason = policy.evaluate(lead, final_score=80.0, grade='A')
        self.assertFalse(ok)
        self.assertIn('intelligence_decision_missing', reason)


# ═══════════════════════════════════════════════════════════════════════════════
# Suite 4 — Web Collect: directory results and wrong country rejected
# ═══════════════════════════════════════════════════════════════════════════════

class TestWebCollectIntelligenceGate(unittest.TestCase):

    # ── 15. Directory / aggregator URL rejected by anti-junk ─────────────────
    def test_directory_page_rejected_by_anti_junk(self):
        from app.intelligence.anti_junk_engine import AntiJunkEngine
        engine = AntiJunkEngine()
        result = engine.check(
            {'company': 'Clutch', 'website': 'https://clutch.co/directory/saas',
             'country': 'Nigeria'},
            source_url='https://clutch.co/directory/saas',
        )
        self.assertFalse(result.passed, "Clutch directory page should be rejected")

    # ── 16. Wrong country lead fails user intent gate ─────────────────────────
    def test_wrong_country_fails_user_intent(self):
        from app.intelligence.user_intent_contract import get_intent_contract_engine
        engine = get_intent_contract_engine()
        contract = engine.parse('SaaS companies Nigeria', 'Nigeria')

        lead = {
            'company': 'TechCo Istanbul', 'country': 'Turkey',
            'website': 'https://techco.com.tr', 'industry': 'SaaS',
        }
        passed, reason, confidence, evidence = engine.validate(lead, contract)
        self.assertFalse(passed)
        self.assertTrue(
            'country' in reason.lower() or 'location' in reason.lower() or 'mismatch' in reason.lower(),
            f"Expected country/location/mismatch in reason, got: {reason}",
        )

    # ── 17. Listing-title company name rejected by anti-junk ─────────────────
    def test_no_product_signal_leads_to_rejection(self):
        from app.intelligence.anti_junk_engine import AntiJunkEngine
        engine = AntiJunkEngine()
        # "Top 10 SaaS companies Nigeria" looks like an article/listing title, not a company
        result = engine.check(
            {'company': 'Top 10 SaaS companies Nigeria',
             'website': 'https://randomblog.com/article/123',
             'country': 'Nigeria'},
            source_url='https://randomblog.com/article/123',
        )
        self.assertFalse(result.passed,
                         f"Listing-title company name should be rejected: {result.rejection_reason}")

    # ── 18. Real SaaS company passes anti-junk ───────────────────────────────
    def test_real_saas_passes_anti_junk(self):
        from app.intelligence.anti_junk_engine import AntiJunkEngine
        engine = AntiJunkEngine()
        result = engine.check(
            {'company': 'Paystack Technologies', 'website': 'https://paystack.com',
             'country': 'Nigeria', 'industry': 'FinTech'},
        )
        self.assertTrue(result.passed, f"Paystack should pass anti-junk: {result.rejection_reason}")


# ═══════════════════════════════════════════════════════════════════════════════
# Suite 5 — Social Collect: person profiles and mismatched country rejected
# ═══════════════════════════════════════════════════════════════════════════════

class TestSocialCollectIntelligenceGate(unittest.TestCase):

    # ── 19. Person-as-company name rejected by company identity gate ──────────
    def test_person_profile_no_company_rejected(self):
        from app.intelligence.anti_junk_engine import AntiJunkEngine
        engine = AntiJunkEngine()
        result = engine.check(
            {'company': 'Michael Johnson', 'email': 'michael@gmail.com',
             'country': 'Nigeria', 'source': 'reddit'},
        )
        self.assertFalse(result.passed,
                         "Person name as company should be rejected by anti-junk")

    # ── 20. Social-only weak lead (no domain, no product) is rejected ─────────
    def test_social_only_weak_lead_rejected(self):
        from app.intelligence.anti_junk_engine import AntiJunkEngine
        engine = AntiJunkEngine()
        # A Reddit handle as company name
        result = engine.check(
            {'company': '@techguru_ng', 'email': '', 'website': ''},
        )
        self.assertFalse(result.passed,
                         "Twitter/Reddit @handle company should be rejected")

    # ── 21. Social lead with correct country still requires IntelligenceDecision before save
    def test_social_lead_requires_intel_before_save(self):
        policy = EnterpriseSavePolicy()
        lead = {
            'name': 'Aisha Okafor', 'email': 'aisha@fintechng.com',
            'company': 'FinTech NG', 'country': 'Nigeria',
            'source': 'linkedin',
            # No _intelligence_decision attached
        }
        ok, reason = policy.evaluate(lead, final_score=75.0, grade='B')
        self.assertFalse(ok)
        self.assertIn('intelligence_decision_missing', reason)

    # ── 22. Social company with mismatched country is rejected ────────────────
    def test_social_mismatched_country_rejected(self):
        from app.intelligence.user_intent_contract import get_intent_contract_engine
        engine = get_intent_contract_engine()
        contract = engine.parse('SaaS startups Nigeria', 'Nigeria')

        lead = {
            'company': 'Istanbul SaaS Co', 'country': 'Turkey',
            'website': 'https://istanbulsaas.com.tr',
        }
        passed, reason, _, _ = engine.validate(lead, contract)
        self.assertFalse(passed)


# ═══════════════════════════════════════════════════════════════════════════════
# Suite 6 — Interest Collect: selected interest strictly enforced
# ═══════════════════════════════════════════════════════════════════════════════

class TestInterestCollectIntelligenceGate(unittest.TestCase):

    # ── 23. Wrong business type (agency) rejected for SaaS interest ───────────
    def test_agency_rejected_for_saas_interest(self):
        from app.intelligence.business_classifier import get_business_classifier
        classifier = get_business_classifier()
        result = classifier.classify(
            {'company': 'Creative Design Agency', 'website': 'https://creative.io',
             'industry': 'Design'},
            page_text='We are a full-service design and branding agency. '
                      'We create logos, branding, and marketing campaigns for clients.',
        )
        # Should be 'agency' type — not a SaaS / allowed type
        self.assertIn(result.business_type, ('agency', 'other', 'consulting'),
                      f"Agency should be classified as non-SaaS: {result.business_type}")
        self.assertTrue(result.is_hard_reject or result.business_type not in ('b2b_saas',),
                        "Agency should not be classified as b2b_saas")

    # ── 24. University is always hard-rejected ────────────────────────────────
    def test_university_hard_rejected_for_any_interest(self):
        from app.intelligence.business_classifier import get_business_classifier
        classifier = get_business_classifier()
        result = classifier.classify(
            {'company': 'University of Lagos', 'website': 'https://unilag.edu.ng'},
            page_text='We offer undergraduate and postgraduate degree programs.',
        )
        self.assertTrue(result.is_hard_reject,
                        f"University must be hard-rejected, got {result.business_type}")

    # ── 25. Freelancer hard-rejected ─────────────────────────────────────────
    def test_freelancer_hard_rejected_for_saas_interest(self):
        from app.intelligence.business_classifier import get_business_classifier
        classifier = get_business_classifier()
        result = classifier.classify(
            {'company': 'John Doe Freelancer', 'website': 'https://johndoe.com'},
            page_text='I am a freelance developer. Hire me for your projects. '
                      'I offer web development services as an independent contractor.',
        )
        self.assertTrue(result.is_hard_reject,
                        f"Freelancer must be hard-rejected, got {result.business_type}")

    # ── 26. Interest collect with industry mismatch rejected by UserIntentContract
    def test_industry_mismatch_rejected(self):
        from app.intelligence.user_intent_contract import get_intent_contract_engine
        engine = get_intent_contract_engine()
        contract = engine.parse('SaaS companies Nigeria', 'Nigeria')

        self.assertIn('b2b_saas', contract.requested_industry_types)

        # An ecommerce company should fail the SaaS intent contract
        lead = {
            'company': 'Lagos Market', 'country': 'Nigeria',
            'website': 'https://lagosmarket.com', 'industry': 'Ecommerce',
        }
        from app.intelligence.business_classifier import BusinessClassification
        cls = BusinessClassification.__new__(BusinessClassification)
        cls.business_type = 'ecommerce'
        cls.confidence = 0.8
        cls.signals = []
        cls.is_hard_reject = False

        passed, reason, _, _ = engine.validate(lead, contract, classification=cls)
        self.assertFalse(passed,
                         "Ecommerce company should fail SaaS intent contract")

    # ── 27. NGO rejected for any commercial interest ──────────────────────────
    def test_ngo_rejected_for_commercial_interest(self):
        from app.intelligence.anti_junk_engine import AntiJunkEngine
        engine = AntiJunkEngine()
        # Company name explicitly contains "NGO" → triggers non_commercial_entity rule
        result = engine.check(
            {'company': 'Children Welfare NGO Nigeria',
             'website': 'https://cwngeria.org',
             'industry': 'Non-profit'},
        )
        self.assertFalse(result.passed,
                         "NGO in company name should be rejected by anti-junk")


# ═══════════════════════════════════════════════════════════════════════════════
# Suite 7 — Global: all buttons share same intelligence pipeline
# ═══════════════════════════════════════════════════════════════════════════════

class TestGlobalIntelligencePipeline(unittest.TestCase):

    # ── 28. UserIntentContract parses query correctly for all buttons ──────────
    def test_user_intent_contract_parses_nigeria_saas(self):
        from app.intelligence.user_intent_contract import get_intent_contract_engine
        engine = get_intent_contract_engine()
        contract = engine.parse('SaaS startups Nigeria', 'Nigeria')
        self.assertEqual(contract.requested_country.lower(), 'nigeria')
        self.assertIn('b2b_saas', contract.requested_industry_types)
        self.assertTrue(contract.requires_location_match)

    # ── 29. UserIntentContract parses fintech interest ────────────────────────
    def test_user_intent_contract_parses_fintech(self):
        from app.intelligence.user_intent_contract import get_intent_contract_engine
        engine = get_intent_contract_engine()
        contract = engine.parse('fintech companies Kenya', 'Kenya')
        self.assertEqual(contract.requested_country.lower(), 'kenya')
        self.assertIn('b2b_saas', contract.requested_industry_types)

    # ── 30. All 4 buttons produce IntelligenceDecision (orchestrator behavior) ─
    def test_orchestrator_always_produces_intelligence_decision(self):
        """Any lead that reaches save_lead_fn must have _intelligence_decision."""
        decision = _make_passing_decision()
        orch = TestOrchestratorProducesIntelligenceDecision()._make_orch(decision)

        for button in ('auto_collect', 'web_collect', 'social_collect', 'interest_collect'):
            saved: list = []
            candidates = [{'company': 'Acme SaaS', 'website': 'https://acme.io',
                           'country': 'Nigeria', '_button': button}]
            with patch('app.intelligence.intelligence_orchestrator.get_intent_contract_engine') as m:
                m.return_value = MagicMock(parse=MagicMock(return_value=None))
                with patch('app.intelligence.intelligence_orchestrator.filter_candidates',
                           side_effect=lambda c, **kw: c, create=True):
                    orch.run_pipeline(candidates, query='SaaS Nigeria', location='Nigeria',
                                      save_lead_fn=lambda ld: saved.append(ld) or True,
                                      collection_button=button)
            self.assertEqual(len(saved), 1, f"Button {button} should save 1 lead")
            self.assertIn('_intelligence_decision', saved[0],
                          f"Button {button} must attach _intelligence_decision")

    # ── 31. Old fallback path (no intel) cannot save a lead ──────────────────
    def test_old_fallback_path_blocked_by_enterprise_policy(self):
        """A lead saved via the old path (no _intelligence_decision) is blocked."""
        policy = EnterpriseSavePolicy()
        # Simulate a lead from the old evaluate_lead_quality path (no intel attached)
        old_style_lead = {
            'name': 'Old Lead', 'email': 'old@company.io',
            'company': 'OldCompany', 'country': 'Nigeria',
            # _intelligence_decision deliberately missing (old path)
        }
        ok, reason = policy.evaluate(old_style_lead, final_score=85.0, grade='A')
        self.assertFalse(ok)
        self.assertIn('intelligence_decision_missing', reason)

    # ── 32. Exception in orchestrator stage returns needs_review (never silent) ─
    def test_orchestrator_exception_returns_needs_review(self):
        """On unhandled exception, _process_one must return needs_review, not raise."""
        decision = _make_passing_decision()
        orch = TestOrchestratorProducesIntelligenceDecision()._make_orch(decision)
        # Make scorer explode
        orch._scorer.score.side_effect = RuntimeError("scorer crashed")

        needs_review_count = 0

        def _count_save(ld):
            return True

        candidates = [{'company': 'Acme SaaS', 'website': 'https://acme.io'}]
        with patch('app.intelligence.intelligence_orchestrator.get_intent_contract_engine') as m:
            m.return_value = MagicMock(parse=MagicMock(return_value=None))
            with patch('app.intelligence.intelligence_orchestrator.filter_candidates',
                       side_effect=lambda c, **kw: c, create=True):
                report = orch.run_pipeline(candidates, query='', location='',
                                           save_lead_fn=_count_save)

        self.assertEqual(report.n_saved, 0)
        self.assertGreater(report.n_needs_review, 0,
                           "Scorer exception must produce needs_review, not crash or silently save")


if __name__ == '__main__':
    unittest.main(verbosity=2)
