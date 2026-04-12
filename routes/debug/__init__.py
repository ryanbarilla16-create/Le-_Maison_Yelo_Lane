from flask import Blueprint, jsonify
from models import db, MenuItem, MenuItemIngredient

debug_bp = Blueprint('debug', __name__)

@debug_bp.route('/force_sync')
def force_sync():
    items = MenuItem.query.all()
    count = 0
    results = []
    for mi in items:
        can_make = True
        missing = []
        for r in mi.ingredients:
            qty_in_kitchen = float(getattr(r.ingredient, 'kitchen_qty', 0) or 0)
            qty_needed = float(r.quantity_needed or 0)
            if qty_in_kitchen < qty_needed:
                can_make = False
                missing.append(r.ingredient.name)
        
        mi.is_available = can_make
        results.append({
            'name': mi.name,
            'is_available': mi.is_available,
            'missing': missing
        })
        count += 1
            
    db.session.commit()
    return jsonify({'updated_count': count, 'results': results})
