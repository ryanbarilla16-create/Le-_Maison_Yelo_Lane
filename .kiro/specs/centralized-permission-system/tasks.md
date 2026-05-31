# Implementation Plan: Centralized Permission System

## Overview

This implementation plan breaks down the centralized role-based permission system into discrete coding tasks. The system will replace hardcoded role checks across 100+ routes with a flexible, configuration-driven permission system using decorators, caching, and audit logging.

## Tasks

- [ ] 1. Create permission system directory structure and core models
  - Create `permissions/` directory with `__init__.py`
  - Create database migration for new Permission, RolePermission, and PermissionAuditLog models
  - Add Permission model with fields: id, name, description, module, action, created_at
  - Add RolePermission model with fields: id, role, permission_name, created_at, unique constraint
  - Add PermissionAuditLog model with fields: id, user_id, action, permission_name, route, reason, ip_address, user_agent, created_at
  - Run migration to create new database tables
  - _Requirements: 1.1, 1.6, 6.4_

- [ ] 2. Implement permission configuration system
  - [ ] 2.1 Create permissions_config.json file
    - Define all permissions using module.action naming convention (menu.view, orders.create, etc.)
    - Define all seven roles (SUPER_ADMIN, ADMIN, CASHIER, KITCHEN, INVENTORY_STAFF, RIDER, USER)
    - Map permissions to each role according to requirements
    - Add permission_groups for common permission sets
    - Include version field and documentation comments
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 1.7, 3.1-3.12_

  - [ ] 2.2 Create PermissionManager class (permissions/manager.py)
    - Implement `__init__()` to load config from file path
    - Implement `_load_config()` to parse JSON and cache in memory
    - Implement `reload_config()` to detect file changes and reload
    - Implement `validate_config()` to check for syntax errors and undefined references
    - Add config_mtime tracking for automatic reload detection
    - _Requirements: 1.1, 1.5, 7.1, 7.2, 7.4, 11.1_

  - [ ] 2.3 Implement core permission checking methods
    - Implement `has_permission(user, permission_name)` with wildcard support
    - Implement `has_any_permission(user, permission_list)` for OR logic
    - Implement `has_all_permissions(user, permission_list)` for AND logic
    - Implement `get_user_permissions(user)` to return all user permissions
    - Implement `_resolve_wildcard(permission_name, user_permissions)` for module.* matching
    - Handle SUPER_ADMIN wildcard (*) permission
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 9.4_

- [ ] 3. Implement permission decorators
  - [ ] 3.1 Create @requires_permission decorator (permissions/decorators.py)
    - Accept variable permission names as arguments
    - Support `require_all` parameter for AND vs OR logic
    - Integrate with Flask-Login's current_user
    - Return HTTP 403 for unauthorized access
    - Redirect unauthenticated users to login page
    - Call PermissionManager.has_permission() for validation
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ] 3.2 Create @requires_branch_access decorator
    - Accept branch_param argument to specify route parameter name
    - Extract branch value from route parameters
    - Call PermissionManager.check_branch_access() for validation
    - Return HTTP 403 for branch access violations
    - Support SUPER_ADMIN access to all branches
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [ ] 3.3 Create @requires_roles legacy decorator wrapper
    - Maintain backward compatibility with existing decorator
    - Log deprecation warning when used
    - Delegate to @requires_permission internally
    - Map legacy role checks to new permission names
    - _Requirements: 5.1, 5.2, 5.4_

- [ ] 4. Implement branch access control logic
  - [ ] 4.1 Add check_branch_access method to PermissionManager
    - Check if user.role == 'SUPER_ADMIN' (grant all access)
    - Check if user.branch == 'ALL' (grant all access)
    - Check if user.branch matches requested branch
    - Return boolean result
    - _Requirements: 4.1, 4.2, 4.5_

  - [ ]* 4.2 Write unit tests for branch access control
    - Test SUPER_ADMIN access to all branches
    - Test ADMIN access to assigned branch only
    - Test ADMIN denial for other branches
    - Test users without branch assignment
    - _Requirements: 4.1, 4.2, 4.5_

- [ ] 5. Implement permission caching system
  - [ ] 5.1 Create PermissionCache class (permissions/cache.py)
    - Implement `__init__()` to initialize cache dictionary
    - Implement `get(key)` to retrieve cached permission results
    - Implement `set(key, value)` to store permission results
    - Implement `clear()` to clear all cached permissions
    - Implement `invalidate_user(user_id)` to clear user-specific cache
    - _Requirements: 8.5, 11.2_

  - [ ] 5.2 Integrate cache with Flask request lifecycle
    - Add `@app.before_request` hook to initialize PermissionCache in `g.permission_cache`
    - Add `@app.teardown_request` hook to clear cache after request
    - Update PermissionManager to use g.permission_cache for lookups
    - _Requirements: 8.5, 8.6, 11.2_

  - [ ]* 5.3 Write unit tests for permission caching
    - Test cache hit and miss scenarios
    - Test cache invalidation on user role change
    - Test cache clearing on request teardown
    - _Requirements: 8.5, 8.6, 11.2_

- [ ] 6. Implement audit logging system
  - [ ] 6.1 Create PermissionAuditLogger class (permissions/audit.py)
    - Implement `log_access_denied(user, permission, route, reason)` to log 403 errors
    - Implement `log_permission_granted(user, permission)` to log successful grants
    - Implement `log_permission_revoked(user, permission)` to log revocations
    - Implement `log_config_change(user, changes)` to log config modifications
    - Implement `_get_request_context()` to extract IP address and user agent
    - Create PermissionAuditLog database entries for each event
    - _Requirements: 6.1, 6.2, 6.3, 6.6_

  - [ ] 6.2 Integrate audit logging with decorators
    - Call `log_access_denied()` when @requires_permission denies access
    - Call `log_access_denied()` when @requires_branch_access denies access
    - Include route path, user info, and reason in audit logs
    - _Requirements: 6.2, 6.6_

  - [ ]* 6.3 Write unit tests for audit logging
    - Test audit log creation for access denials
    - Test audit log creation for permission changes
    - Test IP address and user agent extraction
    - Verify 90-day retention requirement
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6_

- [ ] 7. Implement error handling and validation
  - [ ] 7.1 Create custom exception classes (permissions/exceptions.py)
    - Create PermissionError base exception
    - Create PermissionConfigError for config validation errors
    - Create PermissionDeniedError for authorization failures
    - Create BranchAccessDeniedError for branch access violations
    - _Requirements: 7.3_

  - [ ] 7.2 Add configuration validation to PermissionManager
    - Validate all permission names follow module.action format
    - Validate all role names are in allowed list
    - Validate all permission references exist in permissions section
    - Raise PermissionConfigError on startup if validation fails
    - _Requirements: 7.1, 7.2, 7.4_

  - [ ] 7.3 Add error handling to decorators
    - Return user-friendly error messages for permission denials
    - Include required permission name in error response
    - Show detailed debugging info in development mode
    - Hide internal details in production mode
    - _Requirements: 7.3, 7.5, 7.6_

  - [ ]* 7.4 Write unit tests for error handling
    - Test PermissionConfigError on invalid config
    - Test PermissionDeniedError on unauthorized access
    - Test BranchAccessDeniedError on branch violations
    - Test error message formatting
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 7.6_

- [ ] 8. Create migration utility for legacy decorators
  - [ ] 8.1 Create PermissionMigrationTool class (permissions/migration.py)
    - Implement `scan_codebase(directory)` to find @requires_roles usage
    - Implement `suggest_mappings()` to map roles to permissions
    - Implement `generate_migration_report()` to output findings
    - Use AST parsing to analyze Python files
    - Generate mapping suggestions based on permissions_config.json
    - _Requirements: 5.3, 5.5_

  - [ ] 8.2 Create CLI command for migration scanning
    - Add Flask CLI command `flask permissions scan`
    - Output report showing all @requires_roles decorators
    - Suggest replacement @requires_permission decorators
    - Highlight routes without any authorization
    - _Requirements: 5.3, 5.5, 10.3_

- [ ] 9. Integrate permission system with Flask application
  - [ ] 9.1 Initialize permission system in app.py
    - Import PermissionManager and init_permissions
    - Create PermissionManager instance with config path
    - Call init_permissions(app, permission_manager)
    - Add before_request hook for permission cache setup
    - Add teardown_request hook for cache cleanup
    - _Requirements: 1.5, 8.5, 11.2_

  - [ ] 9.2 Add database indexes for performance
    - Create index on User.role column
    - Create index on PermissionAuditLog.created_at column
    - Create index on PermissionAuditLog.user_id column
    - Run migration to add indexes
    - _Requirements: 11.4_

  - [ ]* 9.3 Write integration tests for Flask app setup
    - Test permission system initialization
    - Test request lifecycle hooks
    - Test database indexes exist
    - _Requirements: 1.5, 8.5, 11.4_

- [ ] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Migrate existing routes to new permission system
  - [ ] 11.1 Migrate admin routes (routes/admin/__init__.py)
    - Replace @requires_roles with @requires_permission on menu routes
    - Replace @requires_roles with @requires_permission on order routes
    - Replace @requires_roles with @requires_permission on user management routes
    - Replace @requires_roles with @requires_permission on reservation routes
    - Add @requires_branch_access where appropriate
    - _Requirements: 2.1, 2.2, 2.3, 4.3_

  - [ ] 11.2 Migrate cashier routes (routes/portals.py)
    - Replace @requires_roles with @requires_permission on order creation routes
    - Replace @requires_roles with @requires_permission on payment routes
    - Replace @requires_roles with @requires_permission on report routes
    - Add @requires_branch_access for branch-specific data
    - _Requirements: 2.1, 2.2, 2.3, 4.3_

  - [ ] 11.3 Migrate kitchen routes (routes/portals.py)
    - Replace @requires_roles with @requires_permission on order viewing routes
    - Replace @requires_roles with @requires_permission on status update routes
    - Replace @requires_roles with @requires_permission on recipe routes
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ] 11.4 Migrate inventory routes (routes/portals.py)
    - Replace @requires_roles with @requires_permission on inventory management routes
    - Replace @requires_roles with @requires_permission on supplier routes
    - Replace @requires_roles with @requires_permission on stock request routes
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ] 11.5 Migrate rider routes (routes/portals.py)
    - Replace @requires_roles with @requires_permission on delivery routes
    - Replace @requires_roles with @requires_permission on order chat routes
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ] 11.6 Migrate API routes (routes/api/__init__.py)
    - Replace @requires_roles with @requires_permission on mobile API endpoints
    - Ensure customer-facing routes use appropriate permissions
    - _Requirements: 2.1, 2.2, 2.3_

- [ ] 12. Checkpoint - Ensure all tests pass after migration
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Create admin interface for permission management
  - [ ] 13.1 Create permission audit log viewer
    - Create route `/admin/permissions/audit` with @requires_permission('users.manage_branch')
    - Display PermissionAuditLog entries in table format
    - Add filters for user, action, date range
    - Add pagination for large result sets
    - _Requirements: 6.5_

  - [ ] 13.2 Create permission matrix report
    - Create route `/admin/permissions/matrix` with @requires_permission('users.manage_branch')
    - Generate table showing roles vs permissions
    - Highlight which roles have which permissions
    - Add export to CSV functionality
    - _Requirements: 10.6_

  - [ ] 13.3 Create permission testing interface
    - Create route `/admin/permissions/test` with @requires_permission('users.manage_branch')
    - Allow admins to simulate permission checks for any user
    - Display which permissions a user has
    - Show which routes a user can access
    - _Requirements: 10.2_

- [ ] 14. Add performance monitoring and metrics
  - [ ] 14.1 Add permission check timing metrics
    - Instrument PermissionManager.has_permission() with timing
    - Log slow permission checks (>5ms)
    - Add metrics endpoint for monitoring
    - _Requirements: 11.3, 11.6_

  - [ ]* 14.2 Write performance tests
    - Test permission check completes in <5ms for 95% of requests
    - Test cache effectiveness
    - Test N+1 query prevention
    - _Requirements: 11.3, 11.5_

- [ ] 15. Create documentation and developer guide
  - [ ] 15.1 Create permissions/README.md
    - Document permission naming conventions
    - Document decorator usage examples
    - Document how to add new permissions
    - Document migration guide from @requires_roles
    - Document troubleshooting common issues
    - _Requirements: 5.5_

  - [ ] 15.2 Create API documentation
    - Document PermissionManager public methods
    - Document decorator parameters and behavior
    - Document exception types and handling
    - Document configuration file format
    - _Requirements: 7.3, 12.4_

  - [ ] 15.3 Create permission configuration management guide
    - Document how to add new roles
    - Document how to add new permissions
    - Document how to modify existing permissions
    - Document how to export/import configurations
    - Document environment-specific configurations
    - _Requirements: 12.1, 12.2, 12.3, 12.5, 12.6_

- [ ] 16. Final checkpoint and cleanup
  - [ ] 16.1 Run full test suite
    - Run all unit tests
    - Run all integration tests
    - Verify test coverage meets requirements
    - _Requirements: 10.4, 10.5_

  - [ ] 16.2 Remove legacy @requires_roles decorator
    - Remove @requires_roles from utils.py
    - Verify no routes still use legacy decorator
    - Update all documentation references
    - _Requirements: 5.4_

  - [ ] 16.3 Final verification
    - Test all seven roles can access appropriate routes
    - Test all seven roles are denied inappropriate routes
    - Test branch access control works correctly
    - Test audit logging captures all events
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 3.1-3.12, 4.1-4.5, 6.1-6.6_

## Notes

- This implementation uses Python and Flask, matching the existing application stack
- The permission system is designed for gradual migration, allowing both old and new decorators to coexist temporarily
- Database migrations should be tested in a development environment before applying to production
- The permission configuration file should be version-controlled for change tracking
- Performance testing should be conducted with realistic user loads to validate caching effectiveness
- All routes should be tested with each role to ensure proper access control

