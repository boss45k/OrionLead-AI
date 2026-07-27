# Structured JSON Logging Implementation

## Overview

The OrionLead AI now uses structured JSON logging for production environments and human-readable text logging for development. This enables:

- **Machine Parsing**: Log aggregation services (ELK Stack, Splunk, Datadog) can easily parse logs
- **Distributed Tracing**: Request IDs and correlation IDs are logged automatically
- **Performance Monitoring**: Track request latency, response times, and database queries
- **Compliance**: Proper logging for audit trails and regulatory requirements

## Log Format

### Development (Text Format)
```
14:23:45 [INFO    ] ai_lead_system: ✓ Logging initialized
2024-01-15 14:23:46 [GET    ] - /api/v1/leads - 200 OK
2024-01-15 14:23:47 [ERROR  ] ai_lead_system.routes.leads: Lead not found (request_id: 550e8400-e29b-41d4-a716-446655440000)
```

### Production (JSON Format)
```json
{
  "timestamp": "2024-01-15T14:23:45.123Z",
  "level": "INFO",
  "name": "ai_lead_system",
  "message": "✓ Logging initialized",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "api_version": "v1",
  "environment": "production",
  "hostname": "api-server-01",
  "app_version": "1.0.0"
}
```

## Configuration

### Environment Variables

```bash
# Enable JSON logging output
JSON_LOGS=true

# Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL=INFO

# Log file paths (created automatically)
# - logs/app.log (text format)
# - logs/app.json.log (JSON format)
```

### Log Files

All logs are written to the `logs/` directory:

| File | Format | Purpose |
|------|--------|---------|
| `app.log` | Text | Human-readable logs for debugging |
| `app.json.log` | JSON | Machine-parseable logs for aggregation |

Files are rotated automatically at 10MB with up to 10 backup files retained.

## Log Fields

### Standard Fields
| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `timestamp` | ISO8601 | 2024-01-15T14:23:45.123Z | Log entry timestamp |
| `level` | String | INFO, ERROR, WARNING | Log level |
| `name` | String | ai_lead_system.routes.leads | Logger name (module) |
| `message` | String | Lead qualification successful | Log message |
| `hostname` | String | api-server-01 | Server hostname |
| `environment` | String | production | Deployment environment |
| `app_version` | String | 1.0.0 | Application version |

### Request Context Fields
| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `request_id` | UUID | 550e8400-e29b-41d4-a716-446655440000 | Unique request identifier |
| `api_version` | String | v1 | API version used |
| `method` | String | POST | HTTP method |
| `path` | String | /api/v1/leads | Request path |
| `status_code` | Integer | 200 | HTTP response code |
| `duration_ms` | Integer | 123 | Request duration in milliseconds |
| `user_id` | Integer | 42 | Authenticated user ID |

### Event-Specific Fields
| Event | Fields | Example |
|-------|--------|---------|
| Request | method, path, remote_addr, user_agent | POST /api/v1/auth/login from 192.168.1.1 |
| Response | status_code, duration_ms, response_size | Returned 200 in 45ms (2.3KB) |
| Error | error_code, error_type, stack_trace | QUALIFICATION_ERROR: Score calculation failed |
| Database | query_type, table, duration_ms | SELECT leads table in 28ms |

## Usage Examples

### Basic Logging
```python
import logging

logger = logging.getLogger('ai_lead_system')

# Info level
logger.info("User registered successfully", extra={'user_id': 123})

# Error with context
logger.error("Database connection failed", extra={
    'retry_count': 3,
    'error_message': str(e),
    'duration_ms': elapsed_time,
})
```

### Request Context Logging (Automatic)
```
{
  "timestamp": "2024-01-15T14:23:46.234Z",
  "level": "INFO",
  "name": "ai_lead_system.routes.auth",
  "message": "User login successful",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "api_version": "v1",
  "method": "POST",
  "path": "/api/v1/auth/login",
  "user_id": 42,
  "duration_ms": 87,
  "status_code": 200
}
```

### Error Logging
```python
try:
    lead = Lead.query.get(lead_id)
    if not lead:
        raise NotFoundError("Lead", lead_id)
except Exception as e:
    logger.error(
        f"Lead retrieval failed: {str(e)}",
        extra={
            'lead_id': lead_id,
            'error_type': type(e).__name__,
            'request_id': g.request_id,
        },
        exc_info=True  # Include stack trace
    )
```

## Log Aggregation Setup

### Using ELK Stack (Elasticsearch, Logstash, Kibana)

1. **Configure Logstash to parse JSON logs**:
```
input {
  file {
    path => "/var/log/app/app.json.log"
    codec => json
  }
}

filter {
  if [level] == "ERROR" or [level] == "CRITICAL" {
    mutate {
      add_tag => [ "alert" ]
    }
  }
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "app-logs-%{+YYYY.MM.dd}"
  }
}
```

2. **Create Kibana dashboards** to visualize:
   - Request rate over time
   - Error rate by endpoint
   - Response time distribution
   - Error types and causes

### Using Splunk

1. **Add log source**:
```
[app_logs]
disabled = false
interval = 5
index = main
sourcetype = app_json
whitelist.0.path = /var/log/app/app.json.log
```

2. **Create searches** for monitoring:
```
sourcetype=app_json level=ERROR | stats count by message
sourcetype=app_json method=POST | stats avg(duration_ms) by path
sourcetype=app_json status_code>=400 | timechart count by status_code
```

### Using CloudWatch (AWS)

1. **Send logs to CloudWatch**:
```python
import watchtower
import logging

cloudwatch_handler = watchtower.CloudWatchLogHandler()
logger.addHandler(cloudwatch_handler)
```

## Monitoring & Alerts

### Key Metrics to Monitor

1. **Error Rate**
   - Alert if errors > 5 per minute
   - Check `level: ERROR` or `level: CRITICAL`

2. **Response Time (P95)**
   - Alert if P95 duration > 1000ms
   - Analyze slow endpoints

3. **Failed Qualifications**
   - Alert if failure rate > 10%
   - Check `QUALIFICATION_ERROR` messages

4. **Database Connectivity**
   - Alert on `DATABASE_ERROR` or connection timeouts
   - Monitor pool exhaustion

### Sample Alerting Rule (JSON)
```json
{
  "name": "High Error Rate",
  "query": "level: ERROR AND timestamp > now-5m",
  "threshold": 10,
  "action": "email",
  "recipients": ["ops-team@example.com"]
}
```

## Performance Impact

- **JSON Logging**: ~2-5% CPU overhead (minimal)
- **File I/O**: Asyncio batching reduces contention
- **Disk Space**: ~50-100MB per day at INFO level
- **Rotation**: Automatic at 10MB prevents unbounded growth

## Security Considerations

### Sensitive Data Handling

**Never log**:
- Passwords or authentication tokens
- API keys or secrets
- Credit card numbers (PCI-DSS)
- Personally identifiable information (PII)

**Redaction Pattern**:
```python
import re
def redact_sensitive(text):
    # Redact tokens
    text = re.sub(r'(token|password)=\S+', r'\1=***', text)
    # Redact email addresses
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***@***.***', text)
    return text
```

## Troubleshooting

### Logs Not Appearing

1. Check log level configuration
   ```bash
   echo $LOG_LEVEL  # Should be DEBUG or INFO
   ```

2. Verify log directory exists
   ```bash
   ls -la logs/
   ```

3. Check file permissions
   ```bash
   chmod 755 logs/
   chmod 644 logs/*.log
   ```

### Performance Issues from Logging

1. Reduce log level to WARNING:
   ```bash
   LOG_LEVEL=WARNING
   ```

2. Disable JSON logging if not needed:
   ```bash
   JSON_LOGS=false
   ```

3. Lower max log file size (for testing):
   ```
   maxBytes=1048576  # 1MB instead of 10MB
   ```

## Best Practices

1. **Use Structured Extras**: Always use `extra={}` dict for context
2. **Include Request ID**: Automatically added to all logs
3. **Log at Appropriate Level**:
   - DEBUG: Detailed diagnostic info
   - INFO: Confirmation that system is working
   - WARNING: Something unexpected (but not critical)
   - ERROR: Serious problem, function failed
   - CRITICAL: System shutdown needed

4. **Avoid Over-Logging**: Don't log in tight loops
5. **Test Log Parsing**: Verify log aggregation pipeline

## Further Reading

- [Python Logging Documentation](https://docs.python.org/3/library/logging.html)
- [python-json-logger](https://github.com/madzak/python-json-logger)
- [ELK Stack](https://www.elastic.co/what-is/elk-stack)
- [JSON Logging Best Practices](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
