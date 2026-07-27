"""
Agent API Routes
REST endpoints for agent operations
"""

from flask import Blueprint, request, jsonify
import logging
import uuid

from app.agents.base_agent import AgentStatus
from app.agents.config import AgentType
from app.agents.agent_registry import AgentRegistry
from app.agents.agent_pool import get_agent_pool
from app.agents.query_agent import QueryAgent
from app.agents.exceptions import (
    AgentException,
    AgentNotFoundError,
)
from app.exceptions import APIException, ValidationError
from app.routes.auth import token_required, admin_required
from app.utils.error_handler import handle_exceptions, validate_request_json
from app.utils.rate_limiter import get_limiter

agents_bp = Blueprint('agents', __name__, url_prefix='/api/v1/agents')
logger = logging.getLogger(__name__)
limiter = get_limiter()

# Initialize registry and register agents
registry = AgentRegistry()


def _register_agents():
    """Register all available agents"""
    try:
        # QualificationAgent is available via services layer (see leads routes)
        # Only register QueryAgent which uses LLM
        registry.register_agent(AgentType.QUERY, QueryAgent)
        logger.info("Agents registered successfully (QueryAgent)")
    except Exception as e:
        logger.error(f"Failed to register agents: {str(e)}")


# Register agents on module load
_register_agents()


@agents_bp.route('', methods=['GET'])
@token_required
@handle_exceptions
def list_agents():
    """
    List all available agents
    
    Returns:
        List of agent information with status
    """
    try:
        agents_list = registry.list_agents()
        
        return jsonify({
            'status': 'success',
            'agents': agents_list,
            'total': len(agents_list),
        }), 200
        
    except Exception as e:
        logger.error(f"Error listing agents: {str(e)}")
        raise APIException(
            message="Failed to list agents",
            status_code=500,
            error_code="LIST_AGENTS_ERROR",
            details={'error': str(e)},
        )


@agents_bp.route('/status', methods=['GET'])
@token_required
@handle_exceptions
def agent_status():
    """
    Get status of all agents
    
    Returns:
        Status information for all agents
    """
    try:
        agents = registry.list_agents()
        
        status_info = {
            'status': 'healthy',
            'agents': agents,
            'total_agents': len(agents),
            'registered_agents': len([a for a in agents if a.get('instantiated')]),
        }
        
        return jsonify(status_info), 200
        
    except Exception as e:
        logger.error(f"Error getting agent status: {str(e)}")
        raise APIException(
            message="Failed to get agent status",
            status_code=500,
            error_code="STATUS_ERROR",
        )


@agents_bp.route('/qualify-lead', methods=['POST'])
@limiter.limit("10 per minute")
@token_required
@handle_exceptions
@validate_request_json()
def qualify_lead():
    """
    Qualify a single lead using the qualification agent
    
    Request body:
    {
        "lead_data": {
            "id": "string",
            "name": "string",
            "company_size": "number",
            "engagement_score": "number",
            ...
        }
    }
    
    Returns:
        AgentResult with qualification score and recommendations
    """
    trace_id = str(uuid.uuid4())
    
    try:
        data = request.get_json()
        lead_data = data.get('lead_data', {})
        
        if not lead_data:
            raise ValidationError(
                message="'lead_data' is required",
                details={'required_fields': ['lead_data']},
            )
        
        # Get lead ID
        lead_id = lead_data.get('id', f'lead_{trace_id[:8]}')
        
        logger.info(
            f"Received qualification request for lead {lead_id}",
            extra={'trace_id': trace_id},
        )
        
        # Get pooled agent instance (reused across requests)
        agent_pool = get_agent_pool()
        agent = agent_pool.get_agent(AgentType.QUALIFICATION)
        
        # Prepare input
        input_data = {
            'id': lead_id,
            'lead_data': lead_data,
        }
        
        # Execute agent
        result = agent.run(input_data)
        
        # Log result
        logger.info(
            f"Qualification complete: {result.status.value}",
            extra={
                'lead_id': lead_id,
                'trace_id': trace_id,
                'qualified': result.data.get('qualified') if result.is_success() else None,
            },
        )
        
        # Return result
        response_data = result.to_dict()
        status_code = 200 if result.is_success() else (400 if result.status == AgentStatus.FAILED else 500)
        
        return jsonify(response_data), status_code
        
    except ValidationError as e:
        logger.warning(f"Validation error: {str(e)}", extra={'trace_id': trace_id})
        return jsonify(e.to_dict()), e.status_code
        
    except AgentException as e:
        logger.error(f"Agent error: {str(e)}", extra={'trace_id': trace_id})
        return jsonify(e.to_dict()), e.status_code
        
    except Exception as e:
        logger.error(
            f"Unexpected error in qualify_lead: {str(e)}",
            extra={'trace_id': trace_id},
            exc_info=True,
        )
        raise APIException(
            message="Lead qualification failed",
            status_code=500,
            error_code="QUALIFICATION_ERROR",
            details={'trace_id': trace_id, 'error': str(e)},
        )


@agents_bp.route('/qualify-leads-batch', methods=['POST'])
@limiter.limit("3 per minute")
@token_required
@handle_exceptions
@validate_request_json()
def qualify_leads_batch():
    """
    Qualify multiple leads in batch
    
    Request body:
    {
        "leads": [
            {"id": "...", "name": "...", ...},
            {"id": "...", "name": "...", ...}
        ]
    }
    
    Returns:
        Batch results with individual qualification scores
    """
    trace_id = str(uuid.uuid4())
    
    try:
        data = request.get_json()
        leads = data.get('leads', [])
        
        if not leads:
            raise ValidationError(
                message="'leads' array is required and cannot be empty",
            )
        
        if len(leads) > 1000:
            raise ValidationError(
                message="Maximum 1000 leads per batch",
            )
        
        logger.info(
            f"Batch qualification requested for {len(leads)} leads",
            extra={'trace_id': trace_id},
        )
        
        # Get qualification agent
        agent = registry.get_agent(
            AgentType.QUALIFICATION,
            trace_id=trace_id,
        )
        
        # Process each lead
        results = []
        successful = 0
        failed = 0
        
        for lead_data in leads:
            try:
                input_data = {
                    'id': lead_data.get('id', f'lead_{uuid.uuid4().hex[:8]}'),
                    'lead_data': lead_data,
                }
                
                result = agent.run(input_data)
                results.append(result.to_dict())
                
                if result.is_success():
                    successful += 1
                else:
                    failed += 1
                    
            except Exception as e:
                logger.error(f"Error processing lead in batch: {str(e)}")
                results.append({
                    'status': 'failed',
                    'lead_id': lead_data.get('id', 'unknown'),
                    'error': str(e),
                })
                failed += 1
        
        response = {
            'status': 'completed' if failed == 0 else 'partial',
            'data': {
                'results': results,
                'summary': {
                    'total': len(leads),
                    'successful': successful,
                    'failed': failed,
                    'success_rate': successful / len(leads) if leads else 0,
                },
                'trace_id': trace_id,
            },
            'metrics': {
                'duration_seconds': 0,  # Will be calculated by frontend
                'leads_processed': len(leads),
            },
        }
        
        return jsonify(response), 200
        
    except ValidationError as e:
        logger.warning(f"Validation error: {str(e)}", extra={'trace_id': trace_id})
        return jsonify(e.to_dict()), e.status_code
        
    except Exception as e:
        logger.error(
            f"Batch qualification error: {str(e)}",
            extra={'trace_id': trace_id},
            exc_info=True,
        )
        raise APIException(
            message="Batch qualification failed",
            status_code=500,
            error_code="BATCH_QUALIFICATION_ERROR",
            details={'trace_id': trace_id},
        )


@agents_bp.route('/qualification/rules', methods=['GET'])
@token_required
@handle_exceptions
def get_qualification_rules():
    """
    Get active qualification rules
    
    Returns:
        List of active rules with their configuration
    """
    try:
        agent = registry.get_agent(AgentType.QUALIFICATION)
        agent_qual: QualificationAgent = agent  # type: ignore[assignment]
        rules = agent_qual.get_rules()
        
        return jsonify({
            'status': 'success',
            'rules': rules,
            'total': len(rules),
        }), 200
        
    except AgentNotFoundError:
        raise APIException(
            message="Qualification agent not found",
            status_code=404,
            error_code="AGENT_NOT_FOUND",
        )
        
    except Exception as e:
        logger.error(f"Error fetching rules: {str(e)}")
        raise APIException(
            message="Failed to fetch qualification rules",
            status_code=500,
            error_code="FETCH_RULES_ERROR",
        )


@agents_bp.route('/qualification/rules', methods=['POST'])
@token_required
@admin_required
@handle_exceptions
@validate_request_json()
def add_qualification_rule():
    """
    Add a custom qualification rule
    
    Request body:
    {
        "name": "rule_name",
        "field": "field_name",
        "operator": "eq|ne|gt|lt|contains",
        "value": "some_value",
        "score": 25.0
    }
    """
    try:
        data = request.get_json()
        
        required_fields = ['name', 'field', 'operator', 'value', 'score']
        for field in required_fields:
            if field not in data:
                raise ValidationError(
                    message=f"Missing required field: {field}",
                    details={'required_fields': required_fields},
                )
        
        from app.agents.engines.qualification_rules import (
            Rule,
            RuleType,
            RuleOperator,
        )
        
        # Create rule
        rule = Rule(
            name=data['name'],
            rule_type=RuleType.FIELD_MATCH,  # Default, can be extended
            field=data['field'],
            operator=RuleOperator(data['operator']),
            value=data['value'],
            score=float(data['score']),
            weight=float(data.get('weight', 1.0)),
            priority=int(data.get('priority', 0)),
        )
        
        agent = registry.get_agent(AgentType.QUALIFICATION)
        agent_qual: QualificationAgent = agent  # type: ignore[assignment]
        agent_qual.add_rule(rule)
        
        logger.info(f"Added custom rule: {rule.name}")
        
        return jsonify({
            'status': 'success',
            'message': f"Rule '{rule.name}' added successfully",
            'rule': {
                'name': rule.name,
                'field': rule.field,
                'operator': rule.operator.value,
                'score': rule.score,
            },
        }), 201
        
    except ValidationError as e:
        return jsonify(e.to_dict()), e.status_code
        
    except ValueError as e:
        raise ValidationError(
            message=f"Invalid operator or value: {str(e)}",
        )
        
    except Exception as e:
        logger.error(f"Error adding rule: {str(e)}")
        raise APIException(
            message="Failed to add qualification rule",
            status_code=500,
            error_code="ADD_RULE_ERROR",
        )


@agents_bp.route('/query', methods=['POST'])
@limiter.limit("5 per minute")
@token_required
@handle_exceptions
@validate_request_json()
def query_leads():
    """
    Execute natural language query on leads
    
    Request body:
    {
        "query": "What are the top opportunities this month?",
        "lead_ids": ["lead_1", "lead_2"],
        "lead_data": {...optional context...}
    }
    
    Returns:
        AI-generated analysis and insights
    """
    trace_id = str(uuid.uuid4())
    
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        
        if not query:
            raise ValidationError(
                message="'query' is required and cannot be empty",
            )
        
        logger.info(
            f"Query request: {query[:100]}...",
            extra={'trace_id': trace_id},
        )
        
        # Get pooled query agent (reused across requests)
        agent_pool = get_agent_pool()
        agent = agent_pool.get_agent(AgentType.QUERY)
        
        # Prepare input
        input_data = {
            'query': query,
            'lead_ids': data.get('lead_ids', []),
            'lead_data': data.get('lead_data', {}),
            'response_format': data.get('response_format', 'json'),
        }
        
        # Execute agent
        result = agent.run(input_data)
        
        logger.info(
            f"Query execution complete: {result.status.value}",
            extra={'trace_id': trace_id},
        )
        
        response_data = result.to_dict()
        status_code = 200 if result.is_success() else 500
        
        return jsonify(response_data), status_code
        
    except ValidationError as e:
        logger.warning(f"Validation error: {str(e)}", extra={'trace_id': trace_id})
        return jsonify(e.to_dict()), e.status_code
        
    except AgentException as e:
        logger.error(f"Agent error: {str(e)}", extra={'trace_id': trace_id})
        return jsonify(e.to_dict()), e.status_code
        
    except Exception as e:
        logger.error(
            f"Query error: {str(e)}",
            extra={'trace_id': trace_id},
            exc_info=True,
        )
        raise APIException(
            message="Query execution failed",
            status_code=500,
            error_code="QUERY_ERROR",
            details={'trace_id': trace_id},
        )

