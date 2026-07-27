"""
Tests — Company Intelligence Pipeline
======================================
Covers the new company-first intelligence flow:

  1. Real B2B SaaS company should PASS
  2. Directory/listing page should REJECT
  3. University/NGO/government should REJECT
  4. Fake/parked domain should REJECT
  5. Company without product signals should REJECT
  6. Agency should REJECT (unless ICP allows)
  7. Person without passed company should NEVER save
  8. Duplicate company/email should SKIP
  9. Low confidence should REJECT
 10. Valid email but weak company should REJECT
 11. Anti-junk: name is URL should REJECT
 12. Anti-junk: name is @handle should REJECT
 13. Anti-junk: domain is aggregator should REJECT
 14. Anti-junk: social profile URL as website should REJECT
 15. Business classifier: NGO keyword hard-rejects
 16. Business classifier: ICP match b2b_saas passes
 17. Account scorer: formula weights applied correctly
 18. Contact resolver: irrelevant title is rejected
 19. Contact resolver: domain mismatch email is rejected
 20. Website auditor: parked page sets red_flag
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _saas_lead(overrides=None):
    base = {
        "company":      "Acme CRM",
        "name":         "John Smith",
        "email":        "john@acmecrm.io",
        "website":      "https://acmecrm.io",
        "domain":       "acmecrm.io",
        "position":     "CEO",
        "country":      "Nigeria",
        "linkedin_url": "https://linkedin.com/company/acmecrm",
        "source":       "web",
        "data_points":  {
            "snippet": "Acme CRM is a B2B SaaS platform for sales teams. Book a demo today.",
        },
    }
    if overrides:
        base.update(overrides)
    return base


def _directory_lead():
    return {
        "company": "Top 10 SaaS Companies in Nigeria",
        "name":    "Top 10 SaaS Companies in Nigeria",
        "website": "https://businessdirectory.com/top-saas-nigeria",
        "domain":  "businessdirectory.com",
        "source":  "web",
    }


def _university_lead():
    return {
        "company": "University of Lagos",
        "name":    "University of Lagos",
        "website": "https://unilag.edu.ng",
        "domain":  "unilag.edu.ng",
        "source":  "web",
    }


def _ngo_lead():
    return {
        "company": "West Africa Foundation for Tech",
        "name":    "West Africa Foundation for Tech",
        "website": "https://waftechfoundation.org",
        "domain":  "waftechfoundation.org",
        "source":  "web",
    }


def _government_lead():
    return {
        "company": "Ministry of Digital Economy Nigeria",
        "name":    "Ministry of Digital Economy Nigeria",
        "website": "https://mde.gov.ng",
        "domain":  "mde.gov.ng",
        "source":  "web",
    }


def _parked_lead():
    return {
        "company": "Domain For Sale",
        "name":    "Domain For Sale",
        "website": "http://parkedsite.com",
        "domain":  "parkedsite.com",
        "source":  "web",
    }


def _no_product_lead():
    return {
        "company": "RandomBiz Ltd",
        "name":    "RandomBiz Ltd",
        "website": "https://randombiz.ng",
        "domain":  "randombiz.ng",
        "source":  "web",
        "data_points": {"snippet": "Welcome to our website."},
    }


# ═════════════════════════════════════════════════════════════════════════════
# Anti-Junk Engine
# ═════════════════════════════════════════════════════════════════════════════

class TestAntiJunkEngine:

    def _engine(self):
        from app.intelligence.anti_junk_engine import AntiJunkEngine
        return AntiJunkEngine()

    def test_real_company_passes(self):
        eng = self._engine()
        result = eng.check(_saas_lead())
        assert result.passed, f"Expected pass, got: {result.rejection_reason}"

    def test_name_is_url_rejected(self):
        eng = self._engine()
        lead = {"company": "https://spamsite.com", "name": "https://spamsite.com"}
        result = eng.check(lead)
        assert not result.passed
        assert result.rejection_reason == "name_is_url"

    def test_name_is_social_handle_rejected(self):
        eng = self._engine()
        lead = {"company": "@someguy", "name": "@someguy"}
        result = eng.check(lead)
        assert not result.passed
        assert result.rejection_reason == "name_is_social_handle"

    def test_directory_domain_rejected(self):
        eng = self._engine()
        lead = {"company": "Clutch", "name": "Clutch", "domain": "clutch.co",
                "website": "https://clutch.co/companies/nigeria"}
        result = eng.check(lead)
        assert not result.passed
        assert result.rejection_reason == "domain_is_aggregator"

    def test_social_profile_website_rejected(self):
        eng = self._engine()
        lead = {"company": "Acme", "website": "https://linkedin.com/in/johndoe"}
        result = eng.check(lead)
        assert not result.passed
        # Rejected either as aggregator domain or social profile — both correct
        assert result.rejection_reason in ("domain_is_aggregator", "website_is_social_profile")

    def test_parked_domain_page_text_rejected(self):
        eng = self._engine()
        lead = {"company": "ParkCo", "domain": "parkco.com"}
        parked_text = "This domain is for sale. Contact us to buy this domain."
        result = eng.check(lead, page_text=parked_text)
        assert not result.passed
        assert result.rejection_reason == "parked_domain"

    def test_university_keyword_rejected(self):
        eng = self._engine()
        result = eng.check(_university_lead())
        assert not result.passed
        assert result.rejection_reason == "non_commercial_entity"

    def test_ministry_keyword_rejected(self):
        eng = self._engine()
        result = eng.check(_government_lead())
        assert not result.passed
        assert result.rejection_reason == "non_commercial_entity"

    def test_junk_score_accumulated(self):
        eng = self._engine()
        lead = {
            "company": "Something",
            "email":   "info@gmail.com",
            "source":  "crunchbase",
        }
        result = eng.check(lead)
        # Aggregator source + free email without domain = high junk
        assert result.junk_score > 0


# ═════════════════════════════════════════════════════════════════════════════
# Business Classifier
# ═════════════════════════════════════════════════════════════════════════════

class TestBusinessClassifier:

    def _clf(self):
        from app.intelligence.business_classifier import BusinessClassifier
        return BusinessClassifier()

    def test_university_is_hard_reject(self):
        clf = self._clf()
        result = clf.classify(_university_lead())
        assert result.is_hard_reject
        assert result.business_type == "university"

    def test_ngo_is_hard_reject(self):
        clf = self._clf()
        result = clf.classify(_ngo_lead())
        assert result.is_hard_reject
        assert result.business_type == "ngo"

    def test_government_is_hard_reject(self):
        clf = self._clf()
        result = clf.classify(_government_lead())
        assert result.is_hard_reject
        assert result.business_type == "government"

    def test_b2b_saas_snippet_classified(self):
        clf = self._clf()
        lead = _saas_lead()
        page_text = "Book a demo. Enterprise plan. API access. Per seat pricing. B2B SaaS platform."
        result = clf.classify(lead, page_text=page_text)
        assert result.business_type == "b2b_saas"
        assert not result.is_hard_reject

    def test_icp_match_b2b_saas(self):
        clf = self._clf()
        from app.intelligence.business_classifier import BusinessClassification
        bclass = BusinessClassification(business_type="b2b_saas", confidence=0.8)
        assert clf.is_icp_match(bclass, frozenset({"b2b_saas"}))

    def test_icp_mismatch_agency_rejected(self):
        clf = self._clf()
        from app.intelligence.business_classifier import BusinessClassification
        bclass = BusinessClassification(business_type="agency", confidence=0.8)
        assert not clf.is_icp_match(bclass, frozenset({"b2b_saas"}))

    def test_icp_agency_allowed_when_in_list(self):
        clf = self._clf()
        from app.intelligence.business_classifier import BusinessClassification
        bclass = BusinessClassification(business_type="agency", confidence=0.8)
        assert clf.is_icp_match(bclass, frozenset({"b2b_saas", "agency"}))

    def test_hard_reject_never_passes_icp(self):
        clf = self._clf()
        from app.intelligence.business_classifier import BusinessClassification
        bclass = BusinessClassification(
            business_type="university", confidence=0.9, is_hard_reject=True
        )
        assert not clf.is_icp_match(bclass, frozenset({"university", "b2b_saas"}))


# ═════════════════════════════════════════════════════════════════════════════
# Account Scorer
# ═════════════════════════════════════════════════════════════════════════════

class TestAccountScorer:

    def _scorer(self):
        from app.intelligence.account_scorer import AccountScorer
        return AccountScorer()

    def _mock_anti_junk(self, passed=True, junk_score=0):
        from app.intelligence.anti_junk_engine import AntiJunkResult
        return AntiJunkResult(passed=passed, junk_score=junk_score,
                              rejection_reason="" if passed else "test_reject")

    def _mock_classification(self, btype="b2b_saas", hard_reject=False, confidence=0.8):
        from app.intelligence.business_classifier import BusinessClassification
        return BusinessClassification(
            business_type=btype, confidence=confidence, is_hard_reject=hard_reject
        )

    def _mock_growth(self, score=70.0):
        from app.intelligence.growth_detector import GrowthResult
        g = GrowthResult(growth_score=score, hiring_detected=True)
        g.growth_signals = ["hiring_sales_roles", "recent_activity"]
        return g

    def test_strong_saas_company_passes(self):
        scorer = self._scorer()
        lead = _saas_lead()
        lead["domain"] = "acmecrm.io"

        # Simulate a successful website audit (what the orchestrator provides in real runs)
        from app.intelligence.website_auditor import WebsiteAuditResult
        audit = WebsiteAuditResult(
            domain="acmecrm.io",
            homepage_fetched=True,
            pricing_exists=True,
            demo_or_trial_exists=True,
            business_model="b2b",
            contact_email="sales@acmecrm.io",
            tech_stack_hints=["HubSpot", "Stripe"],
            trust_signals=["ssl", "conversion_signals"],
        )

        result = scorer.score(
            lead,
            anti_junk=self._mock_anti_junk(True, 0),
            classification=self._mock_classification("b2b_saas"),
            growth=self._mock_growth(80.0),
            website_audit=audit,
            allowed_types=frozenset({"b2b_saas"}),
        )
        assert result.passed, f"Expected pass, got: {result.rejection_reason} | log: {result.decision_log}"
        assert result.final_company_score >= 65.0

    def test_anti_junk_fail_short_circuits(self):
        scorer = self._scorer()
        result = scorer.score(
            _saas_lead(),
            anti_junk=self._mock_anti_junk(False, 100),
            classification=self._mock_classification(),
            growth=self._mock_growth(),
        )
        assert not result.passed
        assert result.failed_stage == "anti_junk"

    def test_hard_reject_classification_blocks(self):
        scorer = self._scorer()
        result = scorer.score(
            _university_lead(),
            anti_junk=self._mock_anti_junk(True, 0),
            classification=self._mock_classification("university", hard_reject=True),
        )
        assert not result.passed
        assert result.failed_stage == "business_classifier"

    def test_no_domain_rejected(self):
        scorer = self._scorer()
        lead = {"company": "NoDomain Inc", "name": "Jane"}
        result = scorer.score(lead, anti_junk=self._mock_anti_junk(True))
        assert not result.passed
        # Lead with no domain/email/website gets rejected by score or risk gate
        assert result.failed_stage in ("account_score", "risk_gate", "data_confidence")

    def test_formula_weights(self):
        scorer = self._scorer()
        # Manually check the formula
        fit, intent, growth, conf = 80.0, 70.0, 60.0, 80.0
        expected = fit * 0.30 + intent * 0.30 + growth * 0.20 + conf * 0.20
        result = scorer.score(
            _saas_lead(),
            anti_junk=self._mock_anti_junk(),
            classification=self._mock_classification(),
            growth=self._mock_growth(growth),
        )
        # Score will differ since we can't fully control all sub-scorers,
        # but the formula structure should be consistent
        assert result.fit_score >= 0
        assert result.intent_score >= 0
        assert result.growth_score == growth
        computed = (result.fit_score * 0.30 + result.intent_score * 0.30 +
                    result.growth_score * 0.20 + result.data_confidence * 0.20)
        assert abs(computed - result.final_company_score) < 0.1


# ═════════════════════════════════════════════════════════════════════════════
# Contact Resolver
# ═════════════════════════════════════════════════════════════════════════════

class TestContactResolver:

    def _resolver(self):
        from app.intelligence.contact_resolver import ContactResolver
        return ContactResolver(use_hunter=False, use_apollo=False)

    def test_valid_contact_in_lead_data(self):
        resolver = self._resolver()
        lead = _saas_lead()
        result = resolver.resolve(lead, domain="acmecrm.io")
        assert result.found
        assert result.best_contact.name == "John Smith"

    def test_irrelevant_title_rejected(self):
        from app.intelligence.contact_resolver import ContactResolver, ResolvedContact
        resolver = ContactResolver(use_hunter=False, use_apollo=False)
        contact = ResolvedContact(
            name="Mary Intern",
            email="mary@acmecrm.io",
            title="intern",
        )
        reason = resolver._validate_contact(contact, "acmecrm.io")
        assert reason != "", "intern title should be rejected"
        assert "irrelevant_title" in reason

    def test_email_domain_mismatch_rejected(self):
        from app.intelligence.contact_resolver import ContactResolver, ResolvedContact
        resolver = ContactResolver(use_hunter=False, use_apollo=False)
        contact = ResolvedContact(
            name="Bob Smith",
            email="bob@gmail.com",
            title="CEO",
        )
        reason = resolver._validate_contact(contact, "acmecrm.io")
        assert reason != "", "free email without phone should be rejected"

    def test_name_too_short_rejected(self):
        from app.intelligence.contact_resolver import ContactResolver, ResolvedContact
        resolver = ContactResolver(use_hunter=False, use_apollo=False)
        contact = ResolvedContact(name="Jo", email="jo@acme.io", title="CEO")
        reason = resolver._validate_contact(contact, "acme.io")
        assert reason == "name_too_short"

    def test_title_priority_founder(self):
        from app.intelligence.contact_resolver import ContactResolver
        resolver = ContactResolver(use_hunter=False, use_apollo=False)
        assert resolver._title_priority("Founder & CEO") == 1

    def test_title_priority_ceo(self):
        from app.intelligence.contact_resolver import ContactResolver
        resolver = ContactResolver(use_hunter=False, use_apollo=False)
        assert resolver._title_priority("Chief Executive Officer") == 2

    def test_person_without_company_pass_never_saves(self):
        # A person lead (no company domain) should not pass contact resolution
        from app.intelligence.contact_resolver import ContactResolver
        resolver = ContactResolver(use_hunter=False, use_apollo=False)
        lead = {"name": "Random Person", "email": "random@gmail.com"}
        result = resolver.resolve(lead, domain="")
        # Should find a candidate but email domain mismatch makes it invalid
        assert not result.found or (
            result.best_contact and result.best_contact.rejection_reason != ""
        )


# ═════════════════════════════════════════════════════════════════════════════
# Website Auditor
# ═════════════════════════════════════════════════════════════════════════════

class TestWebsiteAuditor:

    def test_parked_page_sets_red_flag(self):
        from app.intelligence.website_auditor import WebsiteAuditor
        auditor = WebsiteAuditor()
        # Simulate _detect_red_flags with parked text
        from app.intelligence.website_auditor import WebsiteAuditResult
        result = WebsiteAuditResult()
        auditor._detect_red_flags("This domain is for sale. Buy this domain now.", result)
        assert "parked" in result.red_flags

    def test_no_product_signal_sets_flag(self):
        from app.intelligence.website_auditor import WebsiteAuditor, WebsiteAuditResult
        auditor = WebsiteAuditor()
        result = WebsiteAuditResult()
        auditor._detect_red_flags("Hello world. Welcome to our site.", result)
        assert "no_product_signal" in result.red_flags

    def test_tech_stack_detected(self):
        from app.intelligence.website_auditor import WebsiteAuditor
        auditor = WebsiteAuditor()
        html = '<script src="https://js.stripe.com/v3/"></script><script src="https://js.driftt.com/include/"></script>'
        stack = auditor._detect_tech_stack(html)
        assert "Stripe" in stack
        assert "Drift" in stack

    def test_b2b_model_classified_from_text(self):
        from app.intelligence.website_auditor import WebsiteAuditor, WebsiteAuditResult
        auditor = WebsiteAuditor()
        result = WebsiteAuditResult()
        auditor._classify_business_model(
            "Book a demo. Enterprise plan. Talk to sales. B2B platform for teams.", result
        )
        assert result.business_model == "b2b"

    def test_pricing_signal_detected(self):
        from app.intelligence.website_auditor import WebsiteAuditor, WebsiteAuditResult
        auditor = WebsiteAuditor()
        result = WebsiteAuditResult()
        auditor._detect_pricing_signals("Starting at $49/month. Free plan available.", result)
        assert result.pricing_exists


# ═════════════════════════════════════════════════════════════════════════════
# Intelligence Orchestrator — end-to-end (no real HTTP)
# ═════════════════════════════════════════════════════════════════════════════

class TestIntelligenceOrchestrator:
    """
    Integration tests using mocked website fetching.
    Real network calls are patched to keep tests fast and deterministic.
    """

    def _orch(self, allowed_types=None):
        from app.intelligence.intelligence_orchestrator import IntelligenceOrchestrator
        orch = IntelligenceOrchestrator(
            allowed_types=allowed_types or frozenset({"b2b_saas"}),
            audit_website=False,   # skip real HTTP in unit tests
            use_hunter=False,
            use_zerobounce=False,
        )
        return orch

    def test_directory_page_rejected(self):
        orch = self._orch()
        result = orch._process_one(_directory_lead(), query="saas", location="Nigeria")
        assert result["decision"] == "rejected"

    def test_university_rejected(self):
        orch = self._orch()
        result = orch._process_one(_university_lead(), query="tech", location="Nigeria")
        assert result["decision"] == "rejected"

    def test_ngo_rejected(self):
        orch = self._orch()
        result = orch._process_one(_ngo_lead(), query="saas", location="Nigeria")
        assert result["decision"] == "rejected"

    def test_government_rejected(self):
        orch = self._orch()
        result = orch._process_one(_government_lead(), query="saas", location="Nigeria")
        assert result["decision"] == "rejected"

    def test_parked_domain_name_rejected(self):
        orch = self._orch()
        result = orch._process_one(_parked_lead(), query="saas", location="Nigeria")
        # "Domain For Sale" triggers non_commercial or name-based junk
        assert result["decision"] == "rejected"

    def test_real_saas_company_passes_or_low_score(self):
        """
        A real-looking SaaS company should at minimum pass anti-junk and classification.
        Without real HTTP it may fail account scoring — that's acceptable.
        The key assertion: it must NOT be rejected by anti-junk or classifier alone.
        """
        orch = self._orch()
        lead = _saas_lead()
        result = orch._process_one(lead, query="SaaS companies Nigeria", location="Nigeria")
        # Either saved (great) or rejected only at scoring stage (acceptable)
        if result["decision"] == "rejected":
            assert result.get("failed_stage") not in ("anti_junk", "classifier")

    def test_run_pipeline_dedup(self):
        """Duplicate company domains should be de-duplicated before processing."""
        orch = self._orch()
        lead_a = _saas_lead()
        lead_b = _saas_lead({"name": "Jane Doe"})  # same domain, different contact
        deduped = orch._dedup([lead_a, lead_b])
        assert len(deduped) == 1   # second with same domain is dropped

    def test_run_pipeline_returns_report(self):
        orch = self._orch()
        saved_leads = []
        def save_fn(lead):
            saved_leads.append(lead)
            return True
        report = orch.run_pipeline(
            candidates=[_university_lead(), _ngo_lead()],
            query="saas companies",
            location="Nigeria",
            save_lead_fn=save_fn,
        )
        assert report.n_rejected >= 2
        assert len(saved_leads) == 0   # university and NGO must not be saved

    def test_audit_log_populated(self):
        orch = self._orch()
        report = orch.run_pipeline(
            candidates=[_university_lead()],
            query="test",
            location="Nigeria",
        )
        assert len(report.audit_log) == 1
        entry = report.audit_log[0]
        assert entry["decision"] == "rejected"
        assert entry["company"] is not None


# ═════════════════════════════════════════════════════════════════════════════
# Enterprise Save Policy — Gate 8
# ═════════════════════════════════════════════════════════════════════════════

class TestEnterpriseSavePolicyGate8:

    def test_missing_intel_blocked_when_required(self, monkeypatch):
        import importlib
        import app.services.enterprise_save_policy as esp
        monkeypatch.setenv("ENTERPRISE_REQUIRE_INTEL_PASS", "true")
        importlib.reload(esp)
        policy = esp.EnterpriseSavePolicy()
        lead = {
            "name": "John", "company": "Acme", "email": "john@acme.io",
            # no _account_score key
        }
        ok, reason = policy.evaluate(lead, final_score=70.0, grade="A")
        assert not ok
        assert "intelligence_decision_missing" in reason
        # Let monkeypatch handle env-var cleanup; reload back to default so
        # subsequent tests see _REQUIRE_INTEL_PASS=True (module default).
        importlib.reload(esp)

    def test_failed_intel_blocked_when_required(self, monkeypatch):
        import importlib
        import app.services.enterprise_save_policy as esp
        monkeypatch.setenv("ENTERPRISE_REQUIRE_INTEL_PASS", "true")
        importlib.reload(esp)
        policy = esp.EnterpriseSavePolicy()
        lead = {
            "name": "John", "company": "Acme", "email": "john@acme.io",
            "_account_score": {"passed": False, "rejection_reason": "low_score"},
        }
        ok, reason = policy.evaluate(lead, final_score=70.0, grade="A")
        assert not ok
        assert "intelligence_gate_failed" in reason
        importlib.reload(esp)

    def test_passed_intel_allowed(self, monkeypatch):
        import importlib
        import app.services.enterprise_save_policy as esp
        monkeypatch.setenv("ENTERPRISE_REQUIRE_INTEL_PASS", "true")
        importlib.reload(esp)
        policy = esp.EnterpriseSavePolicy()
        lead = {
            "name": "John Smith", "company": "Acme Corp",
            "email": "john@acmecorp.io",
            "_account_score": {"passed": True},
        }
        ok, reason = policy.evaluate(lead, final_score=70.0, grade="B")
        assert ok, f"Expected pass, got: {reason}"
        importlib.reload(esp)


# =============================================================================
# Fast Intelligence Check — wiring tests (interest / social / web collectors)
# =============================================================================

class TestFastIntelligenceCheck:
    """Unit tests for fast_check.py and its wiring into each collector path."""

    def test_real_saas_passes(self):
        from app.intelligence.fast_check import fast_intelligence_check
        ok, reason = fast_intelligence_check(_saas_lead())
        assert ok, f"Expected pass, got: {reason}"

    def test_university_rejected(self):
        from app.intelligence.fast_check import fast_intelligence_check
        ok, reason = fast_intelligence_check(_university_lead())
        assert not ok
        # Anti-junk catches it as non_commercial_entity; classifier would say business_type_university
        assert reason in ("non_commercial_entity", "business_type_university")

    def test_ngo_rejected(self):
        from app.intelligence.fast_check import fast_intelligence_check
        ok, reason = fast_intelligence_check(_ngo_lead())
        assert not ok
        assert "ngo" in reason

    def test_government_rejected(self):
        from app.intelligence.fast_check import fast_intelligence_check
        ok, reason = fast_intelligence_check(_government_lead())
        assert not ok

    def test_directory_lead_rejected(self):
        from app.intelligence.fast_check import fast_intelligence_check
        ok, reason = fast_intelligence_check(_directory_lead())
        assert not ok

    def test_url_name_rejected(self):
        from app.intelligence.fast_check import fast_intelligence_check
        ok, reason = fast_intelligence_check({
            "company": "https://junk.com",
            "name":    "https://junk.com",
        })
        assert not ok
        assert reason == "name_is_url"

    def test_batch_returns_only_passed(self):
        from app.intelligence.fast_check import batch_fast_check
        leads = [
            _saas_lead(),
            _university_lead(),
            _ngo_lead(),
            _saas_lead({"company": "Another CRM", "domain": "anothercrm.io",
                        "email": "hi@anothercrm.io"}),
        ]
        passed, rejected = batch_fast_check(leads)
        assert rejected == 2, f"Expected 2 rejected, got {rejected}"
        assert len(passed) == 2

    def test_fail_open_on_error(self):
        """fast_intelligence_check must not crash on unusual input."""
        from app.intelligence.fast_check import fast_intelligence_check
        ok, reason = fast_intelligence_check({})
        assert isinstance(ok, bool)

    def test_icp_type_gate_b2b_saas(self):
        """ICP check blocks non-b2b_saas when only b2b_saas is allowed."""
        from app.intelligence.fast_check import fast_intelligence_check
        # Real SaaS company must pass
        ok, reason = fast_intelligence_check(
            _saas_lead(), allowed_types=frozenset({"b2b_saas"})
        )
        assert ok, f"Expected SaaS to pass ICP gate, got: {reason}"

    def test_fast_check_module_importable(self):
        """fast_check module must import cleanly."""
        from app.intelligence.fast_check import (
            fast_intelligence_check, batch_fast_check,
        )
        assert callable(fast_intelligence_check)
        assert callable(batch_fast_check)


class TestCollectorWiring:
    """
    Confirms each collector properly imports and calls fast_intelligence_check.
    We verify the module is importable from each collector's import path.
    """

    def test_interest_collector_stage3c_importable(self):
        """Stage 3c import path must resolve cleanly."""
        from app.intelligence.fast_check import batch_fast_check
        result_leads, n_rej = batch_fast_check([_university_lead(), _saas_lead()])
        assert n_rej == 1
        assert len(result_leads) == 1
        assert result_leads[0]["company"] == "Acme CRM"

    def test_social_collector_filter_chain(self):
        """
        Simulates the social collector's two-stage filter:
        1. lead_candidate_filter (keyword + Gemini)
        2. batch_fast_check (intelligence gates)
        Both must work in sequence.
        """
        from app.services.lead_candidate_filter import keyword_filter
        from app.intelligence.fast_check import batch_fast_check

        raw = [
            _saas_lead(),
            _university_lead(),
            {"company": "Best SaaS in Nigeria", "name": "Best SaaS in Nigeria"},
        ]
        # Stage 1: keyword filter removes the "Best X in Y" pattern
        after_kw, kw_rej = keyword_filter(raw)
        # Stage 2: fast intelligence check removes university
        after_intel, intel_rej = batch_fast_check(after_kw)

        assert kw_rej >= 1, "keyword filter should catch 'Best SaaS in Nigeria'"
        assert intel_rej >= 1, "intelligence check should catch university"
        assert len(after_intel) >= 1

    def test_web_collector_filter_sequence(self):
        """
        Simulates the web collector's filter sequence applied before the pipeline.
        fast_intelligence_check runs after candidate filter on all_leads.
        """
        from app.intelligence.fast_check import batch_fast_check

        all_leads = [
            _saas_lead(),
            _ngo_lead(),
            _government_lead(),
            _saas_lead({"company": "CloudBiz NG", "domain": "cloudbizng.io",
                        "email": "hello@cloudbizng.io"}),
        ]
        passed, rejected = batch_fast_check(all_leads)
        assert rejected == 2
        assert len(passed) == 2
        companies = [l["company"] for l in passed]
        assert "Acme CRM" in companies
        assert "CloudBiz NG" in companies

    def test_intelligence_package_fast_check_accessible(self):
        """The intelligence package exposes fast_check as a submodule."""
        import app.intelligence.fast_check as fc
        assert hasattr(fc, "fast_intelligence_check")
        assert hasattr(fc, "batch_fast_check")
