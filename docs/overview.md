# Overview

The PipeDesk Google backend is a FastAPI service that centralizes Drive file management, Calendar scheduling, Gmail access, Tasks, and CRM communication helpers. It authenticates requests with Supabase-issued JWTs and enforces role-based permissions before touching Google APIs or database state.

Key capabilities:
- **Drive hierarchy management** for companies, leads, and deals (mock or real Google Drive backends).
- **Calendar events** with Meet link creation and webhook-based synchronization into the local database.
- **Gmail access** for listing, reading, sending, and labeling messages plus exposing email data to timelines.
- **Google Tasks support** for listing and mutating tasks within a tasklist.
- **CRM communication helpers** that aggregate calendar and email activity for entities without duplicating data storage.
- **Unified timeline API** that merges audit logs, calendar events, and Gmail messages for CRM entities.
- **Automation endpoints** to scan Gmail messages and store attachments into Drive hierarchies when permissions allow.
- **Health/metrics endpoints** for service monitoring.

This documentation matches the current router and service implementations so teams can rely on it while integrating or maintaining the backend.
