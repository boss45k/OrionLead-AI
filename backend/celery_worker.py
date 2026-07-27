"""
Celery worker entry-point for OrionLead AI.

Usage
-----
# Worker (processes tasks from the queue)
celery -A celery_worker worker --loglevel=info -Q default,agents -c 2

# Beat scheduler (dispatches periodic tasks: requalify, cleanup)
celery -A celery_worker beat --loglevel=info

Notes
-----
* Run this from the backend/ directory so relative imports resolve.
* FLASK_ENV defaults to 'development'; set it before starting for production.
* -c 2 limits concurrency to 2 processes — safe for LLM rate limits.
  Increase for pure-ML (fast path) workloads.
"""

import os
from dotenv import load_dotenv

# Load .env before any Flask / SQLAlchemy / Celery config is read
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Create the Flask app — this also calls make_celery() internally (wired in
# create_app), so the ContextTask base class is set before tasks are imported.
from app import create_app              # noqa: E402
from app.celery_app import celery, make_celery  # noqa: E402

flask_app = create_app()
make_celery(flask_app)   # idempotent — safe to call twice; re-affirms ContextTask

# Register task modules AFTER make_celery so @celery.task picks up ContextTask
import app.tasks.agent_tasks  # noqa: F401, E402

# `celery` is the variable the Celery CLI looks for in this module
