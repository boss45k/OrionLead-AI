from flask import Flask, request, jsonify, g
from flask_cors import CORS
from flasgger import Flasgger
from marshmallow import ValidationError as MarshmallowValidationError
from config.config import config
from config.model_loader import initialize_models
from app.exceptions import APIException
from app.utils.error_handler import (
    handle_api_exception,
    handle_marshmallow_error,
    handle_generic_exception,
)
from app.utils.rate_limiter import init_limiter
from app.utils.versioning import extract_api_version, add_version_headers
from config.logging_config import setup_logging
from app.utils.openapi_spec import OpenAPISpec
from app.utils.metrics import MetricsRegistry, get_metrics_export, track_request_metrics
from app.utils.tracing import init_tracing, init_flask_tracing, TracingContextManager
import os
import logging
from uuid import uuid4
from datetime import datetime

logger = logging.getLogger(__name__)


def create_app(config_name=None):
    """Create and configure Flask app"""

    if config_name is None:
        # Default to 'production' when FLASK_ENV is unset — fail-safe.
        # Developers must explicitly set FLASK_ENV=development locally.
        # run.py does this automatically; wsgi.py enforces production.
        config_name = os.getenv('FLASK_ENV', 'production')

    if config_name not in ('development', 'production', 'testing', 'default'):
        raise ValueError(
            f"Unknown FLASK_ENV value '{config_name}'. "
            "Must be one of: development, production, testing."
        )

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # ============ Initialize Logging ============
    setup_logging(app)

    # Guard: production must never run with DEBUG enabled.
    # Flask DEBUG=True activates the Werkzeug interactive Python REPL on
    # every unhandled exception — full RCE for anyone who can trigger a 500.
    if config_name == 'production' and app.config.get('DEBUG'):
        raise RuntimeError(
            "FATAL: Production config has DEBUG=True. "
            "The Werkzeug interactive debugger is active and allows remote code "
            "execution. Set FLASK_ENV=production and ensure DEBUG is False."
        )

    # Enforce required secrets in production — fail fast rather than run insecurely
    if config_name == 'production':
        from config.config import ProductionConfig
        ProductionConfig._validate()
    
    # ============ Initialize Rate Limiting ============
    limiter = init_limiter(app)
    
    # ============ Initialize Extensions ============
    from app.models.models import db
    db.init_app(app)

    # ============ Wire Celery (SQLAlchemy broker — no Redis needed) ============
    # make_celery sets ContextTask as the base for all @celery.task decorators,
    # so every task runs inside a Flask app context automatically.
    # Wrapped in try/except so a missing kombu[sqlalchemy] package never crashes
    # the web process — tasks simply won't be dispatchable until it's installed.
    try:
        from app.celery_app import make_celery
        make_celery(app)
        logger.info('✓ Celery wired (SQLAlchemy broker)')
    except Exception as _celery_err:
        logger.warning('Celery initialisation skipped: %s', _celery_err)

    # ============ Configure CORS ============
    # CORS_ORIGINS=* allows all origins (dev default — no update needed when IP changes).
    # For production set CORS_ORIGINS to a comma-separated list of allowed origins.
    _cors_raw = os.getenv('CORS_ORIGINS', '*')
    _wildcard = _cors_raw.strip() == '*'
    cors_origins = '*' if _wildcard else [o.strip() for o in _cors_raw.split(',') if o.strip()]

    # supports_credentials cannot be True when origins='*' (browser CORS spec).
    # With wildcard we rely on the JWT in Authorization header instead of cookies.
    cors_config = {
        'origins': cors_origins,
        'methods': ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
        'allow_headers': ['Content-Type', 'Authorization', 'X-Request-ID'],
        'supports_credentials': not _wildcard,
    }
    CORS(app, resources={r'/api/*': cors_config})
    
    # ============ Configure Swagger/OpenAPI Documentation ============
    swagger_config = {
        'headers': [],
        'specs': [
            {
                'endpoint': 'apispec',
                'route': '/apispec.json',
                'rule_filter': lambda rule: True,
                'model_filter': lambda tag: True,
            }
        ],
        'static_url_path': '/flasgger_static',
        'swagger_ui': True,
        'specs_route': '/apidocs/',
        'title': 'OrionLead AI API',
        'uiversion': 3,
        'x-logo': {
            'url': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA=='  # Placeholder
        }
    }
    
    flasgger = Flasgger(
        app,
        config=swagger_config,
        template=OpenAPISpec.to_dict(),
    )
    
    # ============ Request ID Tracking ============
    @app.before_request
    def add_request_id():
        """Add request ID for tracing across logs"""
        # Use existing X-Request-ID header if present, otherwise generate new
        request_id = request.headers.get('X-Request-ID')
        if not request_id:
            request_id = str(uuid4())
        g.request_id = request_id
        
        # Extract API version from request path
        g.api_version = extract_api_version()
    
    # ============ Global Error Handlers ============
    @app.errorhandler(APIException)
    def handle_api_error(error):
        """Handle API exceptions"""
        return handle_api_exception(error)
    
    @app.errorhandler(MarshmallowValidationError)
    def handle_validation_error(error):
        """Handle Marshmallow validation errors"""
        return handle_marshmallow_error(error)
    
    @app.errorhandler(404)
    def handle_not_found(error):
        """Handle 404 errors"""
        response = {
            'error': 'NOT_FOUND',
            'message': 'Resource not found',
            'status_code': 404,
            'path': request.path,
            'request_id': g.get('request_id'),
        }
        return jsonify(response), 404
    
    @app.errorhandler(405)
    def handle_method_not_allowed(error):
        """Handle 405 errors"""
        response = {
            'error': 'METHOD_NOT_ALLOWED',
            'message': 'Method not allowed',
            'status_code': 405,
            'path': request.path,
            'request_id': g.get('request_id'),
        }
        return jsonify(response), 405
    
    @app.errorhandler(429)
    def handle_rate_limit(error):
        """Handle rate limit exceeded"""
        response = {
            'error': 'RATE_LIMITED',
            'message': 'Too many requests. Please slow down.',
            'status_code': 429,
            'path': request.path,
            'request_id': g.get('request_id'),
        }
        return jsonify(response), 429

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Handle unexpected exceptions"""
        return handle_generic_exception(error)
    
    # ============ Request/Response Logging ============
    @app.before_request
    def log_request():
        logger.info(
            f"{request.method} {request.path}",
            extra={
                'method': request.method,
                'path': request.path,
                'remote_addr': request.remote_addr,
                'user_agent': str(request.user_agent),
                'request_id': g.get('request_id'),
            }
        )
    
    @app.after_request
    def log_response(response):
        logger.info(
            f"Response: {response.status_code}",
            extra={
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
                'request_id': g.get('request_id'),
            }
        )
        # Add request ID to response headers for tracing
        response.headers['X-Request-ID'] = g.get('request_id', 'unknown')
        
        # Add API version headers
        add_version_headers(response)
        
        return response
    
    # ============ Register Blueprints ============
    from app.routes.auth import auth_bp
    from app.routes.leads import leads_bp
    from app.routes.agents import agents_bp
    from app.routes.ai import ai_bp
    from app.routes.settings import settings_bp
    from app.routes.sources import sources_bp
    from app.routes.analytics import analytics_bp
    from app.routes.sync import sync_bp
    from app.routes.mobile import mobile_bp
    from app.routes.notifications import notifications_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(leads_bp)
    app.register_blueprint(agents_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(sources_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(sync_bp)
    app.register_blueprint(mobile_bp)
    app.register_blueprint(notifications_bp)

    # Debug blueprint: only mount in development or testing.
    # Never register in production — the route issues admin JWTs and must not
    # exist in the URL map at all, not just return 404 at runtime.
    if config_name in ('development', 'testing'):
        from app.routes.debug import debug_bp
        app.register_blueprint(debug_bp)
        logger.info("Debug blueprint registered (non-production environment)")
    else:
        logger.info("Debug blueprint skipped (environment: %s)", config_name)
    
    # ============ Initialize Database ============
    with app.app_context():
        db.create_all()

        # ── Safe column migrations (idempotent ALTER TABLE) ──────────────────
        try:
            with db.engine.connect() as _conn:
                _result = _conn.execute(
                    db.text("SHOW COLUMNS FROM users LIKE 'api_key'")
                )
                if not _result.fetchone():
                    _conn.execute(db.text(
                        "ALTER TABLE users ADD COLUMN api_key VARCHAR(64) UNIQUE NULL"
                    ))
                    _conn.commit()
                    logger.info("✓ Migrated: added api_key column to users table")
        except Exception as _mig_err:
            logger.warning(f"Column migration skipped (may already exist): {_mig_err}")

        # ── device_tokens table migration (idempotent) ───────────────────────
        try:
            with db.engine.connect() as _conn:
                _result = _conn.execute(
                    db.text("SHOW TABLES LIKE 'device_tokens'")
                )
                if not _result.fetchone():
                    _conn.execute(db.text("""
                        CREATE TABLE device_tokens (
                            id          INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
                            user_id     INT          NOT NULL,
                            token       VARCHAR(512) NOT NULL UNIQUE,
                            platform    VARCHAR(20)  NOT NULL DEFAULT 'android',
                            app_version VARCHAR(20)  NULL,
                            created_at  DATETIME     NULL,
                            updated_at  DATETIME     NULL,
                            INDEX ix_device_tokens_user_id (user_id),
                            CONSTRAINT fk_device_tokens_user
                                FOREIGN KEY (user_id) REFERENCES users(id)
                                ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    _conn.commit()
                    logger.info("✓ Migrated: created device_tokens table")
        except Exception as _dt_mig_err:
            logger.warning("device_tokens migration skipped: %s", _dt_mig_err)

        # ── lead_outcomes approval columns (idempotent) ──────────────────────
        try:
            with db.engine.connect() as _conn:
                _dialect = db.engine.dialect.name
                if _dialect == 'sqlite':
                    _cols = [r[1] for r in _conn.execute(db.text("PRAGMA table_info(lead_outcomes)")).fetchall()]
                    _check = lambda col: col in _cols
                else:
                    _check = lambda col: bool(_conn.execute(
                        db.text(f"SHOW COLUMNS FROM lead_outcomes LIKE '{col}'")
                    ).fetchone())

                _new_cols = [
                    ("approval_status", "VARCHAR(20) NOT NULL DEFAULT 'approved'"),
                    ("approved_by",     "INT NULL"),
                    ("approved_at",     "DATETIME NULL"),
                    ("approval_note",   "TEXT NULL"),
                ]
                for _col_name, _col_def in _new_cols:
                    if not _check(_col_name):
                        _conn.execute(db.text(
                            f"ALTER TABLE lead_outcomes ADD COLUMN {_col_name} {_col_def}"
                        ))
                        logger.info(f"✓ Migrated: added {_col_name} to lead_outcomes")
                _conn.commit()
        except Exception as _lo_mig_err:
            logger.warning("lead_outcomes approval migration skipped: %s", _lo_mig_err)

        # ── leads.collected_by column (idempotent) ───────────────────────────
        try:
            with db.engine.connect() as _conn:
                _dialect = db.engine.dialect.name
                if _dialect == 'sqlite':
                    _lcols = [r[1] for r in _conn.execute(db.text("PRAGMA table_info(leads)")).fetchall()]
                    _has_cb = 'collected_by' in _lcols
                else:
                    _has_cb = bool(_conn.execute(
                        db.text("SHOW COLUMNS FROM leads LIKE 'collected_by'")
                    ).fetchone())
                if not _has_cb:
                    _conn.execute(db.text(
                        "ALTER TABLE leads ADD COLUMN collected_by INT NULL, "
                        "ADD INDEX ix_leads_collected_by (collected_by)"
                    ))
                    _conn.commit()
                    logger.info("✓ Migrated: added collected_by to leads table")
        except Exception as _cb_err:
            logger.warning("leads.collected_by migration skipped: %s", _cb_err)

        # ============ Load ML Models at Startup ============
        try:
            model_manager = initialize_models()
            logger.info("✓ ML Models loaded at startup")
        except Exception as e:
            logger.warning(f"Failed to initialize models: {e}")
        
        # ============ Initialize Agent Pool ============
        try:
            from app.agents.agent_pool import get_agent_pool
            from app.agents.config import AgentType
            from app.agents.query_agent import QueryAgent
            
            agent_pool = get_agent_pool()
            # QualificationAgent is now in services layer for simplicity
            # Only register QueryAgent which requires LLM
            agent_pool.register_agent_class(AgentType.QUERY, QueryAgent)
            logger.info(f"✓ Agent pool eagerly initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize agent pool: {e}")
        
        # ============ Initialize Query Cache ============
        try:
            from app.utils.query_cache import init_query_cache
            query_cache = init_query_cache(
                redis_url=os.getenv('CACHE_REDIS_URL', 'redis://localhost:6379/0')
            )
            logger.info("✓ Query cache initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize query cache: {e}")

        # ============ Pre-warm Advanced AI Stack in Background ============
        # torch + sentence-transformers imports take 10-30 s on first load.
        # Running this in a daemon thread means the app is immediately ready
        # to serve requests; the models are available seconds later.
        try:
            import threading as _t
            from app.services.advanced_ai import initialize_advanced_ai as _init_adv
            _app_ref = app

            def _prewarm():
                with _app_ref.app_context():
                    try:
                        _init_adv()
                        logger.info("✓ Advanced AI stack pre-warm complete")
                    except Exception as _e:
                        logger.warning("Advanced AI pre-warm warning: %s", _e)

            _pw = _t.Thread(target=_prewarm, name="ai-prewarm", daemon=True)
            _pw.start()
            logger.info("Advanced AI stack pre-warming in background thread…")
        except Exception as e:
            logger.warning(f"Failed to start AI pre-warm thread: {e}")
    
    # ============ Health Check Endpoint ============
    @app.route('/api/v1/health', methods=['GET'])
    def health():
        """Comprehensive health check endpoint"""
        from config.model_loader import ModelManager
        from app.agents.agent_pool import get_agent_pool
        from app.utils.query_cache import get_query_cache
        from app.utils.versioning import APIVersion
        
        model_manager = ModelManager()
        agent_pool = get_agent_pool()
        query_cache = get_query_cache()
        
        return {
            'status': 'healthy',
            'environment': config_name,
            'version': '1.0.0',
            'api_version': APIVersion.CURRENT_VERSION,
            'supported_versions': APIVersion.SUPPORTED_VERSIONS,
            'timestamp': datetime.utcnow().isoformat(),
            'components': {
                'models': model_manager.get_health_status(),
                'agent_pool': agent_pool.get_health(),
                'query_cache': query_cache.get_stats(),
            }
        }, 200
    
    # ============ Prometheus Metrics Endpoint ============
    @app.route('/metrics', methods=['GET'])
    def metrics():
        """Prometheus metrics endpoint"""
        return get_metrics_export(), 200, {'Content-Type': 'text/plain; charset=utf-8'}
    
    # ============ Startup Validation ============
    def validate_startup_config():
        """Print a config status table at startup and warn on critical issues."""
        import os

        # ── Critical security checks ──────────────────────────────────────────
        critical = []
        if app.config.get('DEBUG') and config_name not in ('development', 'testing'):
            critical.append("DEBUG=True in non-development env — RCE risk via Werkzeug debugger")

        jwt_key = os.getenv('JWT_SECRET_KEY', '')
        weak_jwt = {'jwt-secret-key', 'jwt-secret-key-change-in-production', 'jwt-secret-key-dev-only-change-in-production'}
        if not jwt_key or jwt_key in weak_jwt or len(jwt_key) < 32:
            critical.append("JWT_SECRET_KEY is weak or missing (must be >= 32 chars)")

        secret_key = os.getenv('SECRET_KEY', '')
        weak_secret = {'dev-secret-key-change-in-production', 'dev-secret-key'}
        if not secret_key or secret_key in weak_secret or len(secret_key) < 32:
            critical.append("SECRET_KEY is weak or missing (must be >= 32 chars)")

        if critical and config_name not in ('testing',):
            logger.warning("=" * 70)
            logger.warning("  CRITICAL STARTUP WARNINGS:")
            for msg in critical:
                logger.warning(f"  [CRITICAL] {msg}")
            logger.warning("=" * 70)

        # ── API key status table (skip during tests to keep output clean) ─────
        if config_name == 'testing':
            return

        _APIS = [
            ("Gemini (LLM enrichment)",     "GEMINI_API_KEY",           True),
            ("Groq (LLM fallback)",          "GROQ_API_KEY",             True),
            ("Hunter.io (email finder)",     "HUNTER_API_KEY",           False),
            ("Apollo.io (people search)",    "APOLLO_API_KEY",           False),
            ("Google Places (local biz)",    "GOOGLE_PLACES_API_KEY",    False),
            ("Serper.dev (web search)",      "SERPER_API_KEY",           False),
            ("People Data Labs (enrich)",    "PDL_API_KEY",              False),
            ("ZeroBounce (email verify)",    "ZEROBOUNCE_API_KEY",       False),
            ("Supabase (mobile sync)",       "SUPABASE_URL",             False),
            ("GitHub (repo search)",         "GITHUB_TOKEN",             False),
            ("Explorium (B2B data)",         "EXPLORIUM_API_KEY",        False),
        ]

        logger.info("=" * 70)
        logger.info("  OrionLead AI — API Configuration")
        logger.info("=" * 70)
        configured, missing_recommended = 0, []
        for name, env_var, recommended in _APIS:
            val = os.getenv(env_var, '').strip()
            if val:
                configured += 1
                logger.info(f"  [OK]      {name}")
            elif recommended:
                missing_recommended.append(name)
                logger.warning(f"  [MISSING] {name}  <-- recommended for AI features")
            else:
                logger.info(f"  [--]      {name}  (optional)")
        logger.info(f"  {configured}/{len(_APIS)} APIs configured")
        if missing_recommended:
            logger.warning(f"  Tip: set {', '.join(env_var for _, env_var, rec in _APIS if rec and not os.getenv(env_var, '').strip())} for full AI capability")
        logger.info("=" * 70)
    
    try:
        validate_startup_config()
    except Exception as e:
        logger.warning(f"Startup validation error: {e}")

    # ============ Background Auto-Sync Scheduler ============
    # Pushes pending MySQL leads → Supabase every 10 minutes.
    # Only starts when Supabase is configured; skipped in testing.
    # Guarded against Flask dev-mode double-start (Werkzeug reloader forks twice).
    if config_name != 'testing':
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            _should_start = (not app.debug) or (os.environ.get('WERKZEUG_RUN_MAIN') == 'true')
            if _should_start:
                _scheduler = BackgroundScheduler(daemon=True)
                _app_ref   = app

                def _auto_sync_job():
                    try:
                        with _app_ref.app_context():
                            from app.services.sync_service import get_sync_service
                            svc = get_sync_service()
                            if not svc._configured:
                                return
                            result = svc.web_to_mobile(triggered_by='scheduler')
                            if result.get('synced', 0) > 0 or result.get('failed', 0) > 0:
                                logger.info(f'[Scheduler] Auto-sync complete: {result}')
                    except Exception as _e:
                        logger.warning(f'[Scheduler] Auto-sync error: {_e}')

                _scheduler.add_job(
                    _auto_sync_job,
                    'interval',
                    minutes=int(os.getenv('SYNC_INTERVAL_MINUTES', '10')),
                    id='auto_sync',
                    replace_existing=True,
                    max_instances=1,
                    misfire_grace_time=60,
                )
                _scheduler.start()
                logger.info(
                    f'✓ Auto-sync scheduler started '
                    f'(every {os.getenv("SYNC_INTERVAL_MINUTES", "10")} min)'
                )
        except Exception as e:
            logger.warning(f'Auto-sync scheduler failed to start: {e}')

    # ============ Initialize Jaeger Tracing ============
    try:
        tracer = init_tracing(app_name='ai-lead-system')
        TracingContextManager.set_tracer(tracer)
        if tracer:
            init_flask_tracing(app, tracer)
            logger.info("Jaeger tracing initialized successfully")
    except Exception as e:
        logger.warning(f"Jaeger tracing initialization failed: {e}")
    
    return app
