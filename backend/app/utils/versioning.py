"""
API Versioning Management Module
Handles version routing, compatibility checks, and deprecation warnings
"""

from typing import Dict, Optional, List, Callable, Any
from functools import wraps
from flask import request, jsonify, g


class APIVersion:
    """Manages API versioning constants and metadata"""
    
    CURRENT_VERSION = "v1"
    SUPPORTED_VERSIONS = ["v1"]
    DEPRECATED_VERSIONS: Dict[str, Optional[str]] = {}  # v0 -> v1 (no v0 yet)
    
    # Endpoint deprecation tracking: endpoint_name -> (removal_version, replacement_url)
    DEPRECATED_ENDPOINTS: Dict[str, tuple] = {}
    
    @classmethod
    def is_supported(cls, version: str) -> bool:
        """Check if version is supported"""
        return version in cls.SUPPORTED_VERSIONS
    
    @classmethod
    def is_deprecated(cls, version: str) -> bool:
        """Check if version is deprecated"""
        return version in cls.DEPRECATED_VERSIONS
    
    @classmethod
    def get_migration_path(cls, old_version: str) -> Optional[str]:
        """Get migration path for deprecated version"""
        return cls.DEPRECATED_VERSIONS.get(old_version)


def version_required(supported_versions: Optional[List[str]] = None):
    """
    Decorator to specify which API versions support this endpoint
    Ensures version compatibility and adds deprecation warnings
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            current_version = getattr(g, 'api_version', APIVersion.CURRENT_VERSION)
            
            if supported_versions and current_version not in supported_versions:
                return jsonify({
                    'error': 'Version Not Supported',
                    'message': f'Endpoint not available in {current_version}',
                    'supported_versions': supported_versions,
                    'current_version': APIVersion.CURRENT_VERSION
                }), 410  # Gone status
            
            # Check for deprecation
            if APIVersion.is_deprecated(current_version):
                migration = APIVersion.get_migration_path(current_version)
                g.deprecation_warning = {
                    'message': f'{current_version} is deprecated',
                    'migrate_to': migration
                }
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def extract_api_version(version_string: Optional[str] = None) -> str:
    """
    Extract and validate API version from request
    
    Args:
        version_string: Version string (e.g., 'v1'). If None, extracts from URL path.
    
    Returns:
        Valid version string (e.g., 'v1')
    """
    if version_string:
        if APIVersion.is_supported(version_string):
            return version_string
        return APIVersion.CURRENT_VERSION
    
    # Extract from URL path: /api/v1/auth/... -> v1
    path_parts = request.path.split('/')
    for part in path_parts:
        if part.startswith('v') and part[1:].isdigit():
            if APIVersion.is_supported(part):
                return part
    
    return APIVersion.CURRENT_VERSION


def add_version_headers(response):
    """
    Add API version headers to response
    Should be called in after_request hook
    """
    version = getattr(g, 'api_version', APIVersion.CURRENT_VERSION)
    response.headers['API-Version'] = version
    response.headers['API-Supported-Versions'] = ', '.join(APIVersion.SUPPORTED_VERSIONS)
    
    if hasattr(g, 'deprecation_warning'):
        response.headers['Deprecation'] = 'true'
        response.headers['Sunset'] = g.deprecation_warning.get('migrate_to', '')
    
    return response


class VersionedEndpointRegistry:
    """
    Registry for managing versioned endpoints
    Enables A/B testing and gradual rollouts
    """
    
    _registry: Dict[str, Dict[str, Callable]] = {}
    
    @classmethod
    def register(cls, endpoint_name: str, version: str, handler: Callable):
        """Register endpoint handler for specific version"""
        if endpoint_name not in cls._registry:
            cls._registry[endpoint_name] = {}
        cls._registry[endpoint_name][version] = handler
    
    @classmethod
    def get_handler(cls, endpoint_name: str, version: str) -> Optional[Callable]:
        """Get handler for endpoint in specific version"""
        if endpoint_name in cls._registry:
            return cls._registry[endpoint_name].get(version)
        return None
    
    @classmethod
    def get_all_versions(cls, endpoint_name: str) -> List[str]:
        """Get all versions supporting this endpoint"""
        if endpoint_name in cls._registry:
            return list(cls._registry[endpoint_name].keys())
        return []


# ============ API Version Documentation ============
API_VERSIONING_GUIDE = """
# API Versioning Strategy

## Current Status
- **Current Version**: v1
- **Supported Versions**: v1
- **Deprecated Versions**: None

## Version Format
All endpoints follow the format: `/api/v{N}/{resource}`

Examples:
- POST /api/v1/auth/register
- GET /api/v1/leads/123
- POST /api/v1/agents/qualify-lead

## Future Versioning
When creating v2:
1. Create new blueprint with url_prefix='/api/v2/...'
2. Add 'v2' to APIVersion.SUPPORTED_VERSIONS
3. Add 'v1' to APIVersion.DEPRECATED_VERSIONS with migration path
4. Maintain v1 endpoints for backward compatibility (X months)
5. Update this file with new version details

## Deprecation Policy
- Deprecated versions get Deprecation: true header
- Sunset header indicates removal date
- Clients should migrate within 6 months
- Error responses include migration path

## Version Headers
All responses include:
- API-Version: Current version used
- API-Supported-Versions: Comma-separated list of supported versions
- Deprecation: true (if endpoint/version deprecated)
- Sunset: Migration path or removal date (if deprecated)
"""
