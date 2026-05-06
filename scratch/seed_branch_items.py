import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app import app, db
from models import Ingredient, MenuItem

with app.app_context():
    # Find bread and set it to Lucban
    bread = Ingredient.query.filter(Ingredient.name.ilike('%bread%')).first()
    if bread:
        bread.branch = 'Lucban'
        bread.stock_qty = 5
        bread.reorder_level = 20
        db.session.commit()
        print('Updated bread to Lucban')
    
    sugar = Ingredient.query.filter(Ingredient.name.ilike('%sugar%')).first()
    if sugar:
        sugar.branch = 'Lucban'
        db.session.commit()
        print('Updated sugar to Lucban')

    hotdog_mi = MenuItem.query.filter(MenuItem.name.ilike('%hotdog%')).first()
    if hotdog_mi:
        hotdog_mi.branch = 'Pagsanjan'
        db.session.commit()
        print('Updated hotdog menu item to Pagsanjan')
