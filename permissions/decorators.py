"""
Permission Decorators

Flask route decorators for permission-based access control.
"""

from functools import wraps
from flask import abort, flash, redirect, url_for, request, current_app
from flask_login import current_user
from permissions.exceptions import PermissionDeniedError, BranchAccessDeniedError
import warnings


def requires_permission(*permission_names, require_all=False):
    """
    Decorator to protect routes with permission checks.
    
    Args:
        *permission_names: One or more permission names required
        require_all: If True, user must have ALL permissions (AND logic)
                    If False, user needs ANY permission (OR logic)
    
    Usage:
        @requires_permission('menu.view')
        @requires_permission('menu.edit', 'menu.create', require_all=False)
        @requires_permission('menu.delete', 'menu.edit', require_all=True)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if user is authenticated
            if not current_user.is_authenticated:
                flash("You need to login first.", "warning")
                return redirect(url_for('main.login'))
            
            # Get permission manager from app
            from permissions import get_permission_manager
            permission_manager = get_permission_manager()
            
            if not permission_manager:
                # Fallback if permission system not initialized
                current_app.logger.error("Permission system not initialized")
                abort(500, description="Permission system not initialized")
            
            # Check permissions
            has_access = False
            if require_all:
                # AND logic - user needs all permissions
                has_access = permission_manager.has_all_permissions(current_user, permission_names)
            else:
                # OR logic - user needs any permission
                has_access = permission_manager.has_any_permission(current_user, permission_names)
            
            if not has_access:
                # Log access denial
                from permissions.audit import PermissionAuditLogger
                audit_logger = PermissionAuditLogger()
                
                perm_list = ', '.join(permission_names)
                reason = f"User lacks required permission(s): {perm_list}"
                audit_logger.log_access_denied(
                    current_user,
                    perm_list,
                    request.path,
                    reason
                )
                
                # Return 403 Forbidden
                if current_app.debug:
                    # Development mode - show detailed error
                    abort(403, description=f"Access Denied. Required permission(s): {perm_list}")
                else:
                    # Production mode - generic error
                    abort(403, description="You do not have permission to view this page.")
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def requires_branch_access(branch_param='branch'):
    """
    Decorator to enforce branch-level access control.
    
    Args:
        branch_param: Name of the route parameter containing branch value
    
    Usage:
        @requires_branch_access()
        @requires_branch_access(branch_param='branch_name')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if user is authenticated
            if not current_user.is_authenticated:
                flash("You need to login first.", "warning")
                return redirect(url_for('main.login'))
            
            # Extract branch value from route parameters
            branch = kwargs.get(branch_param)
            
            if not branch:
                # Try to get from query parameters
                branch = request.args.get(branch_param)
            
            if not branch:
                abort(400, description="Branch parameter missing")
            
            # Get permission manager
            from permissions import get_permission_manager
            permission_manager = get_permission_manager()
            
            if not permission_manager:
                current_app.logger.error("Permission system not initialized")
                abort(500, description="Permission system not initialized")
            
            # Check branch access
            has_access = permission_manager.check_branch_access(current_user, branch)
            
            if not has_access:
                # Log access denial
                from permissions.audit import PermissionAuditLogger
                audit_logger = PermissionAuditLogger()
                
                reason = f"User does not have access to branch: {branch}"
                audit_logger.log_access_denied(
                    current_user,
                    f"branch_access:{branch}",
                    request.path,
                    reason
                )
                
                # Return 403 Forbidden
                abort(403, description=f"You do not have access to branch: {branch}")
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def requires_roles(*allowed_roles):
    """
    Legacy decorator for backward compatibility.
    Logs deprecation warning and delegates to requires_permission.
    
    This decorator is maintained for gradual migration from the old system.
    New code should use @requires_permission instead.
    
    Args:
        *allowed_roles: One or more role names
    
    Usage:
        @requires_roles('SUPER_ADMIN', 'CASHIER')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Log deprecation warning
            warnings.warn(
                f"@requires_roles is deprecated. Use @requires_permission instead. "
                f"Route: {request.endpoint}",
                DeprecationWarning,
                stacklevel=2
            )
            
            # Check if user is authenticated
            if not current_user.is_authenticated:
                flash("You need to login first.", "warning")
                return redirect(url_for('main.login'))
            
            # Check if user's role is in allowed roles
            if current_user.role not in allowed_roles:
                abort(403, description="You do not have permission to view this page.")
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
