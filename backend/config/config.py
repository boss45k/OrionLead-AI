import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '..', '..', '.env'))

class Config:
    """Base configuration"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Database - Use environment variables (required for security)
    _DEFAULT_DB_URL = 'mysql+pymysql://root:password@localhost:3306/ai_lead_db'
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', _DEFAULT_DB_URL)

    # This is a placeholder - MUST be set via environment variable in production
    if not os.getenv('DATABASE_URL'):
        raise ValueError(
            "ERROR: DATABASE_URL environment variable must be set. "
            "See .env.example for format. "
            "NEVER commit hardcoded credentials to version control!"
        )

    # Warn only when the literal placeholder default is still in use
    if SQLALCHEMY_DATABASE_URI == _DEFAULT_DB_URL:
        logger.warning("WARNING: DATABASE_URL is using the placeholder default — update it with real credentials!")
    
    # Connection pooling for better scalability
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,              # Base connection pool size
        'pool_recycle': 3600,         # Recycle connections after 1 hour (MySQL timeout)
        'pool_pre_ping': True,        # Verify connections before use
        'max_overflow': 40,           # Max temporary connections beyond pool_size
        'echo': False                 # Set True for SQL debugging
    }
    
    # JWT — weak defaults are intentional for dev only; production enforces strong values
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key-dev-only-change-in-production')
    JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
    JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', 24))
    
    # AI/ML
    MODEL_PATH = os.getenv('MODEL_PATH', './models/')
    MAX_WORKERS = int(os.getenv('MAX_WORKERS', 4))
    BATCH_SIZE = int(os.getenv('BATCH_SIZE', 32))
    CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', 0.5))
    
    # Data Collection
    CRAWL_RATE_LIMIT = int(os.getenv('CRAWL_RATE_LIMIT', 10))
    CRAWL_TIMEOUT = int(os.getenv('CRAWL_TIMEOUT', 30))
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'logs/app.log')
    
    # Redis
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')

class DevelopmentConfig(Config):
    """Development configuration — local dev only, never deploy to production."""
    # DEBUG=True enables the Werkzeug interactive REPL on error pages (RCE risk).
    # create_app() will refuse to start a production instance with DEBUG=True.
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False   # Must remain False — enforced by create_app() guard + _validate()
    TESTING = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    @classmethod
    def _validate(cls):
        # DEBUG must be False in production — enforced here as a second layer
        # after the guard in create_app().
        if cls.DEBUG:
            raise ValueError(
                "PRODUCTION ERROR: ProductionConfig.DEBUG is True. "
                "This activates the Werkzeug interactive debugger (RCE risk). "
                "This value must never be overridden to True in production."
            )

        _WEAK_JWT = {
            'jwt-secret-key',
            'jwt-secret-key-change-in-production',
            'jwt-secret-key-dev-only-change-in-production',
        }
        _WEAK_SECRET = {'dev-secret-key-change-in-production', 'dev-secret-key'}

        jwt_key = os.getenv('JWT_SECRET_KEY', '')
        if not jwt_key or jwt_key in _WEAK_JWT or len(jwt_key) < 32:
            raise ValueError(
                "PRODUCTION ERROR: JWT_SECRET_KEY must be set to a strong secret "
                "(≥32 chars, not a well-known default)."
            )

        secret_key = os.getenv('SECRET_KEY', '')
        if not secret_key or secret_key in _WEAK_SECRET or len(secret_key) < 32:
            raise ValueError(
                "PRODUCTION ERROR: SECRET_KEY must be set to a strong secret "
                "(≥32 chars, not a well-known default)."
            )

        # Supabase service key is required for sync to work in production
        if not os.getenv('SUPABASE_URL'):
            raise ValueError("PRODUCTION ERROR: SUPABASE_URL must be set.")
        if not os.getenv('SUPABASE_SERVICE_KEY'):
            raise ValueError("PRODUCTION ERROR: SUPABASE_SERVICE_KEY must be set.")

        # Gemini or Groq key required for AI features
        if not os.getenv('GEMINI_API_KEY') and not os.getenv('GROQ_API_KEY'):
            logger.warning(
                "WARNING: Neither GEMINI_API_KEY nor GROQ_API_KEY is set — "
                "AI features will fall back to rule-based scoring only."
            )

class TestingConfig:
    """Testing configuration — uses SQLite in-memory, no external dependencies required."""
    DEBUG = True
    TESTING = True
    SECRET_KEY = 'test-secret-key-minimum-32-bytes-long!!'
    JWT_SECRET_KEY = 'test-jwt-secret-minimum-32-bytes-long!!'
    JWT_ALGORITHM = 'HS256'
    JWT_EXPIRATION_HOURS = 1
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {}  # SQLite doesn't need pooling options
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    LOG_LEVEL = 'WARNING'
    LOG_FILE = None
    MODEL_PATH = './models/'
    MAX_WORKERS = 1
    BATCH_SIZE = 10
    CONFIDENCE_THRESHOLD = 0.5
    CRAWL_RATE_LIMIT = 10
    CRAWL_TIMEOUT = 30
    REDIS_URL = 'redis://localhost:6379'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
