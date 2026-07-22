from app import create_app, db
from models import Order
app = create_app()
with app.app_context():
    orders = Order.query.filter_by(table_number=1).all()
    for o in orders:
        print(f'Order {o.id}: status={o.status}, table_status={o.table_status}, archived={o.is_archived}')
