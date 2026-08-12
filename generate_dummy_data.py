"""
=============================================================================
  Le Maison Yelo Lane - Realistic Dummy Data Generator (FAST/BULK VERSION)
  -------------------------------------------------------------------------
  Generates orders (2018-Jan 2026) and reservations (2024-Jan 2026).
  Uses SQLAlchemy Core bulk inserts for maximum speed.

  SAFE TO RUN MULTIPLE TIMES:
    Checks for existing dummy data before inserting.
    All dummy orders are tagged with notes='[DUMMY_DATA]' for easy cleanup.
    All dummy reservations have cancellation_reason='[DUMMY_DATA]'.

  USAGE:
    python generate_dummy_data.py
=============================================================================
"""

import sys
import os
import random
from datetime import datetime, date, timedelta, time as dtime
from decimal import Decimal

# -- Bootstrap Flask App Context
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db, User, Order, OrderItem, MenuItem, Branch, Reservation
from sqlalchemy import text as sql_text

# Force stdout to UTF-8 safe (avoid CP1252 issues on Windows)
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ---- CONSTANTS ---------------------------------------------------------------

DUMMY_TAG_ORDER       = '[DUMMY_DATA]'
DUMMY_TAG_RESERVATION = '[DUMMY_DATA]'
BATCH_SIZE            = 2000  # rows per bulk insert commit

# Philippine public holidays (month, day)
PH_RECURRING_HOLIDAYS = {
    (1,  1), (2, 25), (4,  9), (5,  1), (6, 12),
    (8, 21), (8, 26), (11, 1), (11, 2), (11, 30),
    (12, 8), (12, 24), (12, 25), (12, 30), (12, 31),
}

# Special occasions
SPECIAL_OCCASIONS = {
    (2, 14),   # Valentine's Day
    (10, 31),  # Halloween
    (12, 22),  # Christmas season spike
    (12, 23),
}

BER_MONTHS = {9, 10, 11, 12}

DINING_OPTIONS   = ['DINE_IN', 'DINE_IN', 'DINE_IN', 'TAKE_OUT', 'DELIVERY']
PAYMENT_METHODS  = ['COUNTER', 'COUNTER', 'COUNTER', 'ONLINE']
OCCASIONS_LIST   = ['Birthday', 'Anniversary', 'Business Meeting', 'Date Night',
                    'Family Gathering', 'Celebration', 'Reunion', None, None, None]
BOOKING_TIMES    = [
    dtime(10, 0), dtime(11, 0), dtime(11, 30), dtime(12, 0),
    dtime(12, 30), dtime(13, 0), dtime(14, 0), dtime(16, 0),
    dtime(17, 0), dtime(18, 0), dtime(18, 30), dtime(19, 0),
    dtime(19, 30), dtime(20, 0),
]

# ---- HELPER FUNCTIONS --------------------------------------------------------

def is_holiday_or_special(d: date) -> bool:
    return (d.month, d.day) in PH_RECURRING_HOLIDAYS or \
           (d.month, d.day) in SPECIAL_OCCASIONS

def get_order_count_for_day(d: date) -> int:
    """Returns realistic noisy order count for the given date."""
    # ~4% of all days are artificially slow (rainy/closure/etc.)
    if random.random() < 0.04:
        return random.randint(5, 12)

    is_weekend = d.weekday() >= 5
    is_special = is_holiday_or_special(d)
    is_ber     = d.month in BER_MONTHS

    if is_special or (is_ber and is_weekend):
        base  = random.randint(70, 80)
        noise = random.randint(-10, 10)
        return max(60, min(90, base + noise))
    elif is_ber and not is_weekend:
        base  = random.randint(35, 45)
        noise = random.randint(-5, 8)
        return max(28, min(55, base + noise))
    elif is_weekend:
        base  = random.randint(40, 50)
        noise = random.randint(-7, 8)
        return max(33, min(58, base + noise))
    else:
        base  = random.randint(20, 30)
        noise = random.randint(-5, 6)
        return max(15, min(35, base + noise))

def weighted_item_pick(bestsellers, regular_items):
    """~55% chance to pick a bestseller, 45% regular."""
    if not bestsellers:
        return random.choice(regular_items)
    if not regular_items:
        return random.choice(bestsellers)
    return random.choice(bestsellers) if random.random() < 0.55 else random.choice(regular_items)

def random_order_time_on(d: date) -> datetime:
    """Random datetime within restaurant hours (9am-10pm)."""
    h  = random.randint(9, 21)
    m  = random.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])
    s  = random.randint(0, 59)
    return datetime(d.year, d.month, d.day, h, m, s)

def random_res_time() -> str:
    """Return a time string HH:MM:SS for reservation."""
    t = random.choice(BOOKING_TIMES)
    return t.strftime('%H:%M:%S')

# ---- MAIN GENERATOR ----------------------------------------------------------

def run():
    with app.app_context():
        print("\n" + "="*65)
        print("  Le Maison Yelo Lane - Dummy Data Generator (BULK MODE)")
        print("="*65)

        # 1. Check for existing dummy data
        existing_orders = db.session.execute(
            sql_text("SELECT COUNT(*) FROM \"order\" WHERE notes = :tag"),
            {"tag": DUMMY_TAG_ORDER}
        ).scalar()
        existing_res = db.session.execute(
            sql_text("SELECT COUNT(*) FROM reservation WHERE cancellation_reason = :tag"),
            {"tag": DUMMY_TAG_RESERVATION}
        ).scalar()

        if existing_orders > 0:
            print(f"\n[!] Dummy order data already exists!")
            print(f"    Orders:       {existing_orders:,}")
            print(f"    Reservations: {existing_res:,}")
            print("\n    To clean up, run these SQL commands:")
            print("      DELETE FROM order_item WHERE order_id IN")
            print("        (SELECT id FROM \"order\" WHERE notes = '[DUMMY_DATA]');")
            print("      DELETE FROM \"order\" WHERE notes = '[DUMMY_DATA]';")
            print("      DELETE FROM reservation WHERE cancellation_reason = '[DUMMY_DATA]';")
            print("\n[ABORTED] No new data inserted.\n")
            return

        # 2. Load real DB data
        print("\n[1/4] Loading real data from database...")

        branches = Branch.query.filter_by(is_active=True).all()
        if len(branches) < 2:
            print(f"[WARNING] Only {len(branches)} active branch(es) found. Need at least 2.")
            return

        branch1 = branches[0].name
        branch2 = branches[1].name

        all_items = MenuItem.query.filter_by(is_available=True, is_deleted=False).all()
        if not all_items:
            print("[ERROR] No available menu items found.")
            return

        bestsellers   = [m for m in all_items if m.is_bestseller]
        regular_items = [m for m in all_items if not m.is_bestseller] or all_items

        customer_users = (
            User.query.filter_by(role='USER', status='ACTIVE').all() or
            User.query.filter_by(status='ACTIVE').all() or
            User.query.all()
        )
        user_ids = [u.id for u in customer_users]

        print(f"    [OK] Branches         : {branch1}, {branch2}")
        print(f"    [OK] Menu items total : {len(all_items)}")
        print(f"    [OK] Bestsellers      : {len(bestsellers)}")
        print(f"    [OK] Regular items    : {len(regular_items)}")
        print(f"    [OK] Customer users   : {len(user_ids)}")

        # Pre-build item lookup lists with IDs and prices
        bs_pool  = [(m.id, float(m.price)) for m in bestsellers]
        reg_pool = [(m.id, float(m.price)) for m in regular_items]
        all_pool = [(m.id, float(m.price)) for m in all_items]

        def weighted_pick_raw():
            if not bs_pool:
                return random.choice(reg_pool)
            if not reg_pool:
                return random.choice(bs_pool)
            return random.choice(bs_pool) if random.random() < 0.55 else random.choice(reg_pool)

        # ---- 3. Generate Orders (2018-01-01 to 2026-01-31) ----------------
        print("\n[2/4] Generating ORDERS (2018-01-01 to 2026-01-31)...")
        print("      (This will take a few minutes - inserting in bulk batches)")

        start_date = date(2018, 1, 1)
        end_date   = date(2026, 1, 31)
        total_days = (end_date - start_date).days + 1

        total_orders       = 0
        total_order_items  = 0
        branch1_orders     = 0
        branch2_orders     = 0

        used_order_codes = set()

        # We'll collect rows and bulk-insert in batches
        order_rows      = []  # dicts for order table
        order_item_rows = []  # dicts for order_item table

        # We need order IDs for order_items — use sequence tracking approach:
        # First get the current max order ID, then assign IDs manually
        max_order_id = db.session.execute(
            sql_text('SELECT COALESCE(MAX(id), 0) FROM "order"')
        ).scalar()
        next_order_id = max_order_id + 1

        for day_offset in range(total_days):
            current_date = start_date + timedelta(days=day_offset)
            n_orders     = get_order_count_for_day(current_date)

            for seq in range(1, n_orders + 1):
                order_id    = next_order_id
                next_order_id += 1

                branch = branch1 if random.random() < 0.55 else branch2

                # Unique order code
                code = f"ORD-{current_date.strftime('%Y%m%d')}-{seq:04d}"
                attempt = 0
                while code in used_order_codes:
                    attempt += 1
                    code = f"ORD-{current_date.strftime('%Y%m%d')}-{seq:04d}-X{attempt}"
                used_order_codes.add(code)

                order_dt   = random_order_time_on(current_date)
                user_id    = random.choice(user_ids)
                dining_opt = random.choice(DINING_OPTIONS)
                pay_method = random.choice(PAYMENT_METHODS)
                n_items    = random.choices([1, 2, 3, 4], weights=[10, 40, 38, 12])[0]

                # Pick items (no duplicates within same order)
                chosen = []
                used_item_ids = set()
                for _ in range(n_items):
                    pick = weighted_pick_raw()
                    attempts = 0
                    while pick[0] in used_item_ids and attempts < 10:
                        pick = weighted_pick_raw()
                        attempts += 1
                    used_item_ids.add(pick[0])
                    chosen.append(pick)

                # Compute total
                total = 0.0
                for (item_id, price) in chosen:
                    qty    = random.randint(1, 3)
                    total += price * qty
                    order_item_rows.append({
                        'order_id':      order_id,
                        'menu_item_id':  item_id,
                        'quantity':      qty,
                        'price_at_time': round(price, 2),
                        'cost_at_time':  None,
                    })
                    total_order_items += 1

                delivery_fee  = 0.0
                delivery_addr = None
                if dining_opt == 'DELIVERY':
                    delivery_fee  = float(random.choice([40, 50, 60, 70, 80]))
                    delivery_addr = 'Dummy Delivery Address, Laguna'
                    total        += delivery_fee

                tendered = total + float(random.choice([0, 5, 10, 20, 50]))
                change   = tendered - total

                order_rows.append({
                    'id':               order_id,
                    'order_code':       code,
                    'user_id':          user_id,
                    'branch':           branch,
                    'total_amount':     round(total, 2),
                    'status':           'COMPLETED',
                    'payment_status':   'PAID',
                    'dining_option':    dining_opt,
                    'payment_method':   pay_method,
                    'amount_tendered':  round(tendered, 2),
                    'change_amount':    round(change, 2),
                    'delivery_fee':     round(delivery_fee, 2),
                    'delivery_address': delivery_addr,
                    'notes':            DUMMY_TAG_ORDER,
                    'created_at':       order_dt,
                    'is_archived':      False,
                    'table_status':     'AVAILABLE',
                    'estimated_cost':   0,
                })

                total_orders += 1
                if branch == branch1:
                    branch1_orders += 1
                else:
                    branch2_orders += 1

            # Bulk commit every BATCH_SIZE orders
            if len(order_rows) >= BATCH_SIZE:
                db.session.execute(
                    Order.__table__.insert(),
                    order_rows
                )
                db.session.execute(
                    OrderItem.__table__.insert(),
                    order_item_rows
                )
                db.session.commit()

                pct = (day_offset + 1) / total_days * 100
                print(f"    >> {pct:.1f}% done | Orders: {total_orders:,} | Items: {total_order_items:,}")

                order_rows      = []
                order_item_rows = []

        # Insert any remaining rows
        if order_rows:
            db.session.execute(Order.__table__.insert(), order_rows)
            db.session.execute(OrderItem.__table__.insert(), order_item_rows)
            db.session.commit()
            print(f"    >> 100.0% done | Orders: {total_orders:,} | Items: {total_order_items:,}")

        print(f"    [OK] Orders generation complete!")

        # ---- 4. Generate Reservations (2024-01-01 to 2026-01-31) ----------
        print("\n[3/4] Generating RESERVATIONS (2024-01-01 to 2026-01-31)...")

        res_start = date(2024, 1, 1)
        res_end   = date(2026, 1, 31)

        # Get next reservation ID
        max_res_id  = db.session.execute(
            sql_text('SELECT COALESCE(MAX(id), 0) FROM reservation')
        ).scalar()
        next_res_id = max_res_id + 1

        total_standard  = 0
        total_exclusive = 0
        branch1_res     = 0
        branch2_res     = 0
        used_res_codes  = set()
        res_rows        = []

        # Collect all dates in range
        all_res_dates = []
        d = res_start
        while d <= res_end:
            all_res_dates.append(d)
            d += timedelta(days=1)

        from collections import defaultdict
        months_map = defaultdict(list)
        for d in all_res_dates:
            months_map[(d.year, d.month)].append(d)

        res_seq = 0

        def _add_reservation(res_date, booking_type):
            nonlocal next_res_id, res_seq, total_standard, total_exclusive
            nonlocal branch1_res, branch2_res

            res_seq += 1
            res_id  = next_res_id
            next_res_id += 1

            branch  = branch1 if random.random() < 0.52 else branch2
            user_id = random.choice(user_ids)

            code = f"RES-{res_date.strftime('%Y%m%d')}-{res_seq:04d}"
            attempt = 0
            while code in used_res_codes:
                attempt += 1
                code = f"RES-{res_date.strftime('%Y%m%d')}-{res_seq:04d}-X{attempt}"
            used_res_codes.add(code)

            t = random.choice(BOOKING_TIMES)

            res_rows.append({
                'id':                   res_id,
                'reservation_code':     code,
                'user_id':              user_id,
                'branch':               branch,
                'date':                 res_date,
                'time':                 t,
                'guest_count':          random.randint(2, 12) if booking_type == 'EXCLUSIVE' else random.randint(2, 6),
                'occasion':             random.choice(OCCASIONS_LIST),
                'booking_type':         booking_type,
                'duration':             2 if booking_type == 'REGULAR' else random.choice([2, 3, 4]),
                'status':               'COMPLETED',
                'cancellation_reason':  DUMMY_TAG_RESERVATION,
                'created_at':           datetime(res_date.year, res_date.month, res_date.day,
                                                  random.randint(8, 20), random.randint(0, 59)),
            })

            if booking_type == 'REGULAR':
                total_standard += 1
            else:
                total_exclusive += 1

            if branch == branch1:
                branch1_res += 1
            else:
                branch2_res += 1

        # Standard reservations: 20-30/month with noise
        for (yr, mo), month_dates in sorted(months_map.items()):
            n = max(15, min(35, random.randint(20, 30) + random.randint(-3, 3)))
            chosen_dates = random.choices(month_dates, k=n)
            for cd in chosen_dates:
                _add_reservation(cd, 'REGULAR')

        # Exclusive 2024: 8-12
        dates_2024 = [d for d in all_res_dates if d.year == 2024]
        for ed in random.sample(dates_2024, min(random.randint(8, 12), len(dates_2024))):
            _add_reservation(ed, 'EXCLUSIVE')

        # Exclusive 2025: 10-14
        dates_2025 = [d for d in all_res_dates if d.year == 2025]
        for ed in random.sample(dates_2025, min(random.randint(10, 14), len(dates_2025))):
            _add_reservation(ed, 'EXCLUSIVE')

        # Exclusive 2026 Jan: exactly 2
        dates_2026_jan = [d for d in all_res_dates if d.year == 2026 and d.month == 1]
        for ed in random.sample(dates_2026_jan, min(2, len(dates_2026_jan))):
            _add_reservation(ed, 'EXCLUSIVE')

        # Bulk insert all reservations
        if res_rows:
            db.session.execute(Reservation.__table__.insert(), res_rows)
            db.session.commit()

        print(f"    [OK] Reservations generation complete!")

        # ---- 5. Print Summary -----------------------------------------------
        total_res = total_standard + total_exclusive
        print("\n[4/4] SUMMARY")
        print("="*65)
        print(f"  ORDERS (2018-01-01 to 2026-01-31)")
        print(f"    Total Orders Created    : {total_orders:,}")
        print(f"    Total Order Items       : {total_order_items:,}")
        print(f"    Avg Items per Order     : {total_order_items / max(1, total_orders):.2f}")
        print(f"    {branch1:<20}: {branch1_orders:,} orders")
        print(f"    {branch2:<20}: {branch2_orders:,} orders")
        print()
        print(f"  RESERVATIONS (2024-01-01 to 2026-01-31)")
        print(f"    Total Standard          : {total_standard:,}")
        print(f"    Total Exclusive         : {total_exclusive:,}")
        print(f"    Grand Total             : {total_res:,}")
        print(f"    {branch1:<20}: {branch1_res:,} reservations")
        print(f"    {branch2:<20}: {branch2_res:,} reservations")
        print()
        print(f"  DUMMY TAG (for cleanup):")
        print(f"    Orders       - notes = '{DUMMY_TAG_ORDER}'")
        print(f"    Reservations - cancellation_reason = '{DUMMY_TAG_RESERVATION}'")
        print("="*65)
        print("  [DONE] All dummy data successfully inserted.\n")


if __name__ == '__main__':
    random.seed()
    run()
