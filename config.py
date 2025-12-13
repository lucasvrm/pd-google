import os

class Config:
    # --- DATABASE ---
    # É fundamental ler isso aqui para centralizar a configuração, 
    # embora o database.py também possa ler diretamente.
    DATABASE_URL = os.getenv("DATABASE_URL")

    # --- GOOGLE AUTH & DRIVE ---
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    USE_MOCK_DRIVE = os.getenv("USE_MOCK_DRIVE", "false").lower() == "true"
    DRIVE_ROOT_FOLDER_ID = os.getenv("DRIVE_ROOT_FOLDER_ID", None) # Optional: isolar arquivos numa pasta raiz
    
    # --- WEBHOOKS & AUTOMAÇÃO ---
    # URL pública do backend (Necessária para o Google enviar notificações para nós)
    WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "http://localhost:8000")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", None)  # Opcional: segurança extra
    
    # --- REDIS CACHE (Upstash/Render Key Value) ---
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    REDIS_CACHE_ENABLED = os.getenv("REDIS_CACHE_ENABLED", "true").lower() == "true"
    REDIS_DEFAULT_TTL = int(os.getenv("REDIS_DEFAULT_TTL", "180"))  # 3 minutos padrão
    
    # --- CORS (Segurança do Frontend) ---
    # Adicione aqui a URL do seu frontend em produção (Vercel, etc)
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,https://pipedesk.vercel.app")
    
    # --- CALENDAR & SLA (Novas Features) ---
    # Quanto tempo manter eventos passados no banco local
    CALENDAR_EVENT_RETENTION_DAYS = int(os.getenv("CALENDAR_EVENT_RETENTION_DAYS", "180"))
    
    # [NOVO] Limite de horas para considerar um lead como "atrasado" (SLA Breach)
    # Se não configurado no Render, assume 48 horas.
    SLA_BREACH_THRESHOLD_HOURS = int(os.getenv("SLA_BREACH_THRESHOLD_HOURS", "48"))

    # --- FEATURE FLAGS & SYSTEM ---
    # Scheduler para rodar o worker de SLA e limpeza
    SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "false").lower() == "true"
    # Rodar migrações ao iniciar (útil no Render para não precisar rodar manualmente)
    RUN_MIGRATIONS_ON_STARTUP = os.getenv("RUN_MIGRATIONS_ON_STARTUP", "true").lower() == "true"

config = Config()