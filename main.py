from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from utils.prometheus import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
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
    timeline,
    automation,
)
from database import engine
import models
from services.scheduler_service import scheduler_service
from contextlib import asynccontextmanager
import logging
import asyncio
from config import config, normalize_cors_origins

# Configure Logging
import logging_config # This initializes logging

logger = logging.getLogger("pipedesk_drive.main")

# Create tables
# models.Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up application...")
    
    # Register audit log event listeners
    try:
        from services.audit_service import register_audit_listeners
        register_audit_listeners()
        logger.info("Audit log event listeners registered successfully")
    except Exception as e:
        logger.error(f"Failed to register audit listeners: {e}")
    
    # Run database migrations in a separate thread to avoid blocking the event loop
    if config.RUN_MIGRATIONS_ON_STARTUP:
        try:
            from migrations.add_soft_delete_fields import migrate_add_soft_delete_fields
            from migrations.create_lead_tags_table import migrate_create_lead_tags_table

            logger.info("Running database migrations...")
            await asyncio.to_thread(migrate_add_soft_delete_fields)
            await asyncio.to_thread(migrate_create_lead_tags_table)

            logger.info("Database migrations completed successfully")
        except ImportError as e:
            logger.warning(f"Migration module not available: {e}")
            logger.info("Skipping migrations - if this is a fresh installation, run migrations manually")
        except Exception as e:
            logger.warning(f"Migration execution issue: {e}")
            logger.info("Continuing startup - this is expected if database columns already exist")
    else:
        logger.info("Skipping migrations (RUN_MIGRATIONS_ON_STARTUP=false)")

    if config.SCHEDULER_ENABLED:
        try:
            scheduler_service.start()
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
    else:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false)")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    if config.SCHEDULER_ENABLED:
        scheduler_service.shutdown()

app = FastAPI(lifespan=lifespan)

# Parse and normalize CORS origins from config (comma-separated string)
# Uses normalize_cors_origins() to handle: whitespace, quotes, trailing slashes, empty entries
origins = normalize_cors_origins(config.CORS_ORIGINS)

# Log normalized origins for debugging
logger.info(f"CORS allowed origins: {origins}")

# Build CORS middleware parameters
cors_params = {
    "allow_origins": origins,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}

# Add regex support for Vercel preview deployments if configured
if config.CORS_ORIGIN_REGEX:
    cors_params["allow_origin_regex"] = config.CORS_ORIGIN_REGEX
    logger.info(f"CORS origin regex enabled: {config.CORS_ORIGIN_REGEX}")

app.add_middleware(
    CORSMiddleware,
    **cors_params,
)


HTTP_STATUS_CODE_MAP = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "too_many_requests",
}


def _http_exception_to_api_error(exc: HTTPException) -> dict:
    detail = exc.detail
    if isinstance(detail, str):
        message = detail
    elif isinstance(detail, dict) and "message" in detail:
        message = str(detail["message"])
    else:
        message = str(detail) if detail else "Request error"

    payload = {
        "error": message,
        "code": HTTP_STATUS_CODE_MAP.get(exc.status_code, "http_error"),
        "message": message,
    }

    if not isinstance(detail, str):
        payload["details"] = detail

    return payload


@app.middleware("http")
async def ensure_api_json_error_response(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception:
        if request.url.path.startswith("/api"):
            logging.getLogger("pipedesk_drive.lead_sales_view").error(
                "Unhandled exception for API request", exc_info=True
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "An unexpected error occurred",
                    "code": "internal_server_error",
                    "message": "An unexpected error occurred",
                },
            )
        raise


@app.exception_handler(HTTPException)
async def http_exception_handler_for_api(request: Request, exc: HTTPException):
    """Normalize HTTPException responses for /api routes while preserving defaults elsewhere."""
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=exc.status_code, content=_http_exception_to_api_error(exc))

    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Normalize validation errors for API routes while preserving default behavior elsewhere."""
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation error",
                "code": "validation_error",
                "message": "Validation error",
                "details": exc.errors(),
            },
        )

    # Fallback to FastAPI's default handler for non-API routes
    return await request_validation_exception_handler(request, exc)

app.include_router(drive.router, prefix="/api")
app.include_router(webhooks.router)
app.include_router(calendar.router, prefix="/api/calendar")
app.include_router(drive_items_adapter.router, prefix="/api/drive")
app.include_router(gmail.router, prefix="/api/gmail")
app.include_router(crm_communication.router, prefix="/api")
app.include_router(tasks.router)
app.include_router(health.router)
app.include_router(leads.router)
app.include_router(timeline.router)
app.include_router(automation.router)


@app.get("/metrics")
def prometheus_metrics():
    """Expose Prometheus metrics collected by the application."""
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

@app.get("/")
def read_root():
    return {"message": "PipeDesk Google Drive Backend"}
