"""
Custom exception classes for the application
Provides structured error handling and logging
"""

from datetime import datetime
from typing import Optional, Dict, Any


class APIException(Exception):
    """Base exception for all API errors"""
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize API exception
        
        Args:
            message: Human-readable error message
            status_code: HTTP status code
            error_code: Machine-readable error code
            details: Additional error details
            headers: Additional HTTP headers
        """
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        self.headers = headers or {}
        self.timestamp = datetime.utcnow()
        
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON response"""
        return {
            'error': self.error_code,
            'message': self.message,
            'status_code': self.status_code,
            'details': self.details,
            'timestamp': self.timestamp.isoformat(),
        }


# ============= Client Errors (4xx) =============

class ValidationError(APIException):
    """Request validation failed (400)"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            status_code=400,
            error_code="VALIDATION_ERROR",
            details=details
        )


class AuthenticationError(APIException):
    """Authentication failed or missing (401)"""
    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="AUTHENTICATION_ERROR"
        )


class TokenExpiredError(APIException):
    """JWT token has expired (401)"""
    def __init__(self, message: str = "Token has expired"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="TOKEN_EXPIRED"
        )


class InvalidTokenError(APIException):
    """JWT token is invalid (401)"""
    def __init__(self, message: str = "Invalid token"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="INVALID_TOKEN"
        )


class AuthorizationError(APIException):
    """User doesn't have permission (403)"""
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            status_code=403,
            error_code="AUTHORIZATION_ERROR"
        )


class NotFoundError(APIException):
    """Resource not found (404)"""
    def __init__(self, resource: str, resource_id: Optional[str] = None):
        message = f"{resource} not found"
        if resource_id:
            message += f" (ID: {resource_id})"
        
        super().__init__(
            message=message,
            status_code=404,
            error_code="NOT_FOUND"
        )


class DuplicateError(APIException):
    """Resource already exists (409)"""
    def __init__(self, resource: str, value: str):
        super().__init__(
            message=f"{resource} already exists: {value}",
            status_code=409,
            error_code="DUPLICATE_RESOURCE"
        )


class RateLimitError(APIException):
    """Rate limit exceeded (429)"""
    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None):
        headers = {}
        if retry_after:
            headers['Retry-After'] = str(retry_after)
        
        super().__init__(
            message=message,
            status_code=429,
            error_code="RATE_LIMIT_EXCEEDED",
            headers=headers
        )


# ============= Server Errors (5xx) =============

class DatabaseError(APIException):
    """Database operation failed (500)"""
    def __init__(self, message: str = "Database error", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code="DATABASE_ERROR",
            details=details
        )


class DuplicateEntryError(DatabaseError):
    """Duplicate database entry"""
    def __init__(self, field: str, value: str):
        super().__init__(
            message=f"Duplicate entry for {field}: {value}",
            details={'field': field, 'value': value}
        )


class ServiceError(APIException):
    """External service failure (503)"""
    def __init__(self, service_name: str, message: Optional[str] = None):
        msg = f"{service_name} service unavailable"
        if message:
            msg += f": {message}"
        
        super().__init__(
            message=msg,
            status_code=503,
            error_code="SERVICE_UNAVAILABLE"
        )


class ConfigurationError(APIException):
    """Configuration error (500)"""
    def __init__(self, message: str):
        super().__init__(
            message=f"Configuration error: {message}",
            status_code=500,
            error_code="CONFIG_ERROR"
        )


class InternalServerError(APIException):
    """Unexpected internal error (500)"""
    def __init__(self, message: str = "Internal server error", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code="INTERNAL_ERROR",
            details=details
        )


# ============= Business Logic Errors =============

class BusinessLogicError(APIException):
    """Business logic validation failed (400)"""
    def __init__(self, message: str, error_code: str = "BUSINESS_ERROR"):
        super().__init__(
            message=message,
            status_code=400,
            error_code=error_code
        )


class InsufficientDataError(BusinessLogicError):
    """Insufficient data for operation"""
    def __init__(self, message: str = "Insufficient data"):
        super().__init__(message, "INSUFFICIENT_DATA")


class InvalidStateError(BusinessLogicError):
    """Invalid state transition"""
    def __init__(self, current_state: str, requested_state: str):
        super().__init__(
            f"Cannot transition from {current_state} to {requested_state}",
            "INVALID_STATE"
        )


class OperationNotAllowedError(BusinessLogicError):
    """Operation not allowed in current context"""
    def __init__(self, message: str = "Operation not allowed"):
        super().__init__(message, "OPERATION_NOT_ALLOWED")
