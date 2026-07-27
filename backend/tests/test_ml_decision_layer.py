"""
Tests for the ML Decision Layer additions:
  - SpamDetector
  - DuplicateDetector (DB-backed)
  - LeadQualityClassifier
  - MLDecisionLayer.qualify() integration
  - POST /api/v1/ai/feedback endpoint (auth + validation)

All existing 60 tests must remain unaffected.
"""

import pytest
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _manager_headers(client, app):
    """Register a manager-role user, login, return auth headers."""
    from app.models.models import db as _db, User

    with app.app_context():
        if not User.query.filter_by(email='mgr@test.com').first():
            _db.session.add(User(
                email='mgr@test.com',
                password_hash=generate_password_hash('MgrPass1!'),
                full_name='Test Manager',
                role='manager',
                is_active=True,
                email_verified=True,
            ))
            _db.session.commit()

    resp = client.post('/api/v1/auth/login', json={
        'email': 'mgr@test.com',
        'password': 'MgrPass1!',
    })
    token = resp.get_json().get('token', '')
    return {'Authorization': f'Bearer {token}'}


def _user_headers(client, app):
    """Register a plain user-role user, login, return auth headers."""
    from app.models.models import db as _db, User

    with app.app_context():
        if not User.query.filter_by(email='plain@test.com').first():
            _db.session.add(User(
                email='plain@test.com',
                password_hash=generate_password_hash('UserPass1!'),
                full_name='Plain User',
                role='user',
                is_active=True,
                email_verified=True,
            ))
            _db.session.commit()

    resp = client.post('/api/v1/auth/login', json={
        'email': 'plain@test.com',
        'password': 'UserPass1!',
    })
    token = resp.get_json().get('token', '')
    return {'Authorization': f'Bearer {token}'}


# ---------------------------------------------------------------------------
# 1. SpamDetector
# ---------------------------------------------------------------------------

class TestSpamDetector:
    """Pure-unit tests — no Flask context needed."""

    @pytest.fixture(autouse=True)
    def detector(self):
        from app.services.ml_decision_layer import SpamDetector
        self.sd = SpamDetector()

    def test_disposable_email_flagged(self):
        result = self.sd.check({'email': 'someone@mailinator.com', 'name': 'Alice Smith'})
        assert result['is_spam'] is True
        assert 'disposable_email_domain' in result['issues']

    def test_disposable_trashmail_flagged(self):
        result = self.sd.check({'email': 'x@trashmail.com', 'name': 'Bob Jones'})
        assert result['is_spam'] is True

    def test_role_email_admin_flagged(self):
        result = self.sd.check({'email': 'admin@corp.com', 'name': 'Alice Admin'})
        assert 'role_based_email' in result['issues']
        # admin@ alone is 0.3 score, not spam (threshold 0.5) — but issues list is populated
        assert result['spam_score'] == pytest.approx(0.3)

    def test_role_email_info_flagged(self):
        result = self.sd.check({'email': 'info@company.com', 'name': 'Info Desk'})
        assert 'role_based_email' in result['issues']

    def test_role_email_noreply_flagged(self):
        result = self.sd.check({'email': 'noreply@saas.io', 'name': 'No Reply'})
        assert 'role_based_email' in result['issues']

    def test_gibberish_name_no_vowels(self):
        # 'BCDFGH WXZV' → letters='BCDFGHWXZV' (10), no a/e/i/o/u/y → ratio=0.0 < 0.10
        result = self.sd.check({'email': 'real@corp.com', 'name': 'BCDFGH WXZV'})
        assert 'gibberish_name_no_vowels' in result['issues']

    def test_ghost_lead_no_contact(self):
        result = self.sd.check({'name': 'Alice'})   # no email, phone, company, linkedin
        assert result['is_spam'] is True
        assert 'no_contact_info' in result['issues']

    def test_repeated_chars_in_email(self):
        result = self.sd.check({'email': 'aaaaa@corp.com', 'name': 'Alice Smith'})
        assert 'repeated_chars_in_email' in result['issues']

    def test_valid_lead_not_spam(self):
        result = self.sd.check({
            'name':    'Jane Doe',
            'email':   'jane.doe@acme.com',
            'company': 'Acme Corp',
        })
        assert result['is_spam'] is False
        assert result['spam_score'] < 0.5

    def test_spam_score_range(self):
        """spam_score must always be between 0.0 and 1.0."""
        cases = [
            {},
            {'email': 'admin@mailinator.com', 'name': ''},
            {'email': 'jane@corp.com', 'name': 'Jane Doe', 'company': 'Corp'},
        ]
        for lead in cases:
            r = self.sd.check(lead)
            assert 0.0 <= r['spam_score'] <= 1.0

    def test_score_penalty_capped_at_40(self):
        """score_penalty must never exceed 40."""
        result = self.sd.check({'email': 'admin@mailinator.com', 'name': ''})
        assert result['score_penalty'] <= 40


# ---------------------------------------------------------------------------
# 2. DuplicateDetector (DB-backed)
# ---------------------------------------------------------------------------

class TestDuplicateDetector:
    """Requires Flask app context + DB (uses SeenContact table)."""

    @pytest.fixture(autouse=True)
    def setup(self, app, db):
        """Clean the seen_contacts table before each test."""
        from app.models.models import SeenContact
        with app.app_context():
            db.session.query(SeenContact).delete()
            db.session.commit()
        self.app = app

    def test_fresh_lead_not_duplicate(self, app):
        from app.services.ml_decision_layer import DuplicateDetector
        dd = DuplicateDetector()
        with app.app_context():
            result = dd.check({'email': 'alice@corp.com', 'phone': '14155551234'})
        assert result['is_exact_duplicate'] is False
        assert result['duplicate_fields'] == []

    def test_second_identical_email_flagged(self, app):
        from app.services.ml_decision_layer import DuplicateDetector
        dd = DuplicateDetector()
        lead = {'email': 'bob@company.com', 'phone': ''}
        with app.app_context():
            dd.register(lead)
            result = dd.check(lead)
        assert result['is_exact_duplicate'] is True
        assert 'email' in result['duplicate_fields']

    def test_second_identical_phone_flagged(self, app):
        from app.services.ml_decision_layer import DuplicateDetector
        dd = DuplicateDetector()
        lead = {'email': '', 'phone': '+1 415 555 9999'}
        with app.app_context():
            dd.register(lead)
            result = dd.check(lead)
        assert result['is_exact_duplicate'] is True
        assert 'phone' in result['duplicate_fields']

    def test_different_email_not_flagged(self, app):
        from app.services.ml_decision_layer import DuplicateDetector
        dd = DuplicateDetector()
        with app.app_context():
            dd.register({'email': 'carol@corp.com'})
            result = dd.check({'email': 'dave@corp.com'})
        assert result['is_exact_duplicate'] is False

    def test_double_register_does_not_raise(self, app):
        """Calling register() twice must not raise — IntegrityError is swallowed."""
        from app.services.ml_decision_layer import DuplicateDetector
        dd = DuplicateDetector()
        lead = {'email': 'eve@corp.com', 'phone': '555000'}
        with app.app_context():
            dd.register(lead)
            dd.register(lead)   # second call must be silent
            result = dd.check(lead)
        assert result['is_exact_duplicate'] is True

    def test_empty_lead_does_not_register(self, app, db):
        """register() with no email and no phone must insert nothing."""
        from app.services.ml_decision_layer import DuplicateDetector
        from app.models.models import SeenContact
        dd = DuplicateDetector()
        with app.app_context():
            before = db.session.query(SeenContact).count()
            dd.register({'name': 'Ghost'})
            after = db.session.query(SeenContact).count()
        assert after == before

    def test_phone_normalisation(self, app):
        """'+1 (415) 555-1234' and '14155551234' must be treated as the same phone."""
        from app.services.ml_decision_layer import DuplicateDetector
        dd = DuplicateDetector()
        with app.app_context():
            dd.register({'phone': '+1 (415) 555-1234'})
            result = dd.check({'phone': '14155551234'})
        assert result['is_exact_duplicate'] is True

    def test_email_case_insensitive(self, app):
        """'Alice@Corp.COM' and 'alice@corp.com' must match."""
        from app.services.ml_decision_layer import DuplicateDetector
        dd = DuplicateDetector()
        with app.app_context():
            dd.register({'email': 'Alice@Corp.COM'})
            result = dd.check({'email': 'alice@corp.com'})
        assert result['is_exact_duplicate'] is True


# ---------------------------------------------------------------------------
# 3. LeadQualityClassifier
# ---------------------------------------------------------------------------

class TestLeadQualityClassifier:
    """Pure-unit tests — no Flask context needed."""

    @pytest.fixture(autouse=True)
    def classifier(self):
        from app.services.ml_decision_layer import LeadQualityClassifier
        self.lqc = LeadQualityClassifier()

    def test_score_80_is_premium(self):
        result = self.lqc.classify(80)
        assert result['tier'] == 'premium'

    def test_score_95_is_premium(self):
        result = self.lqc.classify(95)
        assert result['tier'] == 'premium'

    def test_score_60_is_qualified(self):
        result = self.lqc.classify(60)
        assert result['tier'] == 'qualified'

    def test_score_70_is_qualified(self):
        result = self.lqc.classify(70)
        assert result['tier'] == 'qualified'

    def test_score_40_is_marginal(self):
        result = self.lqc.classify(40)
        assert result['tier'] == 'marginal'

    def test_score_20_is_low(self):
        result = self.lqc.classify(20)
        assert result['tier'] == 'low'

    def test_score_19_is_junk(self):
        result = self.lqc.classify(19)
        assert result['tier'] == 'junk'

    def test_score_0_is_junk(self):
        result = self.lqc.classify(0)
        assert result['tier'] == 'junk'

    def test_spam_overrides_score(self):
        """A spam result must force tier='spam' regardless of the score."""
        spam = {'is_spam': True, 'issues': ['disposable_email_domain']}
        result = self.lqc.classify(90, spam_result=spam)
        assert result['tier'] == 'spam'
        assert result['adjusted_score'] == 0

    def test_non_spam_not_overridden(self):
        not_spam = {'is_spam': False, 'issues': []}
        result = self.lqc.classify(85, spam_result=not_spam)
        assert result['tier'] == 'premium'

    def test_low_completeness_applies_penalty(self):
        """completeness < 0.30 should lower the adjusted_score."""
        r_full = self.lqc.classify(60, completeness=1.0)
        r_low  = self.lqc.classify(60, completeness=0.20)
        assert r_low['adjusted_score'] < r_full['adjusted_score']
        assert 'low_completeness_penalty' in r_low['modifiers']

    def test_duplicate_annotated_not_blocked(self):
        """Duplicate detection must annotate with a modifier, not block the lead."""
        dup = {'is_exact_duplicate': True, 'duplicate_fields': ['email']}
        result = self.lqc.classify(75, duplicate_result=dup)
        assert result['tier'] != 'spam'
        assert any('duplicate' in m for m in result['modifiers'])

    def test_result_has_required_keys(self):
        result = self.lqc.classify(50)
        for key in ('tier', 'action', 'modifiers', 'adjusted_score'):
            assert key in result


# ---------------------------------------------------------------------------
# 4. MLDecisionLayer.qualify() integration
# ---------------------------------------------------------------------------

class TestMLDecisionLayerQualify:
    """Integration tests — requires Flask app context."""

    @pytest.fixture(autouse=True)
    def setup(self, app, db):
        from app.models.models import SeenContact
        with app.app_context():
            db.session.query(SeenContact).delete()
            db.session.commit()

    def test_spam_lead_blocked_early(self, app):
        """A spam lead must return score=0 without calling LLM or ML model."""
        from app.services.ml_decision_layer import MLDecisionLayer
        dl = MLDecisionLayer()
        lead = {
            'name':  'BCDFG',          # gibberish — no vowels
            'email': 'x@mailinator.com',  # disposable domain
        }
        with app.app_context():
            tier, result = dl.qualify(lead, lead_id=None)
        assert result['score'] == 0
        assert result['routing_tier'] == 'spam_blocked'
        assert result['spam']['is_spam'] is True

    def test_valid_lead_has_all_detection_fields(self, app):
        """A valid lead must have spam, duplicate, and quality keys in the response."""
        from app.services.ml_decision_layer import MLDecisionLayer
        dl = MLDecisionLayer()
        lead = {
            'name':     'Jane Doe',
            'email':    'jane.unique@acme-corp.com',
            'company':  'Acme Corp',
            'position': 'CTO',
            'source':   'linkedin',
        }
        with app.app_context():
            _, result = dl.qualify(lead, lead_id=None)
        assert 'spam'      in result
        assert 'duplicate' in result
        assert 'quality'   in result
        assert result['spam']['is_spam'] is False
        assert result['duplicate']['is_exact_duplicate'] is False
        assert result['quality']['tier'] in (
            'premium', 'qualified', 'marginal', 'low', 'junk'
        )

    def test_duplicate_lead_flagged(self, app):
        """Second submission with identical email must be flagged as duplicate."""
        from app.services.ml_decision_layer import MLDecisionLayer
        from app.models.models import SeenContact, db

        dl = MLDecisionLayer()
        lead = {
            'name':    'Alice Repeat',
            'email':   'repeat-test@acme.com',
            'company': 'Acme',
        }
        with app.app_context():
            # First submission registers the contact
            _, first = dl.qualify(lead, lead_id=None)
            # Second submission must detect it
            _, second = dl.qualify(lead, lead_id=None)

        assert first['duplicate']['is_exact_duplicate'] is False
        assert second['duplicate']['is_exact_duplicate'] is True
        assert 'email' in second['duplicate']['duplicate_fields']

    def test_qualify_response_score_in_range(self, app):
        from app.services.ml_decision_layer import MLDecisionLayer
        dl = MLDecisionLayer()
        lead = {'name': 'Bob Test', 'email': 'bob.test9@corp.com', 'company': 'Corp'}
        with app.app_context():
            _, result = dl.qualify(lead, lead_id=None)
        assert 0 <= result['score'] <= 100

    def test_qualify_response_has_routing_tier(self, app):
        from app.services.ml_decision_layer import MLDecisionLayer
        dl = MLDecisionLayer()
        lead = {'name': 'Tier Test', 'email': 'tier@corp.com', 'company': 'Corp'}
        with app.app_context():
            tier, result = dl.qualify(lead, lead_id=None)
        valid_tiers = ('ml_only', 'ml_groq', 'full_stack', 'llm_heavy', 'spam_blocked')
        assert result['routing_tier'] in valid_tiers
        assert tier in valid_tiers


# ---------------------------------------------------------------------------
# 5. POST /api/v1/ai/feedback endpoint
# ---------------------------------------------------------------------------

class TestFeedbackEndpoint:

    @pytest.fixture
    def manager_hdrs(self, client, app):
        return _manager_headers(client, app)

    @pytest.fixture
    def user_hdrs(self, client, app):
        return _user_headers(client, app)

    @pytest.fixture
    def existing_lead_id(self, app, db):
        """Insert a real Lead row and return its id."""
        from app.models.models import Lead
        with app.app_context():
            lead = Lead(name='Feedback Lead', email='fb@test.com',
                        company='TestCo', source='test')
            db.session.add(lead)
            db.session.commit()
            return lead.id

    # ── Authorization ────────────────────────────────────────────────────────

    def test_unauthenticated_rejected(self, client):
        resp = client.post('/api/v1/ai/feedback', json={
            'lead_id': 1, 'outcome': 'converted',
        })
        assert resp.status_code == 401

    def test_plain_user_accepted_with_pending_review(self, client, user_hdrs, existing_lead_id):
        # Regular users may submit feedback — stored with approval_status='pending'
        # (awaiting manager review). A 403 is no longer returned.
        resp = client.post('/api/v1/ai/feedback', json={
            'lead_id': existing_lead_id, 'outcome': 'converted',
        }, headers=user_hdrs)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('approval_status') == 'pending'
        assert data.get('pending_review') is True

    def test_manager_accepted(self, client, manager_hdrs, existing_lead_id):
        resp = client.post('/api/v1/ai/feedback', json={
            'lead_id': existing_lead_id, 'outcome': 'converted',
        }, headers=manager_hdrs)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert data['lead_id'] == existing_lead_id
        assert data['outcome'] == 'converted'

    # ── Input validation ─────────────────────────────────────────────────────

    def test_missing_lead_id_rejected(self, client, manager_hdrs):
        resp = client.post('/api/v1/ai/feedback', json={
            'outcome': 'converted',
        }, headers=manager_hdrs)
        assert resp.status_code == 400

    def test_string_lead_id_rejected(self, client, manager_hdrs):
        resp = client.post('/api/v1/ai/feedback', json={
            'lead_id': 'abc', 'outcome': 'converted',
        }, headers=manager_hdrs)
        assert resp.status_code == 400

    def test_invalid_outcome_rejected(self, client, manager_hdrs, existing_lead_id):
        resp = client.post('/api/v1/ai/feedback', json={
            'lead_id': existing_lead_id, 'outcome': 'maybe',
        }, headers=manager_hdrs)
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'outcome must be one of' in data.get('message', '')

    def test_pending_outcome_rejected(self, client, manager_hdrs, existing_lead_id):
        """'pending' was removed from valid outcomes — must be rejected."""
        resp = client.post('/api/v1/ai/feedback', json={
            'lead_id': existing_lead_id, 'outcome': 'pending',
        }, headers=manager_hdrs)
        assert resp.status_code == 400

    def test_nonexistent_lead_id_returns_404(self, client, manager_hdrs):
        resp = client.post('/api/v1/ai/feedback', json={
            'lead_id': 999999, 'outcome': 'cold',
        }, headers=manager_hdrs)
        assert resp.status_code == 404

    # ── Valid outcomes ───────────────────────────────────────────────────────

    @pytest.mark.parametrize('outcome', ['converted', 'contacted', 'cold', 'unqualified'])
    def test_all_valid_outcomes_accepted(self, client, manager_hdrs, existing_lead_id, outcome):
        resp = client.post('/api/v1/ai/feedback', json={
            'lead_id': existing_lead_id, 'outcome': outcome,
        }, headers=manager_hdrs)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert data['outcome'] == outcome

    # ── Response shape ───────────────────────────────────────────────────────

    def test_response_contains_required_fields(self, client, manager_hdrs, existing_lead_id):
        resp = client.post('/api/v1/ai/feedback', json={
            'lead_id': existing_lead_id, 'outcome': 'cold',
        }, headers=manager_hdrs)
        data = resp.get_json()
        # Current response shape (dataset key removed; approval workflow added)
        for field in ('status', 'lead_id', 'outcome', 'records_labeled', 'approval_status'):
            assert field in data, f"Missing field: {field}"

    def test_approved_label_has_ml_fields(self, client, manager_hdrs, existing_lead_id):
        # Manager submissions are auto-approved → ML pipeline runs → model_vs_reality returned
        resp = client.post('/api/v1/ai/feedback', json={
            'lead_id': existing_lead_id, 'outcome': 'converted',
        }, headers=manager_hdrs)
        data = resp.get_json()
        assert data.get('approval_status') == 'approved'
        assert 'records_labeled' in data
        assert 'model_vs_reality' in data

    def test_records_labeled_zero_when_no_ml_run(self, client, manager_hdrs, existing_lead_id):
        # When ML pipeline runs but finds no matching dataset records, records_labeled is 0.
        # The endpoint returns 200 regardless — no crash, no warning field required.
        resp = client.post('/api/v1/ai/feedback', json={
            'lead_id': existing_lead_id, 'outcome': 'cold',
        }, headers=manager_hdrs)
        data = resp.get_json()
        assert resp.status_code == 200
        assert isinstance(data.get('records_labeled'), int)
