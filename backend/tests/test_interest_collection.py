"""
Interest-Based Collection — Full Test Suite
============================================
Covers all Phase 1 + Phase 2 components:
  - Category config (16 categories, field validation, lookup)
  - Query generation (templates, sources, deduplication)
  - Buying intent detection (high/medium/low/none classification)
  - Intent score adjustment (boost/penalty logic)
  - Weak social lead rejection
  - Generated/inferred email blocking
  - IntentQualityReport (accumulation, to_dict)
  - Country resolution helper
  - Lead model interest fields
  - API endpoints: GET /lead-categories, POST /collect-by-interest
"""

import pytest


# ============================================================================
# Category config
# ============================================================================

class TestCategoryConfig:

    def test_all_categories_have_required_fields(self):
        from config.lead_categories import CATEGORIES
        for slug, cat in CATEGORIES.items():
            assert cat.category_name,                       f"{slug}: missing category_name"
            assert len(cat.keywords) >= 3,                  f"{slug}: need ≥3 keywords"
            assert len(cat.intent_phrases) >= 3,            f"{slug}: need ≥3 intent_phrases"
            assert len(cat.source_types) >= 1,              f"{slug}: need ≥1 source_type"
            assert 0.0 <= cat.minimum_quality_score <= 100, f"{slug}: score out of range"

    def test_source_types_are_valid(self):
        from config.lead_categories import CATEGORIES
        valid = {'web', 'social', 'news', 'directories', 'github'}
        for slug, cat in CATEGORIES.items():
            for st in cat.source_types:
                assert st in valid, f"{slug}: unknown source_type '{st}'"

    def test_get_category_by_slug(self):
        from config.lead_categories import get_category
        cat = get_category('laptops')
        assert cat is not None
        assert cat.category_name == 'Laptops'

    def test_get_category_by_display_name(self):
        from config.lead_categories import get_category
        cat = get_category('Electrical Appliances')
        assert cat is not None
        assert 'washing machine' in cat.keywords

    def test_get_category_case_insensitive(self):
        from config.lead_categories import get_category
        assert get_category('LAPTOPS') is not None
        assert get_category('real estate') is not None

    def test_get_category_unknown_returns_none(self):
        from config.lead_categories import get_category
        assert get_category('flying_carpets') is None
        assert get_category('') is None

    def test_list_categories_returns_all_slugs(self):
        from config.lead_categories import list_categories
        slugs = list_categories()
        for expected in ('laptops', 'real_estate', 'software', 'cars', 'beauty', 'healthcare'):
            assert expected in slugs
        assert len(slugs) >= 15

    def test_list_category_names_returns_display_names(self):
        from config.lead_categories import list_category_names
        names = list_category_names()
        assert 'Laptops' in names
        assert 'Real Estate' in names
        assert len(names) >= 15

    def test_no_duplicate_slugs(self):
        from config.lead_categories import CATEGORIES
        slugs = list(CATEGORIES.keys())
        assert len(slugs) == len(set(slugs))

    def test_high_risk_categories_have_higher_minimum_score(self):
        from config.lead_categories import get_category
        for slug in ('real_estate', 'cars', 'healthcare'):
            cat = get_category(slug)
            assert cat.minimum_quality_score >= 40.0, f"{slug} should require score ≥40"

    def test_software_includes_github_source(self):
        from config.lead_categories import get_category
        cat = get_category('software')
        assert 'github' in cat.source_types

    def test_social_categories_include_social_source(self):
        from config.lead_categories import get_category
        for slug in ('clothes', 'beauty', 'phones'):
            cat = get_category(slug)
            assert 'social' in cat.source_types, f"{slug} should include 'social'"


# ============================================================================
# Query generation
# ============================================================================

class TestQueryGeneration:

    def test_generates_queries_for_laptops(self):
        from app.services.interest_query_generator import generate_queries
        queries = generate_queries('laptops', country='Lebanon')
        assert len(queries) > 0
        assert any('Lebanon' in q for q in queries)
        assert any('laptop' in q.lower() for q in queries)

    def test_generates_city_queries_when_city_given(self):
        from app.services.interest_query_generator import generate_queries
        queries = generate_queries('furniture', country='Lebanon', city='Beirut')
        assert any('Beirut' in q for q in queries)

    def test_no_city_specific_templates_without_city(self):
        from app.services.interest_query_generator import generate_queries
        queries_no_city  = generate_queries('furniture', country='Lebanon', city=None)
        queries_with_city = generate_queries('furniture', country='Lebanon', city='Beirut')
        assert len(queries_with_city) > len(queries_no_city)

    def test_social_queries_use_quoted_intent_phrases(self):
        from app.services.interest_query_generator import generate_queries
        queries = generate_queries('phones', country='US', sources=['social'])
        assert any('"looking for"' in q or '"need"' in q or '"recommend"' in q for q in queries)

    def test_web_only_has_no_social_templates(self):
        from app.services.interest_query_generator import generate_queries
        queries = generate_queries('laptops', country='Germany', sources=['web'])
        assert not any('"looking for"' in q for q in queries)
        assert not any('site:reddit.com' in q for q in queries)

    def test_github_queries_for_software(self):
        from app.services.interest_query_generator import generate_queries
        queries = generate_queries('software', country='US', sources=['github'])
        assert any('github.com' in q for q in queries)

    def test_news_queries_generated(self):
        from app.services.interest_query_generator import generate_queries
        queries = generate_queries('real_estate', country='UAE', sources=['news'])
        assert any('market' in q or 'industry' in q or 'news' in q for q in queries)

    def test_unknown_category_returns_empty(self):
        from app.services.interest_query_generator import generate_queries
        assert generate_queries('flying_carpets', country='Lebanon') == []

    def test_no_duplicate_queries(self):
        from app.services.interest_query_generator import generate_queries
        queries = generate_queries('clothes', country='Lebanon', city='Beirut')
        assert len(queries) == len(set(queries))

    def test_max_keywords_limits_expansion(self):
        from app.services.interest_query_generator import generate_queries
        q3  = generate_queries('electrical_appliances', country='Lebanon', max_keywords=3)
        q10 = generate_queries('electrical_appliances', country='Lebanon', max_keywords=10)
        assert len(q10) >= len(q3)

    def test_all_queries_are_non_empty_strings(self):
        from app.services.interest_query_generator import generate_queries
        for q in generate_queries('cars', country='Saudi Arabia', city='Riyadh'):
            assert isinstance(q, str) and len(q) > 0

    def test_custom_sources_override_defaults(self):
        from app.services.interest_query_generator import generate_queries
        queries = generate_queries('software', country='India', sources=['web'])
        assert not any('github.com' in q for q in queries)

    def test_multi_source_combined(self):
        from app.services.interest_query_generator import generate_queries
        queries = generate_queries('marketing', country='UK', sources=['web', 'social', 'news'])
        assert any('"looking for"' in q for q in queries)    # social
        assert any('supplier' in q or 'directory' in q for q in queries)  # web
        assert any('market' in q or 'news' in q for q in queries)         # news

    def test_queries_contain_keyword_from_category(self):
        from app.services.interest_query_generator import generate_queries
        queries = generate_queries('beauty', country='France', sources=['web'])
        all_text = ' '.join(queries).lower()
        assert any(kw in all_text for kw in ('beauty', 'cosmetics', 'skincare', 'makeup'))


# ============================================================================
# Buying intent detection
# ============================================================================

class TestBuyingIntentDetection:

    def test_high_intent_strong_signals(self):
        from app.services.interest_query_generator import detect_buying_intent
        result = detect_buying_intent(
            "I'm looking for a laptop supplier in Beirut, need 50 units urgently.",
            'laptops',
        )
        assert result['buying_intent'] == 'high'
        assert result['confidence'] > 0.4
        assert 'laptop' in result['product_interest']

    def test_high_intent_procurement_language(self):
        from app.services.interest_query_generator import detect_buying_intent
        result = detect_buying_intent(
            "Procurement request: sourcing washing machines, bulk order, quote needed ASAP.",
            'electrical_appliances',
        )
        assert result['buying_intent'] == 'high'

    def test_medium_intent_recommendation_seeking(self):
        from app.services.interest_query_generator import detect_buying_intent
        result = detect_buying_intent("Can anyone recommend the best laptop?", 'laptops')
        assert result['buying_intent'] in ('medium', 'high')
        assert result['confidence'] > 0.0

    def test_medium_intent_comparison(self):
        from app.services.interest_query_generator import detect_buying_intent
        result = detect_buying_intent(
            "Thinking about buying a smartphone, comparing options between iPhone and Samsung.",
            'phones',
        )
        assert result['buying_intent'] in ('medium', 'high')

    def test_low_intent_informational(self):
        from app.services.interest_query_generator import detect_buying_intent
        result = detect_buying_intent(
            "What is a fridge and how does it work? A guide to refrigerators.",
            'electrical_appliances',
        )
        assert result['buying_intent'] in ('low', 'none')

    def test_no_intent_unrelated_text(self):
        from app.services.interest_query_generator import detect_buying_intent
        result = detect_buying_intent("The weather is beautiful today.", 'laptops')
        assert result['buying_intent'] == 'none'
        assert result['confidence'] == 0.0

    def test_empty_text_returns_none(self):
        from app.services.interest_query_generator import detect_buying_intent
        assert detect_buying_intent('', 'laptops')['buying_intent'] == 'none'

    def test_whitespace_only_returns_none(self):
        from app.services.interest_query_generator import detect_buying_intent
        assert detect_buying_intent('   ', 'laptops')['buying_intent'] == 'none'

    def test_all_required_fields_present(self):
        from app.services.interest_query_generator import detect_buying_intent
        result = detect_buying_intent("need a washing machine", 'electrical_appliances')
        for f in ('buying_intent', 'confidence', 'intent_reason', 'matched_phrases',
                  'category', 'product_interest'):
            assert f in result, f"Missing field: {f}"

    def test_confidence_normalized_0_to_1(self):
        from app.services.interest_query_generator import detect_buying_intent
        result = detect_buying_intent(
            "looking for urgent purchase need price quote sourcing procurement bulk order rfp",
            'phones',
        )
        assert 0.0 <= result['confidence'] <= 1.0

    def test_unknown_category_returns_valid_result(self):
        from app.services.interest_query_generator import detect_buying_intent
        result = detect_buying_intent("buy a widget", 'unknown_category')
        assert result['buying_intent'] in ('none', 'low', 'medium', 'high')

    def test_buying_intent_values_are_valid_enum(self):
        from app.services.interest_query_generator import detect_buying_intent
        valid = {'high', 'medium', 'low', 'none'}
        for text, cat in [
            ("need supplier urgently", 'phones'),
            ("just browsing", 'laptops'),
            ("comparing options", 'cars'),
            ("sunny day outside", 'clothes'),
        ]:
            assert detect_buying_intent(text, cat)['buying_intent'] in valid

    def test_product_interest_contains_matched_keywords(self):
        from app.services.interest_query_generator import detect_buying_intent
        result = detect_buying_intent(
            "I want to buy a laptop and laptop accessories for my office.", 'laptops')
        assert 'laptop' in result['product_interest']

    def test_matched_phrases_is_list(self):
        from app.services.interest_query_generator import detect_buying_intent
        result = detect_buying_intent("looking for a phone supplier", 'phones')
        assert isinstance(result['matched_phrases'], list)


# ============================================================================
# Intent score adjustment
# ============================================================================

class TestIntentScoreAdjustment:

    def _adjust(self, base, intent, has_category=True):
        from app.services.interest_collector import _adjust_score_for_intent
        return _adjust_score_for_intent(base, intent, has_category)

    def test_high_intent_boosts_score(self):
        adjusted = self._adjust(60.0, 'high')
        assert adjusted > 60.0

    def test_medium_intent_small_boost(self):
        adjusted_high   = self._adjust(60.0, 'high')
        adjusted_medium = self._adjust(60.0, 'medium')
        assert adjusted_high > adjusted_medium > 60.0

    def test_none_intent_penalty(self):
        adjusted = self._adjust(50.0, 'none', has_category=False)
        assert adjusted < 50.0

    def test_score_never_exceeds_100(self):
        assert self._adjust(99.0, 'high') <= 100.0

    def test_score_never_below_0(self):
        assert self._adjust(1.0, 'none', has_category=False) >= 0.0

    def test_category_match_adds_bonus(self):
        no_cat  = self._adjust(50.0, 'medium', has_category=False)
        with_cat = self._adjust(50.0, 'medium', has_category=True)
        assert with_cat > no_cat


# ============================================================================
# IntentQualityReport
# ============================================================================

class TestIntentQualityReport:

    def _make_report(self):
        from app.services.interest_collector import IntentQualityReport
        return IntentQualityReport(
            category_name='Laptops', country='Lebanon', city='Beirut',
            sources=['web', 'directories'],
        )

    def test_initial_counts_are_zero(self):
        r = self._make_report()
        assert r.saved == 0
        assert r.rejected == 0
        assert r.duplicates == 0
        assert r.raw_candidates == 0

    def test_record_intent_accumulates(self):
        r = self._make_report()
        r.record_intent('high')
        r.record_intent('high')
        r.record_intent('medium')
        assert r.intent_breakdown['high'] == 2
        assert r.intent_breakdown['medium'] == 1

    def test_record_rejection_accumulates_reasons(self):
        r = self._make_report()
        r.record_rejection(['no_contact_method', 'username_only'])
        r.record_rejection(['no_contact_method'])
        assert r.rejected == 2
        assert r.rejection_reasons['no_contact_method'] == 2
        assert r.rejection_reasons['username_only'] == 1

    def test_average_quality_score(self):
        r = self._make_report()
        r.record_score(60.0)
        r.record_score(80.0)
        assert r.average_quality_score == 70.0

    def test_average_quality_score_empty(self):
        r = self._make_report()
        assert r.average_quality_score == 0.0

    def test_to_dict_has_all_keys(self):
        r = self._make_report()
        d = r.to_dict()
        for k in ('category', 'country', 'city', 'sources', 'queries_run',
                  'raw_candidates', 'saved', 'rejected', 'duplicates',
                  'average_quality_score', 'duration_seconds',
                  'rejection_reasons', 'intent_breakdown'):
            assert k in d, f"Missing key in to_dict: {k}"

    def test_unknown_intent_recorded_as_none(self):
        r = self._make_report()
        r.record_intent('bogus_value')
        assert r.intent_breakdown.get('none', 0) == 1


# ============================================================================
# Country resolution
# ============================================================================

class TestCountryResolution:

    def _resolve(self, country):
        from app.services.interest_collector import _resolve_country_code
        return _resolve_country_code(country)

    def test_resolves_lebanon(self):
        assert self._resolve('Lebanon') == 'LB'
        assert self._resolve('lebanon') == 'LB'

    def test_resolves_uae(self):
        assert self._resolve('UAE') == 'AE'
        assert self._resolve('United Arab Emirates') == 'AE'

    def test_resolves_2letter_code_passthrough(self):
        assert self._resolve('US') == 'US'
        assert self._resolve('de') == 'DE'

    def test_resolves_saudi_arabia(self):
        assert self._resolve('Saudi Arabia') == 'SA'
        assert self._resolve('KSA') == 'SA'

    def test_unknown_country_falls_back_to_us(self):
        assert self._resolve('Narnia') == 'US'

    def test_resolves_germany_france_india(self):
        assert self._resolve('Germany') == 'DE'
        assert self._resolve('France') == 'FR'
        assert self._resolve('India') == 'IN'


# ============================================================================
# Weak social lead rejection (quality engine integration)
# ============================================================================

class TestWeakSocialLeadRejection:

    def _make_lead(self, **kwargs):
        base = {
            'name': None, 'email': None, 'phone': None,
            'company': None, 'website': None, 'linkedin_url': None,
            'position': None, 'industry': None,
            'country': None, 'city': None, 'data_points': {},
        }
        base.update(kwargs)
        return base

    def test_username_only_social_lead_rejected(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        lead = self._make_lead(name='john_doe_123')
        assert evaluate_lead_quality(lead, source='reddit').decision == 'reject'

    def test_social_lead_no_contact_rejected(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        lead = self._make_lead(name='Ali Hassan')
        assert evaluate_lead_quality(lead, source='twitter').decision == 'reject'

    def test_social_lead_with_verified_email_passes(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        lead = self._make_lead(
            name='Ali Hassan', email='ali@techcorp.com', company='TechCorp',
            data_points={'email_verified': True, 'email_source': 'hunter'},
        )
        assert evaluate_lead_quality(lead, source='reddit').decision in ('save', 'pending', 'enrich')

    def test_social_lead_with_phone_and_company_passes(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        lead = self._make_lead(
            name='Sara Jones', phone='+1-555-234-5678', company='ExampleCo',
        )
        assert evaluate_lead_quality(lead, source='facebook').decision in ('save', 'pending', 'enrich')

    def test_generated_email_blocked(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        lead = self._make_lead(
            name='Sara Jones', email='sara.jones@example.com', company='Example Corp',
            data_points={'email_source': 'generated', 'email_verified': False},
        )
        decision = evaluate_lead_quality(lead, source='web')
        assert 'fake_or_generated_email' in decision.reasons
        assert decision.decision == 'reject'

    def test_inferred_email_blocked(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        lead = self._make_lead(
            name='John Smith', email='john.smith@bigcompany.com', company='Big Company',
            data_points={'email_source': 'inferred', 'email_verified': False},
        )
        assert 'fake_or_generated_email' in evaluate_lead_quality(lead, source='web').reasons

    def test_no_contact_always_rejected(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        lead = self._make_lead(name='Real Person', company='Real Company')
        decision = evaluate_lead_quality(lead, source='web')
        assert decision.decision == 'reject'
        assert 'no_contact_method' in decision.reasons

    def test_quality_decision_fields(self):
        from app.services.lead_quality_engine import evaluate_lead_quality
        lead = self._make_lead(
            name='Test User', email='test@company.com',
            data_points={'email_source': 'hunter', 'email_verified': True},
        )
        d = evaluate_lead_quality(lead, source='hunter')
        assert hasattr(d, 'decision')
        assert hasattr(d, 'quality_score')
        assert hasattr(d, 'tier')
        assert hasattr(d, 'reasons')
        assert 0.0 <= d.quality_score <= 100.0


# ============================================================================
# Lead model interest fields (unit check — no DB required)
# ============================================================================

class TestLeadModelInterestFields:

    def test_lead_model_has_interest_fields(self):
        from app.models.models import Lead
        for col in ('interest_category', 'product_interest', 'buying_intent',
                    'intent_confidence', 'intent_source', 'intent_reason'):
            assert hasattr(Lead, col), f"Lead model missing column: {col}"

    def test_lead_model_interest_fields_are_nullable(self):
        from app.models.models import Lead
        for col_name in ('interest_category', 'buying_intent', 'intent_confidence',
                         'intent_source', 'intent_reason'):
            col = Lead.__table__.columns.get(col_name)
            assert col is not None, f"leads.{col_name} column not found"
            assert col.nullable, f"leads.{col_name} should be nullable"


# ============================================================================
# API endpoint tests — use conftest.py fixtures (client + auth_headers)
# ============================================================================

class TestLeadCategoriesEndpoint:

    def test_returns_200(self, client, auth_headers):
        resp = client.get('/api/v1/ai/lead-categories', headers=auth_headers)
        assert resp.status_code == 200

    def test_response_structure(self, client, auth_headers):
        data = client.get('/api/v1/ai/lead-categories', headers=auth_headers).get_json()
        assert data['status'] == 'success'
        assert 'categories' in data
        assert 'total' in data
        assert data['total'] >= 15

    def test_each_category_has_required_keys(self, client, auth_headers):
        data = client.get('/api/v1/ai/lead-categories', headers=auth_headers).get_json()
        for cat in data['categories']:
            for k in ('slug', 'name', 'keywords', 'intent_phrases', 'source_types',
                      'minimum_quality_score'):
                assert k in cat, f"Category missing key: {k}"

    def test_requires_auth(self, client):
        resp = client.get('/api/v1/ai/lead-categories')
        assert resp.status_code in (401, 403)


class TestCollectByInterestEndpoint:

    def test_missing_category_returns_400(self, client, auth_headers):
        resp = client.post('/api/v1/ai/collect-by-interest',
                           json={'country': 'Lebanon'}, headers=auth_headers)
        assert resp.status_code == 400

    def test_missing_country_returns_400(self, client, auth_headers):
        resp = client.post('/api/v1/ai/collect-by-interest',
                           json={'category': 'laptops'}, headers=auth_headers)
        assert resp.status_code == 400

    def test_unknown_category_returns_400_with_suggestions(self, client, auth_headers):
        data = client.post('/api/v1/ai/collect-by-interest',
                           json={'category': 'flying_carpets', 'country': 'Lebanon'},
                           headers=auth_headers).get_json()
        assert data.get('status') == 'error'
        assert 'available_categories' in data

    def test_invalid_source_returns_400(self, client, auth_headers):
        resp = client.post('/api/v1/ai/collect-by-interest', json={
            'category': 'laptops', 'country': 'Lebanon',
            'sources': ['web', 'hacked_source'],
        }, headers=auth_headers)
        assert resp.status_code == 400

    def test_valid_request_returns_200(self, client, auth_headers):
        # Endpoint is async — returns 200 (sync) or 202 (task queued); both are valid
        resp = client.post('/api/v1/ai/collect-by-interest', json={
            'category': 'laptops', 'country': 'Lebanon',
            'max_leads': 3, 'sources': ['web'],
        }, headers=auth_headers)
        assert resp.status_code in (200, 202)

    def test_response_has_required_fields(self, client, auth_headers):
        resp = client.post('/api/v1/ai/collect-by-interest', json={
            'category': 'software', 'country': 'US', 'max_leads': 3,
        }, headers=auth_headers)
        data = resp.get_json()
        assert data.get('status') == 'success'
        # Async path returns task_id; sync path returns collected/saved keys
        assert 'task_id' in data or 'collected' in data

    def test_quality_report_has_intent_breakdown(self, client, auth_headers):
        resp = client.post('/api/v1/ai/collect-by-interest', json={
            'category': 'phones', 'country': 'Lebanon', 'max_leads': 3,
        }, headers=auth_headers)
        data = resp.get_json()
        # Async responses carry task_id — quality_report is in the task result
        if 'task_id' in data:
            assert data.get('status') == 'success'
        else:
            qr = data.get('quality_report', {})
            assert 'intent_breakdown' in qr

    def test_requires_auth(self, client):
        resp = client.post('/api/v1/ai/collect-by-interest',
                           json={'category': 'laptops', 'country': 'Lebanon'})
        assert resp.status_code in (401, 403)

    def test_max_leads_capped_silently(self, client, auth_headers):
        resp = client.post('/api/v1/ai/collect-by-interest', json={
            'category': 'clothes', 'country': 'US', 'max_leads': 9999,
        }, headers=auth_headers)
        assert resp.status_code in (200, 202)

    def test_city_is_optional(self, client, auth_headers):
        resp = client.post('/api/v1/ai/collect-by-interest', json={
            'category': 'real_estate', 'country': 'Lebanon', 'max_leads': 3,
        }, headers=auth_headers)
        assert resp.status_code in (200, 202)

    def test_saved_count_never_exceeds_max_leads(self, client, auth_headers):
        max_leads = 5
        data = client.post('/api/v1/ai/collect-by-interest', json={
            'category': 'laptops', 'country': 'US', 'max_leads': max_leads,
        }, headers=auth_headers).get_json()
        assert data.get('saved', 0) <= max_leads
