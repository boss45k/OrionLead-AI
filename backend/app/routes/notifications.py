"""
Real-time notification feed.
Derives live events from DB state — no separate notifications table needed.
Events: hot leads, unscored leads, sync issues, admin approvals, AI runs.
Also supports admin-broadcast messages via in-memory store (cleared on restart).
"""
from flask import Blueprint, jsonify, request, g
from datetime import datetime, timedelta, timezone
import logging
import threading
import uuid

from app.models.models import db, Lead, User
from app.routes.auth import token_required

logger = logging.getLogger(__name__)

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/v1/notifications')

_TYPE_PRI = {'error': 0, 'warning': 1, 'success': 2, 'info': 3}

# In-memory broadcast store — visible to all users, cleared on restart
_broadcasts: list = []
_broadcasts_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc)


def _ts(dt):
    """Return ISO string for a datetime, handling both aware and naive."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _sort_key(n):
    t = n.get('time')
    ts = 0
    if t:
        try:
            ts = datetime.fromisoformat(t).timestamp()
        except Exception:
            pass
    return (-ts, _TYPE_PRI.get(n.get('type', 'info'), 9))


@notifications_bp.route('/', methods=['GET'])
@token_required
def get_notifications():
    """Return real-time notifications derived from live DB state."""
    try:
        user_id  = g.user_id
        is_admin = getattr(g, 'role', 'user') == 'admin'
        now      = _now()
        items    = []

        # ── 1. Hot leads (score ≥ 80) added in last 48 h ─────────────────────
        hot_leads = (
            Lead.query
            .filter(
                Lead.collected_by == user_id,
                Lead.qualification_score >= 80,
                Lead.created_at >= now - timedelta(hours=48),
            )
            .order_by(Lead.created_at.desc())
            .limit(5)
            .all()
        )
        for lead in hot_leads:
            score = int(lead.qualification_score or 0)
            items.append({
                'id':          f'hot_lead_{lead.id}',
                'type':        'success',
                'category':    'Hot Lead',
                'title':       f'Hot lead: {lead.name or lead.email or "Unknown"}',
                'description': (
                    f'{lead.company or "Unknown company"}'
                    f' — Score {score}/100'
                    f' · {lead.source or "manual"}'
                ),
                'time':       _ts(lead.created_at),
                'email_sent': score >= 80,   # email_service fires for every score >= 80
            })

        # ── 2. New leads added today ──────────────────────────────────────────
        new_today_leads = (
            Lead.query
            .filter(
                Lead.collected_by == user_id,
                Lead.created_at >= now - timedelta(hours=24),
            )
            .order_by(Lead.created_at.desc())
            .all()
        )
        new_today = len(new_today_leads)
        if new_today > 0:
            items.append({
                'id':          f'new_leads_today_{new_today}',
                'type':        'info',
                'category':    'Leads',
                'title':       f'{new_today} new lead{"s" if new_today != 1 else ""} today',
                'description': 'Added in the last 24 hours',
                'time':        _ts(new_today_leads[0].created_at),
                'email_sent':  False,
            })

        # ── 3. Leads with no score (awaiting AI qualification) ────────────────
        unscored = (
            Lead.query
            .filter(
                Lead.collected_by == user_id,
                Lead.created_at >= now - timedelta(hours=72),
                db.or_(
                    Lead.qualification_score.is_(None),
                    Lead.qualification_score == 0,
                ),
            )
            .count()
        )
        if unscored > 0:
            items.append({
                'id':          f'unscored_{unscored}',
                'type':        'warning',
                'category':    'AI Engine',
                'title':       f'{unscored} lead{"s" if unscored != 1 else ""} need{"s" if unscored == 1 else ""} scoring',
                'description': 'Run AI qualification to prioritize your pipeline',
                'time':        None,
                'email_sent':  False,
            })

        # ── 4. Sync status ────────────────────────────────────────────────────
        try:
            from app.services.sync_service import SyncService
            sync_status = SyncService().get_sync_status()
            health = sync_status.get('overall_health', 'ok')
            if health == 'stale':
                pc = sync_status.get('pending_count', 0)
                items.append({
                    'id':          f'sync_stale_{pc}',
                    'type':        'warning',
                    'category':    'Sync',
                    'title':       f'{pc} lead{"s" if pc != 1 else ""} pending sync',
                    'description': 'Mobile app may be showing stale data',
                    'time':        sync_status.get('last_sync_at'),
                    'email_sent':  False,
                })
            elif health == 'error':
                fc = sync_status.get('failed_count', 0)
                items.append({
                    'id':          f'sync_error_{fc}',
                    'type':        'error',
                    'category':    'Sync',
                    'title':       f'{fc} sync failure{"s" if fc != 1 else ""}',
                    'description': 'Check your Supabase connection and retry',
                    'time':        sync_status.get('last_sync_at'),
                    'email_sent':  False,
                })
        except Exception:
            pass

        # ── 5. Admin-only: pending user approvals ─────────────────────────────
        if is_admin:
            pending_users = User.query.filter_by(is_active=False).count()
            if pending_users > 0:
                items.append({
                    'id':          f'pending_users_{pending_users}',
                    'type':        'warning',
                    'category':    'Admin',
                    'title':       f'{pending_users} user{"s" if pending_users != 1 else ""} awaiting approval',
                    'description': 'Review and activate in the Admin Panel',
                    'time':        None,
                    'email_sent':  False,
                })

        # ── 6. Low conversion rate warning ────────────────────────────────────
        try:
            total = Lead.query.filter(Lead.collected_by == user_id).count()
            if total >= 10:
                converted = Lead.query.filter(
                    Lead.collected_by == user_id,
                    Lead.status == 'converted',
                ).count()
                rate = round((converted / total) * 100, 1)
                if rate < 10:
                    items.append({
                        'id':          f'low_conversion_{int(rate)}',
                        'type':        'warning',
                        'category':    'Analytics',
                        'title':       f'Conversion rate at {rate}%',
                        'description': 'Review AI qualification thresholds in the AI Engine',
                        'time':        None,
                        'email_sent':  False,
                    })
        except Exception:
            pass

        # ── 7. Admin broadcasts (pinned at the top for all users) ────────────
        with _broadcasts_lock:
            items = list(_broadcasts) + items

        items.sort(key=_sort_key)

        return jsonify({'notifications': items[:20], 'count': len(items)})

    except Exception as exc:
        logger.error('[notifications] get_notifications error: %s', exc)
        return jsonify({'notifications': [], 'count': 0})


# ── Broadcast management (admin only) ─────────────────────────────────────────

def _admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if getattr(g, 'role', None) != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return wrapper


@notifications_bp.route('/broadcast', methods=['GET'])
@token_required
@_admin_required
def list_broadcasts():
    """Return all active broadcasts."""
    with _broadcasts_lock:
        return jsonify({'broadcasts': list(_broadcasts), 'count': len(_broadcasts)})


@notifications_bp.route('/broadcast', methods=['POST'])
@token_required
@_admin_required
def create_broadcast():
    """Push a notification to all web users."""
    body = request.get_json(silent=True) or {}
    title = (body.get('title') or '').strip()
    description = (body.get('description') or '').strip()
    ntype = body.get('type', 'info')

    if not title:
        return jsonify({'error': 'title is required'}), 400
    if ntype not in ('info', 'success', 'warning', 'error'):
        ntype = 'info'

    broadcast = {
        'id':          f'broadcast_{uuid.uuid4().hex[:8]}',
        'type':        ntype,
        'category':    'Broadcast',
        'title':       title,
        'description': description,
        'time':        _now().isoformat(),
        'email_sent':  False,
    }
    with _broadcasts_lock:
        _broadcasts.insert(0, broadcast)

    logger.info('[notifications] broadcast created by admin %s: %s', g.user_id, title)
    return jsonify({'status': 'success', 'broadcast': broadcast}), 201


@notifications_bp.route('/broadcast/<broadcast_id>', methods=['DELETE'])
@token_required
@_admin_required
def delete_broadcast(broadcast_id):
    """Remove a broadcast (dismiss for all users)."""
    with _broadcasts_lock:
        before = len(_broadcasts)
        _broadcasts[:] = [b for b in _broadcasts if b['id'] != broadcast_id]
        removed = before - len(_broadcasts)

    if removed == 0:
        return jsonify({'error': 'Broadcast not found'}), 404
    return jsonify({'status': 'success', 'message': 'Broadcast removed'})
