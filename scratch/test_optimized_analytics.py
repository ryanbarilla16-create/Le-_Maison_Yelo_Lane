import sys
sys.path.insert(0, '.')
from app import app, db
from models import User, MenuItem, Reservation, Order, OrderItem, MenuItemIngredient, Ingredient
from sqlalchemy import func
from datetime import date, timedelta, datetime

with app.app_context():
    today = date(2026, 5, 26)  # fixed test date matching system
    
    def get_branch_data(br):
        print(f"\n--- Fetching analytics for: {br} ---")
        
        # Reservation counts by type
        res_q = db.session.query(Reservation.booking_type, func.count(Reservation.id))
        if br != 'ALL':
            res_q = res_q.filter(Reservation.branch == br)
        res_rows = res_q.group_by(Reservation.booking_type).all()
        res_map = {row[0]: row[1] for row in res_rows}
        exclusive_count = res_map.get('EXCLUSIVE', 0)
        regular_count = res_map.get('REGULAR', 0)
        total_reservations = sum(res_map.values())
        print(f"Reservations: {total_reservations} (excl: {exclusive_count}, reg: {regular_count})")

        # Menu items
        menu_q = MenuItem.query.filter_by(is_deleted=False)
        if br != 'ALL':
            menu_q = menu_q.filter_by(branch=br)
        total_menu_items = menu_q.count()
        print(f"Menu Items: {total_menu_items}")

        # Order totals and counts (14 days)
        start_date = today - timedelta(days=13)
        orders_by_day_q = db.session.query(
            func.date(Order.created_at).label('order_date'),
            func.sum(Order.total_amount).label('total_rev'),
            func.count(Order.id).label('order_count')
        ).filter(func.date(Order.created_at) >= start_date)
        if br != 'ALL':
            orders_by_day_q = orders_by_day_q.filter(Order.branch == br)
        orders_by_day = orders_by_day_q.group_by('order_date').all()
        
        def to_date_key(d_val):
            if isinstance(d_val, str):
                try:
                    return datetime.strptime(d_val[:10], '%Y-%m-%d').date()
                except ValueError:
                    return d_val
            return d_val

        rev_map = {}
        count_map = {}
        for row in orders_by_day:
            k = to_date_key(row.order_date)
            rev_map[k] = float(row.total_rev or 0.0)
            count_map[k] = int(row.order_count or 0)
            
        print(f"Orders by day records parsed: {len(rev_map)}")

        # Busy Times
        busy_q = db.session.query(
            func.extract('hour', Order.created_at).label('hr'),
            func.count(Order.id)
        )
        if br != 'ALL':
            busy_q = busy_q.filter(Order.branch == br)
        busy_hours_raw = busy_q.group_by('hr').order_by('hr').all()
        busy_map = {int(h): c for h, c in busy_hours_raw}
        print(f"Busy hours distribution keys: {list(busy_map.keys())}")

        # Monthly Revenue (Last 6 Months)
        first_of_current = today.replace(day=1)
        m_val = first_of_current.month - 5
        y_val = first_of_current.year
        while m_val <= 0:
            m_val += 12
            y_val -= 1
        six_months_ago_start = date(y_val, m_val, 1)

        monthly_rev_q = db.session.query(
            func.extract('year', Order.created_at).label('yr'),
            func.extract('month', Order.created_at).label('mon'),
            func.sum(Order.total_amount).label('rev')
        ).filter(Order.created_at >= datetime.combine(six_months_ago_start, datetime.min.time()))
        if br != 'ALL':
            monthly_rev_q = monthly_rev_q.filter(Order.branch == br)
        
        monthly_rows = monthly_rev_q.group_by('yr', 'mon').all()
        monthly_map = {}
        for row in monthly_rows:
            try:
                monthly_map[(int(row.yr), int(row.mon))] = float(row.rev or 0.0)
            except (TypeError, ValueError):
                pass
        print(f"Monthly revenue map: {monthly_map}")

        # Customer Loyalty
        order_counts_sub_q = db.session.query(
            Order.user_id,
            func.count(Order.id).label('order_count')
        )
        if br != 'ALL':
            order_counts_sub_q = order_counts_sub_q.filter(Order.branch == br)
        order_counts_sub = order_counts_sub_q.group_by(Order.user_id).subquery()
        repeat_customers = db.session.query(func.count()).filter(order_counts_sub.c.order_count > 1).scalar() or 0
        onetime_customers = db.session.query(func.count()).filter(order_counts_sub.c.order_count == 1).scalar() or 0
        print(f"Customer loyalty -> Repeat: {repeat_customers}, One-time: {onetime_customers}")

        # Total revenue & COGS
        trev_q = db.session.query(func.coalesce(func.sum(Order.total_amount), 0))
        if br != 'ALL':
            trev_q = trev_q.filter(Order.branch == br)
        total_revenue_val = float(trev_q.scalar())

        cogs_query = db.session.query(
            func.sum(OrderItem.quantity * MenuItemIngredient.quantity_needed * Ingredient.cost_per_unit)
        ).select_from(OrderItem)\
         .join(Order, Order.id == OrderItem.order_id)\
         .join(MenuItem, MenuItem.id == OrderItem.menu_item_id)\
         .join(MenuItemIngredient, MenuItemIngredient.menu_item_id == MenuItem.id)\
         .join(Ingredient, Ingredient.id == MenuItemIngredient.ingredient_id)\
         .filter(Order.status == 'COMPLETED')
        if br != 'ALL':
            cogs_query = cogs_query.filter(Order.branch == br)
        total_cogs = float(cogs_query.scalar() or 0.0)
        net_profit = total_revenue_val - total_cogs
        print(f"Revenue: {total_revenue_val}, COGS: {total_cogs}, Net Profit: {net_profit}")

    for b in ['ALL', 'Pagsanjan', 'Lucban']:
        get_branch_data(b)
    print("\n--- ALL OPTIMIZED QUERIES PASSED SUCCESSFULLY ---")
