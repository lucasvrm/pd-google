# Security

## Authentication
- JWTs are validated with `SUPABASE_JWT_SECRET` using HS256 in `auth/jwt.py`.
- `auth.dependencies` exposes helpers such as `get_current_user`, `get_current_user_with_role`, and `require_manager_or_above` to inject `UserContext` into routes.
- Requests missing or failing validation receive `401`/`403` responses; `/api` routes also normalize error bodies via middleware in `main.py`.

## RBAC
- Roles map to Drive permissions through `services.permission_service.PermissionService` with a numeric hierarchy (admin 100, manager 75, sales/analyst 50, viewer 10).
- Drive endpoints compute `reader`/`writer`/`owner` permissions per entity type, blocking destructive actions for insufficient roles.
- Sensitive endpoints (e.g., folder delete, automation writes) use role-checked dependencies to prevent accidental elevation.

## Data protections
- Soft deletion is used for Drive files/folders and qualified leads; hard deletes against Google APIs are avoided in API handlers.
- Input validation relies on Pydantic schemas per router; validation errors for `/api` routes return structured JSON.
- CORS origins are normalized via `normalize_cors_origins` to avoid wildcard exposure; optional regex support handles preview deployments.
