# Requirements Document: Centralized Permission System

## Introduction

This document specifies requirements for a centralized role-based permission system to replace hardcoded role checks scattered across 100+ routes in a Flask restaurant management application. The system will provide a single source of truth for permission configuration, use decorators for route protection, and support seven distinct roles (SUPER_ADMIN, ADMIN, CASHIER, KITCHEN, INVENTORY_STAFF, RIDER, USER) with granular permissions across multiple modules (menu, orders, inventory, reports, reservations, etc.).

## Glossary

- **Permission_System**: The centralized role-based access control (RBAC) system that manages all authorization logic
- **Permission_Config**: A centralized configuration file or data structure that maps roles to permissions
- **Permission_Decorator**: A Flask route decorator that enforces permission checks before allowing access to protected endpoints
- **Role**: A named user classification (SUPER_ADMIN, ADMIN, CASHIER, KITCHEN, INVENTORY_STAFF, RIDER, USER)
- **Permission**: A named capability that grants access to specific operations or resources (e.g., "menu.view", "orders.create", "inventory.manage")
- **Module**: A functional area of the application (menu, orders, inventory, reports, reservations, users, settings)
- **Route**: A Flask endpoint that handles HTTP requests
- **Audit_Log**: A persistent record of permission-related events and changes
- **Branch**: A physical restaurant location (Pagsanjan, Lucban, or ALL for SUPER_ADMIN)
- **Legacy_Decorator**: The existing `@requires_roles()` decorator currently used in the codebase

## Requirements

### Requirement 1: Centralized Permission Configuration

**User Story:** As a system administrator, I want all role-to-permission mappings defined in a single location, so that I can understand and modify access control without searching through multiple files.

#### Acceptance Criteria

1. THE Permission_System SHALL store all role-to-permission mappings in a single Permission_Config file
2. THE Permission_Config SHALL define permissions using a hierarchical naming convention (module.action format)
3. THE Permission_Config SHALL support all seven roles (SUPER_ADMIN, ADMIN, CASHIER, KITCHEN, INVENTORY_STAFF, RIDER, USER)
4. THE Permission_Config SHALL define permissions for all modules (menu, orders, inventory, reports, reservations, users, settings, deliveries)
5. WHEN the Permission_Config is modified, THE Permission_System SHALL reload the configuration without requiring application restart
6. THE Permission_Config SHALL use a human-readable format (JSON or YAML)
7. THE Permission_Config SHALL include documentation comments explaining each permission's purpose

### Requirement 2: Permission Decorator Implementation

**User Story:** As a developer, I want to protect routes using a simple decorator syntax, so that I can enforce permissions consistently without writing repetitive authorization code.

#### Acceptance Criteria

1. THE Permission_System SHALL provide a `@requires_permission()` decorator that accepts permission names as arguments
2. WHEN a route is decorated with `@requires_permission()`, THE Permission_System SHALL verify the current user has the required permission before executing the route handler
3. IF the current user lacks the required permission, THEN THE Permission_System SHALL return an HTTP 403 Forbidden response
4. THE Permission_Decorator SHALL support multiple permission arguments using OR logic (user needs ANY of the specified permissions)
5. THE Permission_Decorator SHALL support an optional `require_all` parameter for AND logic (user needs ALL specified permissions)
6. THE Permission_Decorator SHALL integrate with Flask-Login's `current_user` object
7. THE Permission_Decorator SHALL redirect unauthenticated users to the appropriate login page based on their intended destination

### Requirement 3: Role-Based Permission Distribution

**User Story:** As a restaurant owner, I want each role to have appropriate access levels, so that staff can perform their duties without accessing sensitive operations outside their responsibility.

#### Acceptance Criteria

1. WHEN a user has the CUSTOMER role, THE Permission_System SHALL grant permissions: menu.view, orders.create_own, orders.view_own, reservations.create, reservations.view_own, reviews.create
2. WHEN a user has the KITCHEN role, THE Permission_System SHALL grant permissions: orders.view, orders.update_status, recipes.view, stock_requests.create
3. WHEN a user has the KITCHEN role, THE Permission_System SHALL deny permissions: menu.view_prices, menu.view_costs, inventory.view_costs, reports.view
4. WHEN a user has the CASHIER role, THE Permission_System SHALL grant permissions: orders.create, orders.view, payments.process, reports.view_daily_sales
5. WHEN a user has the CASHIER role, THE Permission_System SHALL deny permissions: menu.delete, menu.edit_prices, orders.void, orders.delete
6. WHEN a user has the INVENTORY_STAFF role, THE Permission_System SHALL grant permissions: inventory.manage, suppliers.manage, stock_requests.approve, inventory.view_costs
7. WHEN a user has the INVENTORY_STAFF role, THE Permission_System SHALL deny permissions: menu.manage, orders.view, reports.view_sales
8. WHEN a user has the ADMIN role, THE Permission_System SHALL grant permissions: menu.toggle_availability, orders.view_branch, reports.view_branch, reservations.manage_branch, users.manage_branch
9. WHEN a user has the ADMIN role, THE Permission_System SHALL deny permissions: menu.delete, menu.edit_prices, users.access_other_branches
10. WHEN a user has the SUPER_ADMIN role, THE Permission_System SHALL grant all permissions across all branches
11. WHEN a user has the RIDER role, THE Permission_System SHALL grant permissions: deliveries.view_assigned, deliveries.update_status, order_chat.access
12. WHEN a user has the RIDER role, THE Permission_System SHALL deny permissions: orders.view_all, menu.manage, inventory.view, reports.view

### Requirement 4: Branch-Based Access Control

**User Story:** As a branch manager, I want to access only my branch's data, so that operations remain isolated between restaurant locations.

#### Acceptance Criteria

1. WHEN a user has the ADMIN role with a specific branch assignment, THE Permission_System SHALL restrict data access to that branch only
2. WHEN a user has the SUPER_ADMIN role, THE Permission_System SHALL grant access to all branches
3. THE Permission_System SHALL provide a `@requires_branch_access()` decorator that validates branch-level permissions
4. WHEN a route requires branch-specific data, THE Permission_Decorator SHALL automatically filter queries by the user's assigned branch
5. IF a user attempts to access data from a branch they are not assigned to, THEN THE Permission_System SHALL return an HTTP 403 Forbidden response

### Requirement 5: Migration from Legacy System

**User Story:** As a developer, I want to migrate from hardcoded role checks to the new permission system gradually, so that I can ensure stability while modernizing the codebase.

#### Acceptance Criteria

1. THE Permission_System SHALL provide a compatibility layer that supports both `@requires_roles()` and `@requires_permission()` decorators simultaneously
2. THE Permission_System SHALL log a deprecation warning when the Legacy_Decorator is used
3. THE Permission_System SHALL provide a migration utility that scans the codebase and suggests permission mappings for existing `@requires_roles()` decorators
4. THE Permission_System SHALL maintain backward compatibility with existing role checks for at least one major version
5. THE Permission_System SHALL provide documentation mapping old role checks to new permission names

### Requirement 6: Permission Audit Trail

**User Story:** As a security administrator, I want to track all permission changes and access denials, so that I can investigate security incidents and ensure compliance.

#### Acceptance Criteria

1. WHEN a permission is granted or revoked, THE Permission_System SHALL create an Audit_Log entry with timestamp, user, action, and affected permission
2. WHEN a user is denied access to a route, THE Permission_System SHALL create an Audit_Log entry with timestamp, user, attempted route, and reason
3. WHEN the Permission_Config is modified, THE Permission_System SHALL create an Audit_Log entry with timestamp, modifier, and changes made
4. THE Permission_System SHALL store Audit_Log entries in the database with a minimum retention period of 90 days
5. THE Permission_System SHALL provide an admin interface to view and filter Audit_Log entries
6. THE Audit_Log SHALL include the user's IP address and user agent for each entry

### Requirement 7: Permission Validation and Error Handling

**User Story:** As a developer, I want clear error messages when permission checks fail, so that I can quickly diagnose and fix authorization issues.

#### Acceptance Criteria

1. WHEN a permission name is not defined in the Permission_Config, THE Permission_System SHALL raise a descriptive error during application startup
2. WHEN a route decorator references a non-existent permission, THE Permission_System SHALL raise a descriptive error during application startup
3. IF a user is denied access, THEN THE Permission_System SHALL return a user-friendly error message indicating the required permission
4. THE Permission_System SHALL provide a validation utility that checks the Permission_Config for syntax errors and undefined references
5. WHEN running in development mode, THE Permission_System SHALL display detailed permission debugging information in error responses
6. WHEN running in production mode, THE Permission_System SHALL log detailed permission errors without exposing internal details to users

### Requirement 8: Dynamic Permission Checking

**User Story:** As a developer, I want to check permissions programmatically in business logic, so that I can enforce authorization beyond route-level access control.

#### Acceptance Criteria

1. THE Permission_System SHALL provide a `has_permission(user, permission_name)` function that returns a boolean
2. THE Permission_System SHALL provide a `has_any_permission(user, permission_list)` function that returns True if the user has any of the specified permissions
3. THE Permission_System SHALL provide a `has_all_permissions(user, permission_list)` function that returns True if the user has all specified permissions
4. THE Permission_System SHALL provide a `get_user_permissions(user)` function that returns a list of all permissions granted to the user
5. THE Permission_System SHALL cache permission lookups for the duration of a request to avoid repeated database queries
6. THE Permission_System SHALL clear the permission cache when a user's role or permissions are modified

### Requirement 9: Permission Hierarchy and Inheritance

**User Story:** As a system administrator, I want to define permission hierarchies, so that granting a parent permission automatically grants all child permissions.

#### Acceptance Criteria

1. THE Permission_Config SHALL support wildcard permissions using the asterisk notation (e.g., "menu.*" grants all menu permissions)
2. WHEN a role is granted "module.*" permission, THE Permission_System SHALL grant all permissions within that module
3. THE Permission_System SHALL support permission inheritance where SUPER_ADMIN inherits all permissions from all other roles
4. THE Permission_System SHALL resolve permission checks by evaluating specific permissions before wildcard permissions
5. THE Permission_Config SHALL allow defining permission groups that can be assigned to multiple roles

### Requirement 10: Testing and Validation Utilities

**User Story:** As a developer, I want automated tests for permission logic, so that I can ensure authorization rules work correctly across all scenarios.

#### Acceptance Criteria

1. THE Permission_System SHALL provide a test utility that validates all routes have appropriate permission decorators
2. THE Permission_System SHALL provide a test utility that simulates permission checks for all role-permission combinations
3. THE Permission_System SHALL provide a test utility that identifies routes without any authorization protection
4. THE Permission_System SHALL include unit tests covering all permission checking functions
5. THE Permission_System SHALL include integration tests covering all seven roles accessing all protected routes
6. THE Permission_System SHALL provide a CLI command that generates a permission matrix report showing which roles can access which routes

### Requirement 11: Performance and Caching

**User Story:** As a system operator, I want permission checks to execute efficiently, so that authorization does not introduce noticeable latency to requests.

#### Acceptance Criteria

1. THE Permission_System SHALL cache the Permission_Config in memory after initial load
2. THE Permission_System SHALL cache user permission lookups for the duration of a request
3. WHEN checking permissions, THE Permission_System SHALL complete the check in less than 5 milliseconds for 95% of requests
4. THE Permission_System SHALL use database indexes on the User.role column to optimize permission queries
5. THE Permission_System SHALL avoid N+1 query problems when checking permissions for multiple users
6. THE Permission_System SHALL provide metrics tracking permission check performance

### Requirement 12: Configuration Management

**User Story:** As a system administrator, I want to manage permission configurations across environments, so that I can maintain consistent access control in development, staging, and production.

#### Acceptance Criteria

1. THE Permission_System SHALL support loading Permission_Config from a file path specified in environment variables
2. THE Permission_System SHALL support loading Permission_Config from the database for runtime modifications
3. WHEN Permission_Config is stored in the database, THE Permission_System SHALL provide an admin interface for editing permissions
4. THE Permission_System SHALL validate Permission_Config changes before applying them
5. THE Permission_System SHALL support exporting Permission_Config to a file for version control
6. THE Permission_System SHALL support importing Permission_Config from a file to restore previous configurations

## Special Requirements Guidance

### Parser and Serializer Requirements

This feature does not require custom parsers or serializers. The Permission_Config will use standard JSON or YAML parsing provided by Python libraries (`json` or `pyyaml`).

## Notes

- The current system uses a simple `@requires_roles()` decorator defined in `utils.py` that checks if `current_user.role` is in a list of allowed roles
- The existing decorator performs a simple string comparison: `if current_user.role not in allowed_roles: abort(403)`
- Routes are organized in blueprints: `admin_bp`, `cashier_bp`, `kitchen_bp`, `inventory_bp`, `rider_bp`, `main_bp`
- The User model has a `role` column (string) and a `branch` column (string) for branch-level access control
- The application uses Flask-Login for authentication with `current_user` providing access to the authenticated user
- The existing `AuditLog` model can be extended to support permission audit trails
- The application uses SQLAlchemy ORM with PostgreSQL in production and SQLite in development
