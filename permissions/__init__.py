"""
Centralized Permission System

This module provides a flexible, configuration-driven role-based access control (RBAC) system
for the Flask restaurant management application.

Components:
- PermissionManager: Core permission checking and configuration management
- Decorators: @requires_permission, @requires_branch_access for route protection
- PermissionCache: Request-scoped caching for performance
- PermissionAuditLogger: Security audit logging
- Migration utilities: Tools for migrating from legacy @requires_roles decorator
"""

from permissions.manager import PermissionManager
from permissions.decorators import requires_permission, requires_branch_access, requires_roles
from permissions.cache import PermissionCache
from permissions.audit import PermissionAuditLogger

__all__ = [
    'PermissionManager',
    'requires_permission',
    'requires_branch_access',
    'requires_roles',
    'PermissionCache',
    'PermissionAuditLogger',
    'init_permissions'
]

# Global permission manager instance
_permission_manager = None

def init_permissions(app, permission_manager):
    """
    Initialize the permission system with the Flask application.
    
    Args:
        app: Flask application instance
        permission_manager: PermissionManager instance
    """
    global _permission_manager
    _permission_manager = permission_manager
    
    # Register request hooks for permission caching
    @app.before_request
    def setup_permission_cache():
        from flask import g
        g.permission_cache = PermissionCache()
    
    @app.teardown_request
    def clear_permission_cache(exception=None):
        from flask import g
        if hasattr(g, 'permission_cache'):
            g.permission_cache.clear()

def get_permission_manager():
    """Get the global permission manager instance."""
    return _permission_manager
