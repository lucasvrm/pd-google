from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from routers import (
    drive,
    webhooks,
    calendar,
    drive_items_adapter,
    gmail,
    health,
    crm_communication,
    tasks,
    leads,
)
from database import engine
import models
from services.scheduler_service import scheduler_service
from contextlib import asynccontextmanager
import logging
import asyncio
from config import config

# Configure Logging
import logging_config # This initializes logging

logger = logging.getLogger("pipedesk_drive.main")

# Create tables
# models.Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up application...")
    
    # Run database migrations in a separate thread to avoid blocking the event loop
    try:
        from migrations.add_soft_delete_fields import migrate_add_soft_delete_fields
        logger.info("Running database migrations...")
        await asyncio.to_thread(migrate_add_soft_delete_fields)
        logger.info("Database migrations completed successfully")
    except ImportError as e:
        logger.warning(f"Migration module not available: {e}")
        logger.info("Skipping migrations - if this is a fresh installation, run migrations manually")
    except Exception as e:
        logger.warning(f"Migration execution issue: {e}")
        logger.info("Continuing startup - this is expected if database columns already exist")

    try:
        scheduler_service.start()
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    scheduler_service.shutdown()

app = FastAPI(lifespan=lifespan)

# Parse CORS origins from config (comma-separated string)
origins = [origin.strip() for origin in config.CORS_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def ensure_api_json_error_response(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except HTTPException as http_exc:
        if request.url.path.startswith("/api"):
            return JSONResponse(
                status_code=http_exc.status_code,
                content={
                    "error": "http_error",
                    "message": http_exc.detail
                    if isinstance(http_exc.detail, str)
                    else "Request error",
                },
            )
        raise
    except Exception as exc:
        if request.url.path.startswith("/api"):
            logging.getLogger("pipedesk_drive.lead_sales_view").error(
                "Unhandled exception for API request", exc_info=True
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_server_error",
                    "message": "An unexpected error occurred",
                },
            )
        raise

app.include_router(drive.router, prefix="/api")
app.include_router(webhooks.router)
app.include_router(calendar.router, prefix="/api/calendar")
app.include_router(drive_items_adapter.router, prefix="/api/drive")
app.include_router(gmail.router, prefix="/api/gmail")
app.include_router(crm_communication.router, prefix="/api")
app.include_router(tasks.router)
app.include_router(health.router)
app.include_router(leads.router)

@app.get("/")
def read_root():
    return {"message": "PipeDesk Google Drive Backend"}
