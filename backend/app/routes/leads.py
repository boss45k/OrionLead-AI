"""
Lead management routes
Handles CRUD operations, search, filtering, and analytics for leads
"""

from flask import Blueprint, jsonify, request, g, make_response, current_app
from marshmallow import ValidationError as MarshmallowValidationError
from sqlalchemy import or_, desc, asc
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
import logging

from app.models.models import db, Lead, LeadActivity, LeadOutcome, User
from app.schemas.schemas import (
    LeadSchema,
    LeadCreateSchema,
    LeadUpdateSchema,
    PaginationSchema,
    FilterSchema,
    SearchSchema,
)
from app.exceptions import (
    ValidationError,
    NotFoundError,
    DatabaseError,
)
from app.routes.auth import token_required, admin_required
from app.utils.error_handler import handle_exceptions, success_response
from app.utils.rate_limiter import get_limiter
from app.utils.metrics import track_lead_operation, track_database_query, track_error, track_qualification
from app.services.qualification_agent import QualificationAgent
from app.services.clearbit_service import get_clearbit_client, is_clearbit_configured
from app.services.lead_validator import score_lead
from app.services.lead_quality_engine import evaluate_lead_quality
from time import time

logger = logging.getLogger(__name__)


def _push(user_id: int, title: str, body: str, data: dict | None = None):
    """Fire-and-forget push notification — never raises."""
    try:
        from app.services.fcm_service import get_fcm_service
        get_fcm_service().send_to_user(user_id, title, body, data or {})
    except Exception as _e:
        logger.debug("[leads] push notification skipped: %s", _e)


from app.services.lead_dedup import company_duplicate as _company_duplicate


# Initialize AI qualification agent
qualification_agent = QualificationAgent()

leads_bp = Blueprint('leads', __name__, url_prefix='/api/v1/leads')
limiter = get_limiter()


@leads_bp.route('/', methods=['GET'])
@limiter.limit("30 per minute")  # Standard read limit
@token_required
@handle_exceptions
def get_leads():
    """
    Get all leads with pagination and filtering

    Query Parameters:
        page: Page number (default: 1)
        per_page: Items per page (default: 10, max: 100)
        status: Filter by status (pending/qualified/contacted/converted)
        source: Filter by source
        sort_by: Sort field (default: created_at)
        sort_order: asc or desc (default: desc)
        min_score: Minimum qualification score
        max_score: Maximum qualification score

    Returns:
        200: List of leads with pagination info
        400: Invalid query parameters
        401: Unauthorized
    """
    try:
        # Validate pagination parameters
        pagination_schema = PaginationSchema()
        pagination_data: Dict[str, Any] = pagination_schema.load(request.args)  # type: ignore[assignment]
        
        # Validate filter parameters
        filter_schema = FilterSchema()
        filter_data: Dict[str, Any] = filter_schema.load(request.args)  # type: ignore[assignment]
        
        # Build base query
        query = Lead.query

        # ── Visibility rules by role:
        # Admin   → all leads (including null-owner legacy leads)
        # Manager → company-wide leads only
        # User    → company-wide if has company, else own leads only
        if g.role != 'admin':
            _u  = User.query.get(g.user_id)
            _co = (_u.company or '').strip().lower() if _u else ''
            if _co:
                _team_ids = [r.id for r in User.query.filter(
                    db.func.lower(db.func.trim(User.company)) == _co
                ).with_entities(User.id).all()]
                query = query.filter(Lead.collected_by.in_(_team_ids))
            else:
                query = query.filter(Lead.collected_by == g.user_id)

        # Apply filters
        if filter_data.get('status'):
            raw_status = filter_data['status']
            # Support comma-separated multi-status e.g. status=pending,low_quality
            if ',' in raw_status:
                statuses = [s.strip() for s in raw_status.split(',') if s.strip()]
                query = query.filter(Lead.status.in_(statuses))
            else:
                query = query.filter_by(status=raw_status)
        
        if filter_data.get('source'):
            query = query.filter_by(source=filter_data['source'])
        
        if filter_data.get('min_score') is not None:
            query = query.filter(Lead.qualification_score >= filter_data['min_score'])
        
        if filter_data.get('max_score') is not None:
            query = query.filter(Lead.qualification_score <= filter_data['max_score'])
        
        if filter_data.get('date_from'):
            query = query.filter(Lead.created_at >= filter_data['date_from'])
        
        if filter_data.get('date_to'):
            query = query.filter(Lead.created_at <= filter_data['date_to'])
        
        if filter_data.get('location'):
            query = query.filter(Lead.location.ilike(f"%{filter_data['location']}%"))
        
        if filter_data.get('country'):
            query = query.filter(Lead.country.ilike(f"%{filter_data['country']}%"))
        
        if filter_data.get('city'):
            query = query.filter(Lead.city.ilike(f"%{filter_data['city']}%"))
        
        if filter_data.get('industry'):
            query = query.filter(Lead.industry.ilike(f"%{filter_data['industry']}%"))
        
        if filter_data.get('product'):
            query = query.filter(Lead.product.ilike(f"%{filter_data['product']}%"))
        
        if filter_data.get('interest'):
            query = query.filter(Lead.interests.cast(db.Text).ilike(f"%{filter_data['interest']}%"))

        if filter_data.get('buying_intent'):
            query = query.filter(Lead.buying_intent == filter_data['buying_intent'])

        if filter_data.get('quality_tier'):
            tier = filter_data['quality_tier']
            # Map tier name → score range (mirrors frontend getTierFromScore)
            tier_ranges = {
                'high_quality': (80, 101),
                'qualified':    (60, 80),
                'pending':      (35, 60),
                'low_quality':  (15, 35),
            }
            if tier in tier_ranges:
                lo, hi = tier_ranges[tier]
                query = query.filter(
                    Lead.qualification_score >= lo,
                    Lead.qualification_score < hi,
                )

        if filter_data.get('verified_email'):
            # Filter leads whose email_verified flag is True in data_points JSON
            try:
                query = query.filter(
                    Lead.data_points['email_verified'].astext == 'true'
                )
            except Exception:
                pass  # Graceful fallback if JSON path not supported

        if filter_data.get('search'):
            term = f"%{filter_data['search']}%"
            query = query.filter(
                db.or_(
                    Lead.name.ilike(term),
                    Lead.email.ilike(term),
                    Lead.company.ilike(term),
                )
            )

        # Get total count before pagination
        total_count = query.count()
        
        # Apply sorting
        sort_field = getattr(Lead, pagination_data['sort_by'], Lead.created_at)
        if pagination_data['sort_order'] == 'asc':
            query = query.order_by(asc(sort_field), asc(Lead.id))  # Secondary sort by id for stability
        else:
            query = query.order_by(desc(sort_field), desc(Lead.id))  # Secondary sort by id for stability
        
        # Apply pagination
        page = pagination_data['page']
        per_page = pagination_data['per_page']
        leads = query.paginate(page=page, per_page=per_page, error_out=False).items
        
        # Serialize response
        lead_schema = LeadSchema(many=True)
        leads_data: list[dict] = lead_schema.dump(leads)  # type: ignore[assignment]

        # Merge in outcome labels from LeadOutcome table
        lead_ids = [ld['id'] for ld in leads_data]
        if lead_ids:
            outcomes = {
                lo.lead_id: lo.outcome
                for lo in LeadOutcome.query.filter(LeadOutcome.lead_id.in_(lead_ids)).all()
            }
            for ld in leads_data:
                ld['outcome'] = outcomes.get(ld['id'])

        # Batch-resolve assigned_to_name to avoid N+1 queries
        assigned_ids = {ld['assigned_to'] for ld in leads_data if ld.get('assigned_to')}
        if assigned_ids:
            assignee_map = {u.id: u.full_name for u in User.query.filter(User.id.in_(assigned_ids)).with_entities(User.id, User.full_name).all()}
            for ld in leads_data:
                ld['assigned_to_name'] = assignee_map.get(ld.get('assigned_to'))
        else:
            for ld in leads_data:
                ld['assigned_to_name'] = None

        total_pages = (total_count + per_page - 1) // per_page

        return success_response(
            message='Leads retrieved successfully',
            leads=leads_data,
            total=total_count,
            current_page=page,
            total_pages=total_pages,
            per_page=per_page,
        )
    
    except MarshmallowValidationError as e:
        details_dict = dict(e.messages) if isinstance(e.messages, dict) else {}
        raise ValidationError("Invalid query parameters", details=details_dict)


@leads_bp.route('/<int:lead_id>', methods=['GET'])
@token_required
@handle_exceptions
def get_lead(lead_id):
    """
    Get a single lead by ID
    
    Path Parameters:
        lead_id: Lead database ID
    
    Returns:
        200: Lead details
        401: Unauthorized
        404: Lead not found
    """
    lead = db.get_or_404(Lead, lead_id, description="Lead not found")

    # Ownership check by role
    if g.role == 'manager':
        _mgr = User.query.get(g.user_id)
        _co  = (_mgr.company or '').strip().lower() if _mgr else ''
        _ok  = lead.collected_by == g.user_id
        if not _ok and _co and lead.collected_by:
            _owner = User.query.get(lead.collected_by)
            _ok = (_owner is not None and (_owner.company or '').strip().lower() == _co)
        if not _ok:
            raise NotFoundError("Lead", lead_id)
    elif g.role != 'admin':
        if lead.collected_by != g.user_id:
            raise NotFoundError("Lead", lead_id)  # 404 avoids ID enumeration

    lead_schema = LeadSchema()
    lead_data: dict = lead_schema.dump(lead)  # type: ignore[assignment]
    outcome_rec = LeadOutcome.query.filter_by(lead_id=lead_id).first()
    lead_data['outcome'] = outcome_rec.outcome if outcome_rec else None
    if lead.assigned_to:
        _assignee = User.query.get(lead.assigned_to)
        lead_data['assigned_to_name'] = _assignee.full_name if _assignee else None
    else:
        lead_data['assigned_to_name'] = None

    return jsonify({
        'status': 'success',
        'message': 'Lead retrieved successfully',
        'lead': lead_data,
    }), 200


@leads_bp.route('/<int:lead_id>/assign', methods=['PATCH'])
@token_required
@handle_exceptions
def assign_lead(lead_id):
    """
    Assign or unassign a lead.
    - user    : can only claim (assign to themselves) or release their own claim
    - manager : can assign/unassign any lead visible to their company
    - admin   : full control
    Body: { "user_id": <int|null> }
    """
    json_data = request.get_json() or {}
    target_id = json_data.get('user_id')  # None = unassign

    lead = db.get_or_404(Lead, lead_id, description="Lead not found")

    # Visibility gate — same logic as get_lead
    if g.role == 'manager':
        _mgr = User.query.get(g.user_id)
        _co  = (_mgr.company or '').strip().lower() if _mgr else ''
        _ok  = lead.collected_by == g.user_id
        if not _ok and _co and lead.collected_by:
            _owner = User.query.get(lead.collected_by)
            _ok = (_owner is not None and (_owner.company or '').strip().lower() == _co)
        if not _ok:
            raise NotFoundError("Lead", lead_id)
    elif g.role != 'admin':
        # Regular user: must own or already be assigned
        if lead.collected_by != g.user_id and lead.assigned_to != g.user_id:
            raise NotFoundError("Lead", lead_id)
        # Regular user can only assign to themselves or unassign themselves
        if target_id is not None and target_id != g.user_id:
            from app.exceptions import AuthorizationError
            raise AuthorizationError("You can only claim leads for yourself")

    # Validate target user exists and is in the same company (for non-admin)
    if target_id is not None:
        target_user = User.query.get(target_id)
        if not target_user:
            raise ValidationError("Target user not found")
        if g.role not in ('admin', 'manager'):
            pass  # already validated above (can only self-assign)
        elif g.role == 'manager':
            _mgr = User.query.get(g.user_id)
            _mgr_co = (_mgr.company or '').strip().lower() if _mgr else ''
            _tgt_co = (target_user.company or '').strip().lower()
            if _mgr_co and _mgr_co != _tgt_co:
                raise ValidationError("Can only assign to users in your own company")

    lead.assigned_to = target_id
    db.session.commit()

    action = f"assigned to user {target_id}" if target_id else "unassigned"
    activity = LeadActivity(
        lead_id=lead.id,
        user_id=g.user_id,
        activity_type='updated',
        notes=f"Lead {action} by {g.email}",
    )
    db.session.add(activity)
    db.session.commit()

    assignee_name = None
    if target_id:
        _u = User.query.get(target_id)
        assignee_name = _u.full_name if _u else None

    return jsonify({
        'status': 'success',
        'message': 'Lead assigned' if target_id else 'Lead unassigned',
        'assigned_to': target_id,
        'assigned_to_name': assignee_name,
    }), 200


@leads_bp.route('/', methods=['POST'])
@limiter.limit("20 per hour")  # Create lead limit
@token_required
@handle_exceptions
def create_lead():
    """
    Create a new lead
    
    Request Body:
        {
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "+1-555-0100",
            "company": "Acme Corp",
            "position": "Manager",
            "interests": ["electronics", "smart devices"],
            "source": "website",
            "notes": "Contacted via LinkedIn"
        }
    
    Returns:
        201: Lead created
        400: Validation error
        401: Unauthorized
        500: Database error
    """
    try:
        json_data = request.get_json()
        if not json_data:
            raise ValidationError("Request body must be JSON")
        
        # Validate with creation schema (excludes read-only fields)
        schema = LeadCreateSchema()
        data: Dict[str, Any] = schema.load(json_data)  # type: ignore[assignment]
    
    except MarshmallowValidationError as e:
        details_dict = dict(e.messages) if isinstance(e.messages, dict) else {}
        raise ValidationError("Invalid lead data", details=details_dict)
    
    try:
        # Score the lead for completeness_score / email_type
        _score_result = score_lead(data)

        # Quality gate — same strict rules used by all automated collectors.
        # Rejects leads with no real contact method, generated emails, etc.
        _qd = evaluate_lead_quality(data, source=data.get('source', 'manual'))
        if not _qd.should_save:
            return jsonify({
                'status': 'error',
                'message': 'Lead rejected by quality gate',
                'reasons': _qd.reasons,
                'quality_score': round(_qd.quality_score, 1),
                'tier': _qd.tier,
            }), 422

        # Merge quality metadata into data_points before save
        _dp = data.get('data_points') or {}
        _dp.update(_qd.metadata)
        data['data_points'] = _dp

        # Company-level duplicate guard — block if a teammate already owns this lead
        _dup_lead, _dup_collector = _company_duplicate(
            data.get('email'), data.get('linkedin_url'), g.user_id
        )
        if _dup_lead:
            from app.schemas.schemas import LeadSchema as _LS
            return jsonify({
                'status':         'duplicate',
                'message':        f'This lead was already collected by {_dup_collector} in your company.',
                'existing_lead':  _LS().dump(_dup_lead),
            }), 409

        # Create new lead
        lead = Lead(
            name=data['name'],
            email=data.get('email'),
            phone=data.get('phone'),
            company=data.get('company'),
            position=data.get('position'),
            location=data.get('location'),
            country=data.get('country'),
            city=data.get('city'),
            industry=data.get('industry'),
            website=data.get('website'),
            linkedin_url=data.get('linkedin_url'),
            interests=data.get('interests', []),
            product=data.get('product'),
            qualification_score=_qd.quality_score,
            completeness_score=_score_result.completeness_score,
            email_type=_qd.metadata.get('email_type', _score_result.email_type),
            status=data.get('status', 'pending'),
            source=data.get('source', 'manual'),
            notes=data.get('notes'),
            data_points=_dp,
            collected_by=g.user_id,
        )

        db.session.add(lead)
        db.session.commit()
        
        # Log activity
        activity = LeadActivity(
            lead_id=lead.id,
            user_id=g.user_id,
            activity_type='created',
            notes=f"Lead created by user {g.email}"
        )
        db.session.add(activity)
        db.session.commit()
        
        logger.info(f"New lead created: {lead.email} by user {g.email}")

        # Email notifications — fire-and-forget in background thread
        try:
            from app.routes.settings import _get_user_settings
            from app.services.email_service import send_new_lead_notification, send_high_quality_alert
            import threading
            _user_email = g.email
            _prefs      = _get_user_settings(g.user_id)
            _score      = float(lead.qualification_score or 0)
            _lname      = lead.name or ''
            _company    = lead.company or ''
            _source     = lead.source or 'manual'
            _position   = lead.position or ''
            def _send_lead_emails():
                if _prefs.get('notify_new_leads'):
                    send_new_lead_notification(_user_email, _lname, _company, _score, _source)
                if _prefs.get('notify_high_quality') and _score >= 80:
                    send_high_quality_alert(_user_email, _lname, _company, _score, _position)
            threading.Thread(target=_send_lead_emails, daemon=True).start()
        except Exception as _ne:
            logger.debug(f'[leads] email notification skipped: {_ne}')

        # Auto-enrich: fill missing fields via AI if the setting is enabled
        try:
            from app.routes.settings import _get_user_settings as _gus_ae
            if _gus_ae(g.user_id).get('auto_enrich_leads') and lead.email:
                import threading as _th_ae
                _lead_id_ae  = lead.id
                _app_ctx_ae  = current_app.app_context()
                def _do_enrich():
                    try:
                        with _app_ctx_ae:
                            from app.models.models import db as _db_ae, Lead as _Lead_ae
                            from app.services.gemini_service import get_ai_service as _get_ai_ae
                            _lae = _db_ae.session.get(_Lead_ae, _lead_id_ae)
                            if not _lae:
                                return
                            _enriched = _get_ai_ae().enrich_lead({
                                'name': _lae.name or '', 'email': _lae.email or '',
                                'company': _lae.company or '', 'position': _lae.position or '',
                                'industry': _lae.industry or '', 'website': _lae.website or '',
                                'country': _lae.country or '',
                            })
                            _updated: dict = {}
                            if _enriched.get('company') and not _lae.company:
                                _lae.company = _enriched['company'][:255]; _updated['company'] = _lae.company
                            if _enriched.get('industry') and not _lae.industry:
                                _lae.industry = _enriched['industry']; _updated['industry'] = _lae.industry
                            if _enriched.get('position') and not _lae.position:
                                _lae.position = _enriched['position']; _updated['position'] = _lae.position
                            if _enriched.get('country') and not _lae.country:
                                _lae.country = _enriched['country']; _updated['country'] = _lae.country
                            if not _lae.location and (_lae.city or _lae.country):
                                _lae.location = ', '.join(p for p in [_lae.city, _lae.country] if p)
                                _updated['location'] = _lae.location
                            if _updated:
                                _db_ae.session.commit()
                                logger.info('[leads] auto-enrich filled %s for lead %d', list(_updated.keys()), _lead_id_ae)
                    except Exception as _ae_err:
                        logger.debug('[leads] auto-enrich thread error: %s', _ae_err)
                _th_ae.Thread(target=_do_enrich, daemon=True).start()
        except Exception as _ae2:
            logger.debug('[leads] auto-enrich skipped: %s', _ae2)

        _name = lead.name or lead.email or 'New contact'
        _push(g.user_id, f'New lead — {_name}',
              f"{lead.company or ''} · {lead.position or 'Unknown role'}".strip(' ·'),
              {'type': 'new_lead', 'lead_id': str(lead.id)})
        track_lead_operation(operation="created", lead_id=lead.id)
        track_database_query(query_type="insert", duration=0.0)
        
        lead_schema = LeadSchema()
        lead_data = lead_schema.dump(lead)
        
        return success_response(
            message='Lead created successfully',
            status_code=201,
            lead=lead_data,
        )
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Lead creation error: {str(e)}")
        track_lead_operation(operation="created")
        track_error("lead_creation_error")
        raise DatabaseError("Failed to create lead")


@leads_bp.route('/<int:lead_id>', methods=['PUT'])
@limiter.limit("20 per hour")  # Update lead limit
@token_required
@handle_exceptions
def update_lead(lead_id):
    """
    Update a lead
    
    Path Parameters:
        lead_id: Lead database ID
    
    Request Body:
        {
            "name": "John Smith",
            "status": "qualified",
            "qualification_score": 85.0
            # All fields optional, only provided fields are updated
        }
    
    Returns:
        200: Lead updated
        400: Validation error
        401: Unauthorized
        404: Lead not found
        500: Database error
    """
    try:
        json_data = request.get_json()
        if not json_data:
            raise ValidationError("Request body must be JSON")
        
        schema = LeadUpdateSchema()
        data: Dict[str, Any] = schema.load(json_data)  # type: ignore[assignment]
    
    except MarshmallowValidationError as e:
        details_dict = dict(e.messages) if isinstance(e.messages, dict) else {}
        raise ValidationError("Invalid update data", details=details_dict)
    
    lead = db.get_or_404(Lead, lead_id, description="Lead not found")

    # Ownership check outside try/except so NotFoundError propagates correctly (not swallowed as 500)
    if g.role != 'admin':
        owns       = lead.collected_by == g.user_id
        null_web   = lead.collected_by is None and lead.origin != 'mobile'
        is_assignee = lead.assigned_to == g.user_id
        if not owns and not null_web and not is_assignee:
            raise NotFoundError("Lead", lead_id)

    try:
        # Update only provided fields
        if 'name' in data and data['name']:
            lead.name = data['name']
        if 'email' in data and data['email']:
            lead.email = data['email']
        if 'phone' in data:
            lead.phone = data['phone']
        if 'company' in data:
            lead.company = data['company']
        if 'position' in data:
            lead.position = data['position']
        if 'location' in data:
            lead.location = data['location']
        if 'interests' in data and data['interests']:
            lead.interests = data['interests']
        if 'product' in data:
            lead.product = data['product']
        if 'qualification_score' in data and data['qualification_score'] is not None:
            lead.qualification_score = data['qualification_score']
        if 'status' in data and data['status']:
            new_status = data['status']
            old_status = lead.status
            lead.status = new_status
            # Feed status change into ML dataset labeling
            if new_status != old_status:
                try:
                    from app.services.ml_decision_layer import get_decision_layer
                    get_decision_layer().on_lead_status_change(lead.id, new_status)
                except Exception as _dl_err:
                    logger.warning(f"ML dataset label update failed: {_dl_err}")
        if 'country' in data:
            lead.country = data['country']
        if 'city' in data:
            lead.city = data['city']
        if 'industry' in data:
            lead.industry = data['industry']
        if 'website' in data:
            lead.website = data['website']
        if 'linkedin_url' in data:
            lead.linkedin_url = data['linkedin_url']
        if 'notes' in data:
            lead.notes = data['notes']
        
        db.session.commit()
        
        # Log activity
        activity = LeadActivity(
            lead_id=lead.id,
            user_id=g.user_id,
            activity_type='updated',
            notes=f"Lead updated by user {g.email}"
        )
        db.session.add(activity)
        db.session.commit()
        
        logger.info(f"Lead updated: {lead.email} by user {g.email}")
        track_lead_operation(operation="updated", lead_id=lead_id)
        track_database_query(query_type="update", duration=0.0)
        
        lead_schema = LeadSchema()
        lead_data = lead_schema.dump(lead)
        
        return jsonify({
            'status': 'success',
            'message': 'Lead updated successfully',
            'lead': lead_data,
        }), 200
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Lead update error: {str(e)}") 
        track_lead_operation(operation="updated")
        track_error("lead_update_error")
        raise DatabaseError("Failed to update lead")


@leads_bp.route('/<int:lead_id>', methods=['DELETE'])
@limiter.limit("20 per hour")  # Delete lead limit
@token_required
@handle_exceptions
def delete_lead(lead_id):
    """
    Delete a lead
    
    Path Parameters:
        lead_id: Lead database ID
    
    Returns:
        200: Lead deleted
        401: Unauthorized
        404: Lead not found
        500: Database error
    """
    lead = db.get_or_404(Lead, lead_id, description="Lead not found")

    # Ownership check outside try/except so NotFoundError propagates correctly (not swallowed as 500)
    if g.role != 'admin' and lead.collected_by != g.user_id:
        raise NotFoundError("Lead", lead_id)

    try:
        # Delete child activities first to avoid FK constraint violation
        LeadActivity.query.filter_by(lead_id=lead.id).delete()
        db.session.delete(lead)
        db.session.commit()
        
        logger.info(f"Lead deleted: {lead_id} by user {g.email}")
        track_lead_operation(operation="deleted")
        track_database_query(query_type="delete", duration=0.0)
        
        return jsonify({
            'status': 'success',
            'message': 'Lead deleted successfully',
        }), 200
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Lead deletion error: {str(e)}")
        track_lead_operation(operation="deleted")
        track_error("lead_deletion_error")
        raise DatabaseError("Failed to delete lead")


@leads_bp.route('/all', methods=['DELETE'])
@limiter.limit("5 per hour")
@token_required
@admin_required
@handle_exceptions
def delete_all_leads():
    """
    Delete ALL leads from the database (reset to zero).
    Admin only.
    
    Returns:
        200: All leads deleted with count
        500: Database error
    """
    try:
        count = Lead.query.count()
        
        # Delete all activities first (foreign key)
        LeadActivity.query.delete()
        Lead.query.delete()
        db.session.commit()
        
        logger.info(f"All {count} leads deleted by user {g.email}")
        track_lead_operation(operation="bulk_deleted")
        track_database_query(query_type="delete", duration=0.0)
        
        return jsonify({
            'status': 'success',
            'message': f'All {count} leads deleted successfully',
            'deleted_count': count,
        }), 200
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bulk delete error: {str(e)}")
        track_error("bulk_delete_error")
        raise DatabaseError("Failed to delete all leads")


@leads_bp.route('/clear', methods=['POST'])
@limiter.limit("5 per hour")
@token_required
@admin_required
@handle_exceptions
def clear_all_leads():
    """Clear all leads (POST alias for DELETE /all)."""
    try:
        count = Lead.query.count()
        LeadActivity.query.delete()
        Lead.query.delete()
        db.session.commit()
        logger.info(f"All {count} leads cleared by user {g.email}")
        return jsonify({'status': 'success', 'message': f'All {count} leads cleared', 'deleted_count': count}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Clear leads error: {str(e)}")
        raise DatabaseError("Failed to clear leads")


@leads_bp.route('/search', methods=['GET'])
@token_required
@handle_exceptions
def search_leads():
    """
    Search leads by name or email
    
    Query Parameters:
        query: Search query string (required)
        limit: Number of results (default: 10, max: 50)
        offset: Results offset (default: 0)
    
    Returns:
        200: Search results
        400: Missing or invalid query
        401: Unauthorized
    """
    try:
        search_schema = SearchSchema()
        params: Dict[str, Any] = search_schema.load(request.args)  # type: ignore[assignment]
    
    except MarshmallowValidationError as e:
        details_dict = dict(e.messages) if isinstance(e.messages, dict) else {}
        raise ValidationError("Invalid search parameters", details=details_dict)
    
    query_str = params['query']
    limit = params.get('limit', 10)
    offset = params.get('offset', 0)

    # Escape LIKE wildcards so user input is treated as a literal string,
    # not a pattern (prevents unexpected broad matches via % or _).
    escaped = query_str.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

    # Full-text search on name, email, company, country, industry
    search_results = Lead.query.filter(
        or_(
            Lead.name.ilike(f'%{escaped}%'),
            Lead.email.ilike(f'%{escaped}%'),
            Lead.company.ilike(f'%{escaped}%'),
            Lead.country.ilike(f'%{escaped}%'),
            Lead.industry.ilike(f'%{escaped}%'),
            Lead.city.ilike(f'%{escaped}%'),
        )
    ).limit(limit).offset(offset).all()
    
    lead_schema = LeadSchema(many=True)
    leads_data = lead_schema.dump(search_results)
    
    logger.info(f"Search performed: {query_str} by user {g.email}")
    
    return jsonify({
        'status': 'success',
        'message': 'Search completed successfully',
        'leads': leads_data,
        'count': len(leads_data),
        'query': query_str,
    }), 200


@leads_bp.route('/stats', methods=['GET'])
@token_required
@handle_exceptions
def get_stats():
    """
    Get lead statistics and analytics

    Returns:
        200: Statistics data
        401: Unauthorized
    """
    try:
        # Local helper — same RBAC rules as the leads list endpoint
        def _own(q):
            if g.role == 'admin':
                return q
            _u  = User.query.get(g.user_id)
            _co = (_u.company or '').strip().lower() if _u else ''
            if _co:
                _tids = [r.id for r in User.query.filter(
                    db.func.lower(db.func.trim(User.company)) == _co
                ).with_entities(User.id).all()]
                return q.filter(Lead.collected_by.in_(_tids))
            return q.filter(Lead.collected_by == g.user_id)

        base_query = _own(Lead.query)

        total_leads     = base_query.count()
        # Qualified = score >= 60, matching analytics.py QUALIFIED_SCORE_THRESHOLD
        qualified_leads = base_query.filter(Lead.qualification_score >= 60).count()
        hot_leads       = base_query.filter(Lead.status == 'hot').count()
        warm_leads      = base_query.filter(Lead.status == 'warm').count()
        cold_leads      = base_query.filter(Lead.status == 'cold').count()
        contacted_leads = base_query.filter(Lead.status == 'contacted').count()
        converted_leads = base_query.filter(Lead.status == 'converted').count()
        pending_leads   = base_query.filter(Lead.status == 'pending').count()

        avg_score = (
            _own(db.session.query(db.func.avg(Lead.qualification_score)))
            .filter(Lead.qualification_score > 0)
            .scalar() or 0
        )

        # Leads by source
        sources_data = {
            str(src): cnt for src, cnt in
            _own(db.session.query(Lead.source, db.func.count(Lead.id)))
            .filter(Lead.source.isnot(None))
            .group_by(Lead.source).all()
        }

        # Leads by country
        countries_data = {
            country: cnt for country, cnt in
            _own(db.session.query(Lead.country, db.func.count(Lead.id)))
            .filter(Lead.country.isnot(None), Lead.country != '')
            .group_by(Lead.country).order_by(db.func.count(Lead.id).desc()).all()
        }

        # Leads by industry
        industries_data = {
            industry: cnt for industry, cnt in
            _own(db.session.query(Lead.industry, db.func.count(Lead.id)))
            .filter(Lead.industry.isnot(None), Lead.industry != '')
            .group_by(Lead.industry).order_by(db.func.count(Lead.id).desc()).all()
        }

        # New leads this week
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        new_this_week = base_query.filter(Lead.created_at >= week_ago).count()

        # Score distribution buckets (only scored leads)
        score_ranges = [
            ('0-20',  0,  20),
            ('21-40', 21, 40),
            ('41-60', 41, 60),
            ('61-80', 61, 80),
            ('81-100', 81, 100),
        ]
        score_dist = {}
        for label, low, high in score_ranges:
            count = base_query.filter(
                Lead.qualification_score >= low,
                Lead.qualification_score <= high,
            ).count()
            score_dist[label] = count

        logger.info(f"Stats retrieved by user {g.email}")

        return jsonify({
            'status': 'success',
            'message': 'Statistics retrieved successfully',
            'stats': {
                'total_leads': total_leads,
                'qualified_leads': qualified_leads,
                'hot_leads': hot_leads,
                'warm_leads': warm_leads,
                'cold_leads': cold_leads,
                'contacted_leads': contacted_leads,
                'pending_leads': pending_leads,
                'avg_score': float(avg_score),
                'by_source': sources_data,
                'by_country': countries_data,
                'by_industry': industries_data,
                'by_score_range': score_dist,
                'converted_leads': converted_leads,
                'new_this_week': new_this_week,
                'qualification_rate': round((qualified_leads / total_leads * 100), 2) if total_leads > 0 else 0,
                'conversion_rate': round((converted_leads / total_leads * 100), 2) if total_leads > 0 else 0,
            },
        }), 200

    except Exception as e:
        logger.error(f"Stats retrieval error: {str(e)}")
        raise DatabaseError("Failed to retrieve statistics")


@leads_bp.route('/export', methods=['GET'])
@limiter.limit("10 per hour")
@token_required
@handle_exceptions
def export_leads_csv():
    """Export all leads matching current filters as a CSV file."""

    # ── CSV cell helpers ──────────────────────────────────────────────────────
    def _s(v):
        """Standard quoted text cell."""
        if v is None or v == '':
            return '""'
        return '"' + str(v).replace('"', '""') + '"'

    def _n(v):
        """Numeric cell — unquoted integer/float so Excel sorts correctly."""
        if v is None or v == '':
            return ''
        try:
            f = float(v)
            return str(int(f)) if f == int(f) else str(round(f, 1))
        except (ValueError, TypeError):
            return _s(v)

    def _phone(v):
        """Phone cell using Excel formula trick to prevent scientific notation.
        ="{digits}" in a cell forces Excel to treat it as text, not 1.42E+10."""
        if not v:
            return '""'
        formula = '="' + str(v) + '"'
        return '"' + formula.replace('"', '""') + '"'

    def _date(v):
        """Date as DD-Mon-YYYY text (e.g. 24-Jun-2026).
        Avoids Excel auto-converting ISO strings to date type (which causes ########)."""
        if not v:
            return '""'
        try:
            if isinstance(v, str):
                v = datetime.fromisoformat(v.replace('Z', '+00:00'))
            return '"' + v.strftime('%d-%b-%Y') + '"'
        except Exception:
            return _s(str(v))

    def _lead_row(lead):
        """Build one CSV row — works for both SQLAlchemy objects and plain dicts."""
        get = (lambda k, d='': getattr(lead, k, d)) if hasattr(lead, 'qualification_score') \
              else (lambda k, d='': lead.get(k, d))

        interests = get('interests') or []
        if not isinstance(interests, list):
            interests = []

        return ','.join([
            _s(get('id')),
            _s(get('name')),
            _s(get('email')),
            _phone(get('phone')),
            _s(get('company')),
            _s(get('position')),
            _s(get('industry')),
            _s(get('country')),
            _s(get('city')),
            _s(get('website')),
            _s(get('linkedin_url')),
            _n(get('qualification_score')),
            _s(get('status')),
            _s(get('source')),
            _s(get('email_type')),
            _s('; '.join(interests)),
            _date(get('created_at')),
        ])

    HEADERS = [
        'ID', 'Name', 'Email', 'Phone', 'Company', 'Position',
        'Industry', 'Country', 'City', 'Website', 'LinkedIn',
        'Score', 'Status', 'Source', 'Email Type', 'Interests',
        'Date Added',
    ]
    header_line = ','.join(f'"{h}"' for h in HEADERS)

    # ── Real data with all active filters ────────────────────────────────
    query = Lead.query

    # Apply the same company/role scoping as the leads list endpoint:
    # admin → all leads; non-admin with company → company-wide; else → own leads only
    if g.role != 'admin':
        _u  = User.query.get(g.user_id)
        _co = (_u.company or '').strip().lower() if _u else ''
        if _co:
            _team_ids = [r.id for r in User.query.filter(
                db.func.lower(db.func.trim(User.company)) == _co
            ).with_entities(User.id).all()]
            query = query.filter(Lead.collected_by.in_(_team_ids))
        else:
            query = query.filter(Lead.collected_by == g.user_id)

    status = (request.args.get('status') or '').strip()
    if status:
        if ',' in status:
            query = query.filter(Lead.status.in_([s.strip() for s in status.split(',') if s.strip()]))
        else:
            query = query.filter_by(status=status)

    interest = (request.args.get('interest') or '').strip()
    if interest:
        query = query.filter_by(interest_level=interest)

    source = (request.args.get('source') or '').strip()
    if source:
        query = query.filter_by(source=source)

    country = (request.args.get('country') or '').strip()
    if country:
        query = query.filter_by(country=country)

    industry = (request.args.get('industry') or '').strip()
    if industry:
        query = query.filter_by(industry=industry)

    for param, col in [('min_score', 'gte'), ('max_score', 'lte')]:
        val = request.args.get(param)
        if val:
            try:
                fval = float(val)
                if col == 'gte':
                    query = query.filter(Lead.qualification_score >= fval)
                else:
                    query = query.filter(Lead.qualification_score <= fval)
            except ValueError:
                pass

    q = (request.args.get('q') or '').strip()
    if q:
        pattern = f'%{q}%'
        query = query.filter(or_(
            Lead.name.ilike(pattern),
            Lead.email.ilike(pattern),
            Lead.company.ilike(pattern),
        ))

    leads_list = query.order_by(Lead.created_at.desc()).all()
    mode_tag   = ''

    # ── Assemble and respond ──────────────────────────────────────────────────
    lines     = [header_line] + [_lead_row(lead) for lead in leads_list]
    csv_text  = '\r\n'.join(lines) + '\r\n'
    csv_bytes = ('﻿' + csv_text).encode('utf-8')  # UTF-8 BOM for Excel

    date_tag  = datetime.now(timezone.utc).strftime('%Y%m%d')
    filename  = f'OrionLead_Export_{mode_tag}{date_tag}.csv'

    response = make_response(csv_bytes)
    response.headers['Content-Type']        = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    logger.info("CSV export: %d leads by %s", len(leads_list), g.email)
    return response


@leads_bp.route('/<int:lead_id>/qualify', methods=['POST'])
@limiter.limit("20 per hour")
@token_required
@handle_exceptions
def qualify_lead(lead_id):
    """
    🤖 AI-POWERED: Qualify a lead using intelligent multi-criteria analysis
    
    Path Parameters:
        lead_id: Lead database ID
    
    Request Body (optional):
        {
            "force_requalify": false,
            "return_explanation": true
        }
    
    Returns:
        200: Lead qualification with AI score (0-100)
        
    Response Example:
        {
            "message": "Lead qualified by AI",
            "lead_id": 1,
            "score": 85.5,
            "category": "hot",
            "confidence": 0.89,
            "recommendations": [
                "🔥 PRIORITY: Contact immediately",
                "Prepare customized demo..."
            ]
        }
    """
    try:
        json_data = request.get_json() or {}
        force_requalify = json_data.get('force_requalify', False)
        return_explanation = json_data.get('return_explanation', False)
        
        lead = db.get_or_404(Lead, lead_id, description="Lead not found")
        
        if lead.qualification_score is not None and not force_requalify:
            return jsonify({
                'status': 'success',
                'message': 'Lead already qualified',
                'lead_id': lead.id,
                'score': lead.qualification_score,
                'category': _score_to_category(lead.qualification_score),
                'previously_qualified': True
            }), 200
        
        # Prepare lead data for AI qualification
        lead_data = {
            'id': lead.id,
            'name': lead.name,
            'email': lead.email,
            'phone': lead.phone,
            'company': lead.company,
            'position': lead.position,
            'interests': lead.interests,
            'notes': lead.notes,
        }
        
        # Run AI qualification
        start_time = time()
        result = qualification_agent.qualify_lead(lead_data)
        duration = time() - start_time
        
        # Update lead — status tracks the actual AI category so leads leave the pending queue
        lead.qualification_score = result.score
        lead.status = result.category  # 'hot', 'warm', 'cold', or 'unqualified'

        # Sync quality_tier in data_points so the UI Quality badge reflects the new score
        dp = dict(lead.data_points or {})
        dp['quality_tier'] = _score_to_quality_tier(result.score)
        lead.data_points = dp

        # Store AI metadata
        qual_note = f"\n[AI-QUALIFIED {result.analyzed_at}]: Score={result.score}/100, Category={result.category.upper()}, Confidence={result.confidence*100:.0f}%"
        lead.notes = (lead.notes or '') + qual_note
        
        db.session.commit()
        
        # Log activity
        activity = LeadActivity(
            lead_id=lead.id,
            user_id=g.user_id,
            activity_type='qualified',
            notes=f"AI qualification: {result.category.upper()} (score: {result.score})"
        )
        db.session.add(activity)
        db.session.commit()
        
        logger.info(f"Lead {lead_id} AI-qualified: score={result.score}, category={result.category}, duration={duration:.2f}s")
        _emoji = '🔥' if result.category == 'hot' else ('⚡' if result.category == 'warm' else '❄️')
        _push(g.user_id, f'{_emoji} {result.score}/100 — {(lead.name or lead.email)}',
              f"{result.category.upper()} lead · {lead.company or lead.position or 'No company'}",
              {'type': 'lead_scored', 'lead_id': str(lead_id), 'score': str(result.score)})
        track_qualification(agent_name='lead_qualification_agent', status='success', duration=duration)
        
        response_data = {
            'status': 'success',
            'message': '🤖 AI Lead Qualification Complete',
            'lead_id': result.lead_id,
            'score': result.score,
            'category': result.category,
            'confidence': result.confidence,
            'recommendations': result.recommendations,
            'analysis_duration_seconds': round(duration, 2),
        }
        
        if return_explanation:
            response_data['reasoning'] = result.reasoning
            response_data['explanation'] = qualification_agent.explain_score(result)
        
        return jsonify(response_data), 200
    
    except Exception as e:
        logger.error(f"AI qualification error: {str(e)}")
        track_qualification(agent_name='lead_qualification_agent', status='failed', duration=0)
        track_error('ai_qualification_error')
        raise DatabaseError("Failed to qualify lead")


@leads_bp.route('/batch-qualify', methods=['POST'])
@limiter.limit("30 per hour")
@token_required
@handle_exceptions
def batch_qualify_leads():
    """
    🤖 AI-POWERED: Batch qualify multiple leads with AI scoring
    
    Request Body:
        {
            "lead_ids": [1, 2, 3, 4, 5],
            "return_explanations": false
        }
    
    Returns:
        200: Batch qualification results with statistics
        
    Response Example:
        {
            "message": "Batch AI qualification completed",
            "stats": {
                "total": 5,
                "qualified": 5,
                "hot": 2,
                "warm": 2,
                "cold": 1,
                "duration_seconds": 3.45
            },
            "results": [...]
        }
    """
    try:
        json_data = request.get_json()
        if not json_data:
            raise ValidationError("Request body must be JSON")
        
        lead_ids = json_data.get('lead_ids', [])
        if not lead_ids or not isinstance(lead_ids, list):
            raise ValidationError("lead_ids must be a non-empty array")
        
        if len(lead_ids) > 100:
            raise ValidationError("Maximum 100 leads per batch")
        
        leads = Lead.query.filter(Lead.id.in_(lead_ids)).all()
        if not leads:
            raise NotFoundError("Leads")
        
        # Prepare data
        leads_data = []
        for lead in leads:
            leads_data.append({
                'id': lead.id,
                'name': lead.name,
                'email': lead.email,
                'phone': lead.phone,
                'company': lead.company,
                'position': lead.position,
                'interests': lead.interests,
                'notes': lead.notes,
            })
        
        # Batch qualify
        start_time = time()
        results = qualification_agent.batch_qualify(leads_data)
        duration = time() - start_time
        
        # Update leads and track stats
        categories = {'hot': 0, 'warm': 0, 'cold': 0, 'unqualified': 0}
        
        for lead, result in zip(leads, results):
            if result:
                lead.qualification_score = result.score
                lead.status = result.category  # 'hot', 'warm', 'cold', or 'unqualified'
                dp = dict(lead.data_points or {})
                dp['quality_tier'] = _score_to_quality_tier(result.score)
                lead.data_points = dp
                categories[result.category] += 1
                
                activity = LeadActivity(
                    lead_id=lead.id,
                    user_id=g.user_id,
                    activity_type='qualified',
                    notes=f"Batch AI qualification: {result.category.upper()} (score: {result.score})"
                )
                db.session.add(activity)
        
        db.session.commit()
        
        logger.info(f"Batch AI qualification: {len(results)} leads in {duration:.2f}s")
        hot = sum(1 for r in results if r and r.category == 'hot')
        _push(g.user_id, f'🔥 {hot} hot leads found',
              f"{len(results)} leads scored · tap to review",
              {'type': 'batch_scored', 'total': str(len(results)), 'hot': str(hot)})
        track_qualification(agent_name='batch_qualification_agent', status='success', duration=duration)
        
        response_results = [
            {
                'lead_id': r.lead_id,
                'score': r.score,
                'category': r.category,
                'confidence': r.confidence,
            }
            for r in results if r
        ]
        
        return jsonify({
            'status': 'success',
            'message': '🤖 Batch AI Qualification Complete',
            'stats': {
                'total': len(leads),
                'qualified': len([r for r in results if r]),
                'hot': categories['hot'],
                'warm': categories['warm'],
                'cold': categories['cold'],
                'unqualified': categories['unqualified'],
                'duration_seconds': round(duration, 2)
            },
            'results': response_results
        }), 200
    
    except Exception as e:
        logger.error(f"Batch qualification error: {str(e)}")
        track_error('batch_ai_qualification_error')
        raise DatabaseError("Failed to process batch qualification")


def _score_to_category(score: float) -> str:
    """Convert qualification score to category using shared thresholds."""
    from app.services.ml_decision_layer import SCORE_HOT, SCORE_WARM
    if score >= SCORE_HOT:
        return 'hot'
    elif score >= SCORE_WARM:
        return 'warm'
    elif score >= 40:
        return 'cold'
    else:
        return 'unqualified'


def _score_to_quality_tier(score: float) -> str:
    """Map a qualification score to the quality_tier stored in data_points."""
    if score >= 80:
        return 'high_quality'
    if score >= 60:
        return 'qualified'
    if score >= 35:
        return 'pending'
    if score >= 15:
        return 'low_quality'
    return 'rejected'


@leads_bp.route('/cleanup', methods=['POST'])
@limiter.limit("5 per hour")
@token_required
@handle_exceptions
def cleanup_old_leads():
    """Delete leads older than data_retention_days for the current user (min 30 days). auto_delete_old_data must be enabled."""
    from app.routes.settings import _get_user_settings
    prefs = _get_user_settings(g.user_id)

    if not prefs.get('auto_delete_old_data'):
        return jsonify({
            'status': 'error',
            'message': "Auto-delete is disabled. Enable 'Automatically delete old data' in Settings → Data Collection first.",
        }), 400

    retention_days = max(int(prefs.get('data_retention_days') or 90), 30)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    query = Lead.query.filter(Lead.created_at < cutoff)
    if g.role != 'admin':
        query = query.filter(Lead.collected_by == g.user_id)

    leads_to_delete = query.all()
    count = len(leads_to_delete)

    if count == 0:
        return jsonify({
            'status': 'success',
            'message': f'No leads older than {retention_days} days found.',
            'deleted_count': 0,
            'cutoff_date': cutoff.strftime('%Y-%m-%d'),
        }), 200

    lead_ids = [ld.id for ld in leads_to_delete]
    LeadActivity.query.filter(LeadActivity.lead_id.in_(lead_ids)).delete(synchronize_session=False)
    query.delete(synchronize_session=False)
    db.session.commit()

    logger.info(f"[leads] cleanup: deleted {count} leads older than {retention_days}d for user {g.email}")
    return jsonify({
        'status': 'success',
        'message': f'Deleted {count} lead(s) older than {retention_days} days.',
        'deleted_count': count,
        'cutoff_date': cutoff.strftime('%Y-%m-%d'),
    }), 200


@leads_bp.route('/enrich', methods=['POST'])
@limiter.limit("10 per minute")  # Enrichment is API-heavy
@token_required
@handle_exceptions
def enrich_leads():
    """
    Enrich leads with real data from Clearbit
    
    Request Body:
        lead_ids: List of lead IDs to enrich (optional, default: all)
        
    Returns:
        200: Enrichment results with company data
        400: Bad request or Clearbit not configured
    """
    try:
        from datetime import datetime
        
        # Check if Clearbit is configured
        if not is_clearbit_configured():
            return jsonify({
                'error': 'Clearbit not configured',
                'message': 'Set CLEARBIT_API_KEY environment variable',
                'status': 'unconfigured'
            }), 400
        
        # Get request data
        data = request.get_json() or {}
        lead_ids = data.get('lead_ids', [])
        
        # Query leads to enrich
        if lead_ids:
            leads = Lead.query.filter(Lead.id.in_(lead_ids)).all()
        else:
            # Enrich first 5 leads (free tier is limited)
            leads = Lead.query.filter(Lead.company.ilike('%Inc%') | Lead.company.ilike('%Corp%')).limit(5).all()
        
        if not leads:
            return jsonify({'status': 'success', 'message': 'No leads to enrich', 'enriched': 0}), 200
        
        clearbit = get_clearbit_client()
        enriched_count = 0
        results = []
        
        for lead in leads:
            try:
                # Skip if no email
                if not lead.email:
                    continue
                
                # Enrich lead
                enrichment = clearbit.enrich_lead({
                    'email':   lead.email,
                    'company': lead.company or '',
                    'name':    lead.name or '',
                })
                
                # Update lead with company data
                if enrichment.get('company'):
                    company_info = enrichment['company']
                    
                    # Update lead fields
                    lead.company = company_info.get('company_name') or lead.company
                    lead.data_points = lead.data_points or {}
                    
                    # Store enrichment metadata
                    lead.data_points['clearbit_enrichment'] = {
                        'industry': company_info.get('industry'),
                        'company_size': company_info.get('company_size'),
                        'funding_stage': company_info.get('funding_stage'),
                        'founded_year': company_info.get('founded_year'),
                        'tech_stack': company_info.get('tech_stack', []),
                        'location': company_info.get('location'),
                        'enriched_at': datetime.now(timezone.utc).isoformat()
                    }
                    
                    # Add interests from tech stack
                    if company_info.get('tech_stack'):
                        current_interests = lead.interests or []
                        if isinstance(current_interests, str):
                            current_interests = [current_interests]
                        
                        # Add tech stack items as interests
                        tech_interests = set(current_interests)
                        tech_interests.update(company_info.get('tech_stack', []))
                        lead.interests = list(tech_interests)[:10]  # Keep top 10
                    
                    enriched_count += 1
                    results.append({
                        'lead_id': lead.id,
                        'name': lead.name,
                        'email': lead.email,
                        'company': lead.company,
                        'industry': company_info.get('industry'),
                        'location': company_info.get('location'),
                        'tech_stack': company_info.get('tech_stack', []),
                        'status': 'enriched'
                    })
                
            except Exception as e:
                logger.error(f"Failed to enrich lead {lead.id}: {str(e)}")
                results.append({
                    'lead_id': lead.id,
                    'name': lead.name,
                    'status': 'error',
                    'error': str(e)
                })
        
        # Save enriched leads
        if enriched_count > 0:
            db.session.commit()
            logger.info(f"✅ Enriched {enriched_count} leads with Clearbit data")
        
        return jsonify({
            'status': 'success',
            'message': 'Lead enrichment complete',
            'enriched': enriched_count,
            'total': len(leads),
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Enrichment error: {str(e)}")
        track_error('lead_enrichment_error')
        raise DatabaseError("Failed to enrich leads")
