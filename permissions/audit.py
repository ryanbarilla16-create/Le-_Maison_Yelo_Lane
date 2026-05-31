"""
Permission Audit Logger

Logs permission-related events for security auditing.
"""

from flask import request
from datetime import datetime
from models import db, PermissionAuditLog
from utils import get_ph_time


class PermissionAuditLogger:
    """
    Logs permission-related events for security auditing.
    """
    
    def log_access_denied(self, user, permission, route, reason=None):
        """
        Log when access is denied.
        
        Args:
            user: User object
            permission: Permission name that was denied
            route: Route path that was accessed
            reason: Optional reason for denial
        """
        try:
            context = self._get_request_context()
            
            log_entry = PermissionAuditLog(
                user_id=user.id if user and hasattr(user, 'id') else None,
                action='DENIED',
                permission_name=permission,
                route=route,
                reason=reason or 'Access denied',
                ip_address=context['ip_address'],
                user_agent=context['user_agent'],
                created_at=get_ph_time()
            )
            
            db.session.add(log_entry)
            db.session.commit()
        except Exception as e:
            # Don't let audit logging failures break the application
            print(f"❌ Failed to log access denial: {e}")
            db.session.rollback()
    
    def log_permission_granted(self, user, permission):
        """
        Log when permission is granted.
        
        Args:
            user: User object
            permission: Permission name that was granted
        """
        try:
            context = self._get_request_context()
            
            log_entry = PermissionAuditLog(
                user_id=user.id if user and hasattr(user, 'id') else None,
                action='GRANTED',
                permission_name=permission,
                route=request.path if request else None,
                reason='Permission granted',
                ip_address=context['ip_address'],
                user_agent=context['user_agent'],
                created_at=get_ph_time()
            )
            
            db.session.add(log_entry)
            db.session.commit()
        except Exception as e:
            print(f"❌ Failed to log permission grant: {e}")
            db.session.rollback()
    
    def log_permission_revoked(self, user, permission):
        """
        Log when permission is revoked.
        
        Args:
            user: User object
            permission: Permission name that was revoked
        """
        try:
            context = self._get_request_context()
            
            log_entry = PermissionAuditLog(
                user_id=user.id if user and hasattr(user, 'id') else None,
                action='REVOKED',
                permission_name=permission,
                route=request.path if request else None,
                reason='Permission revoked',
                ip_address=context['ip_address'],
                user_agent=context['user_agent'],
                created_at=get_ph_time()
            )
            
            db.session.add(log_entry)
            db.session.commit()
        except Exception as e:
            print(f"❌ Failed to log permission revocation: {e}")
            db.session.rollback()
    
    def log_config_change(self, user, changes):
        """
        Log when permission configuration is modified.
        
        Args:
            user: User object who made the change
            changes: Description of changes made
        """
        try:
            context = self._get_request_context()
            
            log_entry = PermissionAuditLog(
                user_id=user.id if user and hasattr(user, 'id') else None,
                action='CONFIG_CHANGED',
                permission_name=None,
                route=request.path if request else None,
                reason=changes,
                ip_address=context['ip_address'],
                user_agent=context['user_agent'],
                created_at=get_ph_time()
            )
            
            db.session.add(log_entry)
            db.session.commit()
        except Exception as e:
            print(f"❌ Failed to log config change: {e}")
            db.session.rollback()
    
    def _get_request_context(self):
        """
        Extract IP address and user agent from request.
        
        Returns:
            dict: Context with ip_address and user_agent
        """
        context = {
            'ip_address': None,
            'user_agent': None
        }
        
        try:
            if request:
                # Get IP address (handle proxy headers)
                context['ip_address'] = request.headers.get('X-Forwarded-For', request.remote_addr)
                if context['ip_address'] and ',' in context['ip_address']:
                    # Take first IP if multiple proxies
                    context['ip_address'] = context['ip_address'].split(',')[0].strip()
                
                # Get user agent
                context['user_agent'] = request.headers.get('User-Agent', '')[:255]  # Limit to 255 chars
        except Exception as e:
            print(f"⚠️ Failed to extract request context: {e}")
        
        return context
