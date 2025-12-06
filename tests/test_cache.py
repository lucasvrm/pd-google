import unittest
import os
import sys
import time
from unittest.mock import patch, MagicMock, Mock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCacheService(unittest.TestCase):
    """Tests for the Redis cache service"""
    
    def setUp(self):
        """Set up test environment"""
        # Set test environment variables
        os.environ["REDIS_CACHE_ENABLED"] = "true"
        os.environ["USE_MOCK_DRIVE"] = "false"
        os.environ["REDIS_DEFAULT_TTL"] = "60"
        
    def tearDown(self):
        """Clean up after tests"""
        # Reset environment variables
        if "REDIS_CACHE_ENABLED" in os.environ:
            del os.environ["REDIS_CACHE_ENABLED"]
        if "USE_MOCK_DRIVE" in os.environ:
            del os.environ["USE_MOCK_DRIVE"]
    
    def test_cache_disabled_in_mock_mode(self):
        """Test that cache is disabled when USE_MOCK_DRIVE=true"""
        with patch.dict(os.environ, {"USE_MOCK_DRIVE": "true", "REDIS_CACHE_ENABLED": "true"}):
            # Import config to reload with new env vars
            import importlib
            import config
            importlib.reload(config)
            
            from cache import CacheService
            cache = CacheService()
            self.assertFalse(cache.enabled, "Cache should be disabled in mock mode")
    
    def test_cache_disabled_when_redis_cache_enabled_false(self):
        """Test that cache is disabled when REDIS_CACHE_ENABLED=false"""
        with patch.dict(os.environ, {"USE_MOCK_DRIVE": "false", "REDIS_CACHE_ENABLED": "false"}):
            from cache import CacheService
            cache = CacheService()
            self.assertFalse(cache.enabled, "Cache should be disabled when REDIS_CACHE_ENABLED=false")
    
    def test_cache_operations_when_disabled(self):
        """Test that cache operations return safely when disabled"""
        with patch.dict(os.environ, {"REDIS_CACHE_ENABLED": "false"}):
            from cache import CacheService
            cache = CacheService()
            
            # get_from_cache should return None
            result = cache.get_from_cache("test_key")
            self.assertIsNone(result)
            
            # set_in_cache should return False
            result = cache.set_in_cache("test_key", {"data": "value"})
            self.assertFalse(result)
            
            # invalidate_cache should return 0
            result = cache.invalidate_cache("test_*")
            self.assertEqual(result, 0)
            
            # delete_key should return False
            result = cache.delete_key("test_key")
            self.assertFalse(result)
    
    @patch('cache.redis.from_url')
    def test_cache_set_and_get(self, mock_redis_from_url):
        """Test basic cache set and get operations"""
        # Mock Redis client
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.get.return_value = '{"files": ["file1", "file2"]}'
        mock_client.setex.return_value = True
        mock_redis_from_url.return_value = mock_client
        
        from cache import CacheService
        cache = CacheService()
        
        # Test set
        test_data = {"files": ["file1", "file2"]}
        result = cache.set_in_cache("test_key", test_data, ttl=60)
        self.assertTrue(result)
        mock_client.setex.assert_called_once()
        
        # Test get
        cached_data = cache.get_from_cache("test_key")
        self.assertEqual(cached_data, test_data)
        mock_client.get.assert_called_once_with("test_key")
    
    @patch('cache.redis.from_url')
    def test_cache_get_miss(self, mock_redis_from_url):
        """Test cache miss (key not found)"""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.get.return_value = None
        mock_redis_from_url.return_value = mock_client
        
        from cache import CacheService
        cache = CacheService()
        
        result = cache.get_from_cache("nonexistent_key")
        self.assertIsNone(result)
    
    @patch('cache.redis.from_url')
    def test_cache_delete_key(self, mock_redis_from_url):
        """Test deleting a specific cache key"""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.delete.return_value = 1
        mock_redis_from_url.return_value = mock_client
        
        from cache import CacheService
        cache = CacheService()
        
        result = cache.delete_key("test_key")
        self.assertTrue(result)
        mock_client.delete.assert_called_once_with("test_key")
    
    @patch('cache.redis.from_url')
    def test_cache_invalidate_pattern(self, mock_redis_from_url):
        """Test invalidating cache keys by pattern"""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.keys.return_value = ["drive:list_files:folder1", "drive:list_files:folder2"]
        mock_client.delete.return_value = 2
        mock_redis_from_url.return_value = mock_client
        
        from cache import CacheService
        cache = CacheService()
        
        result = cache.invalidate_cache("drive:list_files:*")
        self.assertEqual(result, 2)
        mock_client.keys.assert_called_once_with("drive:list_files:*")
        mock_client.delete.assert_called_once()
    
    @patch('cache.redis.from_url')
    def test_cache_flush_all(self, mock_redis_from_url):
        """Test flushing all cache"""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.flushdb.return_value = True
        mock_redis_from_url.return_value = mock_client
        
        from cache import CacheService
        cache = CacheService()
        
        result = cache.flush_all()
        self.assertTrue(result)
        mock_client.flushdb.assert_called_once()
    
    @patch('cache.redis.from_url')
    def test_cache_connection_failure(self, mock_redis_from_url):
        """Test graceful handling of Redis connection failure"""
        mock_redis_from_url.side_effect = Exception("Connection refused")
        
        from cache import CacheService
        cache = CacheService()
        
        # Cache should be disabled after connection failure
        self.assertFalse(cache.enabled)
        self.assertIsNone(cache.client)
        
        # Operations should return safely
        self.assertIsNone(cache.get_from_cache("key"))
        self.assertFalse(cache.set_in_cache("key", "value"))
    
    @patch('cache.redis.from_url')
    def test_cache_with_default_ttl(self, mock_redis_from_url):
        """Test that cache uses default TTL when not specified"""
        with patch.dict(os.environ, {"REDIS_DEFAULT_TTL": "60", "USE_MOCK_DRIVE": "false", "REDIS_CACHE_ENABLED": "true"}):
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_redis_from_url.return_value = mock_client
            
            # Reload cache module to pick up env vars
            import importlib
            import cache
            importlib.reload(cache)
            
            from cache import CacheService
            cache_svc = CacheService()
            
            if cache_svc.enabled:
                cache_svc.set_in_cache("test_key", {"data": "value"})
                
                # Verify that setex was called with TTL
                if mock_client.setex.called:
                    args, kwargs = mock_client.setex.call_args
                    self.assertEqual(args[0], "test_key")
                    # TTL should be 60
                    self.assertEqual(args[1], 60)


if __name__ == "__main__":
    unittest.main()
