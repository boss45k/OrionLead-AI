import os

# Ensure local dev runner always uses DevelopmentConfig regardless of FLASK_ENV.
# This must happen before create_app() reads FLASK_ENV.
# On a real server use wsgi.py (gunicorn/uWSGI) with FLASK_ENV=production instead.
os.environ.setdefault('FLASK_ENV', 'development')

from app import create_app

app = create_app()

if __name__ == '__main__':
    # app.config['DEBUG'] reflects the loaded config (True for dev, False for prod).
    # Pass it explicitly so the Werkzeug reloader state matches the config intent.
    app.run(
        debug=app.config.get('DEBUG', False),
        host='0.0.0.0',
        port=int(os.getenv('API_PORT', 5000)),
        threaded=True,
    )
