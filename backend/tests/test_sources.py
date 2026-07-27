"""
Tests for /api/v1/sources — data sources CRUD and sync trigger.

All routes require JWT auth.  DELETE additionally requires admin role.
Sources are backed by an in-process dict (not the DB), so tests manipulate
the module-level DATA_SOURCES dict directly via the app context.
"""

import pytest


SOURCES_URL = '/api/v1/sources'


# ── Helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope='function')
def admin_headers(client, app):
    """Create an admin user and return its Authorization headers."""
    from app.models.models import db as _db, User
    from werkzeug.security import generate_password_hash

    with app.app_context():
        if not User.query.filter_by(email='src_admin@example.com').first():
            _db.session.add(User(
                email='src_admin@example.com',
                password_hash=generate_password_hash('AdminPass123!'),
                full_name='Src Admin',
                role='admin',
                is_active=True,
                email_verified=True,
            ))
            _db.session.commit()

    resp = client.post('/api/v1/auth/login', json={
        'email': 'src_admin@example.com',
        'password': 'AdminPass123!',
    })
    token = resp.get_json().get('token', '')
    return {'Authorization': f'Bearer {token}'}


# ── Authentication guard ──────────────────────────────────────────────────────

class TestSourcesAuth:
    def test_list_requires_auth(self, client):
        resp = client.get(SOURCES_URL)
        assert resp.status_code == 401

    def test_create_requires_auth(self, client):
        resp = client.post(SOURCES_URL, json={'name': 'X', 'type': 'API'})
        assert resp.status_code == 401

    def test_delete_requires_auth(self, client):
        resp = client.delete(f'{SOURCES_URL}/1')
        assert resp.status_code == 401

    def test_delete_requires_admin(self, client, auth_headers):
        """Regular user (role=user) must receive 403, not 401."""
        resp = client.delete(f'{SOURCES_URL}/1', headers=auth_headers)
        assert resp.status_code == 403


# ── GET /sources ──────────────────────────────────────────────────────────────

class TestGetSources:
    def test_returns_200(self, client, admin_headers):
        resp = client.get(SOURCES_URL, headers=admin_headers)
        assert resp.status_code == 200

    def test_response_has_status_success(self, client, admin_headers):
        data = client.get(SOURCES_URL, headers=admin_headers).get_json()
        assert data['status'] == 'success'

    def test_response_has_data_list(self, client, admin_headers):
        data = client.get(SOURCES_URL, headers=admin_headers).get_json()
        assert isinstance(data['data'], list)

    def test_response_has_stats(self, client, admin_headers):
        data = client.get(SOURCES_URL, headers=admin_headers).get_json()
        stats = data['stats']
        assert 'total_sources' in stats
        assert 'active_sources' in stats
        assert 'total_records' in stats


# ── POST /sources ─────────────────────────────────────────────────────────────

class TestCreateSource:
    def test_create_returns_201(self, client, admin_headers):
        resp = client.post(SOURCES_URL, json={
            'name': 'Test API Source',
            'type': 'API',
            'url': 'https://api.example.com',
        }, headers=admin_headers)
        assert resp.status_code == 201

    def test_create_response_has_id(self, client, admin_headers):
        resp = client.post(SOURCES_URL, json={
            'name': 'Another Source',
            'type': 'CSV',
        }, headers=admin_headers)
        data = resp.get_json()
        assert 'id' in data['data']

    def test_create_missing_name_returns_400(self, client, admin_headers):
        resp = client.post(SOURCES_URL, json={'type': 'API'}, headers=admin_headers)
        assert resp.status_code == 400

    def test_create_missing_type_returns_400(self, client, admin_headers):
        resp = client.post(SOURCES_URL, json={'name': 'Nameless'}, headers=admin_headers)
        assert resp.status_code == 400


# ── PUT /sources/<id> ─────────────────────────────────────────────────────────

class TestUpdateSource:
    def test_update_existing_returns_200(self, client, admin_headers):
        resp = client.put(f'{SOURCES_URL}/1', json={'name': 'Updated LinkedIn'}, headers=admin_headers)
        assert resp.status_code == 200

    def test_update_reflects_new_name(self, client, admin_headers):
        # Create a user-defined source (not a built-in), then rename it
        create_resp = client.post(SOURCES_URL, json={
            'name': 'Original Name',
            'type': 'API',
        }, headers=admin_headers)
        source_id = create_resp.get_json()['data']['id']
        client.put(f'{SOURCES_URL}/{source_id}', json={'name': 'Renamed Source'}, headers=admin_headers)
        data = client.get(SOURCES_URL, headers=admin_headers).get_json()
        names = [s['name'] for s in data['data']]
        assert 'Renamed Source' in names

    def test_update_nonexistent_returns_404(self, client, admin_headers):
        resp = client.put(f'{SOURCES_URL}/99999', json={'name': 'Ghost'}, headers=admin_headers)
        assert resp.status_code == 404


# ── POST /sources/<id>/sync ───────────────────────────────────────────────────

class TestSyncSource:
    def test_sync_existing_returns_200(self, client, admin_headers):
        resp = client.post(f'{SOURCES_URL}/1/sync', headers=admin_headers)
        assert resp.status_code == 200

    def test_sync_response_has_synced_records(self, client, admin_headers):
        data = client.post(f'{SOURCES_URL}/1/sync', headers=admin_headers).get_json()
        assert 'synced_records' in data['data']
        assert isinstance(data['data']['synced_records'], int)

    def test_sync_nonexistent_returns_404(self, client, admin_headers):
        resp = client.post(f'{SOURCES_URL}/99999/sync', headers=admin_headers)
        assert resp.status_code == 404


# ── DELETE /sources/<id> (admin only) ────────────────────────────────────────

class TestDeleteSource:
    def test_admin_can_delete(self, client, admin_headers):
        # First create a source so we have something to delete
        create_resp = client.post(SOURCES_URL, json={
            'name': 'To Be Deleted',
            'type': 'API',
        }, headers=admin_headers)
        source_id = create_resp.get_json()['data']['id']

        del_resp = client.delete(f'{SOURCES_URL}/{source_id}', headers=admin_headers)
        assert del_resp.status_code == 200

    def test_delete_nonexistent_returns_404(self, client, admin_headers):
        resp = client.delete(f'{SOURCES_URL}/99999', headers=admin_headers)
        assert resp.status_code == 404
