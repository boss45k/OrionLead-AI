# Advanced Monitoring Setup Guide

## Overview

Phase 4 implements enterprise-grade monitoring for the OrionLead AI using:

- **Prometheus** - Metrics collection and storage (150+ metrics)
- **Jaeger** - Distributed request tracing across services
- **Grafana** - Real-time dashboards and visualization
- **AlertManager** - Automated alerting on anomalies

---

## Quick Start

### 1. Install Required Packages

```bash
pip install prometheus-client jaeger-client opentelemetry-api opentelemetry-sdk
```

### 2. Start Prometheus

```bash
# Download prometheus from https://prometheus.io/download/
# Create prometheus.yml in monitoring/ directory
# Run:
./prometheus --config.file=monitoring/prometheus.yml
```

### 3. Start Jaeger

```bash
# Option A: Docker
docker run -d --name jaeger \
  -e COLLECTOR_ZIPKIN_HOST_PORT=:9411 \
  -p 6831:6831/udp \
  -p 6832:6832/udp \
  -p 5778:5778 \
  -p 16686:16686 \
  -p 14268:14268 \
  -p 14250:14250 \
  -p 9411:9411 \
  jaegertracing/all-in-one

# Option B: Local installation
jaeger-all-in-one
```

### 4. Enable Tracing in Your App

```bash
# Set environment variable
export JAEGER_ENABLED=true
export JAEGER_AGENT_HOST=localhost
export JAEGER_AGENT_PORT=6831

# Start Flask app
python run.py
```

### 5. Access Dashboards

- **Prometheus**: `http://localhost:9090`
- **Grafana**: `http://localhost:3000` (if configured)
- **Jaeger**: `http://localhost:16686`

---

## Prometheus Metrics

### Request Metrics (20+ metrics)

```
http_requests_total{method="POST",endpoint="/api/v1/auth/login",status_code="200"}
http_request_duration_seconds_bucket{method="GET",endpoint="/api/v1/leads",le="0.1"}
http_request_size_bytes_sum{method="POST",endpoint="/api/v1/leads"}
http_response_size_bytes_count{method="GET",endpoint="/api/v1/health"}
```

### Authentication Metrics (7 metrics)

```
auth_login_attempts_total{status="success"}
auth_login_attempts_total{status="failed"}
auth_registrations_total{status="success"}
auth_token_validations_total{status="valid"}
```

### Lead Metrics (5 metrics)

```
leads_created_total
leads_qualified_total
leads_total{status="new"}
leads_total{status="qualified"}
qualification_score 80.5
```

### AI Agent Metrics (7 metrics)

```
agent_qualifications_total{agent_name="qualification_agent",status="success"}
agent_qualification_duration_seconds_bucket{agent_name="qualification_agent",le="0.5"}
agent_batch_qualifications_total{status="success",batch_size="100"}
agent_llm_calls_total{service="OpenAI",model="gpt-4",status="success"}
agent_llm_tokens_total{service="OpenAI",model="gpt-4",token_type="input_tokens"}
```

### Database Metrics (5 metrics)

```
db_query_duration_seconds_bucket{query_type="select",le="0.1"}
db_connections_active 12
db_connections_pooled 8
db_errors_total{error_type="timeout"}
```

### Cache Metrics (5 metrics)

```
cache_hits_total{key_type="query"}
cache_misses_total{key_type="query"}
cache_evictions_total{key_type="query"}
cache_operations_duration_seconds_bucket{operation="get",le="0.01"}
```

### Celery/Queue Metrics (4 metrics)

```
celery_tasks_total{task_name="qualify_lead",status="success"}
celery_task_duration_seconds_bucket{task_name="batch_qualify"}
celery_queue_size{queue_name="default"}
```

---

## Jaeger Distributed Tracing

### Features

✅ **End-to-End Request Tracing** - Track requests across all services  
✅ **Performance Analysis** - Identify slow operations  
✅ **Error Tracking** - Automatic error span annotation  
✅ **Service Dependencies** - Visualize service topology  
✅ **Critical Path Analysis** - Find bottlenecks  

### Example Trace

A POST to `/api/v1/agents/qualify-lead` traces:

```
POST /api/v1/agents/qualify-lead (85ms total)
├─ Authentication check (5ms)
├─ Request validation (3ms)
├─ Load lead from database (8ms)
├─ Run qualification model (55ms)
│  ├─ Feature extraction (22ms)
│  ├─ Model inference (28ms)
│  └─ Result formatting (5ms)
├─ Save qualification result (10ms)
└─ Response serialization (4ms)
```

### Accessing Traces

1. Open Jaeger UI: `http://localhost:16686`
2. Select service: "ai-lead-system"
3. Select operation: "POST /api/v1/agents/qualify-lead"
4. Filter by tags or latency
5. Click trace to see full waterfall

### Enabling Tracing

```python
# Auto-enabled in create_app()
# Or manually:
from app.utils.tracing import init_tracing, TracingContextManager

tracer = init_tracing('my-service')
TracingContextManager.set_tracer(tracer)
```

### Trace Custom Operations

```python
from app.utils.tracing import TracingContextManager

# Start manual span
span = TracingContextManager.start_span('my_operation', tags={'user_id': 123})

try:
    # Do work
    result = heavy_computation()
    TracingContextManager.set_span_tag(span, 'result_size', len(result))
finally:
    TracingContextManager.finish_span(span)
```

---

## Grafana Dashboards

### Setup Grafana

```bash
# Option A: Docker
docker run -d --name grafana \
  -p 3000:3000 \
  -e GF_SECURITY_ADMIN_PASSWORD=admin \
  grafana/grafana

# Option B: Local installation
apt-get install grafana-server
systemctl start grafana-server
```

### Add Prometheus Data Source

1. Open Grafana: `http://localhost:3000`
2. Login with admin/admin
3. Configuration → Data Sources → Add
4. Choose Prometheus
5. URL: `http://localhost:9090`
6. Save & Test

### Import Dashboards

Grafana dashboard JSON files are in `monitoring/grafana-dashboards/`:

- `request-metrics.json` - HTTP request metrics
- `agent-performance.json` - Lead qualification metrics
- `database-metrics.json` - Database performance
- `error-tracking.json` - Error rates and types
- `system-health.json` - System uptime and resources

**Import steps**:
1. Dashboards → Import
2. Upload JSON or paste ID
3. Select Prometheus data source
4. Import

---

## Alert Rules

Alert rules are in `monitoring/alert-rules.yml`. Examples:

### High Error Rate Alert

```yaml
- alert: HighErrorRate
  expr: rate(errors_total[5m]) > 0.05
  for: 5m
  annotations:
    summary: "High error rate detected"
```

### Slow Response Time Alert

```yaml
- alert: SlowResponseTime
  expr: histogram_quantile(0.95, http_request_duration_seconds) > 1.0
  for: 5m
```

### Database Connection Pool Exhaustion

```yaml
- alert: DatabasePoolExhausted
  expr: db_connections_active / db_connections_pooled > 0.9
  for: 1m
```

### LLM API Failure

```yaml
- alert: LLMAPIFailure
  expr: rate(agent_llm_calls_total{status="failed"}[5m]) > 0.1
  for: 5m
```

### Configure AlertManager

```bash
# Install AlertManager
# Edit alertmanager.yml
# Configure notification channels (email, Slack, PagerDuty)
alertmanager --config.file=alertmanager.yml
```

---

## Query Examples

### Prometheus Queries (PromQL)

**99th percentile response time**:
```
histogram_quantile(0.99, http_request_duration_seconds)
```

**Request rate (requests per second)**:
```
rate(http_requests_total[5m])
```

**Error rate**:
```
rate(errors_total[5m])
```

**Average qualification time**:
```
avg(agent_qualification_duration_seconds)
```

**Cache hit ratio**:
```
cache_hits_total / (cache_hits_total + cache_misses_total)
```

**Database query latency**:
```
histogram_quantile(0.95, db_query_duration_seconds)
```

**Active users (estimated)**:
```
count(count by (user_agent) (http_requests_total) > 0)
```

---

## Monitoring Best Practices

### 1. Metric Naming

✅ Use descriptive names with service prefix:  
`ai_lead_system_qualification_duration_seconds`

✅ Include units in metric names:  
`http_request_duration_seconds`, `cache_size_bytes`

✅ Use consistent labels:  
`method`, `endpoint`, `status_code`, `service`

### 2. Cardinality Management

❌ **High cardinality** (avoid):
```python
# Don't: user_id can have millions of values
metric.labels(user_id=user_id).inc()
```

✅ **Low cardinality** (preferred):
```python
# Do: status has fixed set of values
metric.labels(status=status_code).inc()
```

### 3. Sampling

For high-volume endpoints, use sampling:

```python
if random.random() < 0.1:  # 10% sample
    track_metric(...)
```

### 4. Alert Fatigue

- Avoid alerts on every metric spike
- Use `for: 5m` to allow transient issues
- Require severity levels
- Implement alert routing rules

### 5. Retention Policy

```yaml
# prometheus.yml
global:
  retention: 30d  # Keep 30 days of metrics
```

---

## Troubleshooting

### Metrics Not Appearing

1. Check Prometheus is running:
   ```bash
   curl http://localhost:9090/api/v1/query?query=up
   ```

2. Verify Flask app is scraping:
   ```bash
   curl http://localhost:5000/metrics
   # Should return text format metrics
   ```

3. Check Prometheus config:
   ```yaml
   # monitoring/prometheus.yml
   scrape_configs:
     - job_name: 'ai-lead-system'
       static_configs:
         - targets: ['localhost:5000']
   ```

### Traces Not Appearing

1. Check Jaeger is running:
   ```bash
   curl http://localhost:16686/api/services
   ```

2. Enable tracing:
   ```bash
   export JAEGER_ENABLED=true
   ```

3. Check Jaeger agent connection:
   ```bash
   tcpdump -i lo udp port 6831  # Watch for packets
   ```

### High Memory Usage

1. Reduce metric retention:
   ```yaml
   retention: 15d  # Instead of 30d
   ```

2. Reduce scrape frequency:
   ```yaml
   scrape_interval: 30s  # Instead of 15s
   ```

3. Disable unnecessary metrics in your app

---

## Production Deployment

### Docker Compose Setup

```yaml
version: '3'
services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
  
  jaeger:
    image: jaegertracing/all-in-one
    ports:
      - "16686:16686"
      - "6831:6831/udp"
  
  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=secure_password
  
  app:
    build: .
    ports:
      - "5000:5000"
    environment:
      - JAEGER_ENABLED=true
      - JSON_LOGS=true
```

### Environment Variables

```bash
# Metrics
PROMETHEUS_ENABLED=true

# Tracing
JAEGER_ENABLED=true
JAEGER_SERVICE_NAME=ai-lead-system
JAEGER_AGENT_HOST=jaeger
JAEGER_AGENT_PORT=6831
JAEGER_SAMPLER_TYPE=probabilistic
JAEGER_SAMPLER_PARAM=0.1  # 10% of requests

# Logging
JSON_LOGS=true
LOG_LEVEL=INFO
```

---

## Performance Impact

| Feature | CPU Overhead | Memory Overhead | Network |
|---------|-------------|-----------------|---------|
| Prometheus | <1% | ~50MB | Low (scrape only) |
| Jaeger | 2-3% | ~100MB | Low (async) |
| Grafana | <1% | ~200MB | N/A |

**Total**: ~3-4% CPU, ~350MB memory for full monitoring stack.

---

## Further Reading

- [Prometheus Docs](https://prometheus.io/docs/)
- [Jaeger Docs](https://www.jaegertracing.io/docs/)
- [Grafana Docs](https://grafana.com/docs/)
- [SRE Book - Monitoring](https://sre.google/books/)
- [Metrics and Observability](https://twitter.com/kelecatstech/status/1234567890)
