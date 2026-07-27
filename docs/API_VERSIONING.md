# API Versioning Strategy & Implementation

## Overview

This document outlines how the OrionLead AI implements API versioning to maintain backward compatibility while enabling future improvements.

## Current Status

- **Current Version**: v1
- **Release Date**: 2024
- **Supported Versions**: v1
- **Deprecated Versions**: None
- **Health Check Endpoint**: `GET /api/v1/health`

## All Endpoints by Resource

### Authentication & User Management
```
POST   /api/v1/auth/register          - Register new user
POST   /api/v1/auth/login             - User login (returns JWT token)
GET    /api/v1/auth/profile           - Get current user profile
PUT    /api/v1/auth/profile/{id}      - Update user profile
POST   /api/v1/auth/logout            - User logout
POST   /api/v1/auth/refresh-token     - Refresh JWT token
```

### Leads Management
```
GET    /api/v1/leads                  - List all leads (paginated, filterable)
POST   /api/v1/leads                  - Create new lead
GET    /api/v1/leads/{id}             - Get specific lead details
PUT    /api/v1/leads/{id}             - Update lead
DELETE /api/v1/leads/{id}             - Delete lead
GET    /api/v1/leads/{id}/history     - Get lead status change history
POST   /api/v1/leads/bulk              - Bulk create leads
```

### AI Agent Operations
```
POST   /api/v1/agents/qualify-lead    - Qualify single lead using AI
POST   /api/v1/agents/qualify-leads-batch - Batch qualify multiple leads
POST   /api/v1/agents/query           - Query leads using natural language
GET    /api/v1/agents/stats           - Get agent performance statistics
```

### System Health & Diagnostics
```
GET    /api/v1/health                 - Overall system health check
GET    /api/v1/debug/models           - Model loading status
GET    /api/v1/debug/cache-stats      - Cache statistics
GET    /api/v1/debug/agents           - Agent pool status
```

## Response Headers

All API responses include versioning metadata:

```
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
API-Version: v1
API-Supported-Versions: v1
```

### Header Reference

| Header | Example | Meaning |
|--------|---------|---------|
| `X-Request-ID` | `550e8400-e29b...` | Unique request identifier for tracing |
| `API-Version` | `v1` | API version used for this request |
| `API-Supported-Versions` | `v1` | Comma-separated list of supported versions |
| `Deprecation` | `true` | Present if endpoint/version is deprecated |
| `Sunset` | `v2` | Migration path (if deprecated) |

## Rate Limiting

Each endpoint has rate limiting to ensure fair usage and system stability:

| Endpoint | Limit | Window |
|----------|-------|--------|
| `POST /api/v1/auth/register` | 5 requests | Per hour |
| `POST /api/v1/auth/login` | 10 requests | Per minute |
| `GET /api/v1/leads` | 30 requests | Per minute |
| `POST /api/v1/leads` | 20 requests | Per hour |
| `POST /api/v1/agents/qualify-lead` | 10 requests | Per minute |
| `POST /api/v1/agents/qualify-leads-batch` | 3 requests | Per minute |
| `POST /api/v1/agents/query` | 5 requests | Per minute |

Rate limit info is included in response headers:
```
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 22
X-RateLimit-Reset: 1234567890
```

## Request/Response Example

### Request
```bash
curl -X POST http://localhost:5000/api/v1/agents/qualify-lead \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGc..." \
  -H "X-Request-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{
    "lead_id": 123,
    "qualification_criteria": {"min_budget": 5000}
  }'
```

### Response
```json
{
  "status": "success",
  "data": {
    "lead_id": 123,
    "score": 85,
    "qualified": true,
    "reasoning": "High fit based on budget and industry"
  },
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T10:30:45.123Z"
}
```

### Response Headers
```
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
API-Version: v1
API-Supported-Versions: v1
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 4
X-RateLimit-Reset: 1234567890
```

## Versioning Policy

### Creating a New Major Version

When introducing breaking changes that cannot be handled within v1:

**1. Planning Phase**
```python
# Update app/utils/versioning.py
class APIVersion:
    CURRENT_VERSION = "v1"  # Keep v1 as current for now
    SUPPORTED_VERSIONS = ["v1", "v2"]  # Add v2 support
    DEPRECATED_VERSIONS = {}  # No versions deprecated yet
```

**2. Implementation Phase**
- Create new route files with v2 handlers (e.g., `/routes/auth_v2.py`)
- Register v2 blueprints with `/api/v2/` prefix
- Keep v1 routes intact and functional

**3. Rollout Phase**
- Deploy with both v1 and v2 active
- Monitor v1 usage metrics
- Provide migration guide to v2

**4. Deprecation Phase**
- After 3-6 months, mark v1 as deprecated
- Start returning Deprecation headers for v1
- Provide removal date in Sunset header

**5. Sunset Phase**
- Remove v1 after agreed deprecation period
- Update documentation

### Backward Compatibility

The system maintains backward compatibility within v1 by:
- Adding new optional fields to existing endpoints
- Supporting new query parameters (old ones still work)
- Preserving all existing error codes
- Not changing existing field types

### Breaking Changes (Requires New Version)

Changes that require v2:
- Removing required fields from responses
- Changing field data types
- Moving/renaming existing endpoints
- Changing request/response structure fundamentally
- Changing authentication mechanism

## Error Codes & Status Codes

All API errors follow standardized formats:

```json
{
  "error": "VALIDATION_ERROR",
  "message": "User-friendly error description",
  "status_code": 400,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "details": {
    "email": ["Invalid email format"],
    "password": ["Password must be at least 8 characters"]
  }
}
```

### HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | OK | Success |
| 201 | Created | Lead created successfully |
| 400 | Bad Request | Invalid input data |
| 401 | Unauthorized | Invalid/missing token |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource doesn't exist |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Server Error | Unexpected error |

## Migration Guide: Future Versions

### v1 to v2 (When Available) - Example Flow

1. **Check Current Version**
   ```bash
   curl http://localhost:5000/api/v1/health
   # Response includes: "api_version": "v1"
   ```

2. **Review v2 Documentation**
   - All changes documented with migration examples

3. **Update Client Code**
   ```javascript
   // Old (v1)
   const response = await axios.get('/api/v1/leads/123');
   
   // New (v2) - if endpoint structure changed
   const response = await axios.get('/api/v2/leads/123');
   ```

4. **Test Integration**
   - Test with v2 endpoints in staging first
   - Verify response parsing still works

5. **Deploy & Monitor**
   - Deploy updated client code
   - Monitor error logs for API changes

## Implementation Details

### Version Extraction from URL

The system automatically extracts version from URL path:
```python
# Input: /api/v1/leads/123
# Extracted version: v1

# Input: /api/v2/leads/123
# Extracted version: v2

# Input: /api/health (no version)
# Default version: v1
```

### Version-Aware Error Responses

All error responses include current API version:
```json
{
  "error": "LEAD_NOT_FOUND",
  "message": "Lead with ID 999 not found",
  "status_code": 404,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "api_version": "v1",
  "supported_versions": ["v1"]
}
```

### Future Extensions

The versioning system supports:
- **A/B Testing**: Route subset of users to v2
- **Gradual Rollout**: Enable v2 endpoints for specific user groups
- **Metrics Collection**: Track v1 vs v2 usage
- **Feature Flags**: Enable/disable endpoints per version

## Testing Versioning

### Local Testing

```bash
# Test v1 endpoint
curl http://localhost:5000/api/v1/health
# HTTP/1.1 200 OK
# API-Version: v1

# Test version header inclusion
curl -i http://localhost:5000/api/v1/health
# Look for API-Version, API-Supported-Versions headers
```

### Verify Client Updates

```javascript
// Check baseURL includes /api/v1
import api from './services/api';
console.log(api.defaults.baseURL); // Should be http://localhost:5000/api/v1
```

## Support & Questions

- **API Documentation**: See `/apidocs` (Swagger UI) - to be implemented
- **Version Status**: `GET /api/v1/health` shows current version
- **Issue Reporting**: Include X-Request-ID header value in bug reports

## Related Documentation

- See [API.md](../docs/API.md) for endpoint specifications
- See [BACKEND_DEVELOPMENT.md](../docs/BACKEND_DEVELOPMENT.md) for development guidelines
- See [app/utils/versioning.py](../backend/app/utils/versioning.py) for implementation code
