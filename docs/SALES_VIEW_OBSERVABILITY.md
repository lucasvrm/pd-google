# Sales View Observability

The `/api/leads/sales-view` endpoint now emits structured logs and Prometheus-compatible metrics so regressions can be detected early.

## Structured logs
Logs are JSON formatted via `StructuredLogger` using the `lead_sales_view` service. Key fields:

- `route`: `"sales_view"` for correlation.
- `params`: request parameters (page, page_size, filters, owner information).
- `status_code`: HTTP status code returned.
- `item_count`: number of items included in the response (0 for errors).
- `avg_latency_ms` / `last_request_ms`: rolling and per-request latency for quick inspection.

Example messages:
- `sales_view_request` – parameters received.
- `sales_view_metrics` – completion log with latency and item counts.
- `sales_view_query_error` / `sales_view_item_error` – include stack trace (`exc_info=True`).

Logs are emitted under the logger name `pipedesk_drive.lead_sales_view`, so they can be filtered in staging/production log aggregators using that name or `service=lead_sales_view`.

## Metrics
Metrics are exported in Prometheus format via the `/metrics` endpoint.

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `sales_view_requests_total` | Counter | `status_code` | Number of requests by HTTP status code. |
| `sales_view_latency_seconds` | Histogram | — | Request latency buckets (p95/p99 via PromQL `histogram_quantile`). |
| `sales_view_items_returned` | Histogram | — | Distribution of items returned per request. |

### Querying (examples)
- p95 latency: `histogram_quantile(0.95, sum(rate(sales_view_latency_seconds_bucket[5m])) by (le))`
- p99 latency: `histogram_quantile(0.99, sum(rate(sales_view_latency_seconds_bucket[5m])) by (le))`
- Requests by status: `sum(rate(sales_view_requests_total[5m])) by (status_code)`
- Average items returned: `sum(rate(sales_view_items_returned_sum[5m])) / sum(rate(sales_view_items_returned_count[5m]))`

### Staging/production
Ensure the Prometheus scraper (or OpenTelemetry collector with Prometheus receiver) targets the `/metrics` endpoint exposed by the FastAPI service. Metrics are process-local; if running multiple workers, aggregate at the Prometheus level. Logs remain structured JSON and should already flow to the central logging pipeline; filter by service `lead_sales_view` to inspect recent activity or error traces.
