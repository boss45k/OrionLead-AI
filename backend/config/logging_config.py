import logging
import os
import json
from datetime import datetime
from logging.handlers import RotatingFileHandler


class _RequestIdFilter(logging.Filter):
    """Inject a default request_id / api_version into every log record
    so formatters that reference these fields never raise KeyError."""

    def filter(self, record):
        if not hasattr(record, 'request_id'):
            record.request_id = '-'
        if not hasattr(record, 'api_version'):
            record.api_version = '-'
        return True

try:
    from pythonjsonlogger import jsonlogger  
    HAS_JSON_LOGGER = True
except ImportError:
    HAS_JSON_LOGGER = False


if HAS_JSON_LOGGER:
    class CustomJsonFormatter(jsonlogger.JsonFormatter):  # type: ignore[attr-defined]
        """
        Custom JSON formatter that includes additional context
        Adds request_id, user_id, and other contextual information to logs
        """
        
        def add_fields(self, log_record, record, message_dict):
            """Add custom fields to log record"""
            super().add_fields(log_record, record, message_dict)
            
            # Add timestamp in ISO format
            log_record['timestamp'] = datetime.utcnow().isoformat() + 'Z'
            
            # Add hostname
            import socket
            log_record['hostname'] = socket.gethostname()
            
            # Add environment
            log_record['environment'] = os.getenv('FLASK_ENV', 'development')
            
            # Add application version
            log_record['app_version'] = '1.0.0'
            
            # Add API version if available
            try:
                from flask import g
                if hasattr(g, 'api_version'):
                    log_record['api_version'] = g.api_version
                if hasattr(g, 'request_id'):
                    log_record['request_id'] = g.request_id
            except (RuntimeError, ImportError):
                pass
else:
    # Fallback JSON formatter when pythonjsonlogger not available
    class CustomJsonFormatterFallback(logging.Formatter):
        """Fallback JSON formatter (text-based)"""
        
        def format(self, record):
            log_data = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'level': record.levelname,
                'name': record.name,
                'message': record.getMessage(),
                'environment': os.getenv('FLASK_ENV', 'development'),
                'app_version': '1.0.0',
            }
            return json.dumps(log_data)
    
    # Alias for compatibility
    CustomJsonFormatter = CustomJsonFormatterFallback  # type: ignore[assignment]


def setup_logging(app):
    """Setup comprehensive logging configuration with JSON support"""
    
    # Create logs directory if it doesn't exist
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Get log level from environment
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    is_json_logs = os.getenv('JSON_LOGS', 'false').lower() == 'true'
    
    # ============ Root Logger Setup ============
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # ============ Application Logger Setup ============
    logger = logging.getLogger('ai_lead_system')
    logger.setLevel(getattr(logging, log_level))
    
    # ============ JSON File Handler (Production) ============
    json_file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'app.json.log'),
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    json_file_handler.setLevel(logging.INFO)
    json_formatter = CustomJsonFormatter(
        fmt='%(timestamp)s %(level)s %(name)s %(message)s %(request_id)s %(api_version)s',
        datefmt='ISO8601'
    )
    json_file_handler.setFormatter(json_formatter)
    
    # ============ Text File Handler (Development/Debugging) ============
    text_file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'app.log'),
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    text_file_handler.setLevel(logging.DEBUG)
    text_formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)-8s | %(request_id)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    text_file_handler.setFormatter(text_formatter)
    
    # ============ Console Handler ============
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level))
    
    if is_json_logs:
        # Use JSON format for console in production
        console_handler.setFormatter(json_formatter)
    else:
        # Use readable format for console in development
        console_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
    
    # ============ Inject default request_id / api_version into every record ============
    _rid_filter = _RequestIdFilter()
    json_file_handler.addFilter(_rid_filter)
    text_file_handler.addFilter(_rid_filter)

    # ============ Add Handlers to Logger ============
    logger.addHandler(json_file_handler)  # Always log to JSON file
    logger.addHandler(text_file_handler)  # Always log to text file
    logger.addHandler(console_handler)    # Always log to console (format depends on env)
    
    # ============ Suppress Verbose Logs from Third-party Libraries ============
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('flasgger').setLevel(logging.WARNING)
    logging.getLogger('celery').setLevel(logging.WARNING)
    
    logger.info("[OK] Logging initialized", extra={
        'environment': os.getenv('FLASK_ENV', 'development'),
        'log_level': log_level,
        'json_logs_enabled': is_json_logs,
    })
    
    return logger

