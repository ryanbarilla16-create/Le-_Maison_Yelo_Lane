from flask import Blueprint, request, redirect, url_for
from flask_login import current_user

# Initialize the Blueprint exactly once here, so it can be shared across all route modules
main_bp = Blueprint('main', __name__)

@main_bp.before_request
def restrict_admin_from_public():
    # Allow admins to access the login and static/API routes if necessary
    if current_user.is_authenticated and current_user.role not in ['USER', 'CUSTOMER']:
        allowed_endpoints = ['main.login', 'main.signup', 'main.profile', 'main.logout', 'admin.admin_login', 'admin.admin_logout']
        portal_prefixes = ('static', 'admin.', 'cashier_portal.', 'kitchen_portal.', 'inventory_portal.', 'rider_portal.')
        if request.endpoint and request.endpoint not in allowed_endpoints and not request.endpoint.startswith(portal_prefixes):
            return redirect(url_for('admin.admin_login'))

# Import the routes from the decoupled files to register them with the blueprint
# These must be imported AFTER main_bp is instantiated to avoid circular imports.
from . import views, auth, reservations, orders
