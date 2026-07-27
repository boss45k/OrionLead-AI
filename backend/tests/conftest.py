"""
Pytest configuration and shared fixtures.
Uses SQLite in-memory so tests run without a MySQL server.
"""

import sys
import os

# Set env vars BEFORE any app import so Config class body doesn't raise ValueError.
# load_dotenv won't override these because it uses setdefault semantics by default.
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'test-secret-key-minimum-32-bytes-long!!')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret-minimum-32-bytes-long!!')
os.environ['FLASK_ENV'] = 'testing'

import pytest

# Make backend the root for imports
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.fixture(scope='session')
def app():
    """Create a Flask app configured for testing (SQLite in-memory)."""
    from app import create_app
    application = create_app('testing')
    application.config['TESTING'] = True
    return application


@pytest.fixture(scope='session')
def db(app):
    """Create all tables once per test session and drop them after."""
    from app.models.models import db as _db
    with app.app_context():
        _db.create_all()
        yield _db
        _db.drop_all()


@pytest.fixture(scope='function')
def db_session(db, app):
    """Wrap each test in a transaction that gets rolled back afterwards."""
    with app.app_context():
        connection = db.engine.connect()
        transaction = connection.begin()
        db.session.bind = connection
        yield db.session
        db.session.remove()
        transaction.rollback()
        connection.close()


@pytest.fixture(scope='function')
def client(app, db):
    """Flask test client with a clean in-memory DB."""
    with app.app_context():
        yield app.test_client()


@pytest.fixture(scope='function')
def auth_headers(client, app):
    """Register + login a test user and return Authorization headers."""
    from app.models.models import db as _db, User
    from werkzeug.security import generate_password_hash

    with app.app_context():
        user = User.query.filter_by(email='test@example.com').first()
        if not user:
            user = User(
                email='test@example.com',
                password_hash=generate_password_hash('TestPass123!'),
                full_name='Test User',
                is_active=True,
                email_verified=True,
            )
            _db.session.add(user)
            _db.session.commit()

    resp = client.post('/api/v1/auth/login', json={
        'email': 'test@example.com',
        'password': 'TestPass123!',
    })
    token = resp.get_json().get('token', '')
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def admin_headers(client, app):
    """Create an admin user and return its Authorization headers."""
    from app.models.models import db as _db, User
    from werkzeug.security import generate_password_hash

    with app.app_context():
        if not User.query.filter_by(email='admin@example.com').first():
            _db.session.add(User(
                email='admin@example.com',
                password_hash=generate_password_hash('AdminPass123!'),
                full_name='Admin User',
                role='admin',
                is_active=True,
                email_verified=True,
                source='web',
                sync_status='synced',
            ))
            _db.session.commit()

    resp = client.post('/api/v1/auth/login', json={
        'email': 'admin@example.com',
        'password': 'AdminPass123!',
    })
    token = resp.get_json().get('token', '')
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def mobile_auth_headers(client, app):
    """Create a mobile-registered user (source='mobile') and return its auth headers.

    Required for any endpoint protected by @mobile_user_required:
      POST /sync/web-to-mobile
      POST /sync/mobile-to-web
      POST /sync/user
    """
    from app.models.models import db as _db, User
    from werkzeug.security import generate_password_hash

    with app.app_context():
        if not User.query.filter_by(email='mobile@example.com').first():
            _db.session.add(User(
                email='mobile@example.com',
                password_hash=generate_password_hash('MobilePass123!'),
                full_name='Mobile User',
                is_active=True,
                email_verified=True,
                source='mobile',
                sync_status='pending',
            ))
            _db.session.commit()

    resp = client.post('/api/v1/auth/login', json={
        'email': 'mobile@example.com',
        'password': 'MobilePass123!',
    })
    token = resp.get_json().get('token', '')
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def sample_lead():
    """Minimal valid lead payload."""
    return {
        'name': 'Jane Doe',
        'email': 'jane@sample.com',
        'company': 'Sample Corp',
        'position': 'CTO',
        'interests': ['automation', 'analytics'],
        'source': 'linkedin',
    }
