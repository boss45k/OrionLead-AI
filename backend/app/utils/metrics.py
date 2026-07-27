"""
Prometheus Metrics Module
Exports application metrics for monitoring and alerting
"""

from prometheus_client import (
    Counter, Histogram, Gauge, Summary, CollectorRegistry,
    generate_latest, REGISTRY, CONTENT_TYPE_LATEST
)
from functools import wraps
from time import time
from typing import Optional
from flask import g
import logging

logger = logging.getLogger(__name__)


class MetricsRegistry:
    """Central metrics registry for the application"""
    
    # ============ Request/Response Metrics ============
    request_count = Counter(
        'http_requests_total',
        'Total HTTP requests',
        ['method', 'endpoint', 'status_code']
    )
    
    request_duration_seconds = Histogram(
        'http_request_duration_seconds',
        'HTTP request duration in seconds',
        ['method', 'endpoint', 'status_code'],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
    )
    
    request_size_bytes = Summary(
        'http_request_size_bytes',
        'HTTP request size in bytes',
        ['method', 'endpoint']
    )
    
    response_size_bytes = Summary(
        'http_response_size_bytes',
        'HTTP response size in bytes',
        ['method', 'endpoint', 'status_code']
    )
    
    # ============ Error Metrics ============
    errors_total = Counter(
        'errors_total',
        'Total number of errors',
        ['error_type', 'error_code', 'endpoint']
    )
    
    exceptions_total = Counter(
        'exceptions_total',
        'Total number of exceptions',
        ['exception_type', 'endpoint']
    )
    
    # ============ Authentication Metrics ============
    auth_login_attempts = Counter(
        'auth_login_attempts_total',
        'Total login attempts',
        ['status']  # success, failed
    )
    
    auth_registrations = Counter(
        'auth_registrations_total',
        'Total user registrations',
        ['status']  # success, failed
    )
    
    auth_token_validations = Counter(
        'auth_token_validations_total',
        'Total token validations',
        ['status']  # valid, expired, invalid
    )
    
    # ============ Lead Metrics ============
    leads_created = Counter(
        'leads_created_total',
        'Total leads created'
    )
    
    leads_qualified = Counter(
        'leads_qualified_total',
        'Total leads qualified'
    )
    
    leads_total_in_system = Gauge(
        'leads_total',
        'Total leads in system by status',
        ['status']
    )
    
    qualification_score_distribution = Histogram(
        'qualification_score',
        'Distribution of qualification scores',
        buckets=(0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100)
    )
    
    # ============ AI Agent Metrics ============
    agent_qualifications_total = Counter(
        'agent_qualifications_total',
        'Total lead qualifications by agent',
        ['agent_name', 'status']  # success, failed
    )
    
    agent_qualification_duration = Histogram(
        'agent_qualification_duration_seconds',
        'Duration of lead qualification',
        ['agent_name'],
        buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0)
    )
    
    agent_batch_qualifications = Counter(
        'agent_batch_qualifications_total',
        'Total batch qualifications',
        ['status', 'batch_size']  # success, partial_failure, failed
    )
    
    agent_llm_calls = Counter(
        'agent_llm_calls_total',
        'Total LLM API calls',
        ['service', 'model', 'status']  # OpenAI, Anthropic; success, failed
    )
    
    agent_llm_tokens = Counter(
        'agent_llm_tokens_total',
        'Total LLM tokens used',
        ['service', 'model', 'token_type']  # input_tokens, output_tokens
    )
    
    # ============ Database Metrics ============
    db_query_duration = Histogram(
        'db_query_duration_seconds',
        'Database query duration',
        ['query_type'],  # select, insert, update, delete
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0)
    )
    
    db_connections_active = Gauge(
        'db_connections_active',
        'Active database connections'
    )
    
    db_connections_pooled = Gauge(
        'db_connections_pooled',
        'Pooled database connections'
    )
    
    db_errors = Counter(
        'db_errors_total',
        'Database errors',
        ['error_type']  # connection, timeout, constraint, etc
    )
    
    # ============ Cache Metrics ============
    cache_hits = Counter(
        'cache_hits_total',
        'Cache hits by key_type',
        ['key_type']  # query, session, etc
    )
    
    cache_misses = Counter(
        'cache_misses_total',
        'Cache misses by key_type',
        ['key_type']
    )
    
    cache_evictions = Counter(
        'cache_evictions_total',
        'Cache evictions',
        ['key_type']
    )
    
    cache_operations_duration = Histogram(
        'cache_operations_duration_seconds',
        'Cache operation duration',
        ['operation']  # get, set, delete
    )
    
    # ============ Queue/Celery Metrics ============
    celery_tasks_total = Counter(
        'celery_tasks_total',
        'Total Celery tasks',
        ['task_name', 'status']  # success, failed, retry
    )
    
    celery_task_duration = Histogram(
        'celery_task_duration_seconds',
        'Celery task duration',
        ['task_name']
    )
    
    celery_queue_size = Gauge(
        'celery_queue_size',
        'Celery queue size',
        ['queue_name']
    )
    
    # ============ System Metrics ============
    system_uptime_seconds = Gauge(
        'system_uptime_seconds',
        'Application uptime in seconds'
    )
    
    system_info = Gauge(
        'system_info',
        'System information',
        ['environment', 'version', 'api_version']
    )


def track_request_metrics(f):
    """Decorator to track HTTP request metrics"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import request
        start_time = time()
        
        try:
            result = f(*args, **kwargs)
            
            # Extract response info - Flask handlers can return (data, status_code) or Response object
            status_code = 200
            if isinstance(result, tuple) and len(result) > 1:
                status_code = int(result[1]) if isinstance(result[1], int) else 200
            else:
                # Try to get status_code attribute from Response object
                try:
                    status_code = int(getattr(result, 'status_code', 200))
                except (AttributeError, ValueError, TypeError):
                    status_code = 200
            method = request.method
            endpoint = request.path
            
            # Record metrics
            duration = time() - start_time
            MetricsRegistry.request_duration_seconds.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code
            ).observe(duration)
            
            MetricsRegistry.request_count.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code
            ).inc()
            
            if hasattr(request, 'content_length') and request.content_length:
                MetricsRegistry.request_size_bytes.labels(
                    method=method,
                    endpoint=endpoint
                ).observe(request.content_length)
            
            return result
            
        except Exception as e:
            duration = time() - start_time
            status_code = 500
            method = request.method
            endpoint = request.path
            
            MetricsRegistry.request_duration_seconds.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code
            ).observe(duration)
            
            MetricsRegistry.exceptions_total.labels(
                exception_type=type(e).__name__,
                endpoint=endpoint
            ).inc()
            
            raise
    
    return decorated_function


def track_authentication(status: str):
    """Track authentication attempts"""
    if status == 'login_success':
        MetricsRegistry.auth_login_attempts.labels(status='success').inc()
    elif status == 'login_failed':
        MetricsRegistry.auth_login_attempts.labels(status='failed').inc()
    elif status == 'registration_success':
        MetricsRegistry.auth_registrations.labels(status='success').inc()
    elif status == 'registration_failed':
        MetricsRegistry.auth_registrations.labels(status='failed').inc()
    elif status == 'token_valid':
        MetricsRegistry.auth_token_validations.labels(status='valid').inc()
    elif status == 'token_expired':
        MetricsRegistry.auth_token_validations.labels(status='expired').inc()
    elif status == 'token_invalid':
        MetricsRegistry.auth_token_validations.labels(status='invalid').inc()


def track_lead_operation(operation: str, **kwargs):
    """Track lead operations"""
    if operation == 'created':
        MetricsRegistry.leads_created.inc()
    elif operation == 'qualified':
        MetricsRegistry.leads_qualified.inc()
        if 'score' in kwargs:
            MetricsRegistry.qualification_score_distribution.observe(kwargs['score'])


def track_qualification(agent_name: str, status: str, duration: Optional[float] = None):
    """Track qualification operations"""
    MetricsRegistry.agent_qualifications_total.labels(
        agent_name=agent_name,
        status=status
    ).inc()
    
    if duration is not None:
        MetricsRegistry.agent_qualification_duration.labels(
            agent_name=agent_name
        ).observe(duration)


def track_llm_call(service: str, model: str, status: str, 
                   input_tokens: int = 0, output_tokens: int = 0):
    """Track LLM API calls"""
    MetricsRegistry.agent_llm_calls.labels(
        service=service,
        model=model,
        status=status
    ).inc()
    
    if input_tokens > 0:
        MetricsRegistry.agent_llm_tokens.labels(
            service=service,
            model=model,
            token_type='input_tokens'
        ).inc(input_tokens)
    
    if output_tokens > 0:
        MetricsRegistry.agent_llm_tokens.labels(
            service=service,
            model=model,
            token_type='output_tokens'
        ).inc(output_tokens)


def track_cache_operation(operation: str, key_type: str, hit: Optional[bool] = None, duration: Optional[float] = None):
    """Track cache operations"""
    if hit is True:
        MetricsRegistry.cache_hits.labels(key_type=key_type).inc()
    elif hit is False:
        MetricsRegistry.cache_misses.labels(key_type=key_type).inc()
    
    if duration is not None:
        MetricsRegistry.cache_operations_duration.labels(
            operation=operation
        ).observe(duration)


def track_database_query(query_type: str, duration: float, error: bool = False):
    """Track database queries"""
    MetricsRegistry.db_query_duration.labels(
        query_type=query_type
    ).observe(duration)
    
    if error:
        MetricsRegistry.db_errors.labels(
            error_type='query_error'
        ).inc()


def track_error(error_type: str, error_code: Optional[str] = None, endpoint: Optional[str] = None):
    """Track errors"""
    MetricsRegistry.errors_total.labels(
        error_type=error_type,
        error_code=error_code or 'UNKNOWN',
        endpoint=endpoint or 'unknown'
    ).inc()


def get_metrics_export():
    """Generate Prometheus metrics in text format"""
    return generate_latest(REGISTRY)


# ============ Utility Functions ============
def record_user_metric(user_id: int, metric_name: str, value: float):
    """Record user-specific metrics"""
    # Can be extended for per-user tracking
    pass


def record_business_metric(metric_name: str, value: float, **labels):
    """Record business metrics"""
    # Custom business metrics
    pass
