"""
Error handling utilities for Flask
Provides decorators and handlers for structured error responses
"""

import logging
from functools import wraps
from typing import Any, Callable, Optional, Tuple
from datetime import datetime, timezone

from flask import jsonify, request
from marshmallow import ValidationError as MarshmallowValidationError

from app.exceptions import APIException, ValidationError, InternalServerError

logger = logging.getLogger(__name__)


def _create_error_response(
    error_code: str,
    message: str,
    status_code: int,
    details: Optional[dict] = None,
    headers: Optional[dict] = None
) -> Tuple[dict, int, dict]:
    """
    Create standardized error response
    
    Args:
        error_code: Machine-readable error code
        message: Human-readable message
        status_code: HTTP status code
        details: Additional error details
        headers: HTTP headers to include
    
    Returns:
        Tuple of (response_dict, status_code, headers)
    """
    response = {
        'error': error_code,
        'message': message,
        'status_code': status_code,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    
    if details:
        response['details'] = details
    
    return response, status_code, headers or {}


def handle_api_exception(error: APIException):
    """Handle APIException and return JSON response"""
    logger.warning(
        f"API Error: {error.error_code} - {error.message}",
        extra={
            'error_code': error.error_code,
            'status_code': error.status_code,
            'path': request.path,
            'method': request.method,
        }
    )
    
    response = error.to_dict()
    return jsonify(response), error.status_code, error.headers


def handle_marshmallow_error(error: MarshmallowValidationError):
    """Handle Marshmallow validation errors"""
    logger.warning(
        f"Validation Error: {error.messages}",
        extra={'path': request.path, 'method': request.method}
    )
    
    response, status_code, headers = _create_error_response(
        error_code='VALIDATION_ERROR',
        message='Request validation failed',
        status_code=400,
        details={'fields': error.messages}
    )
    return jsonify(response), status_code, headers


def handle_generic_exception(error: Exception):
    """Handle unexpected exceptions"""
    logger.exception(
        "Unexpected error",
        extra={'path': request.path, 'method': request.method}
    )
    
    response, status_code, headers = _create_error_response(
        error_code='INTERNAL_ERROR',
        message='An unexpected error occurred',
        status_code=500,
        details={'error_type': type(error).__name__}
    )
    return jsonify(response), status_code, headers


def validate_request_json(required_fields: Optional[list] = None):
    """
    Decorator to validate request has JSON body
    Can be used with or without required fields list.
    
    Args:
        required_fields: List of required field names in JSON, or the decorated function
    """
    # Support using @validate_request_json without parentheses
    if callable(required_fields) and not isinstance(required_fields, list):
        # If required_fields is actually the function being decorated
        func = required_fields
        required_fields = None
        
        @wraps(func)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            if not request.is_json:
                raise ValidationError('Content-Type must be application/json')
            return func(*args, **kwargs)
        
        return decorated_function
    
    # Standard usage with optional required fields
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            if not request.is_json:
                raise ValidationError('Content-Type must be application/json')
            
            if required_fields:
                json_data = request.get_json()
                missing_fields = [
                    field for field in required_fields if field not in json_data
                ]
                if missing_fields:
                    raise ValidationError(
                        'Missing required fields',
                        details={'missing_fields': missing_fields}
                    )
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def handle_exceptions(f: Callable) -> Callable:
    """
    Decorator to handle all exceptions in a route
    Converts exceptions to proper JSON responses
    """
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        from werkzeug.exceptions import HTTPException
        try:
            return f(*args, **kwargs)
        except HTTPException:
            raise  # Let Flask handle 404 / 405 etc. normally
        except APIException as e:
            return handle_api_exception(e)
        except MarshmallowValidationError as e:
            return handle_marshmallow_error(e)
        except Exception as e:
            try:
                import threading as _t
                from flask import g as _g, request as _req
                _uid    = getattr(_g, 'user_id', None)
                _uemail = getattr(_g, 'email',    None)
                if _uid and _uemail:
                    from app.routes.settings import _get_user_settings as _gp
                    from app.services.email_service import send_system_error_alert as _sea
                    if _gp(_uid).get('notify_system_errors'):
                        _path, _method = _req.path, _req.method
                        _etype, _emsg  = type(e).__name__, str(e)[:200]
                        _t.Thread(
                            target=lambda: _sea(_uemail, _path, _method, _etype, _emsg),
                            daemon=True,
                        ).start()
            except Exception:
                pass
            return handle_generic_exception(e)
    
    return decorated_function


def success_response(data: Any = None, message: str = 'OK', status_code: int = 200,
                     **extra) -> tuple:
    """
    Standard success envelope used across all routes.

    Shape:
        { "status": "success", "message": "...", "data": {...}, ...extra }

    Args:
        data:        Main payload (dict, list, or None).
        message:     Human-readable summary.
        status_code: HTTP status (default 200).
        **extra:     Any additional top-level keys (e.g. total=, page=).

    Returns:
        Flask-compatible (Response, int) tuple.
    """
    body: dict = {'status': 'success', 'message': message}
    if data is not None:
        body['data'] = data
    body.update(extra)
    return jsonify(body), status_code


def log_request_response(f: Callable) -> Callable:
    """
    Decorator to log request and response details
    Useful for debugging and audit trails
    """
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        logger.info(
            f"Request: {request.method} {request.path}",
            extra={
                'method': request.method,
                'path': request.path,
                'remote_addr': request.remote_addr,
                'user_agent': request.user_agent,
            }
        )
        
        result = f(*args, **kwargs)
        
        if isinstance(result, tuple):
            response, status_code = result[0], result[1]
        else:
            response, status_code = result, 200
        
        logger.info(
            f"Response: {status_code}",
            extra={
                'method': request.method,
                'path': request.path,
                'status_code': status_code,
            }
        )
        
        return result
    
    return decorated_function
