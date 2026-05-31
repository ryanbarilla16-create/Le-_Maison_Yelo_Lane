"""
Permission Migration Tool

Utility to help migrate from legacy @requires_roles to new permission system.
"""

import os
import ast
import json
from pathlib import Path


class PermissionMigrationTool:
    """
    Utility to help migrate from legacy @requires_roles to new system.
    """
    
    def __init__(self, config_path='permissions_config.json'):
        """
        Initialize migration tool.
        
        Args:
            config_path: Path to permissions configuration file
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.findings = []
    
    def _load_config(self):
        """Load permissions configuration."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Failed to load config: {e}")
            return {}
    
    def scan_codebase(self, directory='routes'):
        """
        Scan codebase for @requires_roles usage.
        
        Args:
            directory: Directory to scan (default: routes)
        
        Returns:
            list: List of findings with file, line, and decorator info
        """
        self.findings = []
        
        # Find all Python files in directory
        path = Path(directory)
        if not path.exists():
            print(f"❌ Directory not found: {directory}")
            return self.findings
        
        python_files = list(path.rglob('*.py'))
        
        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Parse Python file
                tree = ast.parse(content, filename=str(file_path))
                
                # Find function definitions with decorators
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        for decorator in node.decorator_list:
                            # Check if decorator is @requires_roles
                            if self._is_requires_roles_decorator(decorator):
                                roles = self._extract_roles(decorator)
                                
                                finding = {
                                    'file': str(file_path),
                                    'line': node.lineno,
                                    'function': node.name,
                                    'decorator': 'requires_roles',
                                    'roles': roles,
                                    'suggested_permissions': self._suggest_permissions(roles)
                                }
                                
                                self.findings.append(finding)
            
            except Exception as e:
                print(f"⚠️ Failed to parse {file_path}: {e}")
        
        return self.findings
    
    def _is_requires_roles_decorator(self, decorator):
        """Check if decorator is @requires_roles."""
        if isinstance(decorator, ast.Name):
            return decorator.id == 'requires_roles'
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                return decorator.func.id == 'requires_roles'
        return False
    
    def _extract_roles(self, decorator):
        """Extract role names from @requires_roles decorator."""
        roles = []
        
        if isinstance(decorator, ast.Call):
            for arg in decorator.args:
                if isinstance(arg, ast.Constant):
                    roles.append(arg.value)
                elif isinstance(arg, ast.Str):  # Python 3.7 compatibility
                    roles.append(arg.s)
        
        return roles
    
    def suggest_mappings(self):
        """
        Suggest permission mappings for legacy decorators.
        
        Returns:
            dict: Mapping of roles to suggested permissions
        """
        mappings = {}
        
        for finding in self.findings:
            for role in finding['roles']:
                if role not in mappings:
                    mappings[role] = self._get_role_permissions(role)
        
        return mappings
    
    def _suggest_permissions(self, roles):
        """Suggest permissions based on roles."""
        suggested = []
        
        for role in roles:
            perms = self._get_role_permissions(role)
            suggested.extend(perms)
        
        # Remove duplicates
        return list(set(suggested))
    
    def _get_role_permissions(self, role):
        """Get permissions for a role from config."""
        role_data = self.config.get('roles', {}).get(role, {})
        return role_data.get('permissions', [])
    
    def generate_migration_report(self):
        """
        Generate a report of migration progress.
        
        Returns:
            str: Formatted migration report
        """
        if not self.findings:
            return "✅ No @requires_roles decorators found. Migration complete!"
        
        report = []
        report.append("=" * 80)
        report.append("PERMISSION SYSTEM MIGRATION REPORT")
        report.append("=" * 80)
        report.append(f"\nFound {len(self.findings)} routes using @requires_roles decorator:\n")
        
        for i, finding in enumerate(self.findings, 1):
            report.append(f"{i}. {finding['file']}:{finding['line']}")
            report.append(f"   Function: {finding['function']}")
            report.append(f"   Current: @requires_roles({', '.join(repr(r) for r in finding['roles'])})")
            
            if finding['suggested_permissions']:
                # Suggest single permission if only one, otherwise show all
                if len(finding['suggested_permissions']) == 1:
                    report.append(f"   Suggested: @requires_permission('{finding['suggested_permissions'][0]}')")
                else:
                    perms = "', '".join(finding['suggested_permissions'])
                    report.append(f"   Suggested: @requires_permission('{perms}')")
            else:
                report.append(f"   Suggested: [No permissions defined for these roles]")
            
            report.append("")
        
        report.append("=" * 80)
        report.append("\nMigration Steps:")
        report.append("1. Replace @requires_roles with @requires_permission")
        report.append("2. Update imports: from permissions import requires_permission")
        report.append("3. Test each route with appropriate user roles")
        report.append("4. Remove legacy @requires_roles from utils.py when complete")
        report.append("=" * 80)
        
        return "\n".join(report)
    
    def find_unprotected_routes(self, directory='routes'):
        """
        Find routes without any authorization protection.
        
        Args:
            directory: Directory to scan
        
        Returns:
            list: List of unprotected routes
        """
        unprotected = []
        
        path = Path(directory)
        if not path.exists():
            return unprotected
        
        python_files = list(path.rglob('*.py'))
        
        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                tree = ast.parse(content, filename=str(file_path))
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # Check if function has route decorator
                        has_route = False
                        has_auth = False
                        
                        for decorator in node.decorator_list:
                            decorator_name = self._get_decorator_name(decorator)
                            
                            if decorator_name in ['route', 'get', 'post', 'put', 'delete']:
                                has_route = True
                            
                            if decorator_name in ['requires_roles', 'requires_permission', 
                                                   'requires_branch_access', 'login_required']:
                                has_auth = True
                        
                        # If has route but no auth, it's unprotected
                        if has_route and not has_auth:
                            unprotected.append({
                                'file': str(file_path),
                                'line': node.lineno,
                                'function': node.name
                            })
            
            except Exception as e:
                print(f"⚠️ Failed to parse {file_path}: {e}")
        
        return unprotected
    
    def _get_decorator_name(self, decorator):
        """Extract decorator name from AST node."""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                return decorator.func.id
            elif isinstance(decorator.func, ast.Attribute):
                return decorator.func.attr
        return None
