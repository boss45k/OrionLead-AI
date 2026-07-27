"""
Sync routes — two-way MySQL ↔ Supabase synchronization.

Endpoints:
  POST /api/v1/sync/web-to-mobile     Push MySQL leads → Supabase  (authenticated)
  POST /api/v1/sync/mobile-to-web     Push Supabase records → MySQL (authenticated)
  POST /api/v1/sync/webhook           Supabase Database Webhook receiver (HMAC-signed)
  POST /api/v1/sync/poll              Pull pending Supabase records → MySQL (admin)
  POST /api/v1/sync/user              Sync current user → Supabase
  POST /api/v1/sync/users/all         Sync all users → Supabase (admin)
  GET  /api/v1/sync/status            Sync health + pending counts
  GET  /api/v1/sync/logs              Recent sync audit log
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request, g

from app.models.models import db, User, Lead, SyncLog
from app.routes.auth import token_required, admin_required, mobile_user_required
from app.services.sync_service import get_sync_service
from app.utils.error_handler import handle_exceptions

logger = logging.getLogger(__name__)

sync_bp = Blueprint('sync', __name__, url_prefix='/api/v1/sync')

WEBHOOK_SECRET = os.getenv('SUPABASE_WEBHOOK_SECRET', '')


# ─── Webhook signature verification ──────────────────────────────────────────

def _verify_webhook(request_) -> bool:
    """Verify Supabase webhook HMAC-SHA256 signature."""
    if not WEBHOOK_SECRET:
        logger.warning('[Sync] SUPABASE_WEBHOOK_SECRET not set — webhook auth disabled')
        return True   # permissive in dev; set the secret in production

    signature = request_.headers.get('x-supabase-signature', '')
    body = request_.get_data()
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f'sha256={expected}', signature)


# ─── POST /sync/web-to-mobile ─────────────────────────────────────────────────

@sync_bp.route('/web-to-mobile', methods=['POST'])
@token_required
@mobile_user_required
@handle_exceptions
def web_to_mobile():
    """
    Push MySQL leads → Supabase leads_cache.

    Body (optional):
        { "lead_ids": [1,2,3], "since": "2024-01-01T00:00:00Z" }

    If neither provided, syncs ALL leads with sync_status='pending'.
    """
    data     = request.get_json(silent=True) or {}
    lead_ids = data.get('lead_ids')
    since_str= data.get('since')

    since = None
    if since_str:
        try:
            since = datetime.fromisoformat(since_str.replace('Z', '+00:00'))
        except ValueError:
            return jsonify({'error': 'Invalid "since" datetime format'}), 400

    svc    = get_sync_service()
    result = svc.web_to_mobile(lead_ids=lead_ids, since=since, triggered_by=g.email)

    logger.info(f'[Sync] web→mobile by {g.email}: {result}')
    return jsonify({'status': 'success', 'message': 'Web-to-mobile sync complete', **result}), 200


# ─── POST /sync/mobile-to-web ─────────────────────────────────────────────────

@sync_bp.route('/mobile-to-web', methods=['POST'])
@token_required
@mobile_user_required
@handle_exceptions
def mobile_to_web():
    """
    Receive lead records from the mobile app and write them into MySQL.

    Body:
        { "records": [ { ...lead fields... }, ... ] }

    Each record should include:
        lead_uuid, name, email, ..., updated_at, sync_status
    """
    data    = request.get_json() or {}
    records = data.get('records', [])

    if not records:
        return jsonify({'error': '"records" array is required and must not be empty'}), 400

    if len(records) > 200:
        return jsonify({'error': 'Maximum 200 records per request'}), 400

    svc    = get_sync_service()
    result = svc.mobile_to_web(records, triggered_by=g.email)

    logger.info(f'[Sync] mobile→web by {g.email}: {result}')
    return jsonify({'status': 'success', 'message': 'Mobile-to-web sync complete', **result}), 200


# ─── POST /sync/webhook ───────────────────────────────────────────────────────

@sync_bp.route('/webhook', methods=['POST'])
@handle_exceptions
def supabase_webhook():
    """
    Supabase Database Webhook receiver.

    Configure in Supabase:
        Dashboard → Database → Webhooks → Create webhook
        Table: leads_cache
        Events: INSERT, UPDATE
        HTTP URL: https://your-backend.com/api/v1/sync/webhook
        HTTP Headers: x-supabase-signature: sha256=<HMAC>

    Payload format (Supabase sends):
        { "type": "INSERT"|"UPDATE", "table": "leads_cache",
          "record": { ...row... }, "old_record": { ... } }
    """
    if not _verify_webhook(request):
        logger.warning(f'[Sync] Webhook signature invalid from {request.remote_addr}')
        return jsonify({'error': 'Invalid signature'}), 401

    payload = request.get_json(silent=True) or {}
    event   = payload.get('type', '').upper()
    table   = payload.get('table', '')
    record  = payload.get('record', {})

    # Only process leads_cache inserts/updates from mobile
    if table != 'leads_cache' or event not in ('INSERT', 'UPDATE'):
        return jsonify({'status': 'success', 'message': 'Ignored', 'event': event, 'table': table}), 200

    # Skip records that originated from web (already in MySQL) or are already synced
    origin      = record.get('origin', 'mobile')
    sync_status = record.get('sync_status', 'pending')

    if origin == 'web' or sync_status == 'synced':
        return jsonify({'status': 'success', 'message': 'Skipped — no sync needed', 'reason': f'origin={origin}, sync_status={sync_status}'}), 200

    svc    = get_sync_service()
    result = svc.mobile_to_web([record], triggered_by='webhook')

    logger.info(f'[Sync] Webhook processed: {result}')
    return jsonify({'status': 'success', 'message': 'Webhook processed', **result}), 200


# ─── POST /sync/poll ──────────────────────────────────────────────────────────

@sync_bp.route('/poll', methods=['POST'])
@token_required
@admin_required
@handle_exceptions
def poll_supabase():
    """
    Polling fallback: pull sync_status='pending' records from Supabase → MySQL.
    Use this if webhooks are not configured.
    """
    data  = request.get_json(silent=True) or {}
    limit = min(int(data.get('limit', 200)), 500)

    svc    = get_sync_service()
    result = svc.pull_pending_from_supabase(limit=limit)

    logger.info(f'[Sync] Poll by {g.email}: {result}')
    return jsonify({'status': 'success', 'message': 'Poll complete', **result}), 200


# ─── POST /sync/user ──────────────────────────────────────────────────────────

@sync_bp.route('/user', methods=['POST'])
@token_required
@mobile_user_required
@handle_exceptions
def sync_current_user():
    """Sync the authenticated user's record → Supabase users_sync."""
    svc    = get_sync_service()
    result = svc.sync_users_to_supabase(user_ids=[g.user_id], triggered_by=g.email)
    return jsonify({'status': 'success', 'message': 'User synced', **result}), 200


# ─── POST /sync/users/all ─────────────────────────────────────────────────────

@sync_bp.route('/users/all', methods=['POST'])
@token_required
@admin_required
@handle_exceptions
def sync_all_users():
    """Admin: sync ALL pending users → Supabase."""
    svc    = get_sync_service()
    result = svc.sync_users_to_supabase(triggered_by=g.email)
    return jsonify({'status': 'success', 'message': 'All users sync complete', **result}), 200


# ─── POST /sync/retry-failed ──────────────────────────────────────────────────

@sync_bp.route('/retry-failed', methods=['POST'])
@token_required
@handle_exceptions
def retry_failed():
    """
    Reset all leads with sync_status='failed' back to 'pending', then
    immediately push them to Supabase.  Returns the same shape as web-to-mobile.
    """
    svc = get_sync_service()

    # Find failed leads
    failed = Lead.query.filter_by(sync_status='failed').all()
    if not failed:
        return jsonify({'status': 'success', 'message': 'No failed leads to retry', 'synced': 0, 'failed': 0, 'skipped': 0}), 200

    # Reset to pending so web_to_mobile picks them up
    ids = [l.id for l in failed]
    for lead in failed:
        lead.sync_status = 'pending'
    db.session.commit()

    logger.info(f'[Sync] retry-failed: reset {len(ids)} leads to pending, re-pushing…')

    result = svc.web_to_mobile(lead_ids=ids, triggered_by='system')
    return jsonify({'status': 'success', 'retried': len(ids), **result}), 200


# ─── GET /sync/status ─────────────────────────────────────────────────────────

@sync_bp.route('/status', methods=['GET'])
@token_required
@handle_exceptions
def sync_status():
    """Return sync health — pending counts, last sync info."""
    svc = get_sync_service()
    return jsonify(svc.get_status()), 200


# ─── GET /sync/logs ───────────────────────────────────────────────────────────

@sync_bp.route('/logs', methods=['GET'])
@token_required
@handle_exceptions
def sync_logs():
    """Return recent sync audit log entries (last 50)."""
    limit = min(int(request.args.get('limit', 50)), 200)
    logs  = SyncLog.query.order_by(SyncLog.created_at.desc()).limit(limit).all()

    return jsonify({
        'status': 'success',
        'logs': [
            {
                'id':           l.id,
                'operation':    l.operation,
                'direction':    l.direction,
                'records':      l.records,
                'status':       l.status,
                'error_msg':    l.error_msg,
                'triggered_by': l.triggered_by,
                'duration_ms':  l.duration_ms,
                'created_at':   l.created_at.isoformat(),
            }
            for l in logs
        ],
        'total': len(logs),
    }), 200
