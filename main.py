from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import drive, webhooks, calendar, drive_items_adapter
from database import engine
import models
from services.scheduler_service import scheduler_service
from contextlib import asynccontextmanager
import logging

# Configure Logging
import logging_config # This initializes logging

logger = logging.getLogger("pipedesk_drive.main")

# Create tables
# models.Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up application...")
    try:
        scheduler_service.start()
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    scheduler_service.shutdown()

app = FastAPI(lifespan=lifespan)

origins = [
    "http://localhost:5173",  # Vite default
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(drive.router)
app.include_router(webhooks.router)
app.include_router(calendar.router)
app.include_router(drive_items_adapter.router, prefix="/api/drive")

@app.get("/")
def read_root():
    return {"message": "PipeDesk Google Drive Backend"}
