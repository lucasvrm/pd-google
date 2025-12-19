# Migrations

Two idempotent migrations can run automatically during startup when `RUN_MIGRATIONS_ON_STARTUP=true`:
- `migrations/add_soft_delete_fields.py` – Adds soft-delete columns to `drive_files`.
- `migrations/create_lead_tags_table.py` – Creates lead tag mapping tables when missing.

For new databases, run:
```bash
python init_db.py
```

Additional migrations (lead qualification fields, soft delete for leads) live under `migrations/` and should be executed from the application environment when corresponding features are enabled in the main CRM database. Production deployments should monitor startup logs to verify successful execution.
