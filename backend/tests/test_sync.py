"""
Tests for /api/v1/sync — sync status, logs, and route auth guards.

The sync service talks to Supabase (external), so tests that would trigger
actual network calls (web-to-mobile, mobile-to-web, poll) are limited to
verifying auth/role enforcement only.  Endpoints that read local DB state
(status, logs) are tested for correctness.

Fixtures used from conftest.py:
  auth_headers        — regular web user (source='web')
  mobile_auth_headers — mobile-registered user (source='mobile')
  admin_headers       — admin user (role='admin', bypasses mobile guard)
"""

import pytest

SYNC_BASE = '/api/v1/sync'


# ── Auth guards ───────────────────────────────────────────────────────────────

class TestSyncAuthGuards:
    """Every sync endpoint must reject unauthenticated requests with 401."""

    def test_status_requires_auth(self, client):
        assert client.get(f'{SYNC_BASE}/status').status_code == 401

    def test_logs_requires_auth(self, client):
        assert client.get(f'{SYNC_BASE}/logs').status_code == 401

    def test_web_to_mobile_requires_auth(self, client):
        assert client.post(f'{SYNC_BASE}/web-to-mobile').status_code == 401

    def test_mobile_to_web_requires_auth(self, client):
        assert client.post(f'{SYNC_BASE}/mobile-to-web').status_code == 401

    def test_poll_requires_auth(self, client):
        assert client.post(f'{SYNC_BASE}/poll').status_code == 401

    def test_sync_user_requires_auth(self, client):
        assert client.post(f'{SYNC_BASE}/user').status_code == 401

    def test_sync_all_users_requires_auth(self, client):
        assert client.post(f'{SYNC_BASE}/users/all').status_code == 401


class TestSyncRoleGuards:
    """Admin-only endpoints must return 403 (not 401) for non-admin users."""

    def test_poll_rejects_regular_user_with_403(self, client, auth_headers):
        resp = client.post(f'{SYNC_BASE}/poll', headers=auth_headers)
        assert resp.status_code == 403

    def test_sync_all_users_rejects_regular_user_with_403(self, client, auth_headers):
        resp = client.post(f'{SYNC_BASE}/users/all', headers=auth_headers)
        assert resp.status_code == 403

    def test_poll_role_error_is_403_not_401(self, client, auth_headers):
        """Must not return 401 — user IS authenticated, just lacks the role."""
        resp = client.post(f'{SYNC_BASE}/poll', headers=auth_headers)
        assert resp.status_code != 401


class TestMobileUserGuard:
    """Sync endpoints require source='mobile'. Web users get 403; admin bypasses."""

    def test_web_to_mobile_rejects_web_user(self, client, auth_headers):
        resp = client.post(f'{SYNC_BASE}/web-to-mobile', headers=auth_headers)
        assert resp.status_code == 403

    def test_mobile_to_web_rejects_web_user(self, client, auth_headers):
        resp = client.post(
            f'{SYNC_BASE}/mobile-to-web',
            json={'records': [{'name': 'Test'}]},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    def test_sync_user_rejects_web_user(self, client, auth_headers):
        resp = client.post(f'{SYNC_BASE}/user', headers=auth_headers)
        assert resp.status_code == 403

    def test_admin_bypasses_mobile_guard_on_web_to_mobile(self, client, admin_headers):
        """Admin (role='admin') must not be blocked by mobile_user_required."""
        resp = client.post(f'{SYNC_BASE}/web-to-mobile', headers=admin_headers)
        # 200 or Supabase-not-configured 500/200 are both acceptable — not 401/403
        assert resp.status_code not in (401, 403)

    def test_mobile_user_passes_guard(self, client, mobile_auth_headers):
        """Mobile-registered user must reach validation (not be blocked at guard)."""
        # Empty body returns 400 from validation, not 403 from guard — guard passed.
        resp = client.post(
            f'{SYNC_BASE}/mobile-to-web',
            json={},
            headers=mobile_auth_headers,
        )
        assert resp.status_code == 400  # reached validation layer


# ── GET /sync/status ──────────────────────────────────────────────────────────

class TestSyncStatus:
    def test_returns_200(self, client, auth_headers):
        resp = client.get(f'{SYNC_BASE}/status', headers=auth_headers)
        assert resp.status_code == 200

    def test_response_is_json(self, client, auth_headers):
        resp = client.get(f'{SYNC_BASE}/status', headers=auth_headers)
        assert resp.content_type.startswith('application/json')
        assert resp.get_json() is not None


# ── GET /sync/logs ────────────────────────────────────────────────────────────

class TestSyncLogs:
    def test_returns_200(self, client, auth_headers):
        resp = client.get(f'{SYNC_BASE}/logs', headers=auth_headers)
        assert resp.status_code == 200

    def test_response_has_status_success(self, client, auth_headers):
        data = client.get(f'{SYNC_BASE}/logs', headers=auth_headers).get_json()
        assert data['status'] == 'success'

    def test_response_has_logs_list(self, client, auth_headers):
        data = client.get(f'{SYNC_BASE}/logs', headers=auth_headers).get_json()
        assert 'logs' in data
        assert isinstance(data['logs'], list)

    def test_response_has_total(self, client, auth_headers):
        data = client.get(f'{SYNC_BASE}/logs', headers=auth_headers).get_json()
        assert 'total' in data
        assert isinstance(data['total'], int)

    def test_limit_param_accepted(self, client, auth_headers):
        resp = client.get(f'{SYNC_BASE}/logs?limit=5', headers=auth_headers)
        assert resp.status_code == 200


# ── POST /sync/mobile-to-web — input validation ───────────────────────────────

class TestMobileToWebValidation:
    """Input validation fires before the Supabase network call.
    Must use mobile_auth_headers — web users are rejected at the guard (403)
    before reaching validation logic.
    """

    def test_missing_records_returns_400(self, client, mobile_auth_headers):
        resp = client.post(
            f'{SYNC_BASE}/mobile-to-web',
            json={},
            headers=mobile_auth_headers,
        )
        assert resp.status_code == 400

    def test_empty_records_returns_400(self, client, mobile_auth_headers):
        resp = client.post(
            f'{SYNC_BASE}/mobile-to-web',
            json={'records': []},
            headers=mobile_auth_headers,
        )
        assert resp.status_code == 400

    def test_oversized_payload_returns_400(self, client, mobile_auth_headers):
        """More than 200 records must be rejected before any DB work."""
        records = [{'name': f'Lead {i}', 'email': f'l{i}@x.com'} for i in range(201)]
        resp = client.post(
            f'{SYNC_BASE}/mobile-to-web',
            json={'records': records},
            headers=mobile_auth_headers,
        )
        assert resp.status_code == 400
