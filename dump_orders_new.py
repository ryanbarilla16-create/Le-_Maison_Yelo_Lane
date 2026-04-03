from app import app, db
from models import Order

with app.app_context():
    orders = Order.query.filter_by(dining_option='DELIVERY').all()
    with open('out.txt', 'w', encoding='utf-8') as f:
        for o in orders:
            f.write(f'ID: {o.id} | Status: {o.status} | Rider: {o.rider_id} | DelivStatus: {o.delivery_status}\n')
