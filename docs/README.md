# PipeDesk Google Integrations Documentation

This folder centralizes the documentation for the PipeDesk Google integrations backend. Use this index to navigate the current guides, references, and operational notes.

## How to use this documentation
- Start with `overview.md` for a product-level summary and architecture.
- Follow `setup.md` to configure environment variables and run the service locally.
- Review `security.md` for authentication, RBAC, and transport concerns.
- Explore the API references in `api/` for route-by-route behavior.
- Check `operations/` for migration and lifecycle routines.

## Document map
- `overview.md` – Capabilities, major components, and cross-cutting concerns.
- `setup.md` – Required tools, environment variables, and running locally.
- `architecture.md` – Application layout, routers, services, and background workers.
- `security.md` – JWT validation, role hierarchy, and HTTP safety defaults.
- `data-models.md` – Key database tables the service writes to.
- `api/` – Endpoint-level references for Drive, Calendar, Gmail, Tasks, CRM communication, Timeline, Automation, and Health/metrics.
- `operations/soft_delete.md` – How soft deletion works for Drive resources and leads.
- `operations/migrations.md` – Built-in migration hooks and when to run them.

All documents reflect the current codebase; retired or speculative features have been removed to avoid drift.
