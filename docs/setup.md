# Setup

## Requirements
- Python 3.12
- PostgreSQL database reachable by `DATABASE_URL`
- (Optional) Redis instance if `REDIS_CACHE_ENABLED=true`

Install dependencies:
```bash
pip install -r requirements.txt
```

Run locally:
```bash
uvicorn main:app --reload
```

## Environment variables
The service reads configuration from `config.py` via `config.Config`:

- `DATABASE_URL` – PostgreSQL connection string.
- `GOOGLE_SERVICE_ACCOUNT_JSON` – Full JSON for the service account with Drive/Calendar/Gmail/Tasks scopes.
- `USE_MOCK_DRIVE` – `true` to use the in-memory mock Drive service for development.
- `DRIVE_ROOT_FOLDER_ID` – Root folder ID to create entity hierarchies under (required for real Drive).
- `WEBHOOK_BASE_URL` / `WEBHOOK_SECRET` – Base URL and shared secret for Google webhook validation.
- `REDIS_URL`, `REDIS_CACHE_ENABLED`, `REDIS_DEFAULT_TTL` – Cache configuration.
- `CORS_ORIGINS`, `CORS_ORIGIN_REGEX` – Allowed origins or regex for FastAPI CORS middleware.
- `CALENDAR_EVENT_RETENTION_DAYS` – Days to retain calendar events in the local database.
- `SLA_BREACH_THRESHOLD_HOURS` – Threshold for SLA worker logic.
- `SCHEDULER_ENABLED` – Enable/disable background workers.
- `RUN_MIGRATIONS_ON_STARTUP` – Execute bundled migrations during startup.
- `GOOGLE_IMPERSONATE_EMAIL` – User email to impersonate for Workspace access.
- `SUPABASE_JWT_SECRET` – Secret to validate Supabase-issued JWTs for all authenticated routes.

## Running migrations
On startup, `main.py` runs idempotent migrations for Drive soft-delete fields and lead tags when `RUN_MIGRATIONS_ON_STARTUP` is enabled. For new database setups you can also execute `python init_db.py` to create base tables. Additional SQL changes live under `migrations/`.
