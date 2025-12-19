# PipeDesk Google Integrations Backend

FastAPI service that connects the PipeDesk CRM to Google Drive, Calendar, Gmail, and Tasks. It validates Supabase JWTs, enforces RBAC, and keeps local metadata in sync for timelines and automation.

## Features
- Drive hierarchy management for companies, leads, and deals with mock or real Google Drive backends.
- Calendar CRUD with Meet link generation, webhook sync, and local `CalendarEvent` storage.
- Gmail read/write operations (messages, threads, labels, drafts, attachments) plus timeline exposure.
- Google Tasks listing and mutation per tasklist.
- CRM communication and unified timeline endpoints merging Gmail, Calendar, and audit logs.
- Automation endpoints that pull Gmail attachments into Drive.
- Health checks and Prometheus metrics.

## Documentation
All documentation now lives under [`docs/`](docs/README.md):
- `overview.md` – product overview.
- `setup.md` – environment variables and local run instructions.
- `architecture.md` – routers, services, and workers.
- `security.md` – JWT and RBAC model.
- `api/` – endpoint references for Drive, Calendar, Gmail, Tasks, CRM communication, Timeline, Automation, and Health.
- `operations/` – migrations and soft-delete behavior.

## Getting started
```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Provide the environment variables described in `docs/setup.md` before running. The application exposes OpenAPI docs at `/docs` once started.
