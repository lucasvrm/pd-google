# Health and metrics

## Health checks
- `GET /health` – Aggregated status across subsystems.
- `GET /health/calendar` – Calendar connectivity and channel status.
- `GET /health/gmail` – Gmail connectivity status.

All endpoints use `HealthService` and return JSON structures suitable for uptime monitoring.

## Metrics
- `GET /metrics` – Prometheus exposition endpoint registered in `main.py` using the custom registry in `utils/prometheus`.
