"""
Jaeger Distributed Tracing Module
Enables request tracing across distributed services
"""

import os
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class TracingConfig:
    """Jaeger tracing configuration"""
    
    # Jaeger settings
    JAEGER_SERVICE_NAME = os.getenv('JAEGER_SERVICE_NAME', 'ai-lead-system')
    JAEGER_AGENT_HOST = os.getenv('JAEGER_AGENT_HOST', 'localhost')
    JAEGER_AGENT_PORT = int(os.getenv('JAEGER_AGENT_PORT', 6831))
    JAEGER_SAMPLER_TYPE = os.getenv('JAEGER_SAMPLER_TYPE', 'const')
    JAEGER_SAMPLER_PARAM = float(os.getenv('JAEGER_SAMPLER_PARAM', 1.0))
    JAEGER_LOG_SPANS = os.getenv('JAEGER_LOG_SPANS', 'true').lower() == 'true'
    JAEGER_ENABLED = os.getenv('JAEGER_ENABLED', 'false').lower() == 'true'


def init_tracing(app_name: str = 'ai-lead-system'):
    """
    Initialize Jaeger tracing
    
    Args:
        app_name: Application name for traces
    
    Returns:
        Tracer instance or None if disabled
    """
    if not TracingConfig.JAEGER_ENABLED:
        logger.info("Jaeger tracing disabled (JAEGER_ENABLED=false)")
        return None
    
    try:
        from jaeger_client.config import Config
        from jaeger_client.tracer import Tracer
        
        config = Config(
            config={
                'sampler': {
                    'type': TracingConfig.JAEGER_SAMPLER_TYPE,
                    'param': TracingConfig.JAEGER_SAMPLER_PARAM,
                },
                'local_agent': {
                    'reporting_host': TracingConfig.JAEGER_AGENT_HOST,
                    'reporting_port': TracingConfig.JAEGER_AGENT_PORT,
                },
                'logging': TracingConfig.JAEGER_LOG_SPANS,
            },
            service_name=app_name,
            validate=True,
        )
        
        tracer = config.initialize_tracer()
        logger.info(f"Jaeger tracing initialized for {app_name}")
        return tracer
        
    except ImportError:
        logger.warning("jaeger-client not installed. Tracing disabled.")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Jaeger: {e}")
        return None


class TracingContextManager:
    """Context manager for distributed tracing"""
    
    _tracer = None
    
    @classmethod
    def set_tracer(cls, tracer):
        """Set global tracer instance"""
        cls._tracer = tracer
    
    @classmethod
    def get_tracer(cls):
        """Get global tracer instance"""
        return cls._tracer
    
    @classmethod
    def start_span(cls, operation_name: str, tags: Optional[Dict[str, Any]] = None):
        """
        Start a new span
        
        Args:
            operation_name: Name of the operation
            tags: Optional span tags
        
        Returns:
            Span instance or None if tracing disabled
        """
        tracer = cls.get_tracer()
        if not tracer:
            return None
        
        try:
            span = tracer.start_span(operation_name)
            if tags:
                for key, value in tags.items():
                    span.set_tag(key, value)
            return span
        except Exception as e:
            logger.error(f"Failed to start span: {e}")
            return None
    
    @classmethod
    def set_span_tag(cls, span, key: str, value: Any):
        """Set tag on span"""
        if span and hasattr(span, 'set_tag'):
            try:
                span.set_tag(key, value)
            except Exception as e:
                logger.error(f"Failed to set span tag: {e}")
    
    @classmethod
    def set_span_error(cls, span, error: Exception):
        """Mark span as error"""
        if span:
            try:
                span.set_tag('error', True)
                span.set_tag('error.kind', type(error).__name__)
                span.set_tag('error.message', str(error))
                span.log_kv({'event': 'error', 'message': str(error)})
            except Exception as e:
                logger.error(f"Failed to set span error: {e}")
    
    @classmethod
    def finish_span(cls, span):
        """Finish span"""
        if span and hasattr(span, 'finish'):
            try:
                span.finish()
            except Exception as e:
                logger.error(f"Failed to finish span: {e}")


def init_flask_tracing(app, tracer):
    """
    Initialize Flask app with tracing
    
    Args:
        app: Flask application instance
        tracer: Jaeger tracer instance
    """
    if not tracer:
        return
    
    from flask import request, g
    
    @app.before_request
    def before_request_tracing():
        """Start trace for incoming request"""
        operation_name = f"{request.method} {request.path}"
        
        span = TracingContextManager.start_span(
            operation_name,
            tags={
                'http.method': request.method,
                'http.url': request.url,
                'http.target': request.path,
                'span.kind': 'server',
            }
        )
        
        # Add request headers and ID
        if hasattr(g, 'request_id'):
            TracingContextManager.set_span_tag(span, 'request_id', g.request_id)
        if hasattr(g, 'api_version'):
            TracingContextManager.set_span_tag(span, 'api_version', g.api_version)
        
        g.trace_span = span
    
    @app.after_request
    def after_request_tracing(response):
        """Finish trace for outgoing response"""
        span = getattr(g, 'trace_span', None)
        if span:
            TracingContextManager.set_span_tag(span, 'http.status_code', response.status_code)
            TracingContextManager.set_span_tag(span, 'http.response_size', len(response.get_data()))
            TracingContextManager.finish_span(span)
        
        return response
    
    @app.errorhandler(Exception)
    def errorhandler_tracing(error):
        """Track errors in traces"""
        span = getattr(g, 'trace_span', None)
        if span:
            TracingContextManager.set_span_error(span, error)
        
        raise error
    
    logger.info("Flask tracing initialized")


def extract_trace_context(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Extract trace context from HTTP headers
    
    Args:
        headers: HTTP headers dictionary
    
    Returns:
        Trace context headers
    """
    trace_context = {}
    
    # Standard trace header names
    trace_headers = [
        'x-trace-id',
        'x-span-id',
        'x-parent-span-id',
        'traceparent',  # W3C
        'tracestate',   # W3C
    ]
    
    for header in trace_headers:
        if header in headers:
            trace_context[header] = headers[header]
    
    return trace_context


def propagate_trace_context(context: Dict[str, str]) -> Dict[str, str]:
    """
    Propagate trace context to downstream requests
    
    Args:
        context: Trace context to propagate
    
    Returns:
        Headers to add to downstream requests
    """
    headers = {}
    
    for key, value in context.items():
        # Convert header names to standard format
        headers[key] = value
    
    return headers


# ============ Span Utilities ============
class trace_function_call:
    """Decorator to trace function calls"""
    
    def __init__(self, operation_name: Optional[str] = None):
        self.operation_name = operation_name
    
    def __call__(self, func):
        def wrapper(*args, **kwargs):
            op_name = self.operation_name or f"{func.__module__}.{func.__name__}"
            span = TracingContextManager.start_span(op_name)
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                if span:
                    TracingContextManager.set_span_error(span, e)
                raise
            finally:
                if span:
                    TracingContextManager.finish_span(span)
        
        return wrapper


def create_child_span(parent_span, operation_name: str, tags: Optional[Dict[str, Any]] = None):
    """
    Create child span from parent span
    
    Args:
        parent_span: Parent span instance
        operation_name: Child span name
        tags: Optional tags
    
    Returns:
        Child span instance
    """
    if not parent_span or not hasattr(parent_span, 'start_child_span'):
        return None
    
    try:
        child_span = parent_span.start_child_span(operation_name)
        if tags:
            for key, value in tags.items():
                child_span.set_tag(key, value)
        return child_span
    except Exception as e:
        logger.error(f"Failed to create child span: {e}")
        return None


# ============ Service-to-Service Tracing ============
def create_traced_request_headers(trace_context: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Create HTTP headers for traced requests
    
    Args:
        trace_context: Current trace context
    
    Returns:
        Headers dict to add to request
    """
    headers = {}
    
    if trace_context:
        headers.update(propagate_trace_context(trace_context))
    
    # Add custom headers if tracer available
    tracer = TracingContextManager.get_tracer()
    if tracer and hasattr(tracer, 'active_span') and tracer.active_span:
        span = tracer.active_span
        if hasattr(span, 'trace_id'):
            headers['x-trace-id'] = str(span.trace_id)
        if hasattr(span, 'span_id'):
            headers['x-span-id'] = str(span.span_id)
    
    return headers
