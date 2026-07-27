"""
Celery Application Configuration
Broker: SQLAlchemy transport backed by the existing MySQL DB — no Redis required.
Result backend: same MySQL DB via the `db+` scheme.
"""

import os
import logging
from celery import Celery
from celery.schedules import crontab

# config.py calls load_dotenv() at import time → DATABASE_URL is available
from config.config import config  # noqa: F401 (side-effect: loads .env)

logger = logging.getLogger(__name__)


def _broker_url() -> str:
    """
    Build the Celery broker URL from DATABASE_URL.
    mysql+pymysql://user:pass@host:port/db → sqla+mysql+pymysql://user:pass@host:port/db
    Falls back to a local SQLite file when DATABASE_URL is absent (unit tests).
    """
    db_url = os.getenv('DATABASE_URL', '').strip()
    if not db_url:
        return 'sqla+sqlite:///celery_broker.db'
    return f'sqla+{db_url}'


def _backend_url() -> str:
    """
    Build the Celery result-backend URL from DATABASE_URL.
    mysql+pymysql://... → db+mysql+pymysql://...
    """
    db_url = os.getenv('DATABASE_URL', '').strip()
    if not db_url:
        return 'db+sqlite:///celery_results.db'
    return f'db+{db_url}'


celery = Celery('orionlead')

celery.conf.update(
    # ── Broker & backend ─────────────────────────────────────────────────────
    broker_url=_broker_url(),
    result_backend=_backend_url(),

    # ── Serialization ─────────────────────────────────────────────────────────
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # ── Task execution ────────────────────────────────────────────────────────
    task_track_started=True,
    task_time_limit=30 * 60,        # 30-min hard kill
    task_soft_time_limit=28 * 60,   # 28-min soft (SoftTimeLimitExceeded raised)
    worker_prefetch_multiplier=1,   # fair dispatch — essential for long tasks
    worker_max_tasks_per_child=200, # recycle workers periodically to free memory

    # ── Result expiry ─────────────────────────────────────────────────────────
    result_expires=7200,            # keep results 2 h — enough for any UI poll

    # ── Periodic tasks (requires celery beat) ────────────────────────────────
    beat_schedule={
        'requalify-old-leads': {
            'task': 'app.tasks.agent_tasks.requalify_old_leads',
            'schedule': crontab(hour='2', minute='0'),
            'options': {'queue': 'default'},
        },
        'cleanup-stale-data': {
            'task': 'app.tasks.agent_tasks.cleanup_stale_data',
            'schedule': crontab(hour='3', minute='0'),
            'options': {'queue': 'default'},
        },
    },

    # ── Queues ────────────────────────────────────────────────────────────────
    task_default_queue='default',
    task_queues={
        'default': {'exchange': 'default', 'routing_key': 'default'},
        'agents':  {'exchange': 'agents',  'routing_key': 'agents'},
    },
)


def make_celery(flask_app):
    """
    Bind the Celery instance to a Flask app.
    Every task decorated with @celery.task will run inside an app context,
    giving it access to db, config, and all Flask extensions.
    """

    class ContextTask(celery.Task):
        """Wrap each task call in a Flask application context."""
        abstract = True

        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    logger.info('[Celery] ContextTask bound — broker: %s', _broker_url()[:40] + '…')
    return celery
