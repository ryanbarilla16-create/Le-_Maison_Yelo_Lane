"""
Permission Cache

Request-scoped permission cache to avoid repeated lookups.
"""


class PermissionCache:
    """
    Request-scoped permission cache to avoid repeated lookups.
    Cache is cleared at the end of each request.
    """
    
    def __init__(self):
        """Initialize empty cache."""
        self._cache = {}
    
    def get(self, key):
        """
        Get cached permission result.
        
        Args:
            key: Cache key (typically user_id:permission_name)
        
        Returns:
            Cached value or None if not found
        """
        return self._cache.get(key)
    
    def set(self, key, value):
        """
        Cache permission result.
        
        Args:
            key: Cache key (typically user_id:permission_name)
            value: Permission check result (boolean)
        """
        self._cache[key] = value
    
    def clear(self):
        """Clear all cached permissions."""
        self._cache.clear()
    
    def invalidate_user(self, user_id):
        """
        Invalidate cache for a specific user.
        
        Args:
            user_id: User ID to invalidate
        """
        # Remove all cache entries for this user
        keys_to_remove = [key for key in self._cache.keys() if key.startswith(f"{user_id}:")]
        for key in keys_to_remove:
            del self._cache[key]
    
    def get_cache_key(self, user_id, permission_name):
        """
        Generate cache key for a permission check.
        
        Args:
            user_id: User ID
            permission_name: Permission name
        
        Returns:
            str: Cache key
        """
        return f"{user_id}:{permission_name}"
