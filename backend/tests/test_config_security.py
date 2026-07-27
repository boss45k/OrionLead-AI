"""
Tests for environment mode hardening (Issue 2).
Verifies that production config cannot accidentally run with DEBUG enabled,
and that the fail-safe default applies.
"""

import os
import sys
import pytest
from unittest.mock import patch


def _backend_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_path():
    d = _backend_dir()
    if d not in sys.path:
        sys.path.insert(0, d)


# ---------------------------------------------------------------------------
# ProductionConfig class-level checks
# ---------------------------------------------------------------------------

def test_production_config_debug_is_false():
    """ProductionConfig must have DEBUG=False at the class level."""
    _ensure_path()
    from config.config import ProductionConfig
    assert ProductionConfig.DEBUG is False, (
        "ProductionConfig.DEBUG must be False. Enabling it activates the "
        "Werkzeug interactive debugger (RCE risk)."
    )


def test_development_config_debug_is_true():
    """DevelopmentConfig must have DEBUG=True — verifies the separation is explicit."""
    _ensure_path()
    from config.config import DevelopmentConfig
    assert DevelopmentConfig.DEBUG is True


def test_testing_config_has_no_pool_options():
    """TestingConfig must have empty SQLALCHEMY_ENGINE_OPTIONS for SQLite compat."""
    _ensure_path()
    from config.config import TestingConfig
    assert TestingConfig.SQLALCHEMY_ENGINE_OPTIONS == {}


# ---------------------------------------------------------------------------
# _validate() rejects DEBUG=True at the class level
# ---------------------------------------------------------------------------

def test_production_validate_raises_if_debug_true():
    """_validate() must raise ValueError when DEBUG is True on ProductionConfig."""
    _ensure_path()
    from config.config import ProductionConfig
    with patch.object(ProductionConfig, 'DEBUG', True):
        with pytest.raises(ValueError, match="DEBUG is True"):
            ProductionConfig._validate()


# ---------------------------------------------------------------------------
# create_app() guards
# ---------------------------------------------------------------------------

def test_create_app_raises_for_unknown_env():
    """create_app() must reject unrecognised FLASK_ENV values."""
    _ensure_path()
    from app import create_app
    with pytest.raises((ValueError, KeyError)):
        create_app('not_a_real_env')


def test_create_app_production_debug_guard():
    """
    create_app() must raise RuntimeError if production config somehow has DEBUG=True.
    This is the first line of defense before _validate() runs.
    """
    _ensure_path()
    from config.config import ProductionConfig
    with patch('config.config.ProductionConfig._validate', return_value=None), \
         patch.object(ProductionConfig, 'DEBUG', True), \
         patch.object(ProductionConfig, 'SQLALCHEMY_ENGINE_OPTIONS', {}):
        from app import create_app
        with pytest.raises(RuntimeError, match="DEBUG=True"):
            create_app('production')


# ---------------------------------------------------------------------------
# Default config_name is production when FLASK_ENV is unset
# ---------------------------------------------------------------------------

def test_default_config_is_production_when_env_unset():
    """
    When FLASK_ENV is not set, create_app() must use 'production', not 'development'.
    This prevents accidental DEBUG=True if the env var is forgotten on a server.
    """
    _ensure_path()
    from config.config import ProductionConfig
    env_without_flask_env = {k: v for k, v in os.environ.items() if k != 'FLASK_ENV'}

    with patch.dict(os.environ, env_without_flask_env, clear=True), \
         patch('config.config.ProductionConfig._validate', return_value=None), \
         patch.object(ProductionConfig, 'SQLALCHEMY_ENGINE_OPTIONS', {}):
        from app import create_app
        prod_app = create_app()
        assert prod_app.config['DEBUG'] is False, (
            "App created without FLASK_ENV must default to production (DEBUG=False)."
        )


# ---------------------------------------------------------------------------
# Testing-config app has DEBUG=True but that is expected (not production)
# ---------------------------------------------------------------------------

def test_testing_app_has_debug_true(app):
    """TestingConfig sets DEBUG=True — this is intentional and expected."""
    assert app.config['DEBUG'] is True
    assert app.config['TESTING'] is True
