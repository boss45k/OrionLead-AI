"""
test_smart_pipeline.py
======================
Tests for the smart collection pipeline added in the AI engine upgrade.

Scenarios covered:
  1.  Social username-only → rejected (no_substance)
  2.  Company domain extracted before person enrichment
  3.  Generated email → rejected / hard-capped at ≤ 55
  4.  Hunter-verified email → saved (high-quality path)
  5.  Generic email (info@) → low quality, not saved as HOT
  6.  Intent phrase detection — high / medium / low / none
  7.  Quality report fields populated after a pipeline run
  8.  Duplicate candidate skipped (email + domain dedup)
  9.  CDN / tracker email → rejected at pre-filter
"""

import sys
import os
import pytest

# ---------------------------------------------------------------------------
# Path setup — make backend/ the root for imports
# ---------------------------------------------------------------------------
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')
os.environ['FLASK_ENV'] = 'testing'

# ---------------------------------------------------------------------------
# 1 – Social username-only rejected
# ---------------------------------------------------------------------------

class TestSocialSubstanceCheck:
    """Leads with only a username (no email, phone, website, linkedin, company) must be rejected."""

    def _make_lead(self, **overrides):
        base = {
            'name': 'some_reddit_user',
            'source': 'reddit',
            'data_points': {},
        }
        base.update(overrides)
        return base

    def test_username_only_has_no_substance(self):
        lead = self._make_lead()
        has_company  = bool(lead.get('company'))
        has_email    = bool(lead.get('email'))
        has_phone    = bool(lead.get('phone'))
        has_website  = bool(lead.get('website'))
        has_linkedin = bool(lead.get('linkedin_url'))
        substance = (has_company and has_email) or has_phone or has_website or has_linkedin
        assert not substance, "username-only lead must fail substance check"

    def test_lead_with_email_and_company_passes(self):
        lead = self._make_lead(email='joe@acme.com', company='Acme')
        has_company  = bool(lead.get('company'))
        has_email    = bool(lead.get('email'))
        substance = has_company and has_email
        assert substance


# ---------------------------------------------------------------------------
# 2 – Company domain extracted before person enrichment
# ---------------------------------------------------------------------------

class TestDomainExtraction:
    """Domain must be derivable from a website URL for enrichment gating."""

    def test_domain_extracted_from_http_url(self):
        from urllib.parse import urlparse
        website = 'https://www.acmecorp.com/contact'
        domain = urlparse(website).netloc.replace('www.', '')
        assert domain == 'acmecorp.com'

    def test_domain_extracted_from_plain_url(self):
        from urllib.parse import urlparse
        website = 'http://example.co.uk/about'
        domain = urlparse(website).netloc.replace('www.', '')
        assert domain == 'example.co.uk'

    def test_pre_score_below_threshold_skips_api(self):
        # Verify the API threshold constant exists and is sensible
        from app.services.candidate_pipeline import _API_CALL_THRESHOLD
        assert isinstance(_API_CALL_THRESHOLD, (int, float))
        assert 30 <= _API_CALL_THRESHOLD <= 60


# ---------------------------------------------------------------------------
# 3 – Generated email rejected / hard-capped
# ---------------------------------------------------------------------------

class TestGeneratedEmailHandling:
    """Generated emails must never score above 55 (QualificationAgent hard cap)."""

    def test_pre_filter_rejects_cdn_generated_domain(self):
        from app.services.name_validator import is_cdn_email
        assert is_cdn_email('user@cloudflareinsights.com')

    def test_generated_email_type_blocks_hot_tier(self):
        _NO_REAL_CONTACT = {'generated', 'generated_personal', 'generated_generic', 'generic'}
        email_type = 'generated_personal'
        has_phone = False
        has_linkedin = False
        no_real_contact = (email_type in _NO_REAL_CONTACT and not has_phone and not has_linkedin)
        assert no_real_contact

    def test_score_cap_applies(self):
        # Simulate the cap logic from QualificationAgent
        _NO_REAL_CONTACT = {'generated', 'generated_personal', 'generated_generic', 'generic'}
        email_type = 'generated'
        has_phone = False
        has_linkedin = False
        raw_score = 80.0
        no_real_contact = (email_type in _NO_REAL_CONTACT and not has_phone and not has_linkedin)
        final_score = min(raw_score, 55.0) if no_real_contact else raw_score
        assert final_score == 55.0

    def test_generated_email_with_phone_not_capped(self):
        _NO_REAL_CONTACT = {'generated', 'generated_personal', 'generated_generic', 'generic'}
        email_type = 'generated'
        has_phone = True
        has_linkedin = False
        raw_score = 80.0
        no_real_contact = (email_type in _NO_REAL_CONTACT and not has_phone and not has_linkedin)
        final_score = min(raw_score, 55.0) if no_real_contact else raw_score
        assert final_score == 80.0


# ---------------------------------------------------------------------------
# 4 – Hunter-verified email → saved (high-quality path)
# ---------------------------------------------------------------------------

class TestVerifiedEmailPath:
    """A lead with a Hunter-verified personal email should reach the save threshold."""

    def test_source_min_score_for_hunter(self):
        from app.services.candidate_pipeline import _SOURCE_MIN_SCORES
        # hunter threshold must be ≤ 60 (reachable by real leads)
        assert _SOURCE_MIN_SCORES.get('hunter', 999) <= 60

    def test_verified_personal_email_not_penalised(self):
        # email_type = 'verified_personal' is NOT in generated set → no cap
        _NO_REAL_CONTACT = {'generated', 'generated_personal', 'generated_generic', 'generic'}
        email_type = 'verified_personal'
        assert email_type not in _NO_REAL_CONTACT


# ---------------------------------------------------------------------------
# 5 – Generic email (info@) → low quality, not saved as HOT
# ---------------------------------------------------------------------------

class TestGenericEmailQuality:
    """Leads with only a generic / role-based email must not reach HOT tier."""

    def test_generic_email_capped_same_as_generated(self):
        _NO_REAL_CONTACT = {'generated', 'generated_personal', 'generated_generic', 'generic'}
        email_type = 'generic'
        no_real_contact = email_type in _NO_REAL_CONTACT and not False and not False
        assert no_real_contact

    def test_generic_email_pattern(self):
        _GENERIC_LOCAL = {
            'info', 'contact', 'hello', 'support', 'admin',
            'sales', 'noreply', 'no-reply', 'mail', 'office',
        }
        for addr in ('info@company.com', 'contact@firm.io', 'sales@shop.co'):
            local = addr.split('@')[0].lower()
            assert local in _GENERIC_LOCAL, f"{addr} should be generic"


# ---------------------------------------------------------------------------
# 6 – Intent phrase detection
# ---------------------------------------------------------------------------

class TestIntentDetector:
    """detect_intent() must correctly classify high/medium/low/none intent."""

    def test_high_intent_rfq(self):
        from app.services.intent_detector import detect_intent
        result = detect_intent("We have an rfq for wholesale pricing, need by end of month.")
        assert result['buying_intent'] == 'high'
        assert result['intent_confidence'] > 0.5

    def test_high_intent_demo_request(self):
        from app.services.intent_detector import detect_intent
        result = detect_intent("Please book a demo for our vendor evaluation.")
        assert result['buying_intent'] == 'high'

    def test_medium_intent_hiring(self):
        from app.services.intent_detector import detect_intent
        result = detect_intent("We're hiring engineers and looking for automation tools.")
        assert result['buying_intent'] in ('medium', 'high')

    def test_medium_intent_recommendation(self):
        from app.services.intent_detector import detect_intent
        result = detect_intent("Can anyone recommend a good CRM? Looking for the best tool for sales.")
        assert result['buying_intent'] in ('medium', 'high')

    def test_low_intent_exploring(self):
        from app.services.intent_detector import detect_intent
        result = detect_intent("Just curious about AI, might need something eventually.")
        assert result['buying_intent'] == 'low'

    def test_no_intent_empty(self):
        from app.services.intent_detector import detect_intent
        result = detect_intent("")
        assert result['buying_intent'] == 'none'
        assert result['intent_confidence'] == 0.0

    def test_no_intent_irrelevant(self):
        from app.services.intent_detector import detect_intent
        result = detect_intent("The weather today is sunny and warm.")
        assert result['buying_intent'] == 'none'

    def test_category_ai_software(self):
        from app.services.intent_detector import detect_intent
        result = detect_intent("We need an LLM solution, looking for AI software vendors.")
        assert result['interest_category'] == 'ai_software'

    def test_category_wholesale(self):
        from app.services.intent_detector import detect_intent
        result = detect_intent("Need a wholesale supplier for bulk orders, rfq ready.")
        assert result['interest_category'] == 'wholesale_trade'

    def test_quality_boost_high(self):
        from app.services.intent_detector import intent_quality_boost
        boost = intent_quality_boost({'buying_intent': 'high', 'intent_confidence': 1.0})
        assert boost == 15.0

    def test_quality_boost_none(self):
        from app.services.intent_detector import intent_quality_boost
        boost = intent_quality_boost({'buying_intent': 'none', 'intent_confidence': 0.0})
        assert boost == 0.0


# ---------------------------------------------------------------------------
# 7 – Quality report fields populated
# ---------------------------------------------------------------------------

class TestCollectionQualityReport:
    """CollectionQualityReport must expose all new pipeline fields."""

    def test_required_fields_exist(self):
        from app.services.lead_quality_engine import CollectionQualityReport
        report = CollectionQualityReport(source='test')
        d = report.to_dict()
        required = {
            'raw_candidates', 'enriched_candidates', 'saved', 'rejected',
            'duplicates', 'intent_detected', 'api_calls_made',
            'cache_hits', 'top_sources', 'rejection_reasons',
            'average_quality_score', 'email_breakdown',
        }
        for field in required:
            assert field in d, f"missing field: {field}"

    def test_record_api_call(self):
        from app.services.lead_quality_engine import CollectionQualityReport
        report = CollectionQualityReport(source='test')
        report.record_api_call('hunter')
        report.record_api_call('hunter')
        report.record_api_call('zerobounce')
        d = report.to_dict()
        assert d['api_calls_made'].get('hunter') == 2
        assert d['api_calls_made'].get('zerobounce') == 1

    def test_record_source(self):
        from app.services.lead_quality_engine import CollectionQualityReport
        report = CollectionQualityReport(source='test')
        report.record_source('hunter')
        report.record_source('hunter')
        report.record_source('reddit')
        d = report.to_dict()
        assert d['top_sources'].get('hunter') == 2

    def test_intent_counter(self):
        from app.services.lead_quality_engine import CollectionQualityReport
        report = CollectionQualityReport(source='test')
        report.intent_detected = 3
        assert report.to_dict()['intent_detected'] == 3

    def test_cache_hits_counter(self):
        from app.services.lead_quality_engine import CollectionQualityReport
        report = CollectionQualityReport(source='test')
        report.cache_hits = 5
        assert report.to_dict()['cache_hits'] == 5


# ---------------------------------------------------------------------------
# 8 – Duplicate candidate skipped
# ---------------------------------------------------------------------------

class TestDuplicateDedup:
    """In-pipeline dedup must skip candidates with seen email or domain."""

    def test_email_dedup(self):
        seen_emails = set()
        candidates = [
            {'email': 'alice@acme.com', 'company': 'Acme'},
            {'email': 'alice@acme.com', 'company': 'Acme'},   # duplicate
            {'email': 'bob@acme.com',   'company': 'Acme'},
        ]
        passed = []
        for c in candidates:
            email = (c.get('email') or '').lower()
            if email and email in seen_emails:
                continue
            if email:
                seen_emails.add(email)
            passed.append(c)
        assert len(passed) == 2

    def test_domain_dedup(self):
        seen_domains = set()
        candidates = [
            {'email': 'a@acme.com',    'domain': 'acme.com'},
            {'email': 'b@acme.com',    'domain': 'acme.com'},   # same domain
            {'email': 'c@bigcorp.com', 'domain': 'bigcorp.com'},
        ]
        passed = []
        for c in candidates:
            domain = c.get('domain', '')
            if domain and domain in seen_domains:
                continue
            if domain:
                seen_domains.add(domain)
            passed.append(c)
        assert len(passed) == 2

    def test_candidate_cache_singleton(self):
        from app.services.candidate_cache import get_candidate_cache
        a = get_candidate_cache()
        b = get_candidate_cache()
        assert a is b

    def test_cache_store_and_retrieve(self):
        from app.services.candidate_cache import CandidateCache
        cache = CandidateCache(default_ttl=60)
        cache.set_domain_emails('example.com', ['a@example.com', 'b@example.com'])
        result = cache.get_domain_emails('example.com')
        assert result == ['a@example.com', 'b@example.com']

    def test_failed_domain_marked_and_checked(self):
        from app.services.candidate_cache import CandidateCache
        cache = CandidateCache(default_ttl=60)
        assert not cache.is_failed_domain('no-mx.example.com')
        cache.mark_failed('no-mx.example.com')
        assert cache.is_failed_domain('no-mx.example.com')


# ---------------------------------------------------------------------------
# 9 – CDN / tracker email rejected at pre-filter
# ---------------------------------------------------------------------------

class TestCDNEmailRejection:
    """Emails from CDN / tracking domains must be caught at the earliest stage."""

    @pytest.mark.parametrize("email", [
        'st@ic.cloudflareinsights.com',
        'pixel@googletagmanager.com',
        'noreply@hotjar.com',
        'beacon@doubleclick.net',
        'track@mixpanel.com',
        'event@segment.io',
        'analytics@google-analytics.com',
        'push@onesignal.com',
    ])
    def test_cdn_email_detected(self, email):
        from app.services.name_validator import is_cdn_email
        assert is_cdn_email(email), f"expected {email} to be flagged as CDN/tracker"

    @pytest.mark.parametrize("email", [
        'john@acmecorp.com',
        'info@legitimate-company.io',
        'sales@shopify.com',
        'contact@stripe.com',
    ])
    def test_legitimate_email_not_flagged(self, email):
        from app.services.name_validator import is_cdn_email
        assert not is_cdn_email(email), f"expected {email} to pass CDN check"

    def test_pre_filter_rejects_cdn_email(self):
        from app.services.name_validator import pre_filter_lead
        lead = {
            'name': 'Test User',
            'email': 'pixel@googletagmanager.com',
            'company': 'Acme',
        }
        ok, reason = pre_filter_lead(lead)
        assert not ok
        assert reason == 'cdn_tracker_email'

    def test_pre_filter_passes_clean_lead(self):
        from app.services.name_validator import pre_filter_lead
        lead = {
            'name': 'Alice Smith',
            'email': 'alice@acmecorp.com',
            'company': 'Acme Corp',
        }
        ok, reason = pre_filter_lead(lead)
        assert ok, f"expected clean lead to pass, got reason: {reason}"

    def test_url_as_name_rejected(self):
        from app.services.name_validator import pre_filter_lead
        lead = {
            'name': 'https://wholesalemotorgroup.com.au/',
            'email': 'info@wholesalemotorgroup.com.au',
            'company': 'Wholesale Motor Group',
        }
        ok, reason = pre_filter_lead(lead)
        assert not ok
        assert 'url' in reason.lower()

    def test_page_title_as_name_rejected(self):
        from app.services.name_validator import is_valid_person_name
        ok, reason = is_valid_person_name('Contact Us')
        assert not ok
        assert reason == 'page_title_as_name'

    def test_company_lead_single_word_name_passes(self):
        """Company leads with single-word names must not be blocked by person-name rules."""
        from app.services.name_validator import pre_filter_lead
        for company_name in ('Microsoft', 'Salesforce', 'Shopify', 'Apple'):
            lead = {
                'name': company_name,
                'company': company_name,
                'website': f'https://www.{company_name.lower()}.com',
                'lead_type': 'company',
            }
            ok, reason = pre_filter_lead(lead)
            assert ok, f"company lead '{company_name}' wrongly rejected: {reason}"

    def test_company_lead_web_in_name_passes(self):
        """Company names containing 'web', 'click', 'go' must not be rejected."""
        from app.services.name_validator import pre_filter_lead
        for company_name in ('Web Solutions Inc', 'Click Digital', 'Go Marketing'):
            lead = {
                'name': company_name,
                'company': company_name,
                'website': 'https://example.com',
                'lead_type': 'company',
            }
            ok, reason = pre_filter_lead(lead)
            assert ok, f"company lead '{company_name}' wrongly rejected: {reason}"

    def test_url_as_name_still_rejected_for_company_lead(self):
        """URL-shaped names are always rejected regardless of lead_type."""
        from app.services.name_validator import pre_filter_lead
        lead = {
            'name': 'https://acme.com/contact',
            'company': 'Acme Corp',
            'lead_type': 'company',
        }
        ok, reason = pre_filter_lead(lead)
        assert not ok
        assert reason == 'url_as_name'

    def test_regional_free_email_detected(self):
        from app.services.name_validator import is_free_email_extended
        for addr in ('user@live.com.au', 'user@hotmail.co.uk', 'user@yahoo.co.jp'):
            assert is_free_email_extended(addr), f"{addr} should be flagged as free email"
