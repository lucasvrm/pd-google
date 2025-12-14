import os
from typing import List


def normalize_cors_origins(origins_str: str) -> List[str]:
    """
    Normalize a comma-separated string of CORS origins.
    
    Handles:
    - Trim whitespace from each origin
    - Remove surrounding quotes (" and ')
    - Remove trailing slashes (/)
    - Filter out empty entries
    
    Args:
        origins_str: Comma-separated string of origins
        
    Returns:
        List of normalized, non-empty origins
    """
    if not origins_str:
        return []
    
    normalized = []
    for origin in origins_str.split(","):
        # Trim whitespace
        origin = origin.strip()
        
        # Remove surrounding quotes (both " and ')
        if (origin.startswith('"') and origin.endswith('"')) or \
           (origin.startswith("'") and origin.endswith("'")):
            origin = origin[1:-1]
        
        # Trim again after quote removal
        origin = origin.strip()
        
        # Remove trailing slash
        origin = origin.rstrip("/")
        
        # Filter empty entries
        if origin:
            normalized.append(origin)
    
    return normalized


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
    # Production frontend: https://pipedesk.vercel.app
    # Development: localhost ports for Vite (5173) and common alternatives (3000, 8080)
    _DEFAULT_CORS_ORIGINS = [
        "https://pipedesk.vercel.app",  # Production
        "http://localhost:5173",         # Vite default
        "http://localhost:3000",         # Common dev port
        "http://localhost:8080",         # Alternative dev port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
    ]
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", ",".join(_DEFAULT_CORS_ORIGINS))
    
    # Optional: Regex pattern for additional CORS origins (e.g., Vercel preview deployments)
    # Example: https://pipedesk-[a-z0-9]+\.vercel\.app
    # Must be a valid Python regex pattern. Leave empty to disable.
    CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX", None)
    
    # --- CALENDAR & SLA ---
    CALENDAR_EVENT_RETENTION_DAYS = int(os.getenv("CALENDAR_EVENT_RETENTION_DAYS", "180"))
    SLA_BREACH_THRESHOLD_HOURS = int(os.getenv("SLA_BREACH_THRESHOLD_HOURS", "48"))

    # --- FEATURE FLAGS ---
    SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "false").lower() == "true"
    RUN_MIGRATIONS_ON_STARTUP = os.getenv("RUN_MIGRATIONS_ON_STARTUP", "true").lower() == "true"

    # Email do usuário do Workspace que a Service Account vai imitar (Subject)
    # Ex: admin@suaempresa.com. Obrigatório para acessar Gmail/Calendar de usuários.
    GOOGLE_IMPERSONATE_EMAIL = os.getenv("GOOGLE_IMPERSONATE_EMAIL", None)

    # --- SUPABASE JWT AUTH ---
    # Secret used to verify JWT tokens issued by Supabase.
    SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", None)

config = Config()
