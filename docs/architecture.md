# Architecture

## Application entrypoint
- `main.py` configures FastAPI, CORS, JSON error normalization for `/api` routes, and Prometheus `/metrics` exposure.
- Routers registered in `main.py` cover Drive, Calendar, Gmail, CRM communication, Tasks, Timeline, Automation, Health, and webhook handling.
- Startup lifecycle registers audit log listeners, optionally runs migrations (`migrations/add_soft_delete_fields.py`, `migrations/create_lead_tags_table.py`), and starts a scheduler when `SCHEDULER_ENABLED` is true.

## Layers
- **Routers (`routers/`)**: Define HTTP surfaces for each domain (Drive, Calendar, Gmail, Tasks, etc.). Route handlers enforce RBAC via `auth.dependencies` and convert domain objects to response schemas in `schemas/`.
- **Services (`services/`)**: Google API wrappers (`google_drive_real.py`, `google_calendar_service.py`, `google_gmail_service.py`, `google_tasks_service.py`), permission logic (`permission_service.py`), auditing (`audit_service.py`), search helpers, and automation utilities.
- **Database (`database.py`, `models.py`)**: SQLAlchemy session factory plus models for Drive files/folders, calendar events, audit logs, leads/deals, webhook channels, and supporting tables.
- **Caching (`cache.py`)**: Optional Redis cache with invalidation hooks used by Drive listings and search.
- **Auth (`auth/`)**: JWT validation against `settings.SUPABASE_JWT_SECRET` and role parsing; dependencies guard routes with minimum roles.
- **Utilities (`utils/`)**: Structured logging, Prometheus registry wrapper, retry helpers, and JSON safe conversions for Google APIs.

## Background processing
- `services/scheduler_service.py` wires apscheduler workers defined in `services/workers.py` (SLA/lead priority/lead engagement jobs) when enabled.
- Webhook ingestion (`routers/webhooks.py`) syncs Drive and Calendar changes back into local models using real Google clients.

## Data flow (example: Drive list)
1. Request hits `/api/drive/{entity_type}/{entity_id}` with JWT; dependencies parse user context.
2. `HierarchyService` ensures the entity root folder exists (mock or real Drive backend) and maps it in `DriveFolder`.
3. Drive client lists files; soft-deleted entries in the database are filtered unless `include_deleted` is requested.
4. PermissionService resolves the requester’s Drive permission string (reader/writer/owner) for the entity type.
5. Response returns paginated `DriveResponse` with breadcrumbs and permission marker.
