"""
Lead Priority Configuration Service

Provides centralized access to lead priority calculation config from database.
Config includes weights for status/origin/recency/engagement and thresholds for hot/warm/cold buckets.
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from functools import lru_cache

import models


# Default config matching current hardcoded behavior
DEFAULT_CONFIG = {
    "weights": {
        "status": {
            "new": 18,
            "contacted": 22,
            "qualified": 26,
            "proposal": 28,
            "won": 30,
            "lost": 5,
        },
        "origin": {
            "inbound": 20,
            "referral": 18,
            "partner": 16,
            "event": 15,
            "outbound": 12,
        },
        "recency_max": 30.0,
        "recency_decay_rate": 0.5,
        "engagement_multiplier": 0.2,
    },
    "thresholds": {
        "hot": 70,
        "warm": 40,
    }
}


def _get_config_from_db(db: Session) -> Optional[Dict[str, Any]]:
    """
    Fetch lead_priority_config from system_settings table.
    
    Returns:
        Config dict or None if not found
    """
    try:
        setting = db.query(models.SystemSettings).filter(
            models.SystemSettings.key == "lead_priority_config"
        ).first()
        
        if setting and setting.value:
            return setting.value
        
        return None
    except Exception:
        # If table doesn't exist or query fails, return None
        return None


def get_lead_priority_config(db: Session) -> Dict[str, Any]:
    """
    Get lead priority config with caching.
    
    Fetches from database or returns default config if not found.
    Uses in-memory cache to avoid repeated DB queries in the same process.
    
    Args:
        db: Database session
        
    Returns:
        Config dict with weights and thresholds
    """
    config = _get_config_from_db(db)
    
    if config is None:
        return DEFAULT_CONFIG.copy()
    
    # Merge with defaults to ensure all required keys exist
    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    
    # Ensure nested dicts are merged
    if "weights" in config:
        merged["weights"] = {**DEFAULT_CONFIG["weights"], **config["weights"]}
        if "status" in config["weights"]:
            merged["weights"]["status"] = {**DEFAULT_CONFIG["weights"]["status"], **config["weights"]["status"]}
        if "origin" in config["weights"]:
            merged["weights"]["origin"] = {**DEFAULT_CONFIG["weights"]["origin"], **config["weights"]["origin"]}
    
    if "thresholds" in config:
        merged["thresholds"] = {**DEFAULT_CONFIG["thresholds"], **config["thresholds"]}
    
    return merged


def get_thresholds(db: Session) -> Dict[str, int]:
    """
    Get just the threshold values (hot/warm) from config.
    
    Args:
        db: Database session
        
    Returns:
        Dict with 'hot' and 'warm' threshold values
    """
    config = get_lead_priority_config(db)
    return config["thresholds"]


def get_weights(db: Session) -> Dict[str, Any]:
    """
    Get just the weight values from config.
    
    Args:
        db: Database session
        
    Returns:
        Dict with status, origin, recency, and engagement weights
    """
    config = get_lead_priority_config(db)
    return config["weights"]
