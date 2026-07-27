"""
Analytics routes for business intelligence and reporting.
"""
from flask import Blueprint, request, jsonify, g
from app.exceptions import APIException
from app.models.models import db, Lead, User
from app.routes.auth import token_required
from app.utils.error_handler import success_response
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/v1/analytics')

# Canonical definition used across all analytics endpoints:
# Matches the quality engine's 'qualified' tier threshold (score >= 60).
QUALIFIED_SCORE_THRESHOLD = 60


def _ownership_filter(query):
    """Apply the same ownership filter used by the leads list.
    Admin → all leads (including null-owner legacy leads).
    Manager/User with company → company-wide. User without company → own only."""
    if g.role == 'admin':
        return query
    _u  = User.query.get(g.user_id)
    _co = (_u.company or '').strip().lower() if _u else ''
    if _co:
        team_ids = [r.id for r in User.query.filter(
            db.func.lower(db.func.trim(User.company)) == _co
        ).with_entities(User.id).all()]
        return query.filter(Lead.collected_by.in_(team_ids))
    return query.filter(Lead.collected_by == g.user_id)


def _get_daily_lead_counts(days: int):
    """Query real daily lead creation counts from the database."""
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=days)

    rows = (
        _ownership_filter(
            db.session.query(
                func.date(Lead.created_at).label('date'),
                func.count(Lead.id).label('leads'),
                func.sum(
                    db.case((Lead.qualification_score >= QUALIFIED_SCORE_THRESHOLD, 1), else_=0)
                ).label('qualified'),
            )
        )
        .filter(Lead.created_at >= start_date)
        .group_by(func.date(Lead.created_at))
        .order_by(func.date(Lead.created_at))
        .all()
    )

    date_map = {}
    for row in rows:
        key = str(row.date)[:10] if row.date else None
        if key:
            date_map[key] = row

    result = []
    for i in range(days, 0, -1):
        date = today - timedelta(days=i)
        date_str = date.isoformat()
        row = date_map.get(date_str)
        result.append({
            'date': date_str,
            'leads': int(row.leads) if row else 0,
            'qualified': int(row.qualified) if row else 0,
        })
    return result


def get_time_range_days(time_range):
    """Get number of days based on time range parameter."""
    ranges = {'7days': 7, '30days': 30, '90days': 90, 'all': 365}
    return ranges.get(time_range, 7)


@analytics_bp.route('', methods=['GET'])
@token_required
def get_analytics():
    """Get analytics data from real database."""
    try:
        time_range = request.args.get('range', '7days')
        days = get_time_range_days(time_range)

        daily_data = _get_daily_lead_counts(days)

        base = _ownership_filter(Lead.query)
        total_leads     = base.count()
        qualified_leads = base.filter(Lead.qualification_score >= QUALIFIED_SCORE_THRESHOLD).count()
        contacted_leads = _ownership_filter(Lead.query).filter(Lead.status == 'contacted').count()
        converted_leads = _ownership_filter(Lead.query).filter(Lead.status == 'converted').count()
        conversion_rate = round((converted_leads / total_leads * 100), 2) if total_leads > 0 else 0

        avg_score_row = (
            _ownership_filter(db.session.query(func.avg(Lead.qualification_score)))
            .filter(Lead.qualification_score > 0)
            .scalar()
        )
        avg_score = round(float(avg_score_row), 1) if avg_score_row else 0.0

        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        new_this_week = _ownership_filter(Lead.query).filter(Lead.created_at >= week_ago).count()

        # Status distribution
        status_rows = (
            _ownership_filter(db.session.query(Lead.status, func.count(Lead.id).label('count')))
            .filter(Lead.status.isnot(None))
            .group_by(Lead.status)
            .all()
        )

        # Score tier distribution (matches quality engine thresholds)
        score_tiers = {
            'high':   _ownership_filter(Lead.query).filter(Lead.qualification_score >= 70).count(),
            'medium': _ownership_filter(Lead.query).filter(Lead.qualification_score >= 40, Lead.qualification_score < 70).count(),
            'low':    _ownership_filter(Lead.query).filter(Lead.qualification_score > 0,  Lead.qualification_score < 40).count(),
        }

        # Interest distribution
        interest_counts: dict = {}
        for (interests,) in _ownership_filter(db.session.query(Lead.interests)).filter(Lead.interests.isnot(None)).all():
            if isinstance(interests, list):
                for item in interests:
                    interest_counts[item] = interest_counts.get(item, 0) + 1

        # Source distribution
        source_rows = (
            _ownership_filter(db.session.query(Lead.source, func.count(Lead.id).label('count')))
            .filter(Lead.source.isnot(None))
            .group_by(Lead.source)
            .all()
        )

        # Country distribution (for mobile pie chart + web analytics)
        country_rows = (
            _ownership_filter(db.session.query(Lead.country, func.count(Lead.id).label('count')))
            .filter(Lead.country.isnot(None), Lead.country != '')
            .group_by(Lead.country)
            .order_by(func.count(Lead.id).desc())
            .limit(20)
            .all()
        )

        # Industry distribution
        industry_rows = (
            _ownership_filter(db.session.query(Lead.industry, func.count(Lead.id).label('count')))
            .filter(Lead.industry.isnot(None), Lead.industry != '')
            .group_by(Lead.industry)
            .order_by(func.count(Lead.id).desc())
            .limit(10)
            .all()
        )

        return success_response(
            message='Analytics retrieved successfully',
            data={
                'time_range': time_range,
                'period_days': days,
                'daily_data': daily_data,
                'summary': {
                    'total_leads':       total_leads,
                    'qualified_leads':   qualified_leads,
                    'contacted_leads':   contacted_leads,
                    'converted_leads':   converted_leads,
                    'new_this_week':     new_this_week,
                    'qualification_rate': round((qualified_leads / total_leads * 100), 2) if total_leads > 0 else 0,
                    'conversion_rate':   conversion_rate,
                    'average_score':     avg_score,
                },
                'distribution': {
                    'by_interest':  interest_counts,
                    'by_source':    {row.source:   row.count for row in source_rows},
                    'by_country':   {row.country:  row.count for row in country_rows},
                    'by_industry':  {row.industry: row.count for row in industry_rows},
                    'by_status':    {row.status:   row.count for row in status_rows},
                    'by_score_tier': score_tiers,
                },
                'funnel': {
                    'total':     total_leads,
                    'qualified': qualified_leads,
                    'contacted': contacted_leads,
                    'converted': converted_leads,
                },
            },
        )
    except Exception as e:
        logger.error(f"Error fetching analytics: {str(e)}")
        raise APIException(f"Failed to fetch analytics: {str(e)}", status_code=500)


@analytics_bp.route('/daily', methods=['GET'])
@token_required
def get_daily_analytics():
    """Get daily analytics data from real database."""
    try:
        days = request.args.get('days', 30, type=int)
        days = max(1, min(days, 365))
        daily_data = _get_daily_lead_counts(days)
        return jsonify({
            'status': 'success',
            'data': daily_data,
            'period_days': days,
        }), 200
    except Exception as e:
        logger.error(f"Error fetching daily analytics: {str(e)}")
        raise APIException(f"Failed to fetch daily analytics: {str(e)}", status_code=500)


@analytics_bp.route('/summary', methods=['GET'])
@token_required
def get_analytics_summary():
    """Get analytics summary from real database."""
    try:
        total_leads     = _ownership_filter(Lead.query).count()
        qualified_leads = _ownership_filter(Lead.query).filter(Lead.qualification_score >= QUALIFIED_SCORE_THRESHOLD).count()
        qualification_rate = round((qualified_leads / total_leads * 100), 2) if total_leads > 0 else 0

        avg_score_row = (
            _ownership_filter(db.session.query(func.avg(Lead.qualification_score)))
            .filter(Lead.qualification_score > 0)
            .scalar()
        )
        avg_score = round(float(avg_score_row), 1) if avg_score_row else 0.0

        top_source_row = (
            _ownership_filter(db.session.query(Lead.source, func.count(Lead.id).label('count')))
            .filter(Lead.source.isnot(None))
            .group_by(Lead.source)
            .order_by(func.count(Lead.id).desc())
            .first()
        )

        return jsonify({
            'status': 'success',
            'summary': {
                'total_leads':          total_leads,
                'qualified_leads':      qualified_leads,
                'qualification_rate':   qualification_rate,
                'average_lead_quality': avg_score,
                'top_source':           top_source_row.source if top_source_row else 'N/A',
            }
        }), 200
    except Exception as e:
        logger.error(f"Error fetching analytics summary: {str(e)}")
        raise APIException(f"Failed to fetch analytics summary: {str(e)}", status_code=500)


@analytics_bp.route('/score-distribution', methods=['GET'])
@token_required
def get_score_distribution():
    """Count leads in each 10-point score bucket (0-10, 10-20, …, 90-100)."""
    try:
        buckets = []
        for low in range(0, 100, 10):
            high = low + 10
            if high == 100:
                count = _ownership_filter(Lead.query).filter(
                    Lead.qualification_score >= low,
                    Lead.qualification_score <= 100,
                ).count()
            else:
                count = _ownership_filter(Lead.query).filter(
                    Lead.qualification_score >= low,
                    Lead.qualification_score < high,
                ).count()
            buckets.append({'range': f'{low}-{high}', 'low': low, 'high': high, 'count': count})
        return success_response(message='Score distribution retrieved', data={'buckets': buckets})
    except Exception as e:
        logger.error(f"Error fetching score distribution: {str(e)}")
        raise APIException(f"Failed to fetch score distribution: {str(e)}", status_code=500)


@analytics_bp.route('/source-performance', methods=['GET'])
@token_required
def get_source_performance():
    """Per-source breakdown: total, qualified count, qual rate, avg score, contacted, converted."""
    try:
        rows = (
            _ownership_filter(
                db.session.query(
                    Lead.source,
                    func.count(Lead.id).label('total'),
                    func.sum(
                        db.case((Lead.qualification_score >= QUALIFIED_SCORE_THRESHOLD, 1), else_=0)
                    ).label('qualified'),
                    func.avg(Lead.qualification_score).label('avg_score'),
                    func.sum(db.case((Lead.status == 'contacted', 1), else_=0)).label('contacted'),
                    func.sum(db.case((Lead.status == 'converted', 1), else_=0)).label('converted'),
                )
            )
            .filter(Lead.source.isnot(None))
            .group_by(Lead.source)
            .order_by(func.count(Lead.id).desc())
            .all()
        )
        sources = []
        for r in rows:
            total = int(r.total)
            qualified = int(r.qualified or 0)
            sources.append({
                'source':    r.source,
                'total':     total,
                'qualified': qualified,
                'qual_rate': round((qualified / total * 100), 1) if total > 0 else 0.0,
                'avg_score': round(float(r.avg_score), 1) if r.avg_score else 0.0,
                'contacted': int(r.contacted or 0),
                'converted': int(r.converted or 0),
            })
        return success_response(message='Source performance retrieved', data={'sources': sources})
    except Exception as e:
        logger.error(f"Error fetching source performance: {str(e)}")
        raise APIException(f"Failed to fetch source performance: {str(e)}", status_code=500)


@analytics_bp.route('/metrics', methods=['GET'])
@token_required
def get_metrics():
    """Get detailed metrics from real database."""
    try:
        total     = _ownership_filter(Lead.query).count()
        qualified = _ownership_filter(Lead.query).filter(Lead.qualification_score >= QUALIFIED_SCORE_THRESHOLD).count()
        contacted = _ownership_filter(Lead.query).filter(Lead.status == 'contacted').count()
        converted = _ownership_filter(Lead.query).filter(Lead.status == 'converted').count()
        avg_score = _ownership_filter(db.session.query(func.avg(Lead.qualification_score))).scalar() or 0

        return jsonify({
            'status': 'success',
            'metrics': {
                'leads_created':                total,
                'leads_qualified':              qualified,
                'leads_contacted':              contacted,
                'leads_converted':              converted,
                'average_qualification_score':  round(float(avg_score), 2),
                'qualification_threshold':      QUALIFIED_SCORE_THRESHOLD,
            }
        }), 200
    except Exception as e:
        logger.error(f"Error fetching metrics: {str(e)}")
        raise APIException(f"Failed to fetch metrics: {str(e)}", status_code=500)
