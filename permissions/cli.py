"""
Permission System CLI Commands

Flask CLI commands for permission management and migration.
"""

import click
from flask import current_app
from flask.cli import with_appcontext
from permissions.migration import PermissionMigrationTool


@click.group()
def permissions():
    """Permission system management commands."""
    pass


@permissions.command()
@click.option('--directory', default='routes', help='Directory to scan for @requires_roles usage')
@with_appcontext
def scan(directory):
    """
    Scan codebase for @requires_roles usage and suggest migrations.
    
    Usage:
        flask permissions scan
        flask permissions scan --directory=routes/admin
    """
    click.echo("🔍 Scanning codebase for @requires_roles decorators...")
    
    tool = PermissionMigrationTool()
    findings = tool.scan_codebase(directory)
    
    if not findings:
        click.echo("✅ No @requires_roles decorators found!")
        return
    
    # Generate and display report
    report = tool.generate_migration_report()
    click.echo(report)
    
    # Find unprotected routes
    click.echo("\n🔍 Scanning for unprotected routes...")
    unprotected = tool.find_unprotected_routes(directory)
    
    if unprotected:
        click.echo(f"\n⚠️  Found {len(unprotected)} routes without authorization:")
        for route in unprotected:
            click.echo(f"   - {route['file']}:{route['line']} - {route['function']}")
    else:
        click.echo("✅ All routes have authorization protection!")


@permissions.command()
@with_appcontext
def validate():
    """
    Validate permission configuration file.
    
    Usage:
        flask permissions validate
    """
    click.echo("🔍 Validating permission configuration...")
    
    try:
        from permissions import get_permission_manager
        manager = get_permission_manager()
        
        if not manager:
            click.echo("❌ Permission system not initialized")
            return
        
        manager.validate_config()
        click.echo("✅ Permission configuration is valid!")
        
        # Display summary
        config = manager.config
        click.echo(f"\n📊 Configuration Summary:")
        click.echo(f"   - Permissions defined: {len(config.get('permissions', {}))}")
        click.echo(f"   - Roles defined: {len(config.get('roles', {}))}")
        click.echo(f"   - Permission groups: {len(config.get('permission_groups', {}))}")
        
    except Exception as e:
        click.echo(f"❌ Validation failed: {e}")


@permissions.command()
@with_appcontext
def reload():
    """
    Reload permission configuration from file.
    
    Usage:
        flask permissions reload
    """
    click.echo("🔄 Reloading permission configuration...")
    
    try:
        from permissions import get_permission_manager
        manager = get_permission_manager()
        
        if not manager:
            click.echo("❌ Permission system not initialized")
            return
        
        if manager.reload_config():
            click.echo("✅ Configuration reloaded successfully!")
        else:
            click.echo("ℹ️  Configuration unchanged (no modifications detected)")
    
    except Exception as e:
        click.echo(f"❌ Reload failed: {e}")


@permissions.command()
@click.argument('username')
@with_appcontext
def show_user_permissions(username):
    """
    Show all permissions for a specific user.
    
    Usage:
        flask permissions show-user-permissions admin
    """
    from models import User
    from permissions import get_permission_manager
    
    user = User.query.filter_by(username=username).first()
    
    if not user:
        click.echo(f"❌ User '{username}' not found")
        return
    
    manager = get_permission_manager()
    if not manager:
        click.echo("❌ Permission system not initialized")
        return
    
    permissions = manager.get_user_permissions(user)
    
    click.echo(f"\n👤 User: {user.username}")
    click.echo(f"   Role: {user.role}")
    click.echo(f"   Branch: {user.branch or 'N/A'}")
    click.echo(f"\n🔑 Permissions ({len(permissions)}):")
    
    if permissions:
        for perm in permissions:
            click.echo(f"   - {perm}")
    else:
        click.echo("   (No permissions)")


def init_cli(app):
    """Register CLI commands with Flask app."""
    app.cli.add_command(permissions)
