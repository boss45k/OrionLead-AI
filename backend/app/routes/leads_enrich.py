

"""
Lead enrichment routes using Clearbit API
Enriches lead data with company information and tech stack
"""

from flask import Blueprint, jsonify, request
from datetime import datetime
import logging

from app.models.models import db, Lead
from app.exceptions import DatabaseError
from app.routes.auth import token_required
from app.utils.error_handler import handle_exceptions
from app.utils.rate_limiter import get_limiter
from app.utils.metrics import track_error
from app.services.clearbit_service import get_clearbit_client, is_clearbit_configured

logger = logging.getLogger(__name__)

leads_bp = Blueprint('leads_enrich', __name__, url_prefix='/api/v1/leads')
limiter = get_limiter()


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
        401: Unauthorized
    """
    try:
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
            # Enrich all leads (max 10 per request for rate limiting)
            leads = Lead.query.limit(10).all()
        
        if not leads:
            return jsonify({'message': 'No leads to enrich', 'enriched': 0}), 200
        
        clearbit = get_clearbit_client()
        enriched_count = 0
        results = []
        
        for lead in leads:
            try:
                # Skip if no email
                if not lead.email:
                    continue
                
                # Enrich lead
                enrichment = clearbit.enrich_lead(
                    email=lead.email,
                    domain=lead.company if lead.company else None
                )
                
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
                        'enriched_at': datetime.utcnow().isoformat()
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
            logger.info(f"Enriched {enriched_count} leads with Clearbit data")
        
        return jsonify({
            'message': 'Lead enrichment complete',
            'enriched': enriched_count,
            'total': len(leads),
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Enrichment error: {str(e)}")
        track_error('lead_enrichment_error')
        raise DatabaseError("Failed to enrich leads")
