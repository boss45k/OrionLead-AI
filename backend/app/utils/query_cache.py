"""
Query Cache Manager
Caches database query results to Redis for improved performance.
Provides TTL-based cache expiration and invalidation strategies.
"""

import json
import logging
import hashlib
from typing import Any, Optional, Dict, Callable, Union
from functools import wraps
from redis import Redis
import os
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)


class QueryCache:
    """Redis-backed query caching with TTL support"""
    
    def __init__(self, redis_url: Optional[str] = None, default_ttl: int = 300):
        """
        Initialize query cache
        
        Args:
            redis_url: Redis connection URL (uses env if not provided)
            default_ttl: Default cache TTL in seconds (5 minutes)
        """
        self.redis_url = redis_url or os.getenv('CACHE_REDIS_URL', 'redis://localhost:6379/0')
        self.default_ttl = default_ttl
        self.prefix = 'query_cache:'
        self.stats = {
            'hits': 0,
            'misses': 0,
            'errors': 0,
        }
        
        try:
            self.redis_client = Redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("Query cache initialized (Redis)")
        except Exception as e:
            logger.debug(f"Redis unavailable for query cache: {e}. Using no-op cache.")
            self.redis_client = None
    
    def _make_cache_key(self, query_name: str, **kwargs) -> str:
        """
        Generate cache key from query name and parameters
        
        Args:
            query_name: Name of the query
            **kwargs: Query parameters
            
        Returns:
            Cache key string
        """
        params_str = json.dumps(kwargs, sort_keys=True, default=str)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()
        return f"{self.prefix}{query_name}:{params_hash}"
    
    def get(self, query_name: str, **kwargs) -> Optional[Any]:
        """
        Get cached query result
        
        Args:
            query_name: Name of the query
            **kwargs: Query parameters
            
        Returns:
            Cached result or None if not found/expired
        """
        if not self.redis_client:
            return None
        
        try:
            cache_key = self._make_cache_key(query_name, **kwargs)
            cached = self.redis_client.get(cache_key)
            
            if cached:
                self.stats['hits'] += 1
                logger.debug(f"Cache hit: {query_name}")
                if isinstance(cached, str):
                    return json.loads(cached)
                return cached
            
            self.stats['misses'] += 1
            return None
            
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self.stats['errors'] += 1
            return None
    
    def set(
        self,
        query_name: str,
        value: Any,
        ttl: Optional[int] = None,
        **kwargs
    ) -> bool:
        """
        Cache a query result
        
        Args:
            query_name: Name of the query
            value: Result to cache
            ttl: Time to live in seconds (uses default if None)
            **kwargs: Query parameters
            
        Returns:
            True if cache successful
        """
        if not self.redis_client:
            return False
        
        try:
            cache_key = self._make_cache_key(query_name, **kwargs)
            ttl = ttl or self.default_ttl
            
            self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(value, default=str)
            )
            
            logger.debug(f"Cache set: {query_name} (TTL: {ttl}s)")
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            self.stats['errors'] += 1
            return False
    
    def invalidate(self, query_name: str, **kwargs) -> bool:
        """
        Invalidate specific cache entry
        
        Args:
            query_name: Name of the query
            **kwargs: Query parameters (if empty, invalidates all)
            
        Returns:
            True if invalidation successful
        """
        if not self.redis_client:
            return False
        
        try:
            if kwargs:
                # Invalidate specific entry
                cache_key = self._make_cache_key(query_name, **kwargs)
                self.redis_client.delete(cache_key)
            else:
                # Invalidate all entries for this query
                pattern = f"{self.prefix}{query_name}:*"
                keys_list = self.redis_client.keys(pattern)
                if keys_list and isinstance(keys_list, list):
                    self.redis_client.delete(*keys_list)
            
            logger.debug(f"Cache invalidated: {query_name}")
            return True
            
        except Exception as e:
            logger.error(f"Cache invalidate error: {e}")
            return False
    
    def cached_result(
        self,
        query_name: str,
        ttl: Optional[int] = None,
        invalidate_on_change: bool = False
    ):
        """
        Decorator for caching query results
        
        Args:
            query_name: Name for cache key
            ttl: Time to live (uses default if None)
            invalidate_on_change: If True, invalidate on write operations
            
        Example:
            @QueryCache.cached_result('get_leads', ttl=3600)
            def get_leads(status=None, limit=10):
                return Lead.query.filter_by(status=status).limit(limit).all()
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Only cache GET operations (no state changes)
                if not invalidate_on_change:
                    cached = self.get(query_name, **kwargs)
                    if cached is not None:
                        return cached
                
                # Execute function if not cached
                result = func(*args, **kwargs)
                
                # Cache the result
                self.set(query_name, result, ttl=ttl, **kwargs)
                return result
            
            return wrapper
        return decorator
    
    def get_stats(self) -> Dict[str, Union[int, float]]:
        """Get cache statistics"""
        total = self.stats['hits'] + self.stats['misses'] + self.stats['errors']
        hit_rate = (
            round(self.stats['hits'] / total * 100, 2)
            if total > 0 else 0
        )
        
        return {
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'errors': self.stats['errors'],
            'hit_rate_percent': hit_rate,
            'total_requests': total
        }
    
    def clear_all(self):
        """Clear all cached queries (use with caution)"""
        if not self.redis_client:
            return False
        
        try:
            pattern = f"{self.prefix}*"
            keys_list = self.redis_client.keys(pattern)
            if keys_list and isinstance(keys_list, list):
                self.redis_client.delete(*keys_list)
            logger.warning("All query caches cleared")
            return True
        except Exception as e:
            logger.error(f"Clear all error: {e}")
            return False


# Global cache instance
_query_cache = None


def init_query_cache(redis_url: Optional[str] = None) -> QueryCache:
    """Initialize the global query cache"""
    global _query_cache
    _query_cache = QueryCache(redis_url=redis_url)
    return _query_cache


def get_query_cache() -> QueryCache:
    """Get the global query cache instance"""
    global _query_cache
    if _query_cache is None:
        _query_cache = QueryCache()
    return _query_cache
