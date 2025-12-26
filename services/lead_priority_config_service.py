"""
Lead Priority Config Service

Reads lead priority configuration from system_settings table in Supabase.
Cache in memory with TTL to reduce queries.
Pattern mirrored from feature_flags_service.py.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal
from utils.structured_logging import StructuredLogger


logger = logging.getLogger("pipedesk_drive.lead_priority_config")
config_logger = StructuredLogger(
    service="lead_priority_config", logger_name="pipedesk_drive.lead_priority_config"
)


# Cache em memória
CACHE_TTL_SECONDS = 60
_cache: Optional[Dict[str, Any]] = None
_cache_timestamp: Optional[datetime] = None


# Default configuration values
DEFAULT_CONFIG = {
    "thresholds": {
        "hot": 70,
        "warm": 40,
    },
    "scoring": {
        "recencyMaxPoints": 40,
        "staleDays": 30,
        "upcomingMeetingPoints": 25,
        "minScore": 0,
        "maxScore": 100,
    },
    "descriptions": {
        "hot": "High priority - needs immediate attention",
        "warm": "Medium priority - follow up soon",
        "cold": "Low priority - monitor",
    }
}


def _is_cache_valid() -> bool:
    """Verifica se o cache ainda é válido."""
    if _cache_timestamp is None:
        return False
    now = datetime.now(timezone.utc)
    return (now - _cache_timestamp) < timedelta(seconds=CACHE_TTL_SECONDS)


def _sanitize_config(raw_value: Any) -> Dict[str, Any]:
    """
    Sanitiza e normaliza a configuração do banco.
    Garante presença de todas as chaves e tipos numéricos corretos.
    Em caso de dados inválidos, usa defaults.
    """
    if not isinstance(raw_value, dict):
        config_logger.warning(
            action="config_sanitize",
            message="Config value is not a dict, using defaults",
            raw_value=raw_value,
        )
        return DEFAULT_CONFIG.copy()
    
    # Start with defaults and overlay valid values from DB
    config = DEFAULT_CONFIG.copy()
    
    try:
        # Sanitize thresholds
        if "thresholds" in raw_value and isinstance(raw_value["thresholds"], dict):
            thresholds = raw_value["thresholds"]
            if "hot" in thresholds:
                try:
                    config["thresholds"]["hot"] = int(thresholds["hot"])
                except (TypeError, ValueError):
                    pass
            if "warm" in thresholds:
                try:
                    config["thresholds"]["warm"] = int(thresholds["warm"])
                except (TypeError, ValueError):
                    pass
        
        # Sanitize scoring
        if "scoring" in raw_value and isinstance(raw_value["scoring"], dict):
            scoring = raw_value["scoring"]
            for key in ["recencyMaxPoints", "staleDays", "upcomingMeetingPoints", "minScore", "maxScore"]:
                if key in scoring:
                    try:
                        config["scoring"][key] = int(scoring[key])
                    except (TypeError, ValueError):
                        pass
        
        # Sanitize descriptions (strings, less strict)
        if "descriptions" in raw_value and isinstance(raw_value["descriptions"], dict):
            desc = raw_value["descriptions"]
            for key in ["hot", "warm", "cold"]:
                if key in desc and isinstance(desc[key], str):
                    config["descriptions"][key] = desc[key]
        
    except Exception as exc:
        config_logger.error(
            action="config_sanitize_error",
            message="Error sanitizing config, using defaults",
            error=exc,
        )
        return DEFAULT_CONFIG.copy()
    
    return config


def _refresh_cache(db: Session) -> None:
    """Atualiza o cache de configuração do banco."""
    global _cache, _cache_timestamp
    
    try:
        result = db.execute(
            text("SELECT value FROM system_settings WHERE key = :key"),
            {"key": "lead_priority_config"}
        )
        row = result.fetchone()
        
        if row:
            raw_value = row[0]
            _cache = _sanitize_config(raw_value)
            config_logger.debug(
                action="cache_refresh",
                status="success",
                message="Lead priority config cache updated from DB",
                config=_cache,
            )
        else:
            # No config in DB, use defaults
            _cache = DEFAULT_CONFIG.copy()
            config_logger.info(
                action="cache_refresh",
                status="default",
                message="No lead_priority_config in DB, using defaults",
            )
        
        _cache_timestamp = datetime.now(timezone.utc)
        
    except Exception as exc:
        config_logger.error(
            action="cache_refresh_error",
            message="Failed to refresh lead priority config cache",
            error=exc,
        )
        # Use defaults on error
        if _cache is None:
            _cache = DEFAULT_CONFIG.copy()
            _cache_timestamp = datetime.now(timezone.utc)


def get_lead_priority_config(db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Obtém configuração de prioridade de leads.
    
    Args:
        db: Sessão do banco (opcional, cria nova se não fornecida)
    
    Returns:
        Dict com configuração de prioridade (thresholds, scoring, descriptions)
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
    
    # Should always have cache after refresh (either from DB or defaults)
    return _cache.copy() if _cache else DEFAULT_CONFIG.copy()


def clear_cache() -> None:
    """Limpa o cache (útil para testes)."""
    global _cache, _cache_timestamp
    _cache = None
    _cache_timestamp = None
