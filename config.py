import os

class Config:
    # --- DATABASE ---
    # Render injeta esta variável automaticamente.
    DATABASE_URL = os.getenv("DATABASE_URL")

    # --- GOOGLE AUTH & DRIVE ---
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    USE_MOCK_DRIVE = os.getenv("USE_MOCK_DRIVE", "false").lower() == "true"
    DRIVE_ROOT_FOLDER_ID = os.getenv("DRIVE_ROOT_FOLDER_ID", None)
    
    # --- WEBHOOKS (Google Drive & Calendar & Gmail) ---
    # URL pública do backend para o Google enviar notificações.
    # Já deixei o seu URL real como padrão, mas é BOA PRÁTICA manter no Env Var do Render também.
    WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "https://google-api-xwhd.onrender.com")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", None)
    
    # --- REDIS CACHE ---
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    REDIS_CACHE_ENABLED = os.getenv("REDIS_CACHE_ENABLED", "true").lower() == "true"
    REDIS_DEFAULT_TTL = int(os.getenv("REDIS_DEFAULT_TTL", "180"))
    
    # --- CORS (Segurança do Frontend) ---
    # Adicionei o seu frontend da Vercel e localhost para desenvolvimento.
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "https://pipedesk.vercel.app,http://localhost:5173,http://127.0.0.1:5173")
    
    # --- CALENDAR & SLA ---
    CALENDAR_EVENT_RETENTION_DAYS = int(os.getenv("CALENDAR_EVENT_RETENTION_DAYS", "180"))
    SLA_BREACH_THRESHOLD_HOURS = int(os.getenv("SLA_BREACH_THRESHOLD_HOURS", "48"))

    # --- FEATURE FLAGS ---
    SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "false").lower() == "true"
    RUN_MIGRATIONS_ON_STARTUP = os.getenv("RUN_MIGRATIONS_ON_STARTUP", "true").lower() == "true"

config = Config()
