"""
Celery tasks for heavy AI operations.

All tasks use @celery.task so they inherit ContextTask (set by make_celery in
celery_worker.py), which wraps each call in a Flask app context.  No task
should call create_app() itself — the context is already active.

Queues
------
  agents  — LLM-heavy operations (qualify single lead, batch qualify)
  default — periodic maintenance (requalify old leads, cleanup)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.celery_app import celery

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (imported lazily to avoid circular imports at module load time)
# ─────────────────────────────────────────────────────────────────────────────

def _build_lead_data(lead) -> Dict[str, Any]:
    """Serialise a Lead ORM object into the dict the scoring functions expect."""
    dp = lead.data_points if isinstance(lead.data_points, dict) else {}
    return {
        'name':               lead.name,
        'email':              lead.email,
        'company':            lead.company,
        'position':           lead.position,
        'industry':           lead.industry or '',
        'country':            lead.country or '',
        'city':               lead.city or '',
        'website':            lead.website or '',
        'linkedin_url':       lead.linkedin_url or '',
        'phone':              lead.phone or '',
        'interests':          lead.interests or [],
        'product':            lead.product or '',
        'source':             lead.source or '',
        'completeness_score': lead.completeness_score or 0,
        'email_type':         lead.email_type or '',
        'data_points':        dp,
    }


def _save_qualification(lead, result: Dict[str, Any]) -> None:
    """Persist AI qualification result back to the lead record (no commit)."""
    from sqlalchemy.orm.attributes import flag_modified
    from app.routes.ai import _derive_status

    lead.qualification_score = result['score']
    new_st = _derive_status(result)
    # Never demote a hot lead unless the new result is also hot
    if lead.status != 'hot' or new_st == 'hot':
        lead.status = new_st

    if not isinstance(lead.data_points, dict):
        lead.data_points = {}
    lead.data_points['ai_qualification'] = {
        'score':        result['score'],
        'category':     result.get('category', ''),
        'confidence':   result.get('confidence', 0),
        'reasoning':    result.get('reasoning', result.get('reason', '')),
        'strengths':    result.get('strengths', []),
        'weaknesses':   result.get('weaknesses', []),
        'next_action':  result.get('next_action', ''),
        'ai_provider':  result.get('ai_provider', ''),
        'qualified_at': datetime.now(timezone.utc).isoformat(),
    }
    flag_modified(lead, 'data_points')


# ─────────────────────────────────────────────────────────────────────────────
# § 1 · Single-lead async qualification
# ─────────────────────────────────────────────────────────────────────────────

@celery.task(
    bind=True,
    name='app.tasks.agent_tasks.qualify_lead_async',
    queue='agents',
    max_retries=3,
    default_retry_delay=60,
)
def qualify_lead_async(self, lead_id: int) -> Dict[str, Any]:
    """
    Run the full AI qualification pipeline for one lead and persist the result.
    Called from POST /ai/refresh-lead/<id> when use_ai=True.

    Returns the same dict the synchronous path returns so the polling endpoint
    can hand it back to the frontend unchanged.
    """
    from app.models.models import db, Lead
    from app.routes.ai import qualify_lead_with_external_ai

    try:
        lead = db.session.get(Lead, lead_id)
        if not lead:
            return {'status': 'error', 'message': f'Lead {lead_id} not found'}

        lead_data = _build_lead_data(lead)
        ai_result = qualify_lead_with_external_ai(lead_data, lead_id=lead.id)

        _save_qualification(lead, ai_result)
        db.session.commit()

        logger.info('[qualify_lead_async] lead=%d score=%s provider=%s',
                    lead_id, ai_result.get('score'), ai_result.get('ai_provider'))

        return {
            'status':     'success',
            'lead_id':    lead.id,
            'name':       lead.name,
            'new_score':  ai_result['score'],
            'category':   ai_result.get('category', ''),
            'confidence': ai_result.get('confidence', 0),
            'ai_provider': ai_result.get('ai_provider', ''),
            'reason':     ai_result.get('reasoning', ai_result.get('reason', '')),
        }

    except Exception as exc:
        db.session.rollback()
        logger.error('[qualify_lead_async] lead=%d error=%s', lead_id, exc, exc_info=True)
        countdown = 60 * (2 ** self.request.retries)   # 60 s, 120 s, 240 s
        raise self.retry(exc=exc, countdown=countdown)


# ─────────────────────────────────────────────────────────────────────────────
# § 2 · Batch qualification
# ─────────────────────────────────────────────────────────────────────────────

@celery.task(
    bind=True,
    name='app.tasks.agent_tasks.qualify_batch_async',
    queue='agents',
    max_retries=1,
    default_retry_delay=120,
)
def qualify_batch_async(
    self,
    lead_ids:   Optional[List[int]],
    limit:      int,
    use_ai:     bool,
    user_id:    Optional[int]   = None,
    user_email: Optional[str]   = None,
) -> Dict[str, Any]:
    """
    Qualify a batch of leads asynchronously.
    Called from POST /ai/qualify-batch.

    Returns the same 'data' dict the synchronous route returned so the
    frontend polling handler can consume it without changes.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from sqlalchemy import case

    from app.models.models import db, Lead
    from app.routes.ai import (
        qualify_lead_with_external_ai,
        _qualify_fast,
        _derive_status,
        _FAST_BATCH_THRESHOLD,
        _load_ai_settings,
        _add_log,
        AI_ENGINE_STATE,
    )
    from app.services.gemini_service import get_ai_service

    try:
        cfg           = _load_ai_settings()
        conf_threshold = cfg.get('confidence_threshold', 75)
        cfg_workers   = max(1, int(cfg.get('max_workers', 4)))
        ai_svc        = get_ai_service()

        # ── Build lead list ───────────────────────────────────────────────────
        if lead_ids:
            leads = Lead.query.filter(Lead.id.in_(lead_ids)).all()
        else:
            priority = case(
                (Lead.status.in_(['pending', 'warm', 'hot', None, '']), 0),
                else_=1,
            )
            leads = (Lead.query
                     .order_by(priority, Lead.qualification_score.desc())
                     .limit(limit)
                     .all())

        if not leads:
            return {'processed': 0, 'hot': 0, 'warm': 0, 'cold': 0,
                    'errors': 0, 'average_score': 0, 'promoted': 0}

        # ── Fast score-based status promotion (no AI needed) ─────────────────
        promoted = 0
        for lead in leads:
            qs     = lead.qualification_score or 0
            cs     = qs if qs > 0 else (lead.completeness_score or 0)
            new_st = 'hot' if cs >= 80 else 'warm' if cs >= 60 else 'cold'
            if lead.status != new_st:
                lead.status = new_st
                promoted += 1
        if promoted:
            db.session.flush()

        before_scores   = {l.id: (l.qualification_score or 0) for l in leads}
        before_statuses = {l.id: (l.status or 'cold')         for l in leads}

        # ── Build per-lead data dicts ─────────────────────────────────────────
        is_large = len(leads) > _FAST_BATCH_THRESHOLD
        lead_map = {l.id: {'lead': l, 'data': _build_lead_data(l)} for l in leads}

        # ── Scoring worker ────────────────────────────────────────────────────
        def _qualify_one(lid, lead_data):
            try:
                if not use_ai:
                    return lid, ai_svc.qualify_lead_fast(lead_data), None
                if is_large:
                    return lid, _qualify_fast(lead_data), None
                return lid, qualify_lead_with_external_ai(lead_data, lead_id=lid), None
            except Exception as e:
                return lid, None, e

        # Large / fast batches: more parallelism.  LLM batches: cap at 2 to
        # stay within Groq/Gemini rate limits.
        workers = min(cfg_workers, 5) if (not use_ai or is_large) else min(cfg_workers, 2)

        processed = hot = warm = cold = errors = 0
        total_score = 0.0
        results = []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_qualify_one, lid, info['data']): lid
                for lid, info in lead_map.items()
            }
            for future in as_completed(futures):
                lid, result, err = future.result()
                if err or not result:
                    logger.warning('[qualify_batch_async] lead=%d failed: %s', lid, err)
                    errors += 1
                    continue

                lead       = lead_map[lid]['lead']
                new_status = _derive_status(result) if result['score'] >= conf_threshold else 'cold'
                _save_qualification(lead, result)
                if lead.status != 'hot' or new_status == 'hot':
                    lead.status = new_status

                total_score += result['score']
                processed   += 1
                cat = result.get('category', '').lower()
                if cat == 'hot':
                    hot  += 1
                elif cat == 'warm':
                    warm += 1
                else:
                    cold += 1

                results.append({
                    'id':         lead.id,
                    'name':       lead.name,
                    'company':    lead.company,
                    'score':      result['score'],
                    'category':   result.get('category', ''),
                    'reasoning':  result.get('reasoning', ''),
                    'ai_provider': result.get('ai_provider', ''),
                })

        score_changed  = sum(
            1 for info in lead_map.values()
            if abs((info['lead'].qualification_score or 0) - before_scores.get(info['lead'].id, 0)) >= 2
        )
        status_changed = sum(
            1 for info in lead_map.values()
            if (info['lead'].status or 'cold') != before_statuses.get(info['lead'].id, 'cold')
        )

        db.session.commit()

        # ── Update global engine counters ─────────────────────────────────────
        AI_ENGINE_STATE['processed_count'] += processed
        AI_ENGINE_STATE['qualified_count'] += (hot + warm)
        avg = round(total_score / processed, 1) if processed else 0

        engine_used = (
            'QualificationAgent+ML (fast)' if (use_ai and is_large)
            else (ai_svc.provider_name if use_ai else 'Smart Rules')
        )

        _add_log(
            'Batch qualification completed', 'success',
            f'{processed} leads: {hot} hot, {warm} warm, {cold} cold '
            f'(avg {avg}, provider: {engine_used})',
        )

        # ── Optional email notification ───────────────────────────────────────
        if user_email and processed > 0:
            try:
                from app.routes.settings import _get_user_settings
                from app.services.email_service import (
                    send_qualification_summary, send_high_quality_alert,
                )
                prefs     = _get_user_settings(user_id) if user_id else {}
                hot_leads = [r for r in results if r.get('category', '').lower() == 'hot']
                if prefs.get('notify_qualification'):
                    send_qualification_summary(user_email, processed, hot, warm, cold, avg)
                if prefs.get('notify_high_quality') and hot_leads:
                    r = hot_leads[0]
                    send_high_quality_alert(user_email, r.get('name', ''),
                                            r.get('company', ''), r.get('score', 0), '')
            except Exception as _e:
                logger.debug('[qualify_batch_async] email notification skipped: %s', _e)

        logger.info('[qualify_batch_async] processed=%d hot=%d warm=%d cold=%d errors=%d',
                    processed, hot, warm, cold, errors)

        return {
            'processed':      processed,
            'promoted':       promoted,
            'hot':            hot,
            'warm':           warm,
            'cold':           cold,
            'errors':         errors,
            'average_score':  avg,
            'score_changed':  score_changed,
            'status_changed': status_changed,
            'ai_provider':    engine_used,
        }

    except Exception as exc:
        db.session.rollback()
        logger.error('[qualify_batch_async] fatal error: %s', exc, exc_info=True)
        raise self.retry(exc=exc, countdown=120)


# ─────────────────────────────────────────────────────────────────────────────
# § 3 · Periodic maintenance tasks
# ─────────────────────────────────────────────────────────────────────────────

@celery.task(
    name='app.tasks.agent_tasks.requalify_old_leads',
    queue='default',
)
def requalify_old_leads() -> Dict[str, Any]:
    """Re-score leads that have not been qualified in the last 30 days (2 AM daily)."""
    from datetime import timedelta
    from app.models.models import db, Lead
    from app.routes.ai import _qualify_fast

    try:
        cutoff    = datetime.now(timezone.utc) - timedelta(days=30)
        old_leads = Lead.query.filter(Lead.updated_at < cutoff).limit(100).all()

        if not old_leads:
            logger.info('[requalify_old_leads] nothing to process')
            return {'status': 'no_leads_to_requalify'}

        updated = 0
        for lead in old_leads:
            try:
                result = _qualify_fast(_build_lead_data(lead))
                _save_qualification(lead, result)
                updated += 1
            except Exception as e:
                logger.warning('[requalify_old_leads] lead=%d skipped: %s', lead.id, e)

        db.session.commit()
        logger.info('[requalify_old_leads] updated=%d/%d', updated, len(old_leads))
        return {'status': 'completed', 'leads_updated': updated}

    except Exception as exc:
        db.session.rollback()
        logger.error('[requalify_old_leads] error: %s', exc, exc_info=True)
        return {'status': 'failed', 'error': str(exc)}


@celery.task(
    name='app.tasks.agent_tasks.cleanup_stale_data',
    queue='default',
)
def cleanup_stale_data() -> Dict[str, Any]:
    """Delete leads archived for more than 90 days (3 AM daily)."""
    from datetime import timedelta
    from app.models.models import db, Lead

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        deleted = (Lead.query
                   .filter(Lead.updated_at < cutoff, Lead.status == 'archived')
                   .delete(synchronize_session=False))
        db.session.commit()
        logger.info('[cleanup_stale_data] deleted=%d stale records', deleted)
        return {'status': 'completed', 'records_deleted': deleted}

    except Exception as exc:
        db.session.rollback()
        logger.error('[cleanup_stale_data] error: %s', exc, exc_info=True)
        return {'status': 'failed', 'error': str(exc)}
