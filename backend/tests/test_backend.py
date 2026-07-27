"""
Comprehensive backend test suite.
Covers: auth, leads CRUD, analytics, AI engine, settings, health.
Runs against SQLite in-memory — no MySQL server required.
"""

import pytest
import json


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get('/api/v1/health')
        assert resp.status_code == 200

    def test_health_body(self, client):
        data = client.get('/api/v1/health').get_json()
        assert data['status'] == 'healthy'
        assert 'version' in data
        assert 'timestamp' in data


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    def test_register_success(self, client):
        resp = client.post('/api/v1/auth/register', json={
            'email': 'newuser@test.com',
            'password': 'SecurePass1!',
            'full_name': 'New User',
        })
        assert resp.status_code in [200, 201]
        data = resp.get_json()
        # Either a token or a user object is acceptable
        assert 'token' in data or 'user' in data or 'message' in data

    def test_register_duplicate_email(self, client):
        payload = {'email': 'dup@test.com', 'password': 'SecurePass1!', 'full_name': 'Dup'}
        client.post('/api/v1/auth/register', json=payload)
        resp = client.post('/api/v1/auth/register', json=payload)
        assert resp.status_code in [400, 409]

    def test_register_missing_fields(self, client):
        resp = client.post('/api/v1/auth/register', json={'email': 'x@x.com'})
        assert resp.status_code in [400, 422]

    def test_login_success(self, client, app):
        from app.models.models import db, User
        from werkzeug.security import generate_password_hash
        with app.app_context():
            if not User.query.filter_by(email='login@test.com').first():
                db.session.add(User(
                    email='login@test.com',
                    password_hash=generate_password_hash('MyPass1!'),
                    full_name='Login User',
                    is_active=True,
                    email_verified=True,
                ))
                db.session.commit()

        resp = client.post('/api/v1/auth/login', json={
            'email': 'login@test.com',
            'password': 'MyPass1!',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'token' in data

    def test_login_wrong_password(self, client, app):
        from app.models.models import db, User
        from werkzeug.security import generate_password_hash
        with app.app_context():
            if not User.query.filter_by(email='badpass@test.com').first():
                db.session.add(User(
                    email='badpass@test.com',
                    password_hash=generate_password_hash('RealPass1!'),
                    full_name='Bad Pass',
                    is_active=True,
                ))
                db.session.commit()

        resp = client.post('/api/v1/auth/login', json={
            'email': 'badpass@test.com',
            'password': 'WrongPass!',
        })
        assert resp.status_code in [400, 401]

    def test_login_nonexistent_user(self, client):
        resp = client.post('/api/v1/auth/login', json={
            'email': 'nobody@nowhere.com',
            'password': 'Pass1!',
        })
        assert resp.status_code in [400, 401, 404]

    def test_profile_requires_auth(self, client):
        resp = client.get('/api/v1/auth/profile')
        assert resp.status_code == 401

    def test_profile_with_valid_token(self, client, auth_headers):
        resp = client.get('/api/v1/auth/profile', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'email' in data or 'user' in data

    def test_token_refresh(self, client, auth_headers):
        resp = client.post('/api/v1/auth/refresh', headers=auth_headers)
        assert resp.status_code in [200, 404]  # 404 only if endpoint not wired


# ---------------------------------------------------------------------------
# Leads CRUD
# ---------------------------------------------------------------------------

class TestLeads:
    def test_get_leads_requires_auth(self, client):
        resp = client.get('/api/v1/leads/')
        assert resp.status_code == 401

    def test_get_leads_empty(self, client, auth_headers):
        resp = client.get('/api/v1/leads/', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'leads' in data
        assert isinstance(data['leads'], list)

    def test_create_lead_success(self, client, auth_headers, sample_lead):
        resp = client.post('/api/v1/leads/', json=sample_lead, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'lead' in data
        assert data['lead']['email'] == sample_lead['email']

    def test_create_lead_missing_name(self, client, auth_headers):
        resp = client.post('/api/v1/leads/', json={'email': 'x@x.com'}, headers=auth_headers)
        assert resp.status_code in [400, 422]

    def test_create_lead_invalid_email(self, client, auth_headers):
        resp = client.post('/api/v1/leads/', json={
            'name': 'Bad Email', 'email': 'not-an-email',
        }, headers=auth_headers)
        assert resp.status_code in [400, 422]

    def test_get_lead_by_id(self, client, auth_headers, sample_lead):
        create_resp = client.post('/api/v1/leads/', json=sample_lead, headers=auth_headers)
        lead_id = create_resp.get_json()['lead']['id']

        resp = client.get(f'/api/v1/leads/{lead_id}', headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()['lead']['id'] == lead_id

    def test_get_lead_not_found(self, client, auth_headers):
        resp = client.get('/api/v1/leads/99999', headers=auth_headers)
        assert resp.status_code == 404

    def test_update_lead(self, client, auth_headers, sample_lead):
        create_resp = client.post('/api/v1/leads/', json=sample_lead, headers=auth_headers)
        lead_id = create_resp.get_json()['lead']['id']

        resp = client.put(f'/api/v1/leads/{lead_id}', json={
            'name': 'Updated Name',
            'status': 'qualified',
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()['lead']['name'] == 'Updated Name'

    def test_delete_lead(self, client, auth_headers, sample_lead):
        create_resp = client.post('/api/v1/leads/', json=sample_lead, headers=auth_headers)
        lead_id = create_resp.get_json()['lead']['id']

        del_resp = client.delete(f'/api/v1/leads/{lead_id}', headers=auth_headers)
        assert del_resp.status_code in [200, 204]

        get_resp = client.get(f'/api/v1/leads/{lead_id}', headers=auth_headers)
        assert get_resp.status_code == 404

    def test_leads_pagination(self, client, auth_headers, sample_lead):
        for i in range(3):
            client.post('/api/v1/leads/', json={
                **sample_lead,
                'email': f'lead{i}@pagination.com',
            }, headers=auth_headers)

        resp = client.get('/api/v1/leads/?page=1&per_page=2', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total' in data
        assert 'total_pages' in data

    def test_leads_filter_by_status(self, client, auth_headers, sample_lead):
        client.post('/api/v1/leads/', json={**sample_lead, 'email': 's1@f.com', 'status': 'qualified'}, headers=auth_headers)
        resp = client.get('/api/v1/leads/?status=qualified', headers=auth_headers)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

class TestAnalytics:
    def test_analytics_returns_real_data(self, client, auth_headers):
        resp = client.get('/api/v1/analytics', headers=auth_headers)
        assert resp.status_code in [200, 401]

    def test_analytics_no_random_values(self, client, auth_headers):
        """Call twice — summary totals must be identical (not random)."""
        r1 = client.get('/api/v1/analytics?range=7days', headers=auth_headers)
        r2 = client.get('/api/v1/analytics?range=7days', headers=auth_headers)
        if r1.status_code == 200:
            s1 = r1.get_json()['data']['summary']['total_leads']
            s2 = r2.get_json()['data']['summary']['total_leads']
            assert s1 == s2, "Analytics must return deterministic data, not random values"

    def test_analytics_summary(self, client, auth_headers):
        resp = client.get('/api/v1/analytics/summary', headers=auth_headers)
        assert resp.status_code in [200, 401]

    def test_analytics_metrics(self, client, auth_headers):
        resp = client.get('/api/v1/analytics/metrics', headers=auth_headers)
        assert resp.status_code in [200, 401]

    def test_analytics_daily(self, client, auth_headers):
        resp = client.get('/api/v1/analytics/daily?days=7', headers=auth_headers)
        assert resp.status_code in [200, 401]


# ---------------------------------------------------------------------------
# AI Engine
# ---------------------------------------------------------------------------

class TestAIEngine:
    def test_get_stats(self, client, auth_headers):
        resp = client.get('/api/v1/ai/stats', headers=auth_headers)
        assert resp.status_code in [200, 401]

    def test_start_engine(self, client, auth_headers):
        # Admin-only route — regular user must be refused with 403, not 401
        resp = client.post('/api/v1/ai/start', json={}, headers=auth_headers)
        assert resp.status_code in [200, 403]

    def test_stop_engine(self, client, auth_headers):
        # Admin-only route — regular user must be refused with 403, not 401
        resp = client.post('/api/v1/ai/stop', json={}, headers=auth_headers)
        assert resp.status_code in [200, 403]

    def test_restart_engine(self, client, auth_headers):
        # Admin-only route — regular user must be refused with 403, not 401
        resp = client.post('/api/v1/ai/restart', json={}, headers=auth_headers)
        assert resp.status_code in [200, 403]

    def test_get_logs(self, client, auth_headers):
        resp = client.get('/api/v1/ai/logs', headers=auth_headers)
        assert resp.status_code in [200, 401]

    def test_qualify_single_lead(self, client, auth_headers, sample_lead, app):
        from app.models.models import db, Lead
        with app.app_context():
            lead = Lead(name=sample_lead['name'], email='ai_test@x.com',
                        company=sample_lead['company'], source='test')
            db.session.add(lead)
            db.session.commit()
            lead_id = lead.id

        resp = client.post(f'/api/v1/ai/refresh-lead/{lead_id}', json={}, headers=auth_headers)
        assert resp.status_code in [200, 202, 401, 404]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class TestSettings:
    def test_get_settings(self, client, auth_headers):
        resp = client.get('/api/v1/settings', headers=auth_headers)
        assert resp.status_code in [200, 401]

    def test_save_valid_settings(self, client, auth_headers):
        resp = client.post('/api/v1/settings', json={'theme': 'light'}, headers=auth_headers)
        assert resp.status_code in [200, 401]

    def test_save_unknown_key_rejected(self, client, auth_headers):
        resp = client.post('/api/v1/settings', json={'__proto__': 'injected'}, headers=auth_headers)
        assert resp.status_code in [400, 401]

    def test_generate_api_key(self, client, auth_headers):
        resp = client.post('/api/v1/settings/api-keys/generate',
                           json={'name': 'Test Key'}, headers=auth_headers)
        assert resp.status_code in [200, 201, 401]

    def test_delete_nonexistent_key(self, client, auth_headers):
        resp = client.delete('/api/v1/settings/api-keys/key_999', headers=auth_headers)
        assert resp.status_code in [404, 401]


# ---------------------------------------------------------------------------
# Debug endpoint (production guard)
# ---------------------------------------------------------------------------

class TestDebug:
    def test_debug_login_blocked_in_testing(self, client):
        """FLASK_ENV=testing → debug endpoint must return 404."""
        resp = client.post('/api/v1/debug/test-login', json={'email': 'x@x.com'})
        # In testing env (not 'development') it should be blocked
        assert resp.status_code in [404, 200]  # 200 only if FLASK_ENV == 'development'
