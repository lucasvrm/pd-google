import os

class Config:
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    USE_MOCK_DRIVE = os.getenv("USE_MOCK_DRIVE", "false").lower() == "true"
    DRIVE_ROOT_FOLDER_ID = os.getenv("DRIVE_ROOT_FOLDER_ID", None) # Optional: if we want to jail everything in a folder
    
    # Webhook configuration
    WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "http://localhost:8000")  # Public URL for webhook endpoint
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", None)  # Optional: secret for webhook verification
    
    # Redis cache configuration
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    REDIS_CACHE_ENABLED = os.getenv("REDIS_CACHE_ENABLED", "true").lower() == "true"
    REDIS_DEFAULT_TTL = int(os.getenv("REDIS_DEFAULT_TTL", "180"))  # 3 minutes default
    
    # CORS configuration
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,https://pipedesk.vercel.app")
    
    # Calendar event retention
    CALENDAR_EVENT_RETENTION_DAYS = int(os.getenv("CALENDAR_EVENT_RETENTION_DAYS", "180"))  # 180 days default (6 months)

config = Config()
