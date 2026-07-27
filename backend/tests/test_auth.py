"""
Tests for authentication routes and security decorators.

Covers:
  - Login anti-enumeration: unknown email and wrong password return identical 401
  - Role enforcement: admin_required and manager_or_admin_required return 403 not 401
  - Token validation: missing token (401 AUTHENTICATION_ERROR),
                      invalid/garbage token (401 INVALID_TOKEN),
                      expired token (401 TOKEN_EXPIRED)
"""

import jwt
import pytest
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash


# ── Shared helpers ────────────────────────────────────────────────────────────

_ADMIN_ROUTE = '/api/v1/auth/admin/users'
_PROFILE_ROUTE = '/api/v1/auth/profile'

# Must match conftest.py os.environ.setdefault for JWT_SECRET_KEY
_TEST_JWT_SECRET = 'test-jwt-secret-minimum-32-bytes-long!!'
_TEST_JWT_ALGO   = 'HS256'


def _make_token(user_id, email, role='user', exp_delta=timedelta(hours=1)):
    """Mint a JWT signed with the test secret."""
    now = datetime.now(timezone.utc)
    payload = {
        'user_id': user_id,
        'email':   email,
        'role':    role,
        'iat':     now,
        'exp':     now + exp_delta,
    }
    return jwt.encode(payload, _TEST_JWT_SECRET, algorithm=_TEST_JWT_ALGO)


def _make_expired_token(user_id, email, role='user'):
    """Mint a JWT that expired 2 hours ago."""
    return _make_token(user_id, email, role, exp_delta=timedelta(hours=-2))


@pytest.fixture(scope='function')
def admin_headers(client, app):
    """Create an admin user and return its Authorization headers."""
    from app.models.models import db as _db, User

    with app.app_context():
        admin = User.query.filter_by(email='admin@example.com').first()
        if not admin:
            admin = User(
                email='admin@example.com',
                password_hash=generate_password_hash('AdminPass123!'),
                full_name='Admin User',
                role='admin',
                is_active=True,
                email_verified=True,
            )
            _db.session.add(admin)
            _db.session.commit()

    resp = client.post('/api/v1/auth/login', json={
        'email': 'admin@example.com',
        'password': 'AdminPass123!',
    })
    token = resp.get_json().get('token', '')
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture(scope='function')
def registered_user(app):
    """Ensure test@example.com exists; return (user_id, email, password_hash)."""
    from app.models.models import db as _db, User

    with app.app_context():
        user = User.query.filter_by(email='test@example.com').first()
        if not user:
            user = User(
                email='test@example.com',
                password_hash=generate_password_hash('TestPass123!'),
                full_name='Test User',
                is_active=True,
                role='user',
                email_verified=True,
            )
            _db.session.add(user)
            _db.session.commit()
        return user.id, user.email


# ── Login anti-enumeration ────────────────────────────────────────────────────

class TestLoginEnumeration:
    """
    Both 'no such email' and 'wrong password' must produce an identical response
    so that the status code cannot be used to enumerate valid email addresses.
    """

    def test_unknown_email_returns_401(self, client):
        resp = client.post('/api/v1/auth/login', json={
            'email': 'nobody@nowhere.invalid',
            'password': 'AnyPassword1!',
        })
        assert resp.status_code == 401
        body = resp.get_json()
        assert body['error'] == 'AUTHENTICATION_ERROR'
        assert body['message'] == 'Invalid credentials'

    def test_wrong_password_returns_401(self, client, registered_user):
        resp = client.post('/api/v1/auth/login', json={
            'email': 'test@example.com',
            'password': 'WrongPassword!',
        })
        assert resp.status_code == 401
        body = resp.get_json()
        assert body['error'] == 'AUTHENTICATION_ERROR'
        assert body['message'] == 'Invalid credentials'

    def test_enumeration_responses_are_identical(self, client, registered_user):
        """
        Both failure paths must return the same HTTP status AND the same JSON
        shape, so that callers cannot distinguish a missing account from a bad
        password.
        """
        unknown_resp = client.post('/api/v1/auth/login', json={
            'email': 'nobody@nowhere.invalid',
            'password': 'AnyPassword1!',
        })
        wrong_pw_resp = client.post('/api/v1/auth/login', json={
            'email': 'test@example.com',
            'password': 'WrongPassword!',
        })

        assert unknown_resp.status_code == wrong_pw_resp.status_code == 401

        unknown_body   = unknown_resp.get_json()
        wrong_pw_body  = wrong_pw_resp.get_json()

        # Both must carry the same discriminating fields
        assert unknown_body['error']   == wrong_pw_body['error']
        assert unknown_body['message'] == wrong_pw_body['message']

    def test_valid_login_returns_token(self, client, registered_user):
        """Sanity check — correct credentials still work."""
        resp = client.post('/api/v1/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPass123!',
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert 'token' in body


# ── Role enforcement ──────────────────────────────────────────────────────────

class TestRoleEnforcement:
    """
    admin_required and manager_or_admin_required must return 403, not 401.
    Returning 401 would cause clients that clear tokens on 401 (e.g. the mobile
    AuthContext) to silently log out an authenticated user who simply lacks the
    required role.
    """

    def test_admin_route_rejects_regular_user_with_403(self, client, auth_headers):
        """A valid token with role='user' hitting an admin route → 403."""
        resp = client.get(_ADMIN_ROUTE, headers=auth_headers)
        assert resp.status_code == 403
        body = resp.get_json()
        assert body['error'] == 'AUTHORIZATION_ERROR'

    def test_admin_route_does_not_return_401_for_wrong_role(self, client, auth_headers):
        """
        Must not be 401 — that would be confused with 'not authenticated'.
        The user IS authenticated; they just lack the required role.
        """
        resp = client.get(_ADMIN_ROUTE, headers=auth_headers)
        assert resp.status_code != 401

    def test_admin_route_allows_admin_user(self, client, admin_headers):
        """A valid admin token must be admitted (not blocked by the decorator)."""
        resp = client.get(_ADMIN_ROUTE, headers=admin_headers)
        # 200 OK or any non-403/401 success code is acceptable
        assert resp.status_code not in (401, 403)

    def test_manager_promoted_to_admin_passes_admin_check(self, client, app):
        """Explicitly verify a manager token is rejected from admin-only routes."""
        from app.models.models import db as _db, User

        with app.app_context():
            mgr = User.query.filter_by(email='manager@example.com').first()
            if not mgr:
                mgr = User(
                    email='manager@example.com',
                    password_hash=generate_password_hash('MgrPass123!'),
                    full_name='Manager User',
                    role='manager',
                    is_active=True,
                    email_verified=True,
                )
                _db.session.add(mgr)
                _db.session.commit()

        resp = client.post('/api/v1/auth/login', json={
            'email': 'manager@example.com',
            'password': 'MgrPass123!',
        })
        token = resp.get_json().get('token', '')
        mgr_headers = {'Authorization': f'Bearer {token}'}

        # Manager must be refused admin-only route with 403 (not 401)
        resp = client.get(_ADMIN_ROUTE, headers=mgr_headers)
        assert resp.status_code == 403
        assert resp.get_json()['error'] == 'AUTHORIZATION_ERROR'


# ── Token validation ──────────────────────────────────────────────────────────

class TestTokenValidation:
    """token_required must produce well-typed error codes for every failure mode."""

    def test_missing_authorization_header_returns_401(self, client):
        resp = client.get(_PROFILE_ROUTE)  # no Authorization header
        assert resp.status_code == 401
        body = resp.get_json()
        assert body['error'] == 'AUTHENTICATION_ERROR'

    def test_malformed_bearer_prefix_returns_401(self, client):
        """'Token abc' instead of 'Bearer abc' → invalid format."""
        resp = client.get(_PROFILE_ROUTE, headers={'Authorization': 'Token garbage'})
        # The split on ' ' yields 'garbage' which is an invalid JWT
        assert resp.status_code == 401

    def test_garbage_token_returns_invalid_token_error(self, client):
        resp = client.get(_PROFILE_ROUTE, headers={
            'Authorization': 'Bearer this.is.not.a.real.jwt'
        })
        assert resp.status_code == 401
        body = resp.get_json()
        assert body['error'] == 'INVALID_TOKEN'

    def test_expired_token_returns_token_expired_error(self, client, registered_user):
        user_id, email = registered_user
        expired_token = _make_expired_token(user_id, email)
        resp = client.get(_PROFILE_ROUTE, headers={
            'Authorization': f'Bearer {expired_token}'
        })
        assert resp.status_code == 401
        body = resp.get_json()
        assert body['error'] == 'TOKEN_EXPIRED'

    def test_token_signed_with_wrong_secret_returns_invalid_token(self, client, registered_user):
        """A token signed by a different secret must be rejected."""
        user_id, email = registered_user
        forged = jwt.encode(
            {'user_id': user_id, 'email': email, 'role': 'admin',
             'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
            'wrong-secret',
            algorithm=_TEST_JWT_ALGO,
        )
        resp = client.get(_PROFILE_ROUTE, headers={'Authorization': f'Bearer {forged}'})
        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'INVALID_TOKEN'

    def test_valid_token_grants_access(self, client, registered_user):
        """Sanity check — a fresh, correctly-signed token must be accepted."""
        user_id, email = registered_user
        token = _make_token(user_id, email, role='user')
        resp = client.get(_PROFILE_ROUTE, headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200
