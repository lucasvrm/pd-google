"""
Feature Flags Service

Lê feature flags da tabela system_settings do Supabase.
Cache em memória com TTL para reduzir queries.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal
from utils.structured_logging import StructuredLogger


logger = logging.getLogger("pipedesk_drive.feature_flags")
feature_flags_logger = StructuredLogger(
    service="feature_flags", logger_name="pipedesk_drive.feature_flags"
)


# Cache em memória
CACHE_TTL_SECONDS = 60
_cache: Dict[str, Any] = {}
_cache_timestamp: Optional[datetime] = None


def _is_cache_valid() -> bool:
    """Verifica se o cache ainda é válido."""
    if _cache_timestamp is None:
        return False
    now = datetime.now(timezone.utc)
    return (now - _cache_timestamp) < timedelta(seconds=CACHE_TTL_SECONDS)


def _refresh_cache(db: Session) -> None:
    """Atualiza o cache de feature flags do banco."""
    global _cache, _cache_timestamp
    
    try:
        result = db.execute(
            text("SELECT key, value FROM system_settings WHERE key LIKE 'feature_%'")
        )
        rows = result.fetchall()
        
        new_cache = {}
        for row in rows:
            key = row[0]
            value = row[1]
            # Tratar JSONB boolean
            if isinstance(value, bool):
                new_cache[key] = value
            elif isinstance(value, str):
                new_cache[key] = value.lower() in ('true', '1', 'yes')
            else:
                new_cache[key] = bool(value)
        
        _cache = new_cache
        _cache_timestamp = datetime.now(timezone.utc)
        
        feature_flags_logger.debug(
            action="cache_refresh",
            status="success",
            message=f"Feature flags cache atualizado: {len(new_cache)} flags",
            flags=new_cache,
        )
    except Exception as exc:
        feature_flags_logger.error(
            action="cache_refresh_error",
            message="Falha ao atualizar cache de feature flags",
            error=exc,
        )
        # Manter cache antigo ou definir defaults
        if not _cache:
            _cache = {
                "feature_lead_auto_priority": False,
                "feature_lead_auto_next_action": False,
                "feature_lead_manual_priority": True,
                "feature_lead_task_next_action": True,
            }
            _cache_timestamp = datetime.now(timezone.utc)


def get_feature_flag(key: str, default: bool = False, db: Optional[Session] = None) -> bool:
    """
    Obtém valor de uma feature flag.
    
    Args:
        key: Chave da flag (ex: 'feature_lead_auto_priority')
        default: Valor padrão se não encontrada
        db: Sessão do banco (opcional, cria nova se não fornecida)
    
    Returns:
        Boolean com valor da flag
    """
    global _cache, _cache_timestamp
    
    if not _is_cache_valid():
        if db is not None:
            _refresh_cache(db)
        else:
            session = SessionLocal()
            try:
                _refresh_cache(session)
            finally:
                session.close()
    
    return _cache.get(key, default)


# Funções de conveniência
def is_auto_priority_enabled(db: Optional[Session] = None) -> bool:
    """Verifica se cálculo automático de prioridade está habilitado."""
    return get_feature_flag("feature_lead_auto_priority", default=False, db=db)


def is_auto_next_action_enabled(db: Optional[Session] = None) -> bool:
    """Verifica se sugestão automática de next action está habilitada."""
    return get_feature_flag("feature_lead_auto_next_action", default=False, db=db)


def is_manual_priority_enabled(db: Optional[Session] = None) -> bool:
    """Verifica se prioridade manual está habilitada."""
    return get_feature_flag("feature_lead_manual_priority", default=True, db=db)


def is_task_next_action_enabled(db: Optional[Session] = None) -> bool:
    """Verifica se sistema de tarefas para next action está habilitado."""
    return get_feature_flag("feature_lead_task_next_action", default=True, db=db)


def clear_cache() -> None:
    """Limpa o cache (útil para testes)."""
    global _cache, _cache_timestamp
    _cache = {}
    _cache_timestamp = None
