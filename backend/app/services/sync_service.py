"""
SyncService — production-grade two-way sync between MySQL and Supabase.

Architecture:
  Web  → MySQL (via Flask)  → SyncService → Supabase  (web-to-mobile)
  Mobile → Supabase         → SyncService → MySQL      (mobile-to-web)

Features:
  • Conflict resolution  : last-write-wins via updated_at
  • Loop prevention      : origin + sync_status flags stop re-syncing
  • Batching             : configurable batch_size (default 50)
  • Retries              : exponential backoff up to max_retries
  • Audit log            : every operation written to sync_logs table
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests as http_requests

from app.models.models import db, Lead, User, SyncLog

logger = logging.getLogger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value) -> Optional[datetime]:
    """Parse an ISO-8601 string or datetime into a UTC-aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _lead_to_supabase_row(lead: Lead) -> dict:
    """Serialize a MySQL Lead → Supabase leads_cache row."""
    return {
        'flask_lead_id':       lead.id,
        'lead_uuid':           lead.uuid,
        'name':                lead.name,
        'email':               lead.email,
        'phone':               lead.phone,
        'company':             lead.company,
        'position':            lead.position,
        'location':            lead.location,
        'country':             lead.country,
        'city':                lead.city,
        'industry':            lead.industry,
        'website':             lead.website,
        'linkedin_url':        lead.linkedin_url,
        'interests':           lead.interests or [],
        'product':             lead.product,
        'qualification_score': lead.qualification_score or 0.0,
        'status':              lead.status or 'pending',
        'origin':              lead.origin or 'web',
        'source':              lead.source,
        'notes':               lead.notes,
        'sync_status':         'synced',
        'version':             lead.version or 1,
        'updated_at':          lead.updated_at.isoformat() if lead.updated_at else _now().isoformat(),
        'synced_at':           _now().isoformat(),
    }


def _user_to_supabase_row(user: User) -> dict:
    return {
        'flask_user_id': user.id,
        'user_uuid':     user.uuid,
        'email':         user.email,
        'full_name':     user.full_name,
        'company':       user.company,
        'role':          user.role or 'user',
        'is_active':     user.is_active,
        'sync_status':   'synced',
        'version':       user.version or 1,
        'synced_at':     _now().isoformat(),
    }


# ─── SyncService ──────────────────────────────────────────────────────────────

class SyncService:

    def __init__(self):
        self.supabase_url  = os.getenv('SUPABASE_URL', '').rstrip('/')
        self.service_key   = os.getenv('SUPABASE_SERVICE_KEY', '')
        self.batch_size    = int(os.getenv('SYNC_BATCH_SIZE', '50'))
        self.max_retries   = int(os.getenv('SYNC_MAX_RETRIES', '3'))
        self.retry_delay   = float(os.getenv('SYNC_RETRY_DELAY_S', '1.0'))

    @property
    def _configured(self) -> bool:
        return bool(self.supabase_url and self.service_key)

    def _headers(self, extra: dict | None = None) -> dict:
        h = {
            'apikey':        self.service_key,
            'Authorization': f'Bearer {self.service_key}',
            'Content-Type':  'application/json',
        }
        if extra:
            h.update(extra)
        return h

    # ── Supabase REST helpers ─────────────────────────────────────────────────

    # Conflict columns per table — PostgREST needs these to do ON CONFLICT DO UPDATE
    _CONFLICT_COLS: dict[str, str] = {
        'users_sync':   'user_uuid',
        'leads_cache':  'flask_lead_id',
    }

    def _sb_upsert(self, table: str, rows: list[dict]) -> tuple[bool, str | None]:
        """Bulk upsert rows into a Supabase table with retry."""
        if not self._configured:
            return False, 'Supabase not configured (missing SUPABASE_URL or SUPABASE_SERVICE_KEY)'

        conflict_col = self._CONFLICT_COLS.get(table, '')
        url = f'{self.supabase_url}/rest/v1/{table}'
        if conflict_col:
            url = f'{url}?on_conflict={conflict_col}'
        headers = self._headers({'Prefer': 'resolution=merge-duplicates,return=minimal'})

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = http_requests.post(url, json=rows, headers=headers, timeout=15)
                if resp.status_code in (200, 201, 204):
                    return True, None
                err = f'HTTP {resp.status_code}: {resp.text[:300]}'
                logger.warning(f'[SyncService] upsert attempt {attempt}/{self.max_retries}: {err}')
            except Exception as exc:
                err = str(exc)
                logger.warning(f'[SyncService] upsert attempt {attempt}/{self.max_retries} exception: {err}')

            if attempt < self.max_retries:
                time.sleep(self.retry_delay * (2 ** (attempt - 1)))  # exponential backoff

        return False, err  # type: ignore[return-value]

    def _sb_patch(self, table: str, match: dict, data: dict) -> bool:
        """PATCH a single Supabase row."""
        if not self._configured:
            return False
        params = '&'.join(f'{k}=eq.{v}' for k, v in match.items())
        url = f'{self.supabase_url}/rest/v1/{table}?{params}'
        try:
            resp = http_requests.patch(
                url, json=data,
                headers=self._headers({'Prefer': 'return=minimal'}),
                timeout=10,
            )
            return resp.status_code in (200, 204)
        except Exception as exc:
            logger.warning(f'[SyncService] PATCH {table} failed: {exc}')
            return False

    def _sb_select(self, table: str, params: str) -> list[dict]:
        """SELECT from Supabase, returns list of rows."""
        if not self._configured:
            return []
        url = f'{self.supabase_url}/rest/v1/{table}?{params}'
        try:
            resp = http_requests.get(
                url,
                headers=self._headers({'Accept': 'application/json'}),
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            logger.warning(f'[SyncService] SELECT {table} failed: {exc}')
        return []

    # ── Audit log ─────────────────────────────────────────────────────────────

    def _log(self, operation: str, direction: str, records: int,
             status: str, error_msg: str | None = None,
             triggered_by: str | None = None, duration_ms: int | None = None):
        try:
            entry = SyncLog(
                operation=operation, direction=direction,
                records=records, status=status,
                error_msg=error_msg, triggered_by=triggered_by,
                duration_ms=duration_ms,
            )
            db.session.add(entry)
            db.session.commit()
        except Exception as exc:
            logger.error(f'[SyncService] Failed to write audit log: {exc}')
            db.session.rollback()

    # ── WEB → MOBILE (MySQL → Supabase) ───────────────────────────────────────

    # Callers that bypass the mobile-source guard (internal / automated)
    _SYSTEM_CALLERS = frozenset({'system', 'scheduler', 'polling', 'webhook'})

    def web_to_mobile(
        self,
        lead_ids: list[int] | None = None,
        since: datetime | None = None,
        triggered_by: str = 'system',
    ) -> dict:
        """
        Push leads from MySQL → Supabase.

        Only mobile-registered users (source='mobile') and internal system
        callers may trigger this.  Web users are denied at both route level
        (@mobile_user_required) and service level (guard below).

        Loop prevention:
          • Skips leads whose origin='mobile' AND sync_status='synced'
            (they came FROM mobile, no need to echo back).
          • After pushing, marks sync_status='synced' in MySQL.
        """
        # Guard: reject web/unknown callers at service level so the protection
        # holds even when the method is called directly (e.g. scheduler, tests).
        caller = (triggered_by or 'system').strip()
        if caller not in self._SYSTEM_CALLERS and '@' in caller:
            caller_user = User.query.filter_by(email=caller).first()
            if not caller_user or (caller_user.source != 'mobile' and caller_user.role not in ('admin', 'manager')):
                logger.warning('[Sync] web_to_mobile denied for non-mobile caller: %s', caller)
                return {'status': 'denied', 'synced': 0, 'failed': 0,
                        'reason': 'caller is not a mobile-registered user'}
        elif caller not in self._SYSTEM_CALLERS and '@' not in caller:
            # Unknown non-system, non-email caller → deny
            logger.warning('[Sync] web_to_mobile denied for unknown caller: %s', caller)
            return {'status': 'denied', 'synced': 0, 'failed': 0,
                    'reason': 'caller identity could not be verified'}

        start = time.monotonic()

        if lead_ids:
            query = Lead.query.filter(Lead.id.in_(lead_ids))
        elif since:
            query = Lead.query.filter(
                Lead.updated_at >= since,
                Lead.sync_status == 'pending',
            )
        else:
            query = Lead.query.filter(Lead.sync_status == 'pending')

        leads = query.order_by(Lead.updated_at.asc()).all()

        # ── Loop prevention: skip mobile-originated already-synced records ──
        candidate = [
            l for l in leads
            if not (l.origin == 'mobile' and l.sync_status == 'synced')
        ]

        # ── Skip-unchanged optimisation ────────────────────────────────────
        # Fetch current version + updated_at from Supabase in one query and
        # skip any lead whose version + updated_at hasn't changed since the
        # last sync, avoiding unnecessary upserts.
        if candidate:
            flask_ids = [l.id for l in candidate]
            id_filter = ','.join(str(i) for i in flask_ids)
            remote_rows = self._sb_select(
                'leads_cache',
                f'flask_lead_id=in.({id_filter})'
                '&select=flask_lead_id,version,updated_at',
            )
            # Build a lookup: flask_lead_id → {version, updated_at}
            remote_map: dict[int, dict] = {
                r['flask_lead_id']: r for r in remote_rows if r.get('flask_lead_id')
            }
            to_sync: list[Lead] = []
            skipped_unchanged  = 0
            for lead in candidate:
                remote = remote_map.get(lead.id)
                if remote:
                    remote_version  = remote.get('version') or 0
                    remote_updated  = _parse_dt(remote.get('updated_at'))
                    local_updated   = _parse_dt(lead.updated_at)
                    # Skip if remote already has same or newer version AND
                    # updated_at hasn't changed (record is truly unchanged)
                    if (remote_version >= (lead.version or 1)
                            and remote_updated
                            and local_updated
                            and remote_updated >= local_updated):
                        skipped_unchanged += 1
                        continue
                to_sync.append(lead)
            logger.info(
                f'[SyncService] skip-unchanged: {skipped_unchanged} leads already up-to-date'
            )
        else:
            to_sync = []
            skipped_unchanged = 0

        if not to_sync:
            return {
                'synced': 0, 'failed': 0,
                'skipped': len(leads) - len(candidate) + skipped_unchanged,
                'status': 'ok',
            }

        total_synced = 0
        total_failed = 0

        # Process in batches
        for i in range(0, len(to_sync), self.batch_size):
            batch = to_sync[i: i + self.batch_size]
            rows  = [_lead_to_supabase_row(l) for l in batch]
            ok, err = self._sb_upsert('leads_cache', rows)

            if ok:
                for lead in batch:
                    lead.mark_synced()
                db.session.commit()
                total_synced += len(batch)
                logger.info(f'[SyncService] web→mobile batch {i // self.batch_size + 1}: {len(batch)} leads synced')
            else:
                total_failed += len(batch)
                for lead in batch:
                    lead.sync_status = 'failed'
                db.session.commit()
                logger.error(f'[SyncService] web→mobile batch failed: {err}')

        duration = int((time.monotonic() - start) * 1000)
        self._log(
            operation='web_to_mobile',
            direction='mysql_to_supabase',
            records=total_synced,
            status='success' if total_failed == 0 else ('partial' if total_synced else 'failed'),
            error_msg=None if total_failed == 0 else f'{total_failed} records failed',
            triggered_by=triggered_by,
            duration_ms=duration,
        )

        return {
            'synced':   total_synced,
            'failed':   total_failed,
            'skipped':  len(leads) - len(candidate) + skipped_unchanged,
            'status':   'ok',
            'duration_ms': duration,
        }

    # ── MOBILE → WEB (Supabase → MySQL) ───────────────────────────────────────

    def mobile_to_web(
        self,
        records: list[dict],
        triggered_by: str = 'webhook',
    ) -> dict:
        """
        Receive records from Supabase (mobile) and upsert into MySQL.

        Conflict resolution: last-write-wins using updated_at.
        Loop prevention:
          • After writing to MySQL, marks lead.origin='mobile', sync_status='synced'
            so that web_to_mobile() will skip it on next run.
          • Also patches sync_status='synced' in Supabase to stop re-delivery.
        """
        start = time.monotonic()
        created = updated = skipped = failed = 0

        # Resolve the collector's user_id from triggered_by email (if available)
        _collector_id = None
        if triggered_by and triggered_by != 'webhook':
            _u = User.query.filter_by(email=triggered_by).first()
            if _u:
                _collector_id = _u.id

        for record in records:
            try:
                lead_uuid    = record.get('lead_uuid') or record.get('uuid')
                flask_lead_id= record.get('flask_lead_id')
                mobile_updated = _parse_dt(record.get('updated_at'))

                # ── Find existing MySQL record ──
                existing: Lead | None = None
                if flask_lead_id:
                    existing = Lead.query.get(flask_lead_id)
                if existing is None and lead_uuid:
                    existing = Lead.query.filter_by(uuid=lead_uuid).first()

                if existing:
                    # ── Conflict resolution: last-write-wins ──────────────
                    mysql_updated = _parse_dt(existing.updated_at)
                    if mysql_updated and mobile_updated and mysql_updated > mobile_updated:
                        skipped += 1
                        logger.debug(
                            f'[SyncService] Skipping lead {existing.id}: '
                            f'MySQL ({mysql_updated}) > Supabase ({mobile_updated})'
                        )
                        # Still mark Supabase record as synced to stop re-delivery
                        if record.get('id'):
                            self._sb_patch('leads_cache', {'id': record['id']}, {'sync_status': 'synced'})
                        continue

                    # Apply mobile updates to MySQL record
                    _apply_record_to_lead(existing, record)
                    existing.origin      = 'mobile'
                    existing.sync_status = 'synced'
                    if existing.collected_by is None and _collector_id:
                        existing.collected_by = _collector_id
                    existing.bump_version()
                    updated += 1
                    processed_lead = existing
                else:
                    # ── Create new lead from mobile data ──────────────────
                    new_lead = Lead(
                        uuid=lead_uuid or None,   # model will generate if None
                        name=record.get('name', 'Unknown'),
                        origin='mobile',
                        sync_status='synced',
                        collected_by=_collector_id,
                    )
                    _apply_record_to_lead(new_lead, record)
                    db.session.add(new_lead)
                    created += 1
                    processed_lead = new_lead

                db.session.flush()   # get processed_lead.id before commit

                # ── Mark Supabase record as synced (loop prevention) ──────
                if record.get('id'):
                    self._sb_patch('leads_cache', {'id': record['id']}, {
                        'sync_status': 'synced',
                        'flask_lead_id': processed_lead.id,
                        'synced_at': _now().isoformat(),
                    })

            except Exception as exc:
                logger.error(f'[SyncService] mobile→web record failed: {exc}', exc_info=True)
                db.session.rollback()
                failed += 1
                continue

        try:
            db.session.commit()
        except Exception as exc:
            logger.error(f'[SyncService] mobile→web commit failed: {exc}')
            db.session.rollback()
            failed += created + updated
            created = updated = 0

        duration = int((time.monotonic() - start) * 1000)
        self._log(
            operation='mobile_to_web',
            direction='supabase_to_mysql',
            records=created + updated,
            status='success' if failed == 0 else ('partial' if (created + updated) else 'failed'),
            error_msg=None if failed == 0 else f'{failed} records failed',
            triggered_by=triggered_by,
            duration_ms=duration,
        )

        return {
            'created': created,
            'updated': updated,
            'skipped': skipped,
            'failed':  failed,
            'status':  'ok',
            'duration_ms': duration,
        }

    # ── User sync ─────────────────────────────────────────────────────────────

    def sync_users_to_supabase(
        self,
        user_ids: list[int] | None = None,
        triggered_by: str = 'system',
    ) -> dict:
        """Push MySQL users → Supabase users_sync."""
        if user_ids:
            users = User.query.filter(User.id.in_(user_ids), User.source == 'mobile').all()
        else:
            users = User.query.filter_by(sync_status='pending', source='mobile').all()

        if not users:
            return {'synced': 0, 'failed': 0}

        rows = [_user_to_supabase_row(u) for u in users]
        ok, err = self._sb_upsert('users_sync', rows)

        if ok:
            for u in users:
                u.sync_status = 'synced'
            db.session.commit()
            self._log('user_sync', 'mysql_to_supabase', len(users), 'success', triggered_by=triggered_by)
            return {'synced': len(users), 'failed': 0}
        else:
            self._log('user_sync', 'mysql_to_supabase', 0, 'failed', error_msg=err, triggered_by=triggered_by)
            return {'synced': 0, 'failed': len(users)}

    # ── Pull pending from Supabase ────────────────────────────────────────────

    def pull_pending_from_supabase(self, limit: int = 200) -> dict:
        """
        Fetch records with sync_status='pending' from Supabase and write them to MySQL.
        Used for polling-based mobile-to-web sync (alternative to webhooks).
        """
        rows = self._sb_select(
            'leads_cache',
            f"sync_status=eq.pending&order=updated_at.asc&limit={limit}"
        )
        if not rows:
            return {'pulled': 0, 'created': 0, 'updated': 0, 'skipped': 0, 'failed': 0}

        result = self.mobile_to_web(rows, triggered_by='polling')
        result['pulled'] = len(rows)
        return result

    # ── Sync status ───────────────────────────────────────────────────────────

    # Threshold after which a sync is considered stale (no successful sync)
    _STALE_THRESHOLD_HOURS = 1

    def get_status(self) -> dict:
        pending_leads = Lead.query.filter_by(sync_status='pending').count()
        failed_leads  = Lead.query.filter_by(sync_status='failed').count()
        total_leads   = Lead.query.count()
        pending_users = User.query.filter_by(sync_status='pending').count()

        last_log = SyncLog.query.order_by(SyncLog.created_at.desc()).first()
        last_success_log = (
            SyncLog.query
            .filter_by(status='success')
            .order_by(SyncLog.created_at.desc())
            .first()
        )

        last_sync_at     = last_log.created_at.isoformat() if last_log else None
        last_sync_status = last_log.status if last_log else None
        last_success_at  = last_success_log.created_at.isoformat() if last_success_log else None

        # is_stale: no successful sync in the last _STALE_THRESHOLD_HOURS hours
        is_stale = True
        if last_success_log and last_success_log.created_at:
            age = _now() - last_success_log.created_at.replace(tzinfo=timezone.utc)
            is_stale = age.total_seconds() > self._STALE_THRESHOLD_HOURS * 3600

        # overall_health: user-facing state for UI indicators
        if not self._configured:
            overall_health = 'unconfigured'
        elif failed_leads > 0 or last_sync_status == 'failed':
            overall_health = 'error'
        elif is_stale or pending_leads > 0:
            overall_health = 'stale'
        else:
            overall_health = 'ok'

        return {
            'supabase_configured': self._configured,
            'overall_health':      overall_health,   # 'ok' | 'stale' | 'error' | 'unconfigured'
            'is_stale':            is_stale,
            # Flat aliases for quick frontend consumption
            'pending_count':       pending_leads,
            'failed_count':        failed_leads,
            # Detailed counters
            'mysql_leads_total':   total_leads,
            'mysql_leads_pending': pending_leads,
            'mysql_leads_failed':  failed_leads,
            'mysql_users_pending': pending_users,
            # Timestamps
            'last_sync_at':        last_sync_at,
            'last_sync_status':    last_sync_status,
            'last_success_at':     last_success_at,
            'last_sync': {
                'operation':  last_log.operation if last_log else None,
                'status':     last_log.status if last_log else None,
                'records':    last_log.records if last_log else None,
                'created_at': last_sync_at,
                'error_msg':  last_log.error_msg if last_log else None,
            },
        }


# ─── Private helpers ──────────────────────────────────────────────────────────

def _apply_record_to_lead(lead: Lead, record: dict):
    """Apply fields from a Supabase record dict onto a Lead model instance."""
    field_map = {
        'name': 'name', 'email': 'email', 'phone': 'phone',
        'company': 'company', 'position': 'position', 'location': 'location',
        'country': 'country', 'city': 'city', 'industry': 'industry',
        'website': 'website', 'linkedin_url': 'linkedin_url',
        'interests': 'interests', 'product': 'product',
        'qualification_score': 'qualification_score',
        'status': 'status', 'notes': 'notes',
        'source': 'source',
    }
    for sb_field, mysql_field in field_map.items():
        if sb_field in record and record[sb_field] is not None:
            setattr(lead, mysql_field, record[sb_field])

    # Handle updated_at separately (don't overwrite with older value)
    mobile_updated = _parse_dt(record.get('updated_at'))
    if mobile_updated:
        existing_updated = _parse_dt(lead.updated_at)
        if existing_updated is None or mobile_updated > existing_updated:
            lead.updated_at = mobile_updated


# ─── Module-level singleton ───────────────────────────────────────────────────

_sync_service: SyncService | None = None


def get_sync_service() -> SyncService:
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService()
    return _sync_service
