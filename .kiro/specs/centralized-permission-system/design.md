# Design Document: Centralized Permission System

## Overview

This document describes the technical design for a centralized role-based access control (RBAC) system that will replace hardcoded role checks scattered across 100+ routes in the Flask restaurant management application. The system uses a hierarchical permission model with decorators for route protection, supports seven distinct roles, and provides granular permissions across multiple modules.

## Design Language

This design uses **Python** as the implementation language, matching the existing Flask application codebase.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Flask Application                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐      ┌──────────────────────────────┐   │
│  │   Routes     │─────▶│  Permission Decorators       │   │
│  │  (Blueprints)│      │  @requires_permission()      │   │
│  └──────────────┘      │  @requires_branch_access()   │   │
│                         └──────────┬───────────────────┘   │
│                                    │                        │
│                         ┌──────────▼───────────────────┐   │
│                         │  Permission Manager          │   │
│                         │  - has_permission()          │   │
│                         │  - get_user_permissions()    │   │
│                         │  - check_branch_access()     │   │
│                         └──────────┬───────────────────┘   │
│                                    │                        │
│              ┌─────────────────────┼─────────────────┐     │
│              │                     │                 │     │
│   ┌──────────▼──────┐   ┌─────────▼────────┐  ┌────▼────┐│
│   │ Permission      │   │  Permission      │  │ Audit   ││
│   │ Config Loader   │   │  Cache           │  │ Logger  ││
│   │ (JSON/YAML)     │   │  (Request-scoped)│  │         ││
│   └─────────────────┘   └──────────────────┘  └─────────┘│
│                                                              │
├─────────────────────────────────────────────────────────────┤
│                     Database Layer                           │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │   User   │  │  Permission  │  │  PermissionAudit   │   │
│  │  (role,  │  │  (optional)  │  │  Log               │   │
│  │  branch) │  │              │  │                    │   │
│  └──────────┘  └──────────────┘  └────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Data Models

#### Existing User Model (Extended)
```python
class User(db.Model, UserMixin):
    # ... existing fields ...
    role = db.Column(db.String(20), default='USER', index=True)
    branch = db.Column(db.String(50), nullable=True, default=None)
```

#### New Permission Model (Optional - for database-driven config)
```python
class Permission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    module = db.Column(db.String(50), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=get_ph_time)
```

#### New RolePermission Model (Optional - for database-driven config)
```python
class RolePermission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False, index=True)
    permission_name = db.Column(db.String(100), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=get_ph_time)
    
    __table_args__ = (
        db.UniqueConstraint('role', 'permission_name', name='uq_role_permission'),
    )
```

#### New PermissionAuditLog Model
```python
class PermissionAuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False)  # GRANTED, REVOKED, DENIED, CONFIG_CHANGED
    permission_name = db.Column(db.String(100), nullable=True)
    route = db.Column(db.String(255), nullable=True)
    reason = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=get_ph_time, index=True)
    
    user = db.relationship('User', backref=db.backref('permission_audit_logs', lazy=True))
```

### Permission Configuration File

**File Location:** `permissions_config.json`

**Structure:**
```json
{
  "version": "1.0.0",
  "permissions": {
    "menu.view": {
      "description": "View menu items",
      "module": "menu"
    },
    "menu.create": {
      "description": "Create new menu items",
      "module": "menu"
    },
    "menu.edit": {
      "description": "Edit existing menu items",
      "module": "menu"
    },
    "menu.delete": {
      "description": "Delete menu items",
      "module": "menu"
    },
    "menu.toggle_availability": {
      "description": "Toggle menu item availability",
      "module": "menu"
    },
    "menu.view_prices": {
      "description": "View menu item prices",
      "module": "menu"
    },
    "menu.edit_prices": {
      "description": "Edit menu item prices",
      "module": "menu"
    },
    "menu.view_costs": {
      "description": "View menu item costs",
      "module": "menu"
    },
    "orders.view": {
      "description": "View orders",
      "module": "orders"
    },
    "orders.create": {
      "description": "Create new orders",
      "module": "orders"
    },
    "orders.create_own": {
      "description": "Create own orders (customer)",
      "module": "orders"
    },
    "orders.view_own": {
      "description": "View own orders (customer)",
      "module": "orders"
    },
    "orders.view_branch": {
      "description": "View orders for assigned branch",
      "module": "orders"
    },
    "orders.view_all": {
      "description": "View all orders across branches",
      "module": "orders"
    },
    "orders.update_status": {
      "description": "Update order status",
      "module": "orders"
    },
    "orders.void": {
      "description": "Void orders",
      "module": "orders"
    },
    "orders.delete": {
      "description": "Delete orders",
      "module": "orders"
    },
    "inventory.view": {
      "description": "View inventory",
      "module": "inventory"
    },
    "inventory.manage": {
      "description": "Manage inventory (add, update, delete)",
      "module": "inventory"
    },
    "inventory.view_costs": {
      "description": "View inventory costs",
      "module": "inventory"
    },
    "suppliers.manage": {
      "description": "Manage suppliers",
      "module": "inventory"
    },
    "stock_requests.create": {
      "description": "Create stock requests",
      "module": "inventory"
    },
    "stock_requests.approve": {
      "description": "Approve stock requests",
      "module": "inventory"
    },
    "reports.view": {
      "description": "View reports",
      "module": "reports"
    },
    "reports.view_daily_sales": {
      "description": "View daily sales reports",
      "module": "reports"
    },
    "reports.view_branch": {
      "description": "View branch-specific reports",
      "module": "reports"
    },
    "reports.view_sales": {
      "description": "View sales reports",
      "module": "reports"
    },
    "reservations.create": {
      "description": "Create reservations",
      "module": "reservations"
    },
    "reservations.view_own": {
      "description": "View own reservations",
      "module": "reservations"
    },
    "reservations.manage_branch": {
      "description": "Manage reservations for assigned branch",
      "module": "reservations"
    },
    "users.manage_branch": {
      "description": "Manage users for assigned branch",
      "module": "users"
    },
    "users.access_other_branches": {
      "description": "Access data from other branches",
      "module": "users"
    },
    "deliveries.view_assigned": {
      "description": "View assigned deliveries",
      "module": "deliveries"
    },
    "deliveries.update_status": {
      "description": "Update delivery status",
      "module": "deliveries"
    },
    "order_chat.access": {
      "description": "Access order chat",
      "module": "deliveries"
    },
    "reviews.create": {
      "description": "Create reviews",
      "module": "reviews"
    },
    "recipes.view": {
      "description": "View recipes",
      "module": "menu"
    },
    "payments.process": {
      "description": "Process payments",
      "module": "orders"
    }
  },
  "roles": {
    "USER": {
      "description": "Regular customer",
      "permissions": [
        "menu.view",
        "orders.create_own",
        "orders.view_own",
        "reservations.create",
        "reservations.view_own",
        "reviews.create"
      ]
    },
    "KITCHEN": {
      "description": "Kitchen staff",
      "permissions": [
        "orders.view",
        "orders.update_status",
        "recipes.view",
        "stock_requests.create"
      ]
    },
    "CASHIER": {
      "description": "Cashier staff",
      "permissions": [
        "orders.create",
        "orders.view",
        "orders.view_branch",
        "payments.process",
        "reports.view_daily_sales",
        "menu.view",
        "menu.view_prices"
      ]
    },
    "INVENTORY_STAFF": {
      "description": "Inventory management staff",
      "permissions": [
        "inventory.manage",
        "inventory.view",
        "inventory.view_costs",
        "suppliers.manage",
        "stock_requests.approve"
      ]
    },
    "ADMIN": {
      "description": "Branch administrator",
      "permissions": [
        "menu.view",
        "menu.create",
        "menu.edit",
        "menu.toggle_availability",
        "menu.view_prices",
        "orders.view_branch",
        "orders.create",
        "orders.update_status",
        "reports.view_branch",
        "reservations.manage_branch",
        "users.manage_branch",
        "inventory.view",
        "payments.process"
      ]
    },
    "SUPER_ADMIN": {
      "description": "System administrator with full access",
      "permissions": ["*"]
    },
    "RIDER": {
      "description": "Delivery rider",
      "permissions": [
        "deliveries.view_assigned",
        "deliveries.update_status",
        "order_chat.access"
      ]
    }
  },
  "permission_groups": {
    "menu_full": ["menu.view", "menu.create", "menu.edit", "menu.delete", "menu.toggle_availability", "menu.view_prices", "menu.edit_prices", "menu.view_costs"],
    "orders_full": ["orders.view", "orders.create", "orders.update_status", "orders.void", "orders.delete", "orders.view_all"],
    "inventory_full": ["inventory.view", "inventory.manage", "inventory.view_costs", "suppliers.manage", "stock_requests.create", "stock_requests.approve"]
  }
}
```

### Core Components

#### 1. Permission Manager (`permissions/manager.py`)

```python
class PermissionManager:
    """
    Central permission management system.
    Handles permission checking, caching, and configuration loading.
    """
    
    def __init__(self, config_path='permissions_config.json'):
        self.config_path = config_path
        self.config = None
        self.config_mtime = None
        self._load_config()
    
    def _load_config(self):
        """Load permission configuration from file."""
        pass
    
    def reload_config(self):
        """Reload configuration if file has changed."""
        pass
    
    def has_permission(self, user, permission_name):
        """Check if user has a specific permission."""
        pass
    
    def has_any_permission(self, user, permission_list):
        """Check if user has any of the specified permissions."""
        pass
    
    def has_all_permissions(self, user, permission_list):
        """Check if user has all specified permissions."""
        pass
    
    def get_user_permissions(self, user):
        """Get all permissions for a user."""
        pass
    
    def check_branch_access(self, user, branch):
        """Check if user has access to a specific branch."""
        pass
    
    def _resolve_wildcard(self, permission_name, user_permissions):
        """Resolve wildcard permissions (e.g., menu.*)."""
        pass
    
    def validate_config(self):
        """Validate permission configuration for errors."""
        pass
```

#### 2. Permission Decorators (`permissions/decorators.py`)

```python
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
    """
    pass

def requires_branch_access(branch_param='branch'):
    """
    Decorator to enforce branch-level access control.
    
    Args:
        branch_param: Name of the route parameter containing branch value
    
    Usage:
        @requires_branch_access()
        @requires_branch_access(branch_param='branch_name')
    """
    pass

def requires_roles(*allowed_roles):
    """
    Legacy decorator for backward compatibility.
    Logs deprecation warning and delegates to requires_permission.
    """
    pass
```

#### 3. Permission Cache (`permissions/cache.py`)

```python
class PermissionCache:
    """
    Request-scoped permission cache to avoid repeated lookups.
    """
    
    def __init__(self):
        self._cache = {}
    
    def get(self, key):
        """Get cached permission result."""
        pass
    
    def set(self, key, value):
        """Cache permission result."""
        pass
    
    def clear(self):
        """Clear all cached permissions."""
        pass
    
    def invalidate_user(self, user_id):
        """Invalidate cache for a specific user."""
        pass
```

#### 4. Audit Logger (`permissions/audit.py`)

```python
class PermissionAuditLogger:
    """
    Logs permission-related events for security auditing.
    """
    
    def log_access_denied(self, user, permission, route, reason=None):
        """Log when access is denied."""
        pass
    
    def log_permission_granted(self, user, permission):
        """Log when permission is granted."""
        pass
    
    def log_permission_revoked(self, user, permission):
        """Log when permission is revoked."""
        pass
    
    def log_config_change(self, user, changes):
        """Log when permission configuration is modified."""
        pass
    
    def _get_request_context(self):
        """Extract IP address and user agent from request."""
        pass
```

#### 5. Migration Utility (`permissions/migration.py`)

```python
class PermissionMigrationTool:
    """
    Utility to help migrate from legacy @requires_roles to new system.
    """
    
    def scan_codebase(self, directory='routes'):
        """Scan codebase for @requires_roles usage."""
        pass
    
    def suggest_mappings(self):
        """Suggest permission mappings for legacy decorators."""
        pass
    
    def generate_migration_report(self):
        """Generate a report of migration progress."""
        pass
```

### Permission Resolution Algorithm

```python
def resolve_permission(user, permission_name):
    """
    Permission resolution algorithm with wildcard support.
    
    Steps:
    1. Check if user is authenticated
    2. Get user's role
    3. Load role permissions from config
    4. Check for exact permission match
    5. Check for wildcard matches (module.*, *)
    6. Check for permission groups
    7. Return result
    """
    
    # Step 1: Authentication check
    if not user.is_authenticated:
        return False
    
    # Step 2: Get user role
    user_role = user.role.upper()
    
    # Step 3: Load role permissions
    role_permissions = config['roles'].get(user_role, {}).get('permissions', [])
    
    # Step 4: Check for SUPER_ADMIN wildcard
    if '*' in role_permissions:
        return True
    
    # Step 5: Check exact match
    if permission_name in role_permissions:
        return True
    
    # Step 6: Check wildcard matches
    module = permission_name.split('.')[0]
    if f"{module}.*" in role_permissions:
        return True
    
    # Step 7: Check permission groups
    for group_name, group_perms in config.get('permission_groups', {}).items():
        if group_name in role_permissions and permission_name in group_perms:
            return True
    
    return False
```

### Branch Access Control

```python
def check_branch_access(user, requested_branch):
    """
    Branch access control algorithm.
    
    Rules:
    - SUPER_ADMIN: Access to all branches
    - ADMIN/CASHIER/KITCHEN/INVENTORY_STAFF: Access to assigned branch only
    - USER/RIDER: No branch restrictions (data filtered by user_id)
    """
    
    # SUPER_ADMIN has access to all branches
    if user.role.upper() == 'SUPER_ADMIN':
        return True
    
    # Check if user has branch assignment
    if not user.branch:
        return False
    
    # Check if user's branch matches requested branch
    if user.branch == 'ALL':
        return True
    
    return user.branch == requested_branch
```

### Error Handling

```python
class PermissionError(Exception):
    """Base exception for permission-related errors."""
    pass

class PermissionConfigError(PermissionError):
    """Raised when permission configuration is invalid."""
    pass

class PermissionDeniedError(PermissionError):
    """Raised when user lacks required permission."""
    pass

class BranchAccessDeniedError(PermissionError):
    """Raised when user lacks branch access."""
    pass
```

### Integration Points

#### Flask Application Setup

```python
# app.py
from permissions import PermissionManager, init_permissions

# Initialize permission system
permission_manager = PermissionManager('permissions_config.json')
init_permissions(app, permission_manager)

# Register request hooks
@app.before_request
def setup_permission_cache():
    g.permission_cache = PermissionCache()

@app.teardown_request
def clear_permission_cache(exception=None):
    if hasattr(g, 'permission_cache'):
        g.permission_cache.clear()
```

#### Route Protection Example

```python
# Before (legacy)
@admin_bp.route('/menu/create')
@login_required
@admin_required
def create_menu_item():
    pass

# After (new system)
@admin_bp.route('/menu/create')
@login_required
@requires_permission('menu.create')
def create_menu_item():
    pass

# Multiple permissions (OR logic)
@admin_bp.route('/menu/edit/<int:id>')
@login_required
@requires_permission('menu.edit', 'menu.create')
def edit_menu_item(id):
    pass

# Multiple permissions (AND logic)
@admin_bp.route('/menu/delete/<int:id>')
@login_required
@requires_permission('menu.delete', 'menu.edit', require_all=True)
def delete_menu_item(id):
    pass

# Branch-specific access
@admin_bp.route('/orders/<branch>')
@login_required
@requires_permission('orders.view_branch')
@requires_branch_access(branch_param='branch')
def view_branch_orders(branch):
    pass
```

#### Programmatic Permission Checks

```python
# In business logic
from permissions import permission_manager

def process_order(order_id):
    if not permission_manager.has_permission(current_user, 'orders.update_status'):
        raise PermissionDeniedError("Cannot update order status")
    
    # Process order...
```

### Testing Strategy

#### Unit Tests
- Test permission resolution algorithm
- Test wildcard matching
- Test branch access control
- Test cache functionality
- Test audit logging

#### Integration Tests
- Test decorator behavior on routes
- Test permission checks across all roles
- Test configuration loading and reloading
- Test error handling

#### Migration Tests
- Test backward compatibility with legacy decorators
- Test migration utility accuracy

### Performance Considerations

1. **Configuration Caching**: Load config once at startup, reload only on file change
2. **Request-Scoped Cache**: Cache permission lookups for duration of request
3. **Database Indexes**: Index on User.role and PermissionAuditLog.created_at
4. **Lazy Loading**: Load permissions only when needed
5. **Batch Queries**: Avoid N+1 queries when checking multiple permissions

### Security Considerations

1. **Fail Closed**: Deny access by default if permission check fails
2. **Audit Trail**: Log all access denials and permission changes
3. **Configuration Validation**: Validate config on startup to catch errors early
4. **Branch Isolation**: Enforce strict branch-level data isolation
5. **Rate Limiting**: Consider rate limiting on permission checks to prevent abuse

## Correctness Properties

This design does not include property-based testing as it primarily involves configuration management, decorator patterns, and database operations which are better suited for unit and integration testing.

## Implementation Notes

1. **Phase 1**: Implement core permission system (manager, decorators, cache)
2. **Phase 2**: Add audit logging and migration utilities
3. **Phase 3**: Migrate existing routes incrementally
4. **Phase 4**: Add admin UI for permission management
5. **Phase 5**: Remove legacy decorator after full migration

## Dependencies

- Flask (existing)
- Flask-Login (existing)
- SQLAlchemy (existing)
- Python standard library (json, os, functools, threading)

## Configuration Management

- **Development**: Use file-based configuration for easy editing
- **Production**: Support both file-based and database-driven configuration
- **Version Control**: Store permissions_config.json in git for change tracking
- **Deployment**: Validate configuration during deployment pipeline

## Backward Compatibility

The system maintains backward compatibility with the existing `@requires_roles()` decorator by:
1. Keeping the decorator functional but logging deprecation warnings
2. Providing a migration utility to identify and suggest replacements
3. Supporting both decorators simultaneously during transition period
4. Documenting migration path in developer guide

## Future Enhancements

1. **Dynamic Permissions**: Allow runtime permission assignment without config changes
2. **Permission Inheritance**: Support role hierarchies (e.g., ADMIN inherits CASHIER permissions)
3. **Time-Based Permissions**: Support temporary permission grants
4. **Permission Templates**: Pre-defined permission sets for common scenarios
5. **API Endpoints**: REST API for permission management
6. **UI Dashboard**: Web interface for managing permissions and viewing audit logs
