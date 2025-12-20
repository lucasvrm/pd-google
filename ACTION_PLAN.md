# ACTION PLAN: PipeDesk Google Integrations

This plan tracks the backend integration work for Google Drive, Calendar, Gmail, Tasks, and CRM timelines.

## Strategic priorities
1. **Auditability** – Preserve change history for CRM entities and Drive actions.
2. **Unified timeline** – Deliver a consolidated feed of calendar events, audit logs, and Gmail messages.
3. **Security** – Enforce JWT validation and RBAC before touching Google APIs or database state.

## Phase summary
- **Phase 1: Calendar foundation** – ✅ Implemented Calendar models, service, CRUD endpoints, and webhook registration.
- **Phase 2: CRM core (Audit & RBAC)** – 🟡 Audit listeners and RBAC dependencies are live; an audit log query API remains pending.
- **Phase 3: Unified timeline** – ✅ Timeline endpoint merges Calendar events, Gmail messages, and audit logs for CRM entities.
- **Phase 4: Sync & monitoring** – 🟢 Webhook handling for Drive/Calendar is active; health checks and Prometheus metrics are exposed.
- **Phase 5: Automation & SLA** – 🟡 Email automation endpoints exist; SLA/priority workers are wired but feature-flagged via the scheduler.

## Current implementation highlights
- Drive hierarchy endpoints with soft delete, permissions management, search, and repair flows.
- Calendar endpoints with Meet link creation, alias-aware payloads, and local persistence.
- Gmail read/write endpoints plus attachment download support.
- Google Tasks CRUD for tasklists.
- CRM communication and timeline surfaces for lead/deal/contact views.
- Automation endpoints to move Gmail attachments into Drive.
- **Lead change owner endpoint** – `POST /api/leads/{lead_id}/change-owner` for transferring lead ownership with RBAC validation and audit logging.

## Pending items
- Expose audit log query endpoints for admins/managers.
- Add rate limiting for sensitive routes.
- Harden caching strategy for timeline-heavy views.
- Add `lead_members` table and collaborator tracking (deferred - table does not exist).
- Add email notification for lead owner changes (deferred - notification service not implemented).

## Documentation
All docs have been consolidated under `docs/` with updated references to the current codebase:
- `docs/overview.md` – capability overview.
- `docs/api/` – per-router endpoint references.
- `docs/operations/` – migrations and soft delete behavior.
