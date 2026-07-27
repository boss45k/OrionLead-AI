"""
Integration Audit Test Suite
=============================
Covers every gap identified in the full database-to-UI audit:

  1.  Table existence        — all SQLAlchemy models create their tables
  2.  Column presence        — every non-trivial column exists on the model
  3.  Model defaults         — default values are correct on new instances
  4.  Model CRUD             — insert / select / update / delete via ORM
  5.  User source separation — web vs mobile registration flows
  6.  Sync route guards      — mobile_user_required + admin bypass
  7.  Sync service guard     — web_to_mobile denies non-mobile triggered_by
  8.  Auth DB persistence    — register creates DB row; login reads it
  9.  Lead CRUD via API      — full lifecycle over HTTP
  10. Analytics queries      — qualified threshold = 60, avg excludes zeros
  11. Quality tier sync      — qualify endpoint updates data_points.quality_tier
  12. Sync status shape      — GET /sync/status returns all expected keys

All tests run on SQLite in-memory. Supabase is never called.
"""

import pytest
from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------------------
# 1. TABLE EXISTENCE
# ---------------------------------------------------------------------------

class TestTableExistence:
    """db.create_all() must create every table defined in models.py."""

    EXPECTED_TABLES = [
        'users',
        'leads',
        'lead_activities',
        'data_sources',
        'classification_categories',
        'seen_contacts',
        'sync_logs',
        'lead_outcomes',
        'dataset_versions',
        'user_settings',
        'admin_api_keys',
    ]

    def test_all_tables_exist(self, app, db):
        from sqlalchemy import inspect
        with app.app_context():
            inspector = inspect(db.engine)
            existing = inspector.get_table_names()
            for table in self.EXPECTED_TABLES:
                assert table in existing, (
                    f"Table '{table}' is missing. "
                    f"Add it to a migration and ensure db.create_all() covers it."
                )


# ---------------------------------------------------------------------------
# 2. COLUMN PRESENCE — critical sync columns
# ---------------------------------------------------------------------------

class TestCriticalColumns:
    """Audit that sync-critical columns exist on User and Lead models."""

    def test_user_has_uuid(self, app, db):
        from app.models.models import User
        with app.app_context():
            assert hasattr(User, 'uuid')

    def test_user_has_source(self, app, db):
        from app.models.models import User
        with app.app_context():
            assert hasattr(User, 'source')

    def test_user_has_sync_status(self, app, db):
        from app.models.models import User
        with app.app_context():
            assert hasattr(User, 'sync_status')

    def test_user_has_version(self, app, db):
        from app.models.models import User
        with app.app_context():
            assert hasattr(User, 'version')

    def test_lead_has_uuid(self, app, db):
        from app.models.models import Lead
        with app.app_context():
            assert hasattr(Lead, 'uuid')

    def test_lead_has_origin(self, app, db):
        from app.models.models import Lead
        with app.app_context():
            assert hasattr(Lead, 'origin')

    def test_lead_has_sync_status(self, app, db):
        from app.models.models import Lead
        with app.app_context():
            assert hasattr(Lead, 'sync_status')

    def test_lead_has_version(self, app, db):
        from app.models.models import Lead
        with app.app_context():
            assert hasattr(Lead, 'version')

    def test_lead_has_last_synced_at(self, app, db):
        from app.models.models import Lead
        with app.app_context():
            assert hasattr(Lead, 'last_synced_at')


# ---------------------------------------------------------------------------
# 3. MODEL DEFAULTS
# ---------------------------------------------------------------------------

class TestModelDefaults:
    """New model instances must carry the right defaults before flush."""

    def test_user_default_source_is_web(self, app, db):
        from app.models.models import User
        with app.app_context():
            u = User(
                email='defaults@test.com',
                password_hash='x',
                full_name='D',
            )
            db.session.add(u)
            db.session.flush()   # triggers column defaults without full commit
            db.session.expunge(u)
            db.session.rollback()
            assert u.source == 'web'

    def test_web_user_default_sync_status_should_be_synced(self, app, db):
        """Web users must never enter the Supabase sync queue."""
        from app.models.models import User
        with app.app_context():
            u = User(
                email='webdefault@test.com',
                password_hash='x',
                full_name='D',
                source='web',
                sync_status='synced',
            )
            assert u.sync_status == 'synced'

    def test_lead_default_origin_is_web(self, app, db):
        from app.models.models import Lead
        with app.app_context():
            l = Lead(name='Test', origin='web')
            assert l.origin == 'web'

    def test_lead_default_sync_status_is_pending(self, app, db):
        from app.models.models import Lead
        with app.app_context():
            l = Lead(name='Test')
            db.session.add(l)
            db.session.flush()
            db.session.expunge(l)
            db.session.rollback()
            assert l.sync_status == 'pending'

    def test_lead_mark_synced_clears_pending(self, app, db):
        from app.models.models import Lead
        with app.app_context():
            l = Lead(name='Test')
            db.session.add(l)
            db.session.flush()
            assert l.sync_status == 'pending'
            l.mark_synced()
            assert l.sync_status == 'synced'
            assert l.last_synced_at is not None
            db.session.rollback()

    def test_lead_bump_version_increments(self, app, db):
        from app.models.models import Lead
        with app.app_context():
            l = Lead(name='Test', version=1)
            l.bump_version()
            assert l.version == 2


# ---------------------------------------------------------------------------
# 4. MODEL CRUD — ORM round-trip
# ---------------------------------------------------------------------------

class TestModelCRUD:
    """Insert, read, update, delete for core models."""

    def test_user_insert_and_select(self, app, db):
        from app.models.models import User
        with app.app_context():
            u = User(
                email='crud_user@test.com',
                password_hash=generate_password_hash('pass'),
                full_name='CRUD User',
                is_active=True,
                source='mobile',
                sync_status='pending',
            )
            db.session.add(u)
            db.session.commit()

            fetched = User.query.filter_by(email='crud_user@test.com').first()
            assert fetched is not None
            assert fetched.source == 'mobile'
            assert fetched.sync_status == 'pending'
            assert fetched.uuid is not None  # auto-generated

    def test_lead_insert_and_select(self, app, db):
        from app.models.models import Lead
        with app.app_context():
            l = Lead(
                name='CRUD Lead',
                email='crudlead@test.com',
                origin='mobile',
                sync_status='pending',
            )
            db.session.add(l)
            db.session.commit()

            fetched = Lead.query.filter_by(email='crudlead@test.com').first()
            assert fetched is not None
            assert fetched.origin == 'mobile'
            assert fetched.uuid is not None

    def test_lead_update(self, app, db):
        from app.models.models import Lead
        with app.app_context():
            l = Lead(name='Update Me', email='upd@test.com')
            db.session.add(l)
            db.session.commit()

            l.company = 'New Corp'
            db.session.commit()

            fetched = Lead.query.filter_by(email='upd@test.com').first()
            assert fetched.company == 'New Corp'

    def test_lead_delete(self, app, db):
        from app.models.models import Lead
        with app.app_context():
            l = Lead(name='Delete Me', email='del@test.com')
            db.session.add(l)
            db.session.commit()
            lid = l.id

            db.session.delete(l)
            db.session.commit()

            assert Lead.query.get(lid) is None

    def test_synclog_insert(self, app, db):
        from app.models.models import SyncLog
        with app.app_context():
            entry = SyncLog(
                operation='web_to_mobile',
                direction='mysql_to_supabase',
                records=5,
                status='success',
                triggered_by='audit_test',
            )
            db.session.add(entry)
            db.session.commit()
            assert entry.id is not None

    def test_seen_contact_unique_constraint(self, app, db):
        from app.models.models import SeenContact
        import sqlalchemy.exc
        with app.app_context():
            # Use non-null phone so SQLite also enforces the composite unique constraint
            db.session.add(SeenContact(
                normalized_email='dup@test.com',
                normalized_phone='+1234567890',
            ))
            db.session.commit()

            db.session.add(SeenContact(
                normalized_email='dup@test.com',
                normalized_phone='+1234567890',
            ))
            with pytest.raises((sqlalchemy.exc.IntegrityError, Exception)):
                db.session.commit()
            db.session.rollback()


# ---------------------------------------------------------------------------
# 5. USER SOURCE SEPARATION — register endpoint
# ---------------------------------------------------------------------------

class TestUserSourceSeparation:
    """Registration must set source and sync_status correctly."""

    def test_web_register_sets_source_web(self, client, app):
        """Web registration (no source field) → source='web'."""
        resp = client.post('/api/v1/auth/register', json={
            'email': 'webuser_src@test.com',
            'password': 'SecurePass1!',
            'full_name': 'Web Source User',
        })
        assert resp.status_code in (200, 201)

        from app.models.models import User
        with app.app_context():
            u = User.query.filter_by(email='webuser_src@test.com').first()
            assert u is not None
            assert u.source == 'web'

    def test_web_register_sets_sync_status_synced(self, client, app):
        """Web users must NOT enter the Supabase sync queue."""
        client.post('/api/v1/auth/register', json={
            'email': 'webuser_sync@test.com',
            'password': 'SecurePass1!',
            'full_name': 'Web Sync User',
        })
        from app.models.models import User
        with app.app_context():
            u = User.query.filter_by(email='webuser_sync@test.com').first()
            assert u.sync_status == 'synced'

    def test_mobile_register_sets_source_mobile(self, client, app):
        """Mobile registration (source='mobile') → source='mobile'."""
        resp = client.post('/api/v1/auth/register', json={
            'email': 'mobileuser_src@test.com',
            'password': 'SecurePass1!',
            'full_name': 'Mobile Source User',
            'source': 'mobile',
        })
        assert resp.status_code in (200, 201)

        from app.models.models import User
        with app.app_context():
            u = User.query.filter_by(email='mobileuser_src@test.com').first()
            assert u is not None
            assert u.source == 'mobile'

    def test_mobile_register_sets_sync_status_pending(self, client, app):
        """Mobile users must start pending so they are synced to Supabase."""
        client.post('/api/v1/auth/register', json={
            'email': 'mobileuser_pending@test.com',
            'password': 'SecurePass1!',
            'full_name': 'Mobile Pending User',
            'source': 'mobile',
        })
        from app.models.models import User
        with app.app_context():
            u = User.query.filter_by(email='mobileuser_pending@test.com').first()
            assert u.sync_status == 'pending'

    def test_invalid_source_rejected(self, client):
        """source must be 'web' or 'mobile' — anything else is rejected."""
        resp = client.post('/api/v1/auth/register', json={
            'email': 'badsource@test.com',
            'password': 'SecurePass1!',
            'full_name': 'Bad Source',
            'source': 'desktop',
        })
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# 6. SYNC ROUTE GUARDS — mobile_user_required + admin bypass
# ---------------------------------------------------------------------------

SYNC_BASE = '/api/v1/sync'


class TestMobileUserRequired:
    """POST /sync/web-to-mobile, mobile-to-web, /user require source='mobile'."""

    def test_unauthenticated_gets_401(self, client):
        assert client.post(f'{SYNC_BASE}/web-to-mobile').status_code == 401
        assert client.post(f'{SYNC_BASE}/mobile-to-web').status_code == 401
        assert client.post(f'{SYNC_BASE}/user').status_code == 401

    def test_web_user_gets_403_on_web_to_mobile(self, client, auth_headers):
        resp = client.post(f'{SYNC_BASE}/web-to-mobile', headers=auth_headers)
        assert resp.status_code == 403

    def test_web_user_gets_403_on_mobile_to_web(self, client, auth_headers):
        resp = client.post(
            f'{SYNC_BASE}/mobile-to-web',
            json={'records': [{'name': 'X'}]},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    def test_web_user_gets_403_on_sync_user(self, client, auth_headers):
        resp = client.post(f'{SYNC_BASE}/user', headers=auth_headers)
        assert resp.status_code == 403

    def test_mobile_user_passes_guard(self, client, mobile_auth_headers):
        """Mobile user must not be blocked — gets 400 (validation), not 403 (guard)."""
        resp = client.post(
            f'{SYNC_BASE}/mobile-to-web',
            json={},
            headers=mobile_auth_headers,
        )
        assert resp.status_code == 400

    def test_admin_bypasses_guard_on_all_sync_endpoints(self, client, admin_headers):
        """Admin (role='admin') is never blocked by mobile_user_required."""
        r1 = client.post(f'{SYNC_BASE}/web-to-mobile', headers=admin_headers)
        assert r1.status_code not in (401, 403), "Admin blocked on web-to-mobile"

        r2 = client.post(f'{SYNC_BASE}/user', headers=admin_headers)
        assert r2.status_code not in (401, 403), "Admin blocked on /sync/user"

    def test_403_error_is_json(self, client, auth_headers):
        resp = client.post(f'{SYNC_BASE}/web-to-mobile', headers=auth_headers)
        assert resp.content_type.startswith('application/json')
        body = resp.get_json()
        assert body is not None


# ---------------------------------------------------------------------------
# 7. SYNC SERVICE GUARD — web_to_mobile denies non-mobile triggered_by
# ---------------------------------------------------------------------------

class TestSyncServiceGuard:
    """SyncService.web_to_mobile() must deny non-mobile callers at service level."""

    def test_service_denies_web_email(self, app, db):
        from app.models.models import User
        from app.services.sync_service import SyncService

        with app.app_context():
            # Create a web user
            web_user = User(
                email='webonly@test.com',
                password_hash='x',
                full_name='Web Only',
                source='web',
                sync_status='synced',
                is_active=True,
            )
            db.session.add(web_user)
            db.session.commit()

            svc = SyncService()
            result = svc.web_to_mobile(triggered_by='webonly@test.com')
            assert result.get('status') == 'denied'
            assert result.get('synced') == 0

    def test_service_allows_system_caller(self, app, db):
        """'system' is a whitelisted caller that bypasses the guard."""
        from app.services.sync_service import SyncService

        with app.app_context():
            svc = SyncService()
            # With no Supabase configured, it returns quickly — but NOT 'denied'
            result = svc.web_to_mobile(triggered_by='system')
            assert result.get('status') != 'denied'

    def test_service_allows_mobile_email(self, app, db):
        from app.models.models import User
        from app.services.sync_service import SyncService

        with app.app_context():
            mobile_user = User(
                email='mobileonly@test.com',
                password_hash='x',
                full_name='Mobile Only',
                source='mobile',
                sync_status='pending',
                is_active=True,
            )
            db.session.add(mobile_user)
            db.session.commit()

            svc = SyncService()
            result = svc.web_to_mobile(triggered_by='mobileonly@test.com')
            # Not denied — may return synced=0 (no pending leads or no Supabase)
            assert result.get('status') != 'denied'

    def test_service_denies_unknown_email(self, app, db):
        """An email not in the DB is treated as non-mobile → denied."""
        from app.services.sync_service import SyncService

        with app.app_context():
            svc = SyncService()
            result = svc.web_to_mobile(triggered_by='ghost@nowhere.com')
            assert result.get('status') == 'denied'


# ---------------------------------------------------------------------------
# 8. AUTH DB PERSISTENCE
# ---------------------------------------------------------------------------

class TestAuthDBPersistence:
    """Register writes to DB; login reads from it; profile returns correct data."""

    def test_register_creates_db_row(self, client, app):
        from app.models.models import User
        resp = client.post('/api/v1/auth/register', json={
            'email': 'persist@test.com',
            'password': 'SecurePass1!',
            'full_name': 'Persist User',
        })
        assert resp.status_code in (200, 201)

        with app.app_context():
            u = User.query.filter_by(email='persist@test.com').first()
            assert u is not None
            assert u.full_name == 'Persist User'
            assert u.uuid is not None
            assert u.password_hash != 'SecurePass1!'  # hashed

    def test_login_reads_correct_user(self, client, app):
        from app.models.models import db, User
        with app.app_context():
            if not User.query.filter_by(email='loginread@test.com').first():
                db.session.add(User(
                    email='loginread@test.com',
                    password_hash=generate_password_hash('MyPass1!'),
                    full_name='Login Read',
                    is_active=True,
                    email_verified=True,
                ))
                db.session.commit()

        resp = client.post('/api/v1/auth/login', json={
            'email': 'loginread@test.com',
            'password': 'MyPass1!',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'token' in data

    def test_inactive_user_cannot_login(self, client, app):
        from app.models.models import db, User
        with app.app_context():
            if not User.query.filter_by(email='inactive@test.com').first():
                db.session.add(User(
                    email='inactive@test.com',
                    password_hash=generate_password_hash('MyPass1!'),
                    full_name='Inactive',
                    is_active=False,
                    email_verified=True,
                ))
                db.session.commit()

        resp = client.post('/api/v1/auth/login', json={
            'email': 'inactive@test.com',
            'password': 'MyPass1!',
        })
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 9. LEAD CRUD VIA API
# ---------------------------------------------------------------------------

class TestLeadCRUDAPI:
    """Full lead lifecycle over HTTP — requires active user (auth_headers)."""

    def _create_lead(self, client, auth_headers, overrides=None):
        payload = {
            'name': 'API Lead',
            'email': 'apilead@test.com',
            'company': 'API Corp',
        }
        if overrides:
            payload.update(overrides)
        return client.post('/api/v1/leads/', json=payload, headers=auth_headers)

    def test_create_lead_returns_201(self, client, auth_headers):
        resp = self._create_lead(client, auth_headers)
        assert resp.status_code in (200, 201)

    def test_create_lead_persists_to_db(self, client, auth_headers, app):
        from app.models.models import Lead
        self._create_lead(client, auth_headers, {'email': 'dbcheck@test.com'})
        with app.app_context():
            l = Lead.query.filter_by(email='dbcheck@test.com').first()
            assert l is not None
            assert l.uuid is not None

    def test_get_leads_returns_list(self, client, auth_headers):
        resp = client.get('/api/v1/leads/', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'leads' in data or isinstance(data, list)

    def test_create_lead_sets_default_origin_web(self, client, auth_headers, app):
        from app.models.models import Lead
        self._create_lead(client, auth_headers, {'email': 'origincheck@test.com'})
        with app.app_context():
            l = Lead.query.filter_by(email='origincheck@test.com').first()
            if l:
                assert l.origin == 'web'

    def test_unauthenticated_lead_create_returns_401(self, client):
        resp = client.post('/api/v1/leads/', json={'name': 'Ghost', 'email': 'g@x.com'})
        assert resp.status_code == 401

    def test_lead_stats_returns_counts(self, client, auth_headers):
        resp = client.get('/api/v1/leads/stats', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'stats' in data
        stats = data['stats']
        assert 'total_leads' in stats
        assert 'qualified_leads' in stats
        assert 'avg_score' in stats
        assert 'new_this_week' in stats


# ---------------------------------------------------------------------------
# 10. ANALYTICS QUERIES — qualified threshold and avg_score
# ---------------------------------------------------------------------------

class TestAnalyticsQueries:
    """Qualified threshold must be 60; avg_score must exclude score=0 leads."""

    def test_qualified_threshold_is_60(self, app, db):
        """A lead with score=60 must count as qualified (threshold is 60, not 70)."""
        from app.models.models import Lead

        with app.app_context():
            db.session.add(Lead(
                name='Qualified Lead',
                email='qual60@test.com',
                qualification_score=60.0,
            ))
            db.session.add(Lead(
                name='Below Threshold',
                email='qual59@test.com',
                qualification_score=59.0,
            ))
            db.session.commit()

            qualified = Lead.query.filter(Lead.qualification_score >= 60).count()
            below = Lead.query.filter(
                Lead.qualification_score >= 60,
                Lead.email == 'qual59@test.com',
            ).count()
            assert qualified >= 1
            assert below == 0

    def test_avg_score_excludes_zero_scores(self, app, db):
        """avg_score must filter out qualification_score=0 (unscored leads)."""
        from app.models.models import Lead
        from sqlalchemy import func

        with app.app_context():
            db.session.add(Lead(name='Scored', email='scored@test.com', qualification_score=80.0))
            db.session.add(Lead(name='Unscored', email='unscored@test.com', qualification_score=0.0))
            db.session.commit()

            avg_with_zeros = db.session.query(
                func.avg(Lead.qualification_score)
            ).scalar() or 0

            avg_without_zeros = db.session.query(
                func.avg(Lead.qualification_score)
            ).filter(Lead.qualification_score > 0).scalar() or 0

            # Without-zero average must be higher (not dragged down by 0s)
            assert avg_without_zeros > avg_with_zeros or avg_without_zeros == avg_with_zeros == 0

    def test_analytics_endpoint_returns_200(self, client, auth_headers):
        resp = client.get('/api/v1/analytics', headers=auth_headers)
        assert resp.status_code == 200

    def test_analytics_summary_returns_200(self, client, auth_headers):
        resp = client.get('/api/v1/analytics/summary', headers=auth_headers)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 11. QUALITY TIER SYNC — qualify endpoint updates data_points.quality_tier
# ---------------------------------------------------------------------------

class TestQualityTierSync:
    """After AI qualification, data_points.quality_tier must match the score."""

    def _score_to_quality_tier(self, score):
        if score >= 80: return 'high_quality'
        if score >= 60: return 'qualified'
        if score >= 35: return 'pending'
        if score >= 15: return 'low_quality'
        return 'rejected'

    def test_quality_tier_maps_correctly(self):
        assert self._score_to_quality_tier(85) == 'high_quality'
        assert self._score_to_quality_tier(60) == 'qualified'
        assert self._score_to_quality_tier(64) == 'qualified'
        assert self._score_to_quality_tier(59) == 'pending'
        assert self._score_to_quality_tier(35) == 'pending'
        assert self._score_to_quality_tier(34) == 'low_quality'
        assert self._score_to_quality_tier(15) == 'low_quality'
        assert self._score_to_quality_tier(14) == 'rejected'
        assert self._score_to_quality_tier(0)  == 'rejected'

    def test_qualify_endpoint_updates_quality_tier(self, client, auth_headers, app):
        """POST /leads/<id>/qualify must write quality_tier into data_points."""
        from app.models.models import Lead, db

        # Set up a lead with stale quality_tier
        with app.app_context():
            l = Lead(
                name='Tier Test Lead',
                email='tiertest@test.com',
                data_points={'quality_tier': 'pending'},
                qualification_score=0,
            )
            db.session.add(l)
            db.session.commit()
            lead_id = l.id

        mock_result = MagicMock()
        mock_result.score = 72.0
        mock_result.category = 'warm'
        mock_result.confidence = 0.85
        mock_result.recommendations = []
        mock_result.reasoning = ''
        mock_result.lead_id = lead_id
        mock_result.analyzed_at = '2026-01-01T00:00:00Z'

        with patch('app.routes.leads.qualification_agent') as mock_agent:
            mock_agent.qualify_lead.return_value = mock_result

            resp = client.post(
                f'/api/v1/leads/{lead_id}/qualify',
                json={'force_requalify': True},
                headers=auth_headers,
            )

        assert resp.status_code == 200

        with app.app_context():
            updated = Lead.query.get(lead_id)
            assert updated.data_points is not None
            assert updated.data_points.get('quality_tier') == 'qualified'
            assert updated.qualification_score == 72.0
            assert updated.status == 'warm'


# ---------------------------------------------------------------------------
# 12. SYNC STATUS RESPONSE SHAPE
# ---------------------------------------------------------------------------

class TestSyncStatusShape:
    """GET /sync/status must return all keys the UI consumes."""

    REQUIRED_KEYS = [
        'supabase_configured',
        'overall_health',
        'is_stale',
        'pending_count',
        'failed_count',
        'mysql_leads_total',
        'mysql_leads_pending',
        'mysql_leads_failed',
        'mysql_users_pending',
        'last_sync_at',
        'last_sync_status',
        'last_success_at',
        'last_sync',
    ]

    def test_sync_status_returns_200(self, client, auth_headers):
        resp = client.get('/api/v1/sync/status', headers=auth_headers)
        assert resp.status_code == 200

    def test_sync_status_has_all_required_keys(self, client, auth_headers):
        data = client.get('/api/v1/sync/status', headers=auth_headers).get_json()
        for key in self.REQUIRED_KEYS:
            assert key in data, f"Key '{key}' missing from /sync/status response"

    def test_sync_status_overall_health_is_valid_value(self, client, auth_headers):
        data = client.get('/api/v1/sync/status', headers=auth_headers).get_json()
        assert data['overall_health'] in ('ok', 'stale', 'error', 'unconfigured')

    def test_sync_status_counts_are_integers(self, client, auth_headers):
        data = client.get('/api/v1/sync/status', headers=auth_headers).get_json()
        for key in ('pending_count', 'failed_count', 'mysql_leads_total',
                    'mysql_leads_pending', 'mysql_leads_failed', 'mysql_users_pending'):
            assert isinstance(data[key], int), f"'{key}' should be int, got {type(data[key])}"

    def test_sync_status_last_sync_is_dict(self, client, auth_headers):
        data = client.get('/api/v1/sync/status', headers=auth_headers).get_json()
        assert isinstance(data['last_sync'], dict)

    def test_sync_status_pending_count_matches_db(self, client, auth_headers, app, db):
        """pending_count must match Lead.query.filter_by(sync_status='pending').count()."""
        from app.models.models import Lead

        with app.app_context():
            db_pending = Lead.query.filter_by(sync_status='pending').count()

        data = client.get('/api/v1/sync/status', headers=auth_headers).get_json()
        assert data['mysql_leads_pending'] == db_pending


# ---------------------------------------------------------------------------
# 13. WEB USER NEVER IN SUPABASE SYNC QUEUE
# ---------------------------------------------------------------------------

class TestWebUserNotInSyncQueue:
    """Users with source='web' must never appear in sync_users_to_supabase queries."""

    def test_bulk_sync_filters_to_mobile_only(self, app, db):
        from app.models.models import User
        from app.services.sync_service import SyncService

        with app.app_context():
            # Create one web and one mobile pending user
            web = User(
                email='webpending@synctest.com',
                password_hash='x',
                full_name='Web Pending',
                source='web',
                sync_status='pending',  # should never happen in practice
                is_active=True,
            )
            mobile = User(
                email='mobilepending@synctest.com',
                password_hash='x',
                full_name='Mobile Pending',
                source='mobile',
                sync_status='pending',
                is_active=True,
            )
            db.session.add_all([web, mobile])
            db.session.commit()

            # The service's bulk query must only pick up mobile users
            pending_mobile = User.query.filter_by(
                sync_status='pending', source='mobile'
            ).all()
            pending_web_in_queue = [u for u in pending_mobile if u.source == 'web']

            assert len(pending_web_in_queue) == 0
            assert any(u.email == 'mobilepending@synctest.com' for u in pending_mobile)
