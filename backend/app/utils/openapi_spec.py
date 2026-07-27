"""
OpenAPI/Swagger Configuration Module
Generates and manages OpenAPI 3.0 specification for the API
"""

from typing import Dict, Any, Optional, List


class OpenAPISpec:
    """Generates OpenAPI 3.0 specification for the API"""
    
    SPEC = {
        'openapi': '3.0.0',
        'info': {
            'title': 'OrionLead AI API',
            'description': 'RESTful API for OrionLead AI — intelligent lead qualification and management',
            'version': '1.0.0',
            'contact': {
                'name': 'API Support',
                'email': 'support@ailead.dev',
            },
            'license': {
                'name': 'MIT',
                'url': 'https://opensource.org/licenses/MIT',
            },
        },
        'servers': [
            {
                'url': 'http://localhost:5000',
                'description': 'Development Server',
            },
            {
                'url': 'https://api.example.com',
                'description': 'Production Server',
            },
        ],
        'tags': [
            {
                'name': 'Authentication',
                'description': 'User authentication and profile management',
            },
            {
                'name': 'Leads',
                'description': 'Lead management operations',
            },
            {
                'name': 'Agents',
                'description': 'AI agent operations for lead qualification',
            },
            {
                'name': 'System',
                'description': 'System health and diagnostics',
            },
        ],
        'components': {
            'securitySchemes': {
                'BearerAuth': {
                    'type': 'http',
                    'scheme': 'bearer',
                    'bearerFormat': 'JWT',
                    'description': 'JWT token authentication',
                },
            },
            'schemas': {
                'User': {
                    'type': 'object',
                    'required': ['id', 'email', 'name', 'created_at'],
                    'properties': {
                        'id': {
                            'type': 'integer',
                            'description': 'User ID',
                        },
                        'email': {
                            'type': 'string',
                            'format': 'email',
                            'description': 'User email address',
                        },
                        'name': {
                            'type': 'string',
                            'description': 'User full name',
                        },
                        'role': {
                            'type': 'string',
                            'enum': ['user', 'admin'],
                            'default': 'user',
                        },
                        'created_at': {
                            'type': 'string',
                            'format': 'date-time',
                        },
                    },
                },
                'Lead': {
                    'type': 'object',
                    'required': ['id', 'name', 'email', 'status'],
                    'properties': {
                        'id': {
                            'type': 'integer',
                            'description': 'Lead ID',
                        },
                        'name': {
                            'type': 'string',
                            'description': 'Lead name',
                        },
                        'email': {
                            'type': 'string',
                            'format': 'email',
                        },
                        'phone': {
                            'type': 'string',
                            'nullable': True,
                        },
                        'company': {
                            'type': 'string',
                            'nullable': True,
                        },
                        'status': {
                            'type': 'string',
                            'enum': ['new', 'qualified', 'contacted', 'converted', 'rejected'],
                        },
                        'qualification_score': {
                            'type': 'number',
                            'minimum': 0,
                            'maximum': 100,
                            'nullable': True,
                        },
                        'created_at': {
                            'type': 'string',
                            'format': 'date-time',
                        },
                    },
                },
                'QualificationResult': {
                    'type': 'object',
                    'properties': {
                        'lead_id': {
                            'type': 'integer',
                        },
                        'score': {
                            'type': 'integer',
                            'minimum': 0,
                            'maximum': 100,
                        },
                        'qualified': {
                            'type': 'boolean',
                        },
                        'reasoning': {
                            'type': 'string',
                        },
                        'factors': {
                            'type': 'object',
                            'additionalProperties': {
                                'type': 'number',
                            },
                        },
                    },
                },
                'Error': {
                    'type': 'object',
                    'required': ['error', 'message', 'status_code'],
                    'properties': {
                        'error': {
                            'type': 'string',
                            'description': 'Error code',
                        },
                        'message': {
                            'type': 'string',
                            'description': 'Error message',
                        },
                        'status_code': {
                            'type': 'integer',
                        },
                        'request_id': {
                            'type': 'string',
                            'format': 'uuid',
                        },
                        'details': {
                            'type': 'object',
                            'description': 'Additional error details',
                        },
                    },
                },
                'HealthStatus': {
                    'type': 'object',
                    'properties': {
                        'status': {
                            'type': 'string',
                            'enum': ['healthy', 'degraded', 'unhealthy'],
                        },
                        'environment': {
                            'type': 'string',
                        },
                        'version': {
                            'type': 'string',
                            'format': 'semver',
                        },
                        'api_version': {
                            'type': 'string',
                        },
                        'supported_versions': {
                            'type': 'array',
                            'items': {
                                'type': 'string',
                            },
                        },
                        'timestamp': {
                            'type': 'string',
                            'format': 'date-time',
                        },
                        'components': {
                            'type': 'object',
                            'properties': {
                                'models': {
                                    'type': 'object',
                                },
                                'agent_pool': {
                                    'type': 'object',
                                },
                                'query_cache': {
                                    'type': 'object',
                                },
                            },
                        },
                    },
                },
            },
            'responses': {
                'Unauthorized': {
                    'description': 'Authentication failed or token invalid',
                    'content': {
                        'application/json': {
                            'schema': {'$ref': '#/components/schemas/Error'},
                        },
                    },
                },
                'NotFound': {
                    'description': 'Resource not found',
                    'content': {
                        'application/json': {
                            'schema': {'$ref': '#/components/schemas/Error'},
                        },
                    },
                },
                'RateLimitExceeded': {
                    'description': 'Rate limit exceeded',
                    'headers': {
                        'X-RateLimit-Limit': {
                            'schema': {'type': 'integer'},
                            'description': 'Total requests allowed in window',
                        },
                        'X-RateLimit-Remaining': {
                            'schema': {'type': 'integer'},
                            'description': 'Remaining requests in current window',
                        },
                        'X-RateLimit-Reset': {
                            'schema': {'type': 'integer'},
                            'description': 'Unix timestamp when rate limit resets',
                        },
                    },
                },
                'InternalError': {
                    'description': 'Internal server error',
                    'content': {
                        'application/json': {
                            'schema': {'$ref': '#/components/schemas/Error'},
                        },
                    },
                },
            },
        },
        'security': [
            {'BearerAuth': []},
        ],
    }
    
    @classmethod
    def get_spec(cls) -> Dict[str, Any]:
        """Get the full OpenAPI spec"""
        return cls.SPEC
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Convert spec to dictionary (for Flasgger)"""
        return cls.SPEC.copy()


def add_endpoint_docs(app_openapi_spec: Dict[str, Any], endpoint_name: str, method: str, 
                      path: str, tags: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
    """
    Helper to add endpoint documentation to OpenAPI spec
    
    Args:
        app_openapi_spec: Reference to the OpenAPI spec to update
        endpoint_name: Unique endpoint identifier
        method: HTTP method (get, post, put, delete, patch)
        path: API path (e.g., /api/v1/leads)
        tags: List of tags for grouping
        **kwargs: Additional OpenAPI fields (summary, description, parameters, requestBody, responses, etc.)
    
    Returns:
        Updated OpenAPI spec
    """
    if 'paths' not in app_openapi_spec:
        app_openapi_spec['paths'] = {}
    
    if path not in app_openapi_spec['paths']:
        app_openapi_spec['paths'][path] = {}
    
    endpoint_doc = {
        'operationId': endpoint_name,
        'tags': tags or ['Other'],
        **kwargs,
    }
    
    app_openapi_spec['paths'][path][method.lower()] = endpoint_doc
    
    return app_openapi_spec


# ============ Pre-defined Endpoint Specifications ============

AUTH_REGISTER_SPEC = {
    'summary': 'Register a new user',
    'description': 'Create a new user account with email and password',
    'requestBody': {
        'required': True,
        'content': {
            'application/json': {
                'schema': {
                    'type': 'object',
                    'required': ['email', 'password', 'name'],
                    'properties': {
                        'email': {'type': 'string', 'format': 'email'},
                        'password': {'type': 'string', 'minLength': 8},
                        'name': {'type': 'string', 'minLength': 2},
                    },
                },
            },
        },
    },
    'responses': {
        '201': {
            'description': 'User registered successfully',
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'status': {'type': 'string', 'enum': ['success']},
                            'data': {'$ref': '#/components/schemas/User'},
                        },
                    },
                },
            },
        },
        '400': {
            'description': 'Invalid input',
            'content': {
                'application/json': {
                    'schema': {'$ref': '#/components/schemas/Error'},
                },
            },
        },
    },
}

AUTH_LOGIN_SPEC = {
    'summary': 'User login',
    'description': 'Authenticate user and receive JWT token',
    'requestBody': {
        'required': True,
        'content': {
            'application/json': {
                'schema': {
                    'type': 'object',
                    'required': ['email', 'password'],
                    'properties': {
                        'email': {'type': 'string', 'format': 'email'},
                        'password': {'type': 'string'},
                    },
                },
            },
        },
    },
    'responses': {
        '200': {
            'description': 'Login successful',
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'status': {'type': 'string', 'enum': ['success']},
                            'token': {'type': 'string', 'description': 'JWT token'},
                            'user': {'$ref': '#/components/schemas/User'},
                        },
                    },
                },
            },
        },
        '401': {'$ref': '#/components/responses/Unauthorized'},
    },
}

LEADS_GET_SPEC = {
    'summary': 'List leads',
    'description': 'Retrieve a paginated list of leads with filtering options',
    'parameters': [
        {
            'name': 'page',
            'in': 'query',
            'schema': {'type': 'integer', 'default': 1},
        },
        {
            'name': 'per_page',
            'in': 'query',
            'schema': {'type': 'integer', 'default': 20, 'maximum': 100},
        },
        {
            'name': 'status',
            'in': 'query',
            'schema': {
                'type': 'string',
                'enum': ['new', 'qualified', 'contacted', 'converted', 'rejected'],
            },
        },
    ],
    'responses': {
        '200': {
            'description': 'List of leads',
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'status': {'type': 'string', 'enum': ['success']},
                            'data': {
                                'type': 'array',
                                'items': {'$ref': '#/components/schemas/Lead'},
                            },
                            'pagination': {
                                'type': 'object',
                                'properties': {
                                    'page': {'type': 'integer'},
                                    'per_page': {'type': 'integer'},
                                    'total': {'type': 'integer'},
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}

AGENTS_QUALIFY_SPEC = {
    'summary': 'Qualify a lead using AI',
    'description': 'Use AI agent to analyze and qualify a single lead',
    'requestBody': {
        'required': True,
        'content': {
            'application/json': {
                'schema': {
                    'type': 'object',
                    'required': ['lead_id'],
                    'properties': {
                        'lead_id': {'type': 'integer'},
                        'qualification_criteria': {
                            'type': 'object',
                            'nullable': True,
                        },
                    },
                },
            },
        },
    },
    'responses': {
        '200': {
            'description': 'Qualification result',
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'status': {'type': 'string', 'enum': ['success']},
                            'data': {'$ref': '#/components/schemas/QualificationResult'},
                        },
                    },
                },
            },
        },
        '429': {'$ref': '#/components/responses/RateLimitExceeded'},
    },
}
