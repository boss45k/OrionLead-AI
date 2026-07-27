"""
Rate Limiter Utility
Centralized rate limiting configuration for all routes
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import logging

logger = logging.getLogger(__name__)

_limiter = None


def init_limiter(app):
    """
    Initialize the global limiter instance (call during app creation)
    
    Args:
        app: Flask application instance
    """
    global _limiter
    
    storage_uri = os.getenv('RATE_LIMIT_REDIS_URL', 'memory://')

    if storage_uri == 'memory://' and os.getenv('FLASK_ENV') == 'production':
        logger.warning(
            'Rate limiter is using in-memory storage in production. '
            'Under multiple Gunicorn workers each process has its own counter, '
            'so per-IP limits are multiplied by the worker count. '
            'Set RATE_LIMIT_REDIS_URL to a Redis instance to enforce global limits.'
        )

    _limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["5000 per day", "500 per hour"],
        storage_uri=storage_uri,
        strategy="moving-window",
    )
    
    return _limiter


def get_limiter():
    """
    Get the global limiter instance
    
    Returns:
        Limiter instance (creates if doesn't exist)
    """
    global _limiter
    if _limiter is None:
        # Create a dummy limiter for cases where init_limiter hasn't been called
        _limiter = Limiter(
            key_func=get_remote_address,
            strategy="moving-window",
            default_limits=["5000 per day", "500 per hour"],
        )
    return _limiter
