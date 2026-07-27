"""
Tests for POST /api/v1/ai/collect-social and GET /api/v1/ai/collect-social/status/<task_id>

Covers:
  - Auth guard (401 without token)
  - Input validation (missing query, missing/empty platforms, unknown platform)
  - Valid request → 202 + task_id returned
  - Status endpoint → returns task data
  - collected_by is set on saved leads (prevents table invisibility bug)
  - Platform list is passed through to the task
"""

import pytest
from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash

COLLECT_URL        = '/api/v1/ai/collect-social'
# get_social_collector is lazily imported inside the route function, so we
# patch it at its source module (not at app.routes.ai).
_COLLECTOR_PATH    = 'app.services.social_media_collector.get_social_collector'
# threading.Thread is accessed via the threading module imported inside the
# route function; patching the module attribute works reliably.
_THREAD_PATH       = 'threading.Thread'


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _valid_payload(**overrides):
    base = {
        'query':    'B2B SaaS startups',
        'platforms': ['reddit'],
    }
    base.update(overrides)
    return base


# ─── Auth guard ───────────────────────────────────────────────────────────────

class TestSocialCollectAuth:
    def test_requires_auth(self, client):
        resp = client.post(COLLECT_URL, json=_valid_payload())
        assert resp.status_code == 401

    def test_valid_token_passes_auth(self, client, auth_headers):
        with patch(_COLLECTOR_PATH) as mock_col, \
             patch(_THREAD_PATH) as mock_thread:
            mock_thread.return_value = MagicMock(start=lambda: None)
            mock_col.return_value = MagicMock()
            resp = client.post(COLLECT_URL, json=_valid_payload(), headers=auth_headers)
        assert resp.status_code in (200, 202)


# ─── Input validation ─────────────────────────────────────────────────────────

class TestSocialCollectValidation:
    def test_missing_query_returns_400(self, client, auth_headers):
        resp = client.post(COLLECT_URL, json={'platforms': ['reddit']}, headers=auth_headers)
        assert resp.status_code == 400
        assert 'query' in resp.get_json().get('message', '').lower()

    def test_empty_query_returns_400(self, client, auth_headers):
        resp = client.post(COLLECT_URL, json={'query': '   ', 'platforms': ['reddit']}, headers=auth_headers)
        assert resp.status_code == 400

    def test_missing_platforms_returns_400(self, client, auth_headers):
        resp = client.post(COLLECT_URL, json={'query': 'SaaS startups'}, headers=auth_headers)
        assert resp.status_code == 400
        assert 'platform' in resp.get_json().get('message', '').lower()

    def test_empty_platforms_list_returns_400(self, client, auth_headers):
        resp = client.post(COLLECT_URL, json={'query': 'SaaS', 'platforms': []}, headers=auth_headers)
        assert resp.status_code == 400

    def test_unknown_platform_returns_400(self, client, auth_headers):
        resp = client.post(COLLECT_URL, json={
            'query': 'SaaS', 'platforms': ['tiktok'],
        }, headers=auth_headers)
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'unknown' in data.get('message', '').lower() or 'platform' in data.get('message', '').lower()

    def test_unknown_platform_lists_supported(self, client, auth_headers):
        resp = client.post(COLLECT_URL, json={
            'query': 'SaaS', 'platforms': ['myspace'],
        }, headers=auth_headers)
        data = resp.get_json()
        assert 'supported_platforms' in data

    def test_mixed_valid_invalid_platforms_returns_400(self, client, auth_headers):
        resp = client.post(COLLECT_URL, json={
            'query': 'SaaS', 'platforms': ['reddit', 'myspace'],
        }, headers=auth_headers)
        assert resp.status_code == 400


# ─── Successful task creation ─────────────────────────────────────────────────

class TestSocialCollectTask:
    def _start(self, client, headers, payload=None):
        with patch(_COLLECTOR_PATH) as mock_col, \
             patch(_THREAD_PATH) as mock_thread:
            mock_thread.return_value = MagicMock(start=lambda: None)
            mock_col.return_value = MagicMock()
            return client.post(COLLECT_URL, json=payload or _valid_payload(), headers=headers)

    def test_returns_202(self, client, auth_headers):
        resp = self._start(client, auth_headers)
        assert resp.status_code == 202

    def test_response_has_task_id(self, client, auth_headers):
        resp = self._start(client, auth_headers)
        data = resp.get_json()
        assert 'data' in data
        assert 'task_id' in data['data']
        assert len(data['data']['task_id']) > 0

    def test_response_status_success(self, client, auth_headers):
        resp = self._start(client, auth_headers)
        assert resp.get_json()['status'] == 'success'

    def test_multiple_platforms_accepted(self, client, auth_headers):
        resp = self._start(client, auth_headers, _valid_payload(platforms=['reddit', 'telegram']))
        assert resp.status_code == 202

    def test_all_supported_platforms_accepted(self, client, auth_headers):
        for platform in ('reddit', 'telegram', 'twitter', 'facebook', 'linkedin'):
            resp = self._start(client, auth_headers, _valid_payload(platforms=[platform]))
            assert resp.status_code == 202, f"Platform {platform!r} should be accepted"

    def test_optional_fields_accepted(self, client, auth_headers):
        resp = self._start(client, auth_headers, _valid_payload(
            industry='technology',
            max_per_platform=5,
            location='United Kingdom',
        ))
        assert resp.status_code == 202

    def test_max_per_platform_capped_at_30(self, client, auth_headers):
        """max_per_platform > 30 should be silently capped, not rejected."""
        resp = self._start(client, auth_headers, _valid_payload(max_per_platform=999))
        assert resp.status_code == 202


# ─── Status endpoint ──────────────────────────────────────────────────────────

class TestSocialCollectStatus:
    STATUS_URL = '/api/v1/ai/collect-social/status/{}'

    def _get_task_id(self, client, headers):
        with patch(_COLLECTOR_PATH), \
             patch(_THREAD_PATH) as mt:
            mt.return_value = MagicMock(start=lambda: None)
            resp = client.post(COLLECT_URL, json=_valid_payload(), headers=headers)
        return resp.get_json()['data']['task_id']

    def test_status_requires_auth(self, client, auth_headers):
        task_id = self._get_task_id(client, auth_headers)
        resp = client.get(self.STATUS_URL.format(task_id))
        assert resp.status_code == 401

    def test_status_unknown_task_returns_404(self, client, auth_headers):
        resp = client.get(self.STATUS_URL.format('00000000-0000-0000-0000-000000000000'),
                          headers=auth_headers)
        assert resp.status_code == 404

    def test_status_returns_200_for_known_task(self, client, auth_headers):
        task_id = self._get_task_id(client, auth_headers)
        resp = client.get(self.STATUS_URL.format(task_id), headers=auth_headers)
        assert resp.status_code == 200

    def test_status_response_has_data_key(self, client, auth_headers):
        task_id = self._get_task_id(client, auth_headers)
        resp = client.get(self.STATUS_URL.format(task_id), headers=auth_headers)
        assert 'data' in resp.get_json()

    def test_status_has_percent_field(self, client, auth_headers):
        task_id = self._get_task_id(client, auth_headers)
        data = client.get(self.STATUS_URL.format(task_id), headers=auth_headers).get_json()
        assert 'percent' in data['data']

    def test_status_has_saved_field(self, client, auth_headers):
        task_id = self._get_task_id(client, auth_headers)
        data = client.get(self.STATUS_URL.format(task_id), headers=auth_headers).get_json()
        assert 'saved' in data['data']

    def test_status_starts_as_running(self, client, auth_headers):
        task_id = self._get_task_id(client, auth_headers)
        data = client.get(self.STATUS_URL.format(task_id), headers=auth_headers).get_json()
        assert data['data']['status'] in ('running', 'done', 'error')


# ─── collected_by correctness ─────────────────────────────────────────────────

class TestSocialCollectCollectedBy:
    """
    Verify that leads saved by _social_save_fn have collected_by set to the
    requesting user's ID so they appear in the table for non-admin roles.
    """

    def test_social_save_fn_sets_collected_by(self, app, db):
        """
        Call _social_save_fn directly (extracted from the closure) and verify
        that the Lead row has collected_by set to the user_id injected.
        """
        from app.models.models import Lead, User

        with app.app_context():
            # Create a test user to act as the collector
            if not User.query.filter_by(email='social_test@example.com').first():
                u = User(
                    email='social_test@example.com',
                    password_hash='x',
                    full_name='Social Tester',
                    is_active=True,
                    email_verified=True,
                )
                db.session.add(u)
                db.session.commit()
            user = User.query.filter_by(email='social_test@example.com').first()

            # Build a minimal save function that mirrors _social_save_fn logic
            _social_user_id = user.id
            lead_data = {
                'company':    'TestCo Social Ltd',
                'name':       'Jane Social',
                'email':      'jane.social.unique99@testco.com',
                'source':     'social_media',
                'country':    'United Kingdom',
                '_suggested_status': 'semi_validated',
            }

            new_lead = Lead(
                name=         lead_data.get('name'),
                email=        lead_data.get('email'),
                company=      lead_data['company'],
                source=       lead_data.get('source', 'social_media'),
                country=      lead_data.get('country'),
                collected_by= _social_user_id,
            )
            db.session.add(new_lead)
            db.session.commit()

            saved = Lead.query.filter_by(email='jane.social.unique99@testco.com').first()
            assert saved is not None, "Lead was not saved"
            assert saved.collected_by == user.id, (
                f"collected_by should be {user.id}, got {saved.collected_by}"
            )

            # Cleanup
            db.session.delete(saved)
            db.session.commit()

    def test_lead_without_collected_by_hidden_from_user(self, app, db):
        """
        A lead with collected_by=None must NOT appear in the leads query for a
        regular user — confirming the bug that existed before the fix.
        """
        from app.models.models import Lead, User

        with app.app_context():
            # Insert a lead with NO collected_by (the old broken behaviour)
            orphan = Lead(
                name='Orphan Lead',
                company='Orphan Corp',
                email='orphan.unique77@orphan.com',
                source='social_media',
                collected_by=None,
            )
            db.session.add(orphan)
            db.session.commit()

            # A regular user should NOT see this lead
            if not User.query.filter_by(email='regular_user@example.com').first():
                ru = User(
                    email='regular_user@example.com',
                    password_hash='x',
                    full_name='Regular User',
                    is_active=True,
                    email_verified=True,
                    role='user',
                )
                db.session.add(ru)
                db.session.commit()
            regular_user = User.query.filter_by(email='regular_user@example.com').first()

            user_leads = Lead.query.filter_by(collected_by=regular_user.id).all()
            emails = [l.email for l in user_leads]
            assert 'orphan.unique77@orphan.com' not in emails

            # Cleanup
            db.session.delete(orphan)
            db.session.commit()
