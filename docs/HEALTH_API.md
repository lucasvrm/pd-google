# Health Check API Documentation

This document describes the health check endpoints available in the PipeDesk Google Drive Backend for monitoring service health and availability.

## Overview

The Health Check API provides endpoints to monitor the health status of various Google API integrations (Calendar, Gmail) and the overall system health. These endpoints are designed to be lightweight and suitable for use in monitoring systems, load balancers, and automated health checks.

## Endpoints

### GET /health

**General health check endpoint** that aggregates the health status of all services.

#### Response

```json
{
  "overall_status": "healthy",
  "timestamp": "2025-12-09T01:22:31.816Z",
  "services": {
    "calendar": {
      "status": "healthy",
      "active_channels": 2,
      "last_sync": "2025-12-09T01:20:00.000Z"
    },
    "gmail": {
      "status": "healthy",
      "auth_ok": true,
      "api_reachable": true
    }
  }
}
```

#### Response Fields

- **overall_status** (string): Overall system health status
  - `healthy`: All services are operational
  - `degraded`: At least one service is degraded, none unhealthy
  - `unhealthy`: At least one service is unhealthy
- **timestamp** (string): ISO 8601 timestamp of the health check
- **services** (object): Health status of individual services
  - **calendar** (object): Calendar service health
    - **status** (string): Calendar service status
    - **active_channels** (number): Number of active webhook channels
    - **last_sync** (string|null): Timestamp of last sync activity
  - **gmail** (object): Gmail service health
    - **status** (string): Gmail service status
    - **auth_ok** (boolean): Whether Gmail authentication is configured correctly
    - **api_reachable** (boolean): Whether Gmail API is accessible

#### Status Codes

- **200 OK**: Health check completed (status may be healthy, degraded, or unhealthy)

#### Usage Example

```bash
curl http://localhost:8000/health
```

---

### GET /health/calendar

**Calendar-specific health check** that monitors the Calendar API integration and webhook channels.

#### Response

```json
{
  "service": "calendar",
  "status": "healthy",
  "timestamp": "2025-12-09T01:22:31.816Z",
  "active_channels": 2,
  "last_sync": "2025-12-09T01:20:00.000Z",
  "event_count": 150,
  "oldest_event": "2025-06-01T10:00:00.000Z",
  "newest_event": "2025-12-31T18:00:00.000Z"
}
```

#### Response Fields

- **service** (string): Always "calendar"
- **status** (string): Calendar service health status
  - `healthy`: Service is fully operational
  - `degraded`: Service is operational but with issues (e.g., no active webhook channels)
  - `unhealthy`: Service is not operational
- **timestamp** (string): ISO 8601 timestamp of the health check
- **active_channels** (number): Number of active, non-expired webhook channels
- **last_sync** (string|null): Timestamp of last successful sync (if available)
- **event_count** (number): Total number of active (non-cancelled) events in database
- **oldest_event** (string|null): Start time of oldest active event (if any)
- **newest_event** (string|null): Start time of newest active event (if any)
- **issues** (array, optional): List of issues when status is degraded or unhealthy

#### Health Criteria

The Calendar service is considered:
- **Healthy**: Active webhook channels exist and sync activity is recent
- **Degraded**: 
  - No active webhook channels
  - No sync activity recorded
  - Other operational issues

#### Status Codes

- **200 OK**: Health check completed

#### Usage Example

```bash
curl http://localhost:8000/health/calendar
```

---

### GET /health/gmail

**Gmail-specific health check** that verifies Gmail API credentials, scopes, and connectivity.

#### Response

```json
{
  "service": "gmail",
  "status": "healthy",
  "timestamp": "2025-12-09T01:22:31.816Z",
  "auth_ok": true,
  "api_reachable": true,
  "configured_scopes": [
    "https://www.googleapis.com/auth/gmail.readonly"
  ]
}
```

#### Response Fields

- **service** (string): Always "gmail"
- **status** (string): Gmail service health status
  - `healthy`: Service is fully operational
  - `degraded`: Service is partially operational (auth OK but API issues)
  - `unhealthy`: Service is not operational (auth failed or not configured)
- **timestamp** (string): ISO 8601 timestamp of the health check
- **auth_ok** (boolean): Whether Gmail credentials and scopes are configured correctly
- **api_reachable** (boolean): Whether Gmail API is accessible and responding
- **configured_scopes** (array): List of Gmail API scopes configured for the service
- **issues** (array, optional): List of issues when status is degraded or unhealthy

#### Health Criteria

The Gmail service is considered:
- **Healthy**: Credentials configured correctly AND API is reachable
- **Degraded**: Credentials configured correctly BUT API is not reachable or returning errors
- **Unhealthy**: 
  - Credentials not configured (GOOGLE_SERVICE_ACCOUNT_JSON missing)
  - Failed to initialize Gmail service
  - Critical authentication errors

#### API Call Details

The health check performs a lightweight call to the Gmail API to verify connectivity:
- **Operation**: `list_labels()` - Lists Gmail labels for the authenticated user
- **Performance**: Very lightweight, typically <100ms
- **Purpose**: Verifies both authentication and API accessibility without retrieving large datasets

#### Status Codes

- **200 OK**: Health check completed

#### Usage Example

```bash
curl http://localhost:8000/health/gmail
```

---

## Using Health Checks for Monitoring

### Load Balancer Configuration

Health check endpoints can be used by load balancers to determine if an instance is healthy:

**Example (AWS ALB Target Group):**
```
Health Check Path: /health
Health Check Interval: 30 seconds
Healthy Threshold: 2
Unhealthy Threshold: 3
Timeout: 5 seconds
```

**Example (Google Cloud Load Balancer):**
```yaml
healthCheck:
  type: HTTP
  requestPath: /health
  port: 8000
  checkIntervalSec: 30
  timeoutSec: 5
  healthyThreshold: 2
  unhealthyThreshold: 3
```

### Monitoring System Integration

#### Prometheus

Example scrape configuration:

```yaml
scrape_configs:
  - job_name: 'pipedesk-health'
    metrics_path: '/health'
    scrape_interval: 30s
    static_configs:
      - targets: ['pipedesk-backend:8000']
```

You can create a custom exporter to convert health check responses to Prometheus metrics.

#### Datadog

Example Python integration:

```python
import requests
from datadog import statsd

response = requests.get('http://localhost:8000/health')
data = response.json()

# Send overall status
status_map = {'healthy': 0, 'degraded': 1, 'unhealthy': 2}
statsd.gauge('pipedesk.health.overall', status_map.get(data['overall_status'], 2))

# Send service-specific metrics
for service, details in data['services'].items():
    statsd.gauge(f'pipedesk.health.{service}', status_map.get(details['status'], 2))
```

#### Nagios/Icinga

Example check command:

```bash
#!/bin/bash
RESPONSE=$(curl -s http://localhost:8000/health)
STATUS=$(echo $RESPONSE | jq -r '.overall_status')

case $STATUS in
  "healthy")
    echo "OK - All services healthy"
    exit 0
    ;;
  "degraded")
    echo "WARNING - Some services degraded"
    exit 1
    ;;
  "unhealthy")
    echo "CRITICAL - One or more services unhealthy"
    exit 2
    ;;
  *)
    echo "UNKNOWN - Unable to determine health status"
    exit 3
    ;;
esac
```

### Alerting Rules

Example alerting conditions:

1. **Critical Alert**: Overall status is "unhealthy" for more than 5 minutes
2. **Warning Alert**: Overall status is "degraded" for more than 15 minutes
3. **Info Alert**: Individual service transitions from healthy to degraded

### Automation and Scripts

#### Kubernetes Liveness Probe

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

#### Kubernetes Readiness Probe

```yaml
readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 3
  successThreshold: 1
  failureThreshold: 2
```

#### Shell Script for Monitoring

```bash
#!/bin/bash
# health_monitor.sh - Simple health monitoring script

ENDPOINT="http://localhost:8000/health"
ALERT_EMAIL="ops@example.com"

while true; do
  RESPONSE=$(curl -s "$ENDPOINT")
  STATUS=$(echo "$RESPONSE" | jq -r '.overall_status')
  
  if [ "$STATUS" = "unhealthy" ]; then
    echo "ALERT: System is unhealthy!" | mail -s "PipeDesk Health Alert" "$ALERT_EMAIL"
  fi
  
  sleep 60
done
```

## Best Practices

1. **Polling Frequency**: 
   - General monitoring: Every 30-60 seconds
   - Load balancer checks: Every 10-30 seconds
   - Don't poll more frequently than every 5 seconds to avoid unnecessary load

2. **Timeout Configuration**:
   - Set timeouts to 5 seconds or less
   - Health checks are designed to be fast (<1 second typically)

3. **Response Interpretation**:
   - `healthy`: Service is fully operational, no action needed
   - `degraded`: Service is operational but may need attention soon
   - `unhealthy`: Service requires immediate attention

4. **Service-Specific Checks**:
   - Use `/health/calendar` or `/health/gmail` for targeted monitoring
   - Use `/health` for overall system health

5. **Structured Logging**:
   - All health check operations are logged using structured logging
   - Check application logs for detailed health check history and issues

## Troubleshooting

### "unhealthy" Status for Gmail

**Possible causes:**
- `GOOGLE_SERVICE_ACCOUNT_JSON` environment variable not set
- Invalid or corrupted service account credentials
- Service account lacks necessary Gmail API permissions
- Gmail API not enabled in Google Cloud Console

**Resolution:**
1. Verify environment variable is set: `echo $GOOGLE_SERVICE_ACCOUNT_JSON`
2. Check service account has Gmail API access enabled
3. Ensure scopes include `https://www.googleapis.com/auth/gmail.readonly`
4. Review application logs for detailed error messages

### "degraded" Status for Gmail

**Possible causes:**
- Gmail API quota exceeded
- Network connectivity issues
- Temporary Google API outage
- Service account permissions changed

**Resolution:**
1. Check Google Cloud Console for API quota usage
2. Verify network connectivity to Google APIs
3. Review recent changes to service account permissions
4. Monitor Google API status page

### "degraded" Status for Calendar

**Possible causes:**
- No active webhook channels registered
- All webhook channels have expired
- Calendar sync process not running

**Resolution:**
1. Check `active_channels` field in response
2. Register new webhook channels if needed
3. Ensure calendar sync scheduler is running
4. Review webhook configuration in Google Cloud Console

## Related Documentation

- [Calendar API Documentation](./CALENDAR_API.md)
- [Gmail API Documentation](../GMAIL_API.md)
- [Webhook Documentation](../README.md#webhooks-do-google-drive)
- [Deployment Guide](../README.md#deploy)

## Changelog

### 2025-12-09
- Added Gmail health check endpoint (`/health/gmail`)
- Added general health check endpoint (`/health`)
- Implemented structured logging for health checks
- Created comprehensive health check documentation

### Earlier
- Initial Calendar health check endpoint (`/health/calendar`)
