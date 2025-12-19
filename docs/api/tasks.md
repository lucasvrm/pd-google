# Google Tasks API

Prefix: `/api/tasks`

## Endpoints
- `GET /` – List tasks for a provided `project_id` (tasklist) with optional due date range, pagination token, and `include_completed` flag.
- `POST /` – Create a task in a tasklist.
- `PATCH /{task_id}` – Update title/notes/status/due date for a task.
- `DELETE /{task_id}` – Delete a task from the tasklist.

`services.google_tasks_service.GoogleTasksService` wraps the Google Tasks API; authentication comes from the same service account impersonation model used for Gmail/Calendar. Route access is protected by `get_current_user`.
