"""
Lead Quality Tests
==================
Tests covering all quality rules from Tasks 2-8.

Run with: pytest backend/tests/test_lead_quality.py -v
"""

import pytest
from typing import Any, Dict


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _lead(**kwargs) -> Dict[str, Any]:
    """Build a minimal lead dict with defaults."""
    base = {
        'name':    'John Smith',
        'email':   'john.smith@acme.com',
        'phone':   '+1 (555) 123-4567',
        'company': 'Acme Corp',
        'website': 'https://acme.com',
        'source':  'web',
        'data_points': {},
    }
    base.update(kwargs)
    return base


def _dp(**kwargs) -> Dict[str, Any]:
    """Build a data_points dict."""
    return dict(kwargs)


# ============================================================================
# lead_quality_engine tests
# ============================================================================

class TestEvaluateLeadQuality:

    def test_high_quality_lead_saves(self):
        from app.services.lead_quality_engine import evaluate_lead_quality, QualityTier
        lead = _lead(
            name='Jane Doe',
            email='jane.doe@enterprise.com',
            company='Enterprise Corp',
            position='CTO',
            phone='+44 20 7946 0958',
            data_points=_dp(email_verified=True, email_source='hunter'),
        )
        d = evaluate_lead_quality(lead, source='hunter')
        assert d.decision == 'save'
        assert d.tier in (QualityTier.HIGH_QUALITY, QualityTier.QUALIFIED)
        assert d.should_save is True

    def test_generated_email_never_counted_as_contact(self):
        from app.services.lead_quality_engine import evaluate_lead_quality, RejectionReason
        lead = _lead(
            email='john.smith@acme.com',
            phone='',
            website='',
            linkedin_url='',
            data_points=_dp(email_source='generated'),
        )
        d = evaluate_lead_quality(lead, source='web')
        assert RejectionReason.FAKE_OR_GENERATED_EMAIL in d.reasons
        assert d.decision == 'reject'  # no contact method remains
        assert 'generated_email_blocked' in d.metadata

    def test_generated_personal_email_rejected(self):
        from app.services.lead_quality_engine import evaluate_lead_quality, RejectionReason
        lead = _lead(
            email='john.smith@acme.com',
            phone='',
            website='',
            linkedin_url='',
            data_points=_dp(email_source='generated_personal'),
        )
        d = evaluate_lead_quality(lead, source='web')
        assert RejectionReason.FAKE_OR_GENERATED_EMAIL in d.reasons
        assert d.decision == 'reject'

    def test_generated_generic_email_rejected(self):
        from app.services.lead_quality_engine import evaluate_lead_quality, RejectionReason
        lead = _lead(
            email='info@acme.com',
            phone='',
            website='',
            linkedin_url='',
            data_points=_dp(email_source='generated_generic'),
        )
        d = evaluate_lead_quality(lead, source='web')
        assert RejectionReason.FAKE_OR_GENERATED_EMAIL in d.reasons
        assert d.decision == 'reject'

    def test_no_contact_method_rejects(self):
        from app.services.lead_quality_engine import evaluate_lead_quality, RejectionReason
        lead = _lead(email='', phone='', website='', linkedin_url='')
        d = evaluate_lead_quality(lead, source='web')
        assert d.decision == 'reject'
        assert RejectionReason.NO_CONTACT_METHOD in d.reasons

    def test_company_only_no_contact_rejected(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        lead = {
            'name': 'Acme Corp',
            'company': 'Acme Corp',
            'email': '',
            'phone': '',
            'website': '',
            'linkedin_url': '',
            'data_points': {},
        }
        d = evaluate_lead_quality(lead, source='web')
        assert d.decision == 'reject'

    def test_username_only_reddit_lead_rejected(self):
        from app.services.lead_quality_engine import evaluate_lead_quality, RejectionReason
        lead = {
            'name': 'reddituserXYZ',
            'company': '',
            'email': '',
            'phone': '',
            'website': '',
            'linkedin_url': '',
            'source': 'reddit',
            'data_points': {'platform': 'reddit'},
        }
        d = evaluate_lead_quality(lead, source='reddit')
        assert d.decision == 'reject'

    def test_social_lead_without_substance_rejected(self):
        from app.services.lead_quality_engine import evaluate_lead_quality, RejectionReason
        lead = {
            'name': 'John Smith',
            'company': '',
            'email': '',
            'phone': '',
            'website': '',
            'linkedin_url': '',
            'source': 'reddit',
            'data_points': {'platform': 'reddit'},
        }
        d = evaluate_lead_quality(lead, source='reddit')
        assert d.decision == 'reject'
        assert RejectionReason.LOW_QUALITY_SOCIAL in d.reasons

    def test_social_lead_with_company_and_website_accepted(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        lead = {
            'name': 'Jane Doe',
            'company': 'Startup Inc',
            'email': 'jane@startup.com',
            'phone': '',
            'website': 'https://startup.com',
            'linkedin_url': '',
            'source': 'reddit',
            'data_points': {'platform': 'reddit', 'email_source': 'contact_page_scrape'},
        }
        d = evaluate_lead_quality(lead, source='reddit')
        assert d.should_save is True

    def test_verified_personal_email_scores_highest(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        verified_lead = _lead(data_points=_dp(email_verified=True, email_source='hunter'))
        unverified_lead = _lead(data_points=_dp(email_verified=False, email_source='web'))
        d_verified   = evaluate_lead_quality(verified_lead, source='hunter')
        d_unverified = evaluate_lead_quality(unverified_lead, source='web')
        assert d_verified.quality_score > d_unverified.quality_score

    def test_generic_email_scores_lower_than_personal(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        personal = _lead(email='john.doe@company.com')
        generic  = _lead(email='info@company.com')
        d_personal = evaluate_lead_quality(personal, source='web')
        d_generic  = evaluate_lead_quality(generic, source='web')
        assert d_personal.quality_score > d_generic.quality_score

    def test_invalid_phone_not_counted(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        good_phone  = _lead(phone='+1 (555) 123-4567')
        fake_phone  = _lead(phone='1234567890')  # sequential digits
        d_good = evaluate_lead_quality(good_phone, source='web')
        d_fake = evaluate_lead_quality(fake_phone, source='web')
        assert d_good.quality_score >= d_fake.quality_score

    def test_invalid_email_structure_rejected(self):
        from app.services.lead_quality_engine import evaluate_lead_quality, RejectionReason
        lead = _lead(email='not-an-email', phone='', website='', linkedin_url='')
        d = evaluate_lead_quality(lead, source='web')
        assert RejectionReason.INVALID_EMAIL in d.reasons
        assert d.decision == 'reject'

    def test_quality_report_counts_rejections(self):
        from app.services.lead_quality_engine import (
            evaluate_lead_quality, CollectionQualityReport, RejectionReason,
        )
        report = CollectionQualityReport(source='test')
        # Rejected lead
        reject_lead = _lead(email='', phone='', website='', linkedin_url='')
        reject_lead['data_points'] = {}
        report.raw_candidates += 1
        evaluate_lead_quality(reject_lead, source='web', report=report)
        assert report.rejected >= 1

    def test_hunter_source_higher_reliability_than_reddit(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        lead = _lead()
        d_hunter = evaluate_lead_quality(lead, source='hunter')
        d_reddit = evaluate_lead_quality(lead, source='reddit')
        assert d_hunter.quality_score > d_reddit.quality_score

    def test_collection_report_to_dict(self):
        from app.services.lead_quality_engine import CollectionQualityReport
        report = CollectionQualityReport(source='test_source')
        report.raw_candidates = 10
        report.parsed_candidates = 7
        report.rejected = 3
        report.saved = 7
        report.duplicates = 1
        report.record_score(75.0)
        report.record_score(60.0)
        report.record_email('personal_business', True)
        report.record_email('generic', False)
        report.record_email('missing', False)
        d = report.to_dict()
        assert d['source'] == 'test_source'
        assert d['raw_candidates'] == 10
        assert d['rejected'] == 3
        assert d['email_breakdown']['verified_personal'] == 1
        assert d['email_breakdown']['company_generic'] == 1
        assert d['email_breakdown']['missing'] == 1
        assert d['average_quality_score'] == 67.5


# ============================================================================
# lead_validator tests
# ============================================================================

class TestLeadValidator:

    def test_generated_email_gives_zero_points(self):
        from app.services.lead_validator import score_lead
        lead = _lead(
            email='john.smith@acme.com',
            data_points=_dp(email_source='generated'),
        )
        result = score_lead(lead)
        # Generated email should not contribute points
        assert result.email_type == 'generated'
        assert 'generated_email_not_counted' in result.reasons

    def test_verified_personal_business_email_scores_35(self):
        from app.services.lead_validator import score_lead
        lead = _lead(
            email='john.smith@enterprise.com',
            data_points=_dp(email_verified=True, email_source='hunter'),
        )
        result = score_lead(lead)
        assert result.score >= 35  # email alone gives 35 pts

    def test_unverified_personal_email_scores_15(self):
        from app.services.lead_validator import score_lead
        lead = {
            'email': 'john.smith@company.com',
            'name': '', 'phone': '', 'company': '', 'website': '',
            'data_points': {'email_verified': False},
        }
        result = score_lead(lead)
        # Only email field, unverified personal = 15 pts
        assert 10 <= result.score <= 20

    def test_unverified_generic_email_scores_low(self):
        from app.services.lead_validator import score_lead
        lead = {
            'email': 'info@company.com',
            'name': '', 'phone': '', 'company': '', 'website': '',
            'data_points': {'email_verified': False},
        }
        result = score_lead(lead)
        assert result.score <= 10
        assert result.email_type == 'generic'

    def test_tier_high_quality_requires_verified_email(self):
        from app.services.lead_validator import score_lead
        lead = _lead(
            email='john.doe@acme.com',
            position='CEO',
            industry='Technology',
            country='US',
            linkedin_url='https://linkedin.com/in/johndoe',
            data_points=_dp(email_verified=True, email_source='hunter'),
        )
        result = score_lead(lead)
        assert result.tier == 'high_quality'

    def test_duplicate_filter_normalizes_case(self):
        from app.services.lead_validator import DuplicateFilter
        dedup = DuplicateFilter()
        lead_a = {'email': 'JOHN@COMPANY.COM', 'name': 'John Smith', 'company': 'Acme Corp', 'website': ''}
        lead_b = {'email': 'john@company.com', 'name': 'john smith', 'company': 'acme corp', 'website': ''}
        is_dup_a, _ = dedup.is_duplicate(lead_a)
        dedup.register(lead_a)
        is_dup_b, reason = dedup.is_duplicate(lead_b)
        assert is_dup_a is False
        assert is_dup_b is True
        assert 'duplicate_email' in reason

    def test_duplicate_filter_normalizes_company_legal_suffix(self):
        from app.services.lead_validator import DuplicateFilter
        dedup = DuplicateFilter()
        lead_a = {'email': '', 'name': 'Jane Doe', 'company': 'Acme Corp LLC', 'website': ''}
        lead_b = {'email': '', 'name': 'jane doe', 'company': 'Acme Corp',     'website': ''}
        dedup.is_duplicate(lead_a)
        dedup.register(lead_a)
        is_dup, reason = dedup.is_duplicate(lead_b)
        assert is_dup is True

    def test_validate_and_score_rejects_empty_lead(self):
        from app.services.lead_validator import validate_and_score
        lead = {'name': '', 'email': '', 'phone': '', 'company': '',
                'website': '', 'linkedin_url': '', 'data_points': {}}
        _, should_save, reason = validate_and_score(lead)
        assert should_save is False

    def test_social_source_stricter_threshold(self):
        from app.services.lead_validator import score_lead
        # A lead that would be 'qualified' on web but 'pending' on social
        lead = _lead(
            phone='',
            website='',
            position='',
            industry='',
            linkedin_url='',
            country='',
            data_points={'platform': 'reddit'},
        )
        result = score_lead(lead)
        # Unverified personal email (15) + company (15) + name (10) = 40 pts
        # On social, threshold for qualified is 75 — so this should be pending
        assert result.tier in ('pending', 'low_quality')


# ============================================================================
# lead_fallback tests
# ============================================================================

class TestLeadFallback:

    def test_generated_email_goes_to_candidates_not_email_field(self):
        from app.services.lead_fallback import enrich_lead_fallbacks
        lead = {
            'name': 'John Smith', 'email': '', 'company': 'Acme',
            'website': 'https://acme.com', 'data_points': {},
        }
        result = enrich_lead_fallbacks(
            lead,
            scrape_contact=False,
            use_hunter=False,
            generate_email=True,
            debug=False,
        )
        # Generated emails must NOT be placed in lead['email']
        assert result.get('email', '') == ''
        dp = result.get('data_points', {})
        # Candidates should be stored separately
        assert 'email_candidates' in dp
        assert dp.get('email_source') == 'generated'
        assert dp.get('email_verified') is False

    def test_hunter_confidence_threshold_is_80(self):
        """Hunter email-finder must require confidence ≥ 80."""
        from app.services.lead_fallback import hunter_find_email
        import unittest.mock as mock

        low_confidence_response = {
            'data': {
                'email': 'john@example.com',
                'score': 75,  # below threshold
            }
        }
        with mock.patch('requests.get') as mock_get:
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = low_confidence_response
            mock_get.return_value = mock_resp

            import os
            os.environ['HUNTER_API_KEY'] = 'test-key'
            result = hunter_find_email('example.com', 'John', 'Smith')
            assert result is None  # rejected because confidence < 80

    def test_scrape_contact_email_marked_unverified(self):
        """Emails scraped from contact pages must have email_verified=False."""
        from app.services.lead_fallback import enrich_lead_fallbacks
        import unittest.mock as mock

        with mock.patch(
            'app.services.lead_fallback.scrape_contact_pages',
            return_value=('contact@acme.com', None),
        ):
            lead = {
                'name': 'Acme Corp', 'email': '', 'company': 'Acme',
                'website': 'https://acme.com', 'data_points': {},
            }
            result = enrich_lead_fallbacks(
                lead, scrape_contact=True, use_hunter=False,
                generate_email=False, debug=False,
            )
            dp = result.get('data_points', {})
            assert result.get('email') == 'contact@acme.com'
            assert dp.get('email_verified') is False
            assert dp.get('email_source') == 'contact_page_scrape'


# ============================================================================
# hunter_service tests
# ============================================================================

class TestHunterService:

    def test_find_email_rejects_low_confidence(self):
        from app.services.hunter_service import HunterService
        import unittest.mock as mock

        svc = HunterService()
        svc.api_key = 'fake-key'

        with mock.patch.object(svc.session, 'get') as mock_get:
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {'data': {'email': 'test@company.com', 'score': 70}}
            mock_resp.raise_for_status = lambda: None
            mock_get.return_value = mock_resp

            result = svc.find_email('John', 'Smith', 'company.com')
            assert result is None  # confidence 70 < 80

    def test_find_email_accepts_high_confidence(self):
        from app.services.hunter_service import HunterService
        import unittest.mock as mock

        svc = HunterService()
        svc.api_key = 'fake-key'

        with mock.patch.object(svc.session, 'get') as mock_get:
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {'data': {'email': 'john@company.com', 'score': 90}}
            mock_resp.raise_for_status = lambda: None
            mock_get.return_value = mock_resp

            result = svc.find_email('John', 'Smith', 'company.com')
            assert result is not None
            assert result['email'] == 'john@company.com'
            assert result['email_verified'] is True
            assert result['email_source'] == 'hunter'

    def test_domain_search_excludes_generic_emails(self):
        from app.services.hunter_service import HunterService
        import unittest.mock as mock

        svc = HunterService()
        svc.api_key = 'fake-key'

        with mock.patch.object(svc.session, 'get') as mock_get:
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                'data': {
                    'organization': 'Acme Corp',
                    'emails': [
                        {'value': 'info@acme.com', 'first_name': 'Info', 'last_name': 'Box', 'confidence': 95, 'position': ''},
                        {'value': 'john@acme.com', 'first_name': 'John', 'last_name': 'Smith', 'confidence': 90, 'position': 'CEO'},
                    ],
                }
            }
            mock_resp.raise_for_status = lambda: None
            mock_get.return_value = mock_resp

            leads = svc.domain_search('acme.com')
            emails = [l['email'] for l in leads]
            assert 'info@acme.com' not in emails  # generic excluded
            assert 'john@acme.com' in emails       # personal included

    def test_domain_search_excludes_low_confidence(self):
        from app.services.hunter_service import HunterService
        import unittest.mock as mock

        svc = HunterService()
        svc.api_key = 'fake-key'

        with mock.patch.object(svc.session, 'get') as mock_get:
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                'data': {
                    'organization': 'Acme',
                    'emails': [
                        {'value': 'jane@acme.com', 'first_name': 'Jane', 'last_name': 'Doe', 'confidence': 55},
                    ],
                }
            }
            mock_resp.raise_for_status = lambda: None
            mock_get.return_value = mock_resp

            leads = svc.domain_search('acme.com')
            assert len(leads) == 0  # confidence 55 < 80


# ============================================================================
# clearbit_service tests
# ============================================================================

class TestClearbitService:

    def test_does_not_fabricate_linkedin_from_empty_handle(self):
        from app.services.clearbit_service import ClearbitService
        svc = ClearbitService()
        data = {
            'name': 'Acme Corp',
            'domain': 'acme.com',
            'linkedin': {'handle': ''},  # empty handle
            'metrics': {'employees': 50},
            'geo': {},
            'category': {},
        }
        normalized = svc._normalize_company(data)
        assert normalized['linkedin_url'] == ''

    def test_does_not_fabricate_linkedin_from_slash_handle(self):
        from app.services.clearbit_service import ClearbitService
        svc = ClearbitService()
        data = {
            'name': 'Acme Corp',
            'domain': 'acme.com',
            'linkedin': {'handle': '/'},  # slash-only handle
            'metrics': {'employees': 50},
            'geo': {},
            'category': {},
        }
        normalized = svc._normalize_company(data)
        assert normalized['linkedin_url'] == ''

    def test_company_size_stored_as_int_not_empty_string(self):
        from app.services.clearbit_service import ClearbitService
        svc = ClearbitService()
        data = {
            'name': 'Tiny Co',
            'domain': 'tinyco.com',
            'linkedin': {},
            'metrics': {'employees': 0},  # 0 employees
            'geo': {},
            'category': {},
        }
        normalized = svc._normalize_company(data)
        # Should be None, not "" (empty string)
        assert normalized['company_size'] is None

    def test_enrich_lead_tags_enrichment_source(self):
        from app.services.clearbit_service import ClearbitService
        import unittest.mock as mock

        svc = ClearbitService()
        with mock.patch.object(svc, 'enrich_person', return_value={}):
            with mock.patch.object(svc, 'enrich_company', return_value={
                'company': 'Acme Corp', 'industry': 'Technology',
                'enrichment_source': 'clearbit', 'enriched_at': '2026-01-01T00:00:00',
                'linkedin_url': 'https://linkedin.com/company/acme',
                'website': '', 'location': '', 'country': '', 'city': '', 'phone': '',
            }):
                with mock.patch('app.services.clearbit_service._key', return_value='fake-key'):
                    lead = {'email': 'john@acme.com', 'company': '', 'industry': '', 'website': 'https://acme.com', 'data_points': {}}
                    result = svc.enrich_lead(lead)
                    dp = result.get('data_points', {})
                    assert dp.get('enrichment_source') == 'clearbit'
                    assert 'enriched_at' in dp


# ============================================================================
# lead_extractor tests
# ============================================================================

class TestLeadExtractor:

    def test_base64_email_requires_full_validation(self):
        from app.services.lead_extractor import _maybe_decode_base64
        # Valid email in base64
        import base64
        valid_email = 'john@company.com'
        encoded = base64.b64encode(valid_email.encode()).decode()
        result = _maybe_decode_base64(encoded)
        assert result == valid_email

    def test_base64_not_email_returns_none(self):
        from app.services.lead_extractor import _maybe_decode_base64
        import base64
        # base64 that decodes to something with @ but not a valid email
        not_email = 'some text @ not an email'
        encoded = base64.b64encode(not_email.encode()).decode()
        result = _maybe_decode_base64(encoded)
        assert result is None

    def test_name_extraction_rejects_single_word(self):
        from app.services.lead_extractor import _looks_like_person_name
        assert _looks_like_person_name('John') is False

    def test_name_extraction_rejects_tech_keywords(self):
        from app.services.lead_extractor import _looks_like_person_name
        assert _looks_like_person_name('Machine Learning') is False
        assert _looks_like_person_name('Digital Solutions') is False
        assert _looks_like_person_name('Cloud Technology') is False

    def test_name_extraction_accepts_real_name(self):
        from app.services.lead_extractor import _looks_like_person_name
        assert _looks_like_person_name('John Smith') is True
        assert _looks_like_person_name('Jane Marie Doe') is True
        assert _looks_like_person_name("O'Brien Williams") is True

    def test_name_extraction_rejects_numeric_words(self):
        from app.services.lead_extractor import _looks_like_person_name
        assert _looks_like_person_name('John 123') is False

    def test_generic_email_extended_prefixes(self):
        from app.services.lead_extractor import GENERIC_LOCAL_PARTS
        # New prefixes added in this upgrade
        assert 'reach' in GENERIC_LOCAL_PARTS
        assert 'partners' in GENERIC_LOCAL_PARTS
        assert 'legal' in GENERIC_LOCAL_PARTS
        assert 'privacy' in GENERIC_LOCAL_PARTS

    def test_placeholder_domain_rejected(self):
        from app.services.lead_extractor import _validate_email
        assert _validate_email('test@example.com') is False
        assert _validate_email('user@placeholder.com') is False
        assert _validate_email('john@acme.io') is True

    def test_file_extension_email_rejected(self):
        from app.services.lead_extractor import _validate_email
        assert _validate_email('image@example.png') is False
        assert _validate_email('style@site.css') is False


# ============================================================================
# Source reliability scores
# ============================================================================

class TestSourceReliability:

    def test_hunter_higher_than_reddit(self):
        from app.services.lead_quality_engine import SOURCE_RELIABILITY
        assert SOURCE_RELIABILITY['hunter'] > SOURCE_RELIABILITY['reddit']

    def test_pdl_higher_than_social(self):
        from app.services.lead_quality_engine import SOURCE_RELIABILITY
        assert SOURCE_RELIABILITY['pdl'] > SOURCE_RELIABILITY['social_media']

    def test_generated_source_is_zero(self):
        from app.services.lead_quality_engine import SOURCE_RELIABILITY
        assert SOURCE_RELIABILITY['generated'] == 0.0

    def test_social_sources_in_low_range(self):
        from app.services.lead_quality_engine import SOURCE_RELIABILITY
        for src in ('reddit', 'twitter', 'facebook', 'telegram'):
            assert SOURCE_RELIABILITY[src] <= 35


# ============================================================================
# Deduplication correctness
# ============================================================================

class TestDeduplication:

    def test_duplicate_not_saved_twice(self):
        from app.services.lead_validator import DuplicateFilter
        dedup = DuplicateFilter()
        lead = _lead()
        _, reason1 = dedup.is_duplicate(lead)
        dedup.register(lead)
        is_dup2, reason2 = dedup.is_duplicate(lead)
        assert reason1 == ''       # first time: not duplicate
        assert is_dup2 is True     # second time: duplicate

    def test_gmail_dot_trick_deduped(self):
        from app.services.lead_validator import DuplicateFilter
        dedup = DuplicateFilter()
        lead_a = _lead(email='john.smith@gmail.com')
        lead_b = _lead(email='johnsmith@gmail.com')  # same Gmail account
        dedup.is_duplicate(lead_a)
        dedup.register(lead_a)
        is_dup, _ = dedup.is_duplicate(lead_b)
        assert is_dup is True

    def test_different_people_same_company_not_deduped(self):
        from app.services.lead_validator import DuplicateFilter
        dedup = DuplicateFilter()
        alice = _lead(name='Alice Doe', email='alice@acme.com', company='Acme Corp')
        bob   = _lead(name='Bob Smith', email='bob@acme.com',   company='Acme Corp')
        dedup.is_duplicate(alice)
        dedup.register(alice)
        is_dup, _ = dedup.is_duplicate(bob)
        assert is_dup is False  # different people, same company — ok

    def test_generic_email_not_used_for_dedup(self):
        from app.services.lead_validator import DuplicateFilter
        dedup = DuplicateFilter()
        # Two different companies with info@ addresses should NOT be deduped by email
        lead_a = _lead(name='Alice Co', email='info@alice.com',   company='Alice Co',   website='https://alice.com')
        lead_b = _lead(name='Bob Ltd',  email='info@bob.com',     company='Bob Ltd',    website='https://bob.com')
        dedup.is_duplicate(lead_a)
        dedup.register(lead_a)
        is_dup, _ = dedup.is_duplicate(lead_b)
        assert is_dup is False
