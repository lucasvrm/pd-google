import os
import redis
import json
from typing import Any, Optional
from config import config

class CacheConfig:
    """Configuration for Redis cache"""
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_CACHE_ENABLED = os.getenv("REDIS_CACHE_ENABLED", "true").lower() == "true"
    REDIS_DEFAULT_TTL = int(os.getenv("REDIS_DEFAULT_TTL", "180"))  # 3 minutes default

class CacheService:
    """Redis cache service for Google Drive operations"""
    
    def __init__(self):
        self.enabled = CacheConfig.REDIS_CACHE_ENABLED and not config.USE_MOCK_DRIVE
        self.client = None
        
        if self.enabled:
            try:
                self.client = redis.from_url(
                    CacheConfig.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # Test connection
                self.client.ping()
                print(f"✓ Redis cache enabled (TTL: {CacheConfig.REDIS_DEFAULT_TTL}s)")
            except Exception as e:
                print(f"⚠ Redis connection failed, cache disabled: {e}")
                self.enabled = False
                self.client = None
        else:
            reason = "mock mode" if config.USE_MOCK_DRIVE else "REDIS_CACHE_ENABLED=false"
            print(f"✗ Redis cache disabled ({reason})")
    
    def get_from_cache(self, key: str) -> Optional[Any]:
        """
        Retrieve value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value (deserialized from JSON) or None if not found/disabled
        """
        if not self.enabled or not self.client:
            return None
        
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            print(f"Cache GET error for key '{key}': {e}")
            return None
    
    def set_in_cache(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Store value in cache.
        
        Args:
            key: Cache key
            value: Value to cache (will be serialized to JSON)
            ttl: Time-to-live in seconds (default: REDIS_DEFAULT_TTL)
            
        Returns:
            True if successfully cached, False otherwise
        """
        if not self.enabled or not self.client:
            return False
        
        try:
            ttl = ttl or CacheConfig.REDIS_DEFAULT_TTL
            serialized = json.dumps(value)
            self.client.setex(key, ttl, serialized)
            return True
        except Exception as e:
            print(f"Cache SET error for key '{key}': {e}")
            return False
    
    def invalidate_cache(self, key_prefix: str) -> int:
        """
        Invalidate all cache keys matching a prefix.
        
        Args:
            key_prefix: Prefix pattern (e.g., 'drive:list_files:*')
            
        Returns:
            Number of keys deleted
        """
        if not self.enabled or not self.client:
            return 0
        
        try:
            # Find all keys matching the pattern
            keys = self.client.keys(key_prefix)
            if keys:
                return self.client.delete(*keys)
            return 0
        except Exception as e:
            print(f"Cache INVALIDATE error for prefix '{key_prefix}': {e}")
            return 0
    
    def delete_key(self, key: str) -> bool:
        """
        Delete a specific cache key.
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if key was deleted, False otherwise
        """
        if not self.enabled or not self.client:
            return False
        
        try:
            result = self.client.delete(key)
            return result > 0
        except Exception as e:
            print(f"Cache DELETE error for key '{key}': {e}")
            return False
    
    def flush_all(self) -> bool:
        """
        Flush all cache (use with caution).
        
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.client:
            return False
        
        try:
            self.client.flushdb()
            return True
        except Exception as e:
            print(f"Cache FLUSH error: {e}")
            return False

# Global cache instance
cache_service = CacheService()
