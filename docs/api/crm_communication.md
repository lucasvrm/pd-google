# CRM Communication API

Prefix: `/api/crm`

## Endpoints
- `GET /emails` – Fetch Gmail messages related to an entity by matching contact addresses and optional search filters.
- `GET /events` – List calendar events relevant to an entity.
- `GET /timeline` – Combined view of events and emails for CRM contexts.

`routers/crm_communication.py` orchestrates Google Gmail and Calendar services plus `CRMContactService` to resolve entity contacts. Results are read-only and respect permissions derived from `PermissionService` and the caller’s JWT role.
