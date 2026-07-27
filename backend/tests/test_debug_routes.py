"""
Tests that the debug blueprint is:
  - absent from the URL map in production
  - present in development / testing environments
  - functionally correct when active
"""

import os
import sys
import pytest
from unittest.mock import patch

_DEBUG_URL = '/api/v1/debug/test-login'


def _url_rules(flask_app):
    return [rule.rule for rule in flask_app.url_map.iter_rules()]


# ---------------------------------------------------------------------------
# prod_app fixture
# Two patches are required for SQLite-based test runs:
#   1. _validate() — skips production secret checks (not needed in unit tests)
#   2. SQLALCHEMY_ENGINE_OPTIONS → {} — SQLite rejects pool_size/max_overflow
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def prod_app():
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    from config.config import ProductionConfig
    with patch('config.config.ProductionConfig._validate', return_value=None), \
         patch.object(ProductionConfig, 'SQLALCHEMY_ENGINE_OPTIONS', {}):
        from app import create_app
        application = create_app('production')
        application.config['TESTING'] = True
    return application


# ---------------------------------------------------------------------------
# URL-map tests (blueprint registration gate)
# The existing `app` fixture (testing config) covers the non-production case.
# ---------------------------------------------------------------------------

def test_debug_route_absent_in_production(prod_app):
    """Debug route must NOT appear in the production URL map at all."""
    assert _DEBUG_URL not in _url_rules(prod_app), (
        f"{_DEBUG_URL} is mounted in production — this allows admin JWT issuance "
        "via an unauthenticated endpoint."
    )


def test_debug_route_present_in_testing(app):
    """Debug route must be registered when config_name is 'testing'."""
    assert _DEBUG_URL in _url_rules(app), (
        f"{_DEBUG_URL} missing from testing URL map — check blueprint gate in __init__.py"
    )


# ---------------------------------------------------------------------------
# Runtime behaviour tests (use the testing-config client from conftest)
# ---------------------------------------------------------------------------

def test_debug_login_returns_token(client):
    """In testing env the endpoint should return a JWT token."""
    resp = client.post(_DEBUG_URL, json={'email': 'dev@example.com'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'token' in data
    assert data['token']


def test_debug_login_rejects_invalid_email(client):
    """Endpoint must validate the email field even in dev/testing."""
    resp = client.post(_DEBUG_URL, json={'email': 'not-an-email'})
    assert resp.status_code == 400


def test_debug_route_returns_404_in_production(prod_app):
    """
    Production URL map has no debug route → any request to it must 404.
    This is the primary guarantee; the URL-map test above is the stricter check.
    """
    with patch.dict(os.environ, {'FLASK_ENV': 'production'}):
        with prod_app.test_client() as prod_client:
            resp = prod_client.post(_DEBUG_URL, json={'email': 'attacker@evil.com'})
            assert resp.status_code == 404
