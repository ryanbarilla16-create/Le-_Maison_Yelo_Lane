"""
Permission Manager

Core permission management system that handles permission checking,
configuration loading, and validation.
"""

import json
import os
from datetime import datetime
from permissions.exceptions import PermissionConfigError


class PermissionManager:
    """
    Central permission management system.
    Handles permission checking, caching, and configuration loading.
    """
    
    def __init__(self, config_path='permissions_config.json'):
        """
        Initialize the permission manager.
        
        Args:
            config_path: Path to the permissions configuration JSON file
        """
        self.config_path = config_path
        self.config = None
        self.config_mtime = None
        self._load_config()
        self.validate_config()
    
    def _load_config(self):
        """Load permission configuration from file."""
        try:
            if not os.path.exists(self.config_path):
                raise PermissionConfigError(f"Configuration file not found: {self.config_path}")
            
            # Track file modification time for reload detection
            self.config_mtime = os.path.getmtime(self.config_path)
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            
            print(f"✅ Permission configuration loaded from {self.config_path}")
        except json.JSONDecodeError as e:
            raise PermissionConfigError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise PermissionConfigError(f"Failed to load configuration: {e}")
    
    def reload_config(self):
        """Reload configuration if file has changed."""
        try:
            if not os.path.exists(self.config_path):
                return False
            
            current_mtime = os.path.getmtime(self.config_path)
            
            # Only reload if file has been modified
            if current_mtime != self.config_mtime:
                self._load_config()
                self.validate_config()
                print(f"🔄 Permission configuration reloaded")
                return True
            
            return False
        except Exception as e:
            print(f"❌ Failed to reload configuration: {e}")
            return False
    
    def validate_config(self):
        """Validate permission configuration for errors."""
        if not self.config:
            raise PermissionConfigError("Configuration is empty")
        
        # Validate required sections
        if 'permissions' not in self.config:
            raise PermissionConfigError("Configuration missing 'permissions' section")
        
        if 'roles' not in self.config:
            raise PermissionConfigError("Configuration missing 'roles' section")
        
        # Validate permission naming convention (module.action)
        for perm_name in self.config['permissions'].keys():
            if perm_name != '*' and '.' not in perm_name:
                raise PermissionConfigError(
                    f"Permission '{perm_name}' does not follow module.action format"
                )
        
        # Validate role names
        valid_roles = ['SUPER_ADMIN', 'ADMIN', 'CASHIER', 'KITCHEN', 'INVENTORY_STAFF', 'INVENTORY', 'STAFF', 'RIDER', 'USER']
        for role_name in self.config['roles'].keys():
            if role_name not in valid_roles:
                raise PermissionConfigError(
                    f"Invalid role name '{role_name}'. Must be one of: {', '.join(valid_roles)}"
                )
        
        # Validate permission references in roles
        defined_permissions = set(self.config['permissions'].keys())
        for role_name, role_data in self.config['roles'].items():
            if 'permissions' not in role_data:
                raise PermissionConfigError(f"Role '{role_name}' missing 'permissions' list")
            
            for perm in role_data['permissions']:
                # Skip wildcard permissions
                if perm == '*' or perm.endswith('.*'):
                    continue
                
                # Check if permission is defined
                if perm not in defined_permissions:
                    raise PermissionConfigError(
                        f"Role '{role_name}' references undefined permission '{perm}'"
                    )
        
        print("✅ Permission configuration validated successfully")
    
    def has_permission(self, user, permission_name):
        """
        Check if user has a specific permission.
        
        Args:
            user: User object with role attribute
            permission_name: Permission name (e.g., 'menu.view')
        
        Returns:
            bool: True if user has permission, False otherwise
        """
        # Check if user is authenticated
        if not user or not hasattr(user, 'is_authenticated') or not user.is_authenticated:
            return False
        
        # Get user role
        user_role = user.role.upper() if hasattr(user, 'role') else None
        if not user_role:
            return False
        
        # Get role permissions from config
        role_data = self.config['roles'].get(user_role, {})
        role_permissions = role_data.get('permissions', [])
        
        # Check for SUPER_ADMIN wildcard
        if '*' in role_permissions:
            return True
        
        # Check exact match
        if permission_name in role_permissions:
            return True
        
        # Check wildcard matches (e.g., menu.* matches menu.view)
        if '.' in permission_name:
            module = permission_name.split('.')[0]
            if f"{module}.*" in role_permissions:
                return True
        
        # Check permission groups
        for group_name, group_perms in self.config.get('permission_groups', {}).items():
            if group_name in role_permissions and permission_name in group_perms:
                return True
        
        return False
    
    def has_any_permission(self, user, permission_list):
        """
        Check if user has any of the specified permissions (OR logic).
        
        Args:
            user: User object
            permission_list: List of permission names
        
        Returns:
            bool: True if user has at least one permission
        """
        for permission in permission_list:
            if self.has_permission(user, permission):
                return True
        return False
    
    def has_all_permissions(self, user, permission_list):
        """
        Check if user has all specified permissions (AND logic).
        
        Args:
            user: User object
            permission_list: List of permission names
        
        Returns:
            bool: True if user has all permissions
        """
        for permission in permission_list:
            if not self.has_permission(user, permission):
                return False
        return True
    
    def get_user_permissions(self, user):
        """
        Get all permissions for a user.
        
        Args:
            user: User object
        
        Returns:
            list: List of permission names
        """
        if not user or not hasattr(user, 'is_authenticated') or not user.is_authenticated:
            return []
        
        user_role = user.role.upper() if hasattr(user, 'role') else None
        if not user_role:
            return []
        
        role_data = self.config['roles'].get(user_role, {})
        permissions = role_data.get('permissions', [])
        
        # Expand wildcards and permission groups
        expanded_permissions = set()
        for perm in permissions:
            if perm == '*':
                # SUPER_ADMIN gets all permissions
                expanded_permissions.update(self.config['permissions'].keys())
            elif perm.endswith('.*'):
                # Module wildcard - add all permissions in that module
                module = perm[:-2]
                for defined_perm in self.config['permissions'].keys():
                    if defined_perm.startswith(f"{module}."):
                        expanded_permissions.add(defined_perm)
            elif perm in self.config.get('permission_groups', {}):
                # Permission group - add all permissions in group
                expanded_permissions.update(self.config['permission_groups'][perm])
            else:
                # Regular permission
                expanded_permissions.add(perm)
        
        return sorted(list(expanded_permissions))
    
    def check_branch_access(self, user, branch):
        """
        Check if user has access to a specific branch.
        
        Args:
            user: User object with role and branch attributes
            branch: Branch name to check access for
        
        Returns:
            bool: True if user has access to the branch
        """
        if not user or not hasattr(user, 'is_authenticated') or not user.is_authenticated:
            return False
        
        # SUPER_ADMIN has access to all branches
        if hasattr(user, 'role') and user.role.upper() == 'SUPER_ADMIN':
            return True
        
        # Check if user has branch assignment
        if not hasattr(user, 'branch') or not user.branch:
            return False
        
        # Check if user's branch is 'ALL' (multi-branch access)
        if user.branch == 'ALL':
            return True
        
        # Check if user's branch matches requested branch
        return user.branch == branch
    
    def _resolve_wildcard(self, permission_name, user_permissions):
        """
        Resolve wildcard permissions (e.g., menu.*).
        
        Args:
            permission_name: Permission to check
            user_permissions: List of user's permissions
        
        Returns:
            bool: True if wildcard matches
        """
        if '.' not in permission_name:
            return False
        
        module = permission_name.split('.')[0]
        wildcard = f"{module}.*"
        
        return wildcard in user_permissions or '*' in user_permissions
