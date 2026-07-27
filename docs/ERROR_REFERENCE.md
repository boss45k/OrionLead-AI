# API Error Reference

## Overview

This document provides a comprehensive reference for all error codes, HTTP status codes, and error responses in the OrionLead AI API.

## Error Response Format

All errors return a consistent JSON format with the following structure:

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable error message",
  "status_code": 400,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "field_name": ["Field-specific error message"]
  }
}
```

### Standard Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `error` | string | Yes | Machine-readable error code |
| `message` | string | Yes | Human-readable description |
| `status_code` | integer | Yes | HTTP status code |
| `request_id` | UUID string | Yes | Request ID for tracing |
| `timestamp` | ISO8601 | Yes | When error occurred |
| `details` | object | No | Field-specific error details |

## HTTP Status Codes

| Code | Name | Use Case |
|------|------|----------|
| 400 | Bad Request | Invalid input data, validation failed |
| 401 | Unauthorized | Missing or invalid authentication token |
| 403 | Forbidden | Authenticated but lacks permissions |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Duplicate resource or state conflict |
| 410 | Gone | Resource removed or API version deprecated |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Unexpected server error |
| 503 | Service Unavailable | Service temporarily unavailable |

## Error Codes by Category

### Authentication Errors (401)

#### INVALID_TOKEN
```json
{
  "error": "INVALID_TOKEN",
  "message": "Invalid or malformed JWT token",
  "status_code": 401,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z"
}
```
**Causes:** Corrupted token, wrong signature, token from different server  
**Resolution:** Re-authenticate to get a new token

#### TOKEN_EXPIRED
```json
{
  "error": "TOKEN_EXPIRED",
  "message": "JWT token has expired",
  "status_code": 401,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z"
}
```
**Causes:** Token older than 24 hours  
**Resolution:** Use refresh endpoint to get new token, or re-authenticate

#### AUTHENTICATION_FAILED
```json
{
  "error": "AUTHENTICATION_FAILED",
  "message": "Invalid email or password",
  "status_code": 401,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z"
}
```
**Causes:** Wrong password, account doesn't exist, account inactive  
**Resolution:** Verify credentials and account status

#### MISSING_TOKEN
```json
{
  "error": "MISSING_TOKEN",
  "message": "Authorization header missing or malformed",
  "status_code": 401,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z"
}
```
**Causes:** No Authorization header, wrong format (not "Bearer token")  
**Resolution:** Include valid Authorization header: `Authorization: Bearer <token>`

---

### Authorization Errors (403)

#### PERMISSION_DENIED
```json
{
  "error": "PERMISSION_DENIED",
  "message": "User lacks permission to access this resource",
  "status_code": 403,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "required_role": "admin",
    "current_role": "user"
  }
}
```
**Causes:** User role insufficient, resource belongs to another user  
**Resolution:** Request access from administrator, use appropriate user role

#### RESOURCE_OWNERSHIP_VIOLATION
```json
{
  "error": "RESOURCE_OWNERSHIP_VIOLATION",
  "message": "Cannot access resource owned by another user",
  "status_code": 403,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z"
}
```
**Causes:** Trying to modify/delete lead belonging to different user  
**Resolution:** Only users with admin role can access others' resources

---

### Validation Errors (400)

#### VALIDATION_ERROR
```json
{
  "error": "VALIDATION_ERROR",
  "message": "Input validation failed",
  "status_code": 400,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "email": ["Invalid email format"],
    "password": ["Password must be at least 8 characters"],
    "full_name": ["Full name is required"]
  }
}
```
**Causes:** Invalid input data format, missing required fields  
**Resolution:** Fix the fields listed in `details` and retry

#### INVALID_JSON
```json
{
  "error": "INVALID_JSON",
  "message": "Request body must be valid JSON",
  "status_code": 400,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z"
}
```
**Causes:** Malformed JSON, syntax error  
**Resolution:** Validate JSON format (use jsonlint.com)

#### MISSING_REQUIRED_FIELD
```json
{
  "error": "MISSING_REQUIRED_FIELD",
  "message": "Required field missing from request",
  "status_code": 400,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "missing_fields": ["email", "password"]
  }
}
```
**Causes:** Required field not included in request body  
**Resolution:** Add missing fields to request

#### INVALID_PARAMETER
```json
{
  "error": "INVALID_PARAMETER",
  "message": "Invalid query parameter value",
  "status_code": 400,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "parameter": "status",
    "value": "invalid_status",
    "allowed_values": ["new", "qualified", "contacted", "converted", "rejected"]
  }
}
```
**Causes:** Out-of-range value, invalid enum option  
**Resolution:** Use value from `allowed_values` list

---

### Resource Errors (404)

#### NOT_FOUND
```json
{
  "error": "NOT_FOUND",
  "message": "Resource not found",
  "status_code": 404,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "resource_type": "Lead",
    "resource_id": 999
  }
}
```
**Causes:** Resource ID doesn't exist, was deleted  
**Resolution:** Verify resource ID exists before accessing

#### USER_NOT_FOUND
```json
{
  "error": "USER_NOT_FOUND",
  "message": "User account not found",
  "status_code": 404,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "email": "nonexistent@example.com"
  }
}
```
**Causes:** Email address not registered  
**Resolution:** Create account or verify email spelling

#### LEAD_NOT_FOUND
```json
{
  "error": "LEAD_NOT_FOUND",
  "message": "Lead with specified ID not found",
  "status_code": 404,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "lead_id": 12345
  }
}
```
**Causes:** Lead ID doesn't exist, was deleted  
**Resolution:** List leads to find correct ID

---

### Duplicate/Conflict Errors (409)

#### DUPLICATE_ERROR
```json
{
  "error": "DUPLICATE_ERROR",
  "message": "Resource already exists",
  "status_code": 409,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "field": "email",
    "value": "user@example.com"
  }
}
```
**Causes:** Email already registered, lead already exists  
**Resolution:** Use different value or update existing resource

#### DUPLICATE_EMAIL
```json
{
  "error": "DUPLICATE_EMAIL",
  "message": "Email address already registered",
  "status_code": 409,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "email": "user@example.com"
  }
}
```
**Causes:** Account with email already exists  
**Resolution:** Use different email or login instead

#### STATE_CONFLICT
```json
{
  "error": "STATE_CONFLICT",
  "message": "Resource in invalid state for this operation",
  "status_code": 409,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "current_state": "converted",
    "expected_state": "qualified"
  }
}
```
**Causes:** Operation only valid for certain states  
**Resolution:** Check resource state before performing operation

---

### Rate Limiting Errors (429)

#### RATE_LIMIT_EXCEEDED
```json
{
  "error": "RATE_LIMIT_EXCEEDED",
  "message": "Too many requests, please try again later",
  "status_code": 429,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z"
}
```
**Headers:**
```
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1705344225
```

**Causes:** Exceeded rate limit for endpoint  
**Resolution:** Wait until `X-RateLimit-Reset` time, then retry

#### Rate Limits by Endpoint

| Endpoint | Limit | Window |
|----------|-------|--------|
| `POST /api/v1/auth/register` | 5 | Per hour |
| `POST /api/v1/auth/login` | 10 | Per minute |
| `GET /api/v1/leads` | 30 | Per minute |
| `POST /api/v1/leads` | 20 | Per hour |
| `POST /api/v1/agents/qualify-lead` | 10 | Per minute |
| `POST /api/v1/agents/qualify-leads-batch` | 3 | Per minute |
| `POST /api/v1/agents/query` | 5 | Per minute |

---

### Business Logic Errors (400/409)

#### QUALIFICATION_ERROR
```json
{
  "error": "QUALIFICATION_ERROR",
  "message": "Lead qualification failed",
  "status_code": 400,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "reason": "Missing required lead data: company",
    "lead_id": 123
  }
}
```
**Causes:** Insufficient lead data, model error, invalid criteria  
**Resolution:** Provide complete lead information or check qualification criteria

#### INVALID_QUALIFICATION_CRITERIA
```json
{
  "error": "INVALID_QUALIFICATION_CRITERIA",
  "message": "Qualification criteria validation failed",
  "status_code": 400,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "min_budget": "Must be greater than 0",
    "max_budget": "Must be greater than min_budget"
  }
}
```
**Causes:** Invalid budget ranges, conflicting criteria  
**Resolution:** Review criteria values and correct them

---

### Database Errors (500)

#### DATABASE_ERROR
```json
{
  "error": "DATABASE_ERROR",
  "message": "Database operation failed",
  "status_code": 500,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z"
}
```
**Causes:** Connection pool exhausted, SQL error, transaction failed  
**Resolution:** Retry after a few seconds; contact support if persists

#### DATABASE_CONNECTION_ERROR
```json
{
  "error": "DATABASE_CONNECTION_ERROR",
  "message": "Unable to connect to database",
  "status_code": 503,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z"
}
```
**Causes:** Database server down, connection timeout  
**Resolution:** Contact system administrator

---

### External Service Errors (500/503)

#### LLM_SERVICE_ERROR
```json
{
  "error": "LLM_SERVICE_ERROR",
  "message": "Failed to contact LLM service",
  "status_code": 503,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "service": "OpenAI",
    "reason": "Service rate limited"
  }
}
```
**Causes:** API service down, rate limited, invalid API key  
**Resolution:** Retry later or contact LLM provider support

#### CACHE_SERVICE_ERROR
```json
{
  "error": "CACHE_SERVICE_ERROR",
  "message": "Cache service unavailable, queries degraded",
  "status_code": 503,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "service": "Redis",
    "fallback": "in-memory cache active"
  }
}
```
**Causes:** Redis unavailable  
**Resolution:** System continues with reduced performance; automated recovery in progress

---

### API Versioning Errors (410)

#### VERSION_NOT_SUPPORTED
```json
{
  "error": "VERSION_NOT_SUPPORTED",
  "message": "Endpoint not available in specified API version",
  "status_code": 410,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "requested_version": "v0",
    "current_version": "v1",
    "supported_versions": ["v1"],
    "migrate_to": "v1"
  }
}
```
**Causes:** Using deprecated API version  
**Resolution:** Update client to use v1 endpoints

#### API_DEPRECATION_WARNING
```
Headers:
Deprecation: true
Sunset: v2
```
**Meaning:** You're using a deprecated version; migrate to v2  
**Resolution:** Plan migration to new version

---

### Server Errors (500)

#### INTERNAL_SERVER_ERROR
```json
{
  "error": "INTERNAL_SERVER_ERROR",
  "message": "An unexpected error occurred",
  "status_code": 500,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z"
}
```
**Causes:** Unhandled exception, bug in code  
**Resolution:** Contact support with request_id

#### SERVICE_UNAVAILABLE
```json
{
  "error": "SERVICE_UNAVAILABLE",
  "message": "Service is temporarily unavailable",
  "status_code": 503,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T14:23:45.123Z",
  "details": {
    "reason": "Maintenance in progress",
    "estimated_recovery": "2024-01-15T15:00:00Z"
  }
}
```
**Causes:** Scheduled maintenance, system overload  
**Resolution:** Retry after specified time

---

## Error Handling Best Practices

### Client-Side Error Handling

```javascript
// Example using JavaScript/React
async function callApi(endpoint, options = {}) {
  try {
    const response = await fetch(endpoint, options);
    const data = await response.json();
    
    if (!response.ok) {
      // Handle different error types
      switch (data.error) {
        case 'INVALID_TOKEN':
        case 'TOKEN_EXPIRED':
          // Redirect to login
          window.location.href = '/login';
          break;
          
        case 'RATE_LIMIT_EXCEEDED':
          // Show user-friendly message with retry time
          const retryTime = new Date(data.headers['X-RateLimit-Reset'] * 1000);
          alert(`Too many requests. Please try again at ${retryTime}`);
          break;
          
        case 'VALIDATION_ERROR':
          // Show field-specific errors
          showFieldErrors(data.details);
          break;
          
        default:
          // Generic error handling
          console.error(data.message);
      }
      
      throw new Error(data.message);
    }
    
    return data;
  } catch (error) {
    console.error(`Request failed (ID: ${error.request_id}):`, error.message);
    throw error;
  }
}
```

### Retry Strategy

```javascript
async function retryWithBackoff(fn, maxRetries = 3, baseDelay = 1000) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      if (attempt === maxRetries - 1) throw error;
      
      // Don't retry on client errors (4xx)
      if (error.status_code >= 400 && error.status_code < 500) {
        throw error;
      }
      
      // Exponential backoff for server errors
      const delay = baseDelay * Math.pow(2, attempt);
      console.log(`Retry attempt ${attempt + 1} after ${delay}ms`);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}
```

## Debugging with Request IDs

Every error includes a unique `request_id` for tracing:

```bash
# Check logs for specific request
grep "550e8400-e29b-41d4-a716-446655440000" logs/app.json.log

# Get full request context
grep -A 50 "550e8400-e29b-41d4-a716-446655440000" logs/app.json.log

# Extract all errors for a time period
grep "error\|ERROR" logs/app.json.log | grep "2024-01-15T14:"
```

## Support & Escalation

### When to Contact Support

- Error persists after retry
- Receiving 500 Internal Server Error consistently
- Unexpected error code not documented here
- Rate limit seems incorrect for your usage

### Provide This Information

1. Request ID from error response
2. Error code and message
3. Endpoint and HTTP method
4. Approximate time of error
5. Steps to reproduce

### Support Channel

- **Email**: support@ailead.dev
- **Slack**: #api-support channel
- **Priority Queue**: Include request ID in subject line

## Error Code Quick Reference

| Code | Status | Category |
|------|--------|----------|
| INVALID_TOKEN | 401 | Auth |
| TOKEN_EXPIRED | 401 | Auth |
| AUTHENTICATION_FAILED | 401 | Auth |
| PERMISSION_DENIED | 403 | Auth |
| VALIDATION_ERROR | 400 | Input |
| NOT_FOUND | 404 | Resource |
| DUPLICATE_ERROR | 409 | Conflict |
| RATE_LIMIT_EXCEEDED | 429 | Limit |
| DATABASE_ERROR | 500 | Server |
| INTERNAL_SERVER_ERROR | 500 | Server |
| SERVICE_UNAVAILABLE | 503 | Server |

For complete list, search above by error code.
