"""
Production WSGI entrypoint — used by gunicorn / uWSGI.

Launch with:
    gunicorn "wsgi:app" --workers 4 --bind 0.0.0.0:5000

FLASK_ENV must be set to 'production' (or left unset, which now defaults to
'production'). If FLASK_ENV=development reaches this file, the server will
refuse to start to prevent accidentally exposing the Werkzeug debugger.
"""

import os

_env = os.getenv('FLASK_ENV', 'production')
if _env == 'development':
    raise RuntimeError(
        "FLASK_ENV=development detected in wsgi.py. "
        "This file is the production WSGI entrypoint and must not run in "
        "development mode. Use run.py for local development instead."
    )

from app import create_app  # noqa: E402 (import after env check is intentional)

app = create_app()

if __name__ == "__main__":
    # Direct execution is dev-only fallback; prefer gunicorn in production.
    app.run(debug=False, host='0.0.0.0', port=5000)
