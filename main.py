from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import drive, webhooks, calendar, drive_items_adapter
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

# --- CORREÇÃO AQUI: Adicionado prefix="/api" para alinhar com o Frontend ---
app.include_router(drive.router, prefix="/api") 
app.include_router(webhooks.router)
app.include_router(calendar.router)
app.include_router(drive_items_adapter.router, prefix="/api/drive")

@app.get("/")
def read_root():
    return {"message": "PipeDesk Google Drive Backend"}