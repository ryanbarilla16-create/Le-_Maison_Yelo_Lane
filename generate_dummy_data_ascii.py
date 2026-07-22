"""
=============================================================================
  Le Maison Yelo Lane ? Realistic Dummy Data Generator
  -----------------------------------------------------
  Generates orders (2018?Jan 2026) and reservations (2024?Jan 2026).
  
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

# ?? Bootstrap Flask App Context ???????????????????????????????????????????????
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db, User, Order, OrderItem, MenuItem, Branch, Reservation

# ??? CONSTANTS & HELPERS ??????????????????????????????????????????????????????

DUMMY_TAG_ORDER       = '[DUMMY_DATA]'
DUMMY_TAG_RESERVATION = '[DUMMY_DATA]'

# Philippine public holidays (month, day) ? recurring each year
PH_RECURRING_HOLIDAYS = {
    (1,  1),   # New Year's Day
    (2, 25),   # EDSA Revolution
    (4,  9),   # Araw ng Kagitingan
    (5,  1),   # Labor Day
    (6, 12),   # Independence Day
    (8, 21),   # Ninoy Aquino Day
    (8, 26),   # National Heroes Day (last Mon Aug ? approximated)
    (11, 1),   # All Saints' Day
    (11, 2),   # All Souls' Day
    (11, 30),  # Bonifacio Day
    (12, 8),   # Immaculate Conception
    (12, 24),  # Christmas Eve
    (12, 25),  # Christmas Day
    (12, 30),  # Rizal Day
    (12, 31),  # New Year's Eve
}

# Special occasions (month, day)
SPECIAL_OCCASIONS = {
    (2, 14),   # Valentine's Day
    (10, 31),  # Halloween / Trick or Treat
    (12, 22),  # Christmas season start spike
    (12, 23),
}

# Ber months (Sep-Dec)
BER_MONTHS = {9, 10, 11, 12}

DINING_OPTIONS = ['DINE_IN', 'DINE_IN', 'DINE_IN', 'TAKE_OUT', 'DELIVERY']
PAYMENT_METHODS = ['COUNTER', 'COUNTER', 'COUNTER', 'ONLINE']
OCCASIONS = ['Birthday', 'Anniversary', 'Business Meeting', 'Date Night',
             'Family Gathering', 'Celebration', 'Reunion', None, None, None]
BOOKING_TIMES = [
    dtime(10, 0), dtime(11, 0), dtime(11, 30), dtime(12, 0),
    dtime(12, 30), dtime(13, 0), dtime(14, 0), dtime(16, 0),
    dtime(17, 0), dtime(18, 0), dtime(18, 30), dtime(19, 0),
    dtime(19, 30), dtime(20, 0),
]


def is_holiday_or_special(d: date) -> bool:
    """Return True if the date is a PH holiday or special occasion."""
    return (d.month, d.day) in PH_RECURRING_HOLIDAYS or \
           (d.month, d.day) in SPECIAL_OCCASIONS


def is_ber_month(d: date) -> bool:
    return d.month in BER_MONTHS


def get_order_count_for_day(d: date) -> int:
    """
    Returns a realistic, noisy order count for the given date.
    ~3-5% of all days are artificially 'slow days'.
    """
    # Random slow day (rainy, closure, etc.)
    if random.random() < 0.04:  # 4% chance
        return random.randint(5, 12)

    is_weekend = d.weekday() >= 5  # Sat=5, Sun=6
    is_special  = is_holiday_or_special(d)
    is_ber      = is_ber_month(d)

    if is_special or (is_ber and is_weekend):
        # Ber months weekends AND special occasions ? high volume
        base = random.randint(70, 80)
        noise = random.randint(-10, 10)
        return max(60, min(90, base + noise))

    elif is_ber and not is_weekend:
        # Ber months weekdays ? elevated
        base = random.randint(35, 45)
        noise = random.randint(-5, 8)
        return max(28, min(55, base + noise))

    elif is_weekend:
        # Regular weekend
        base = random.randint(40, 50)
        noise = random.randint(-7, 8)
        return max(33, min(58, base + noise))

    else:
        # Regular weekday
        base = random.randint(20, 30)
        noise = random.randint(-5, 6)
        return max(15, min(35, base + noise))


def weighted_item_choice(bestsellers, regular_items):
    """
    Picks a MenuItem with ~55% chance from bestsellers, 45% from regular.
    Falls back gracefully if either list is empty.
    """
    if not bestsellers:
        return random.choice(regular_items)
    if not regular_items:
        return random.choice(bestsellers)

    if random.random() < 0.55:
        return random.choice(bestsellers)
    return random.choice(regular_items)


def random_order_time_on(d: date) -> datetime:
    """Return a random datetime on the given date within restaurant hours (9am?10pm)."""
    hour   = random.randint(9, 21)
    minute = random.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])
    second = random.randint(0, 59)
    return datetime(d.year, d.month, d.day, hour, minute, second)


def random_reservation_time() -> dtime:
    return random.choice(BOOKING_TIMES)


def generate_order_code(d: date, seq: int) -> str:
    return f"ORD-{d.strftime('%Y%m%d')}-{seq:04d}"


def generate_reservation_code(d: date, seq: int) -> str:
    return f"RES-{d.strftime('%Y%m%d')}-{seq:04d}"


# ??? MAIN GENERATOR ???????????????????????????????????????????????????????????

def run():
    with app.app_context():
        print("\n" + "="*65)
        print("  Le Maison Yelo Lane ? Dummy Data Generator")
        print("="*65)

        # ?? 1. Check for existing dummy data ?????????????????????????????
        existing_dummy_orders = Order.query.filter(
            Order.notes == DUMMY_TAG_ORDER
        ).count()
        existing_dummy_reservations = Reservation.query.filter(
            Reservation.cancellation_reason == DUMMY_TAG_RESERVATION
        ).count()

        if existing_dummy_orders > 0 or existing_dummy_reservations > 0:
            print(f"\n[!] Dummy data already exists!")
            print(f"    Orders:       {existing_dummy_orders:,}")
            print(f"    Reservations: {existing_dummy_reservations:,}")
            print("\n    Remove existing dummy data first, then re-run.")
            print("    Tip: DELETE FROM \"order\" WHERE notes = '[DUMMY_DATA]';")
            print("         DELETE FROM reservation WHERE cancellation_reason = '[DUMMY_DATA]';")
            print("\n[ABORTED] No new data inserted.\n")
            return

        # ?? 2. Load real DB data ??????????????????????????????????????????
        print("\n[1/4] Loading real data from database...")

        branches = Branch.query.filter_by(is_active=True).all()
        if len(branches) < 2:
            print(f"\n[WARNING] Only {len(branches)} active branch(es) found.")
            print("          Need at least 2 branches. Please add another branch and re-run.\n")
            return

        branch_names = [b.name for b in branches]
        branch1 = branch_names[0]  # Main / busier branch
        branch2 = branch_names[1]  # Second branch

        all_menu_items = MenuItem.query.filter_by(
            is_available=True, is_deleted=False
        ).all()

        if not all_menu_items:
            print("\n[ERROR] No available menu items found in the database.")
            print("        Please add some menu items first.\n")
            return

        bestsellers  = [m for m in all_menu_items if m.is_bestseller]
        regular_items = [m for m in all_menu_items if not m.is_bestseller]

        # Make sure regular has fallback
        if not regular_items:
            regular_items = all_menu_items

        # Get only USER-role accounts (customers)
        customer_users = User.query.filter_by(role='USER', status='ACTIVE').all()
        if not customer_users:
            # Fall back to any active user
            customer_users = User.query.filter_by(status='ACTIVE').all()
        if not customer_users:
            customer_users = User.query.all()

        user_ids = [u.id for u in customer_users]

        print(f"    ? Branches loaded      : {branch1}, {branch2}")
        print(f"    ? Total menu items     : {len(all_menu_items)}")
        print(f"    ? Bestseller items     : {len(bestsellers)}")
        print(f"    ? Regular items        : {len(regular_items)}")
        print(f"    ? Customer users found : {len(user_ids)}")

        # ?? 3. Generate Orders (2018-01-01 to 2026-01-31) ?????????????????
        print("\n[2/4] Generating ORDERS (Jan 2018 ? Jan 2026)...")

        start_date = date(2018, 1, 1)
        end_date   = date(2026, 1, 31)

        total_orders_created       = 0
        total_order_items_created  = 0
        branch1_orders             = 0
        branch2_orders             = 0

        # Daily sequence counters (reset per day)
        current_day     = None
        day_order_seq   = 0

        # Track used order codes to guarantee uniqueness
        used_order_codes = set()

        delta = end_date - start_date
        total_days = delta.days + 1

        orders_buffer = []
        order_items_buffer = []

        for day_offset in range(total_days):
            current_date = start_date + timedelta(days=day_offset)
            n_orders     = get_order_count_for_day(current_date)
            day_order_seq = 0

            for _ in range(n_orders):
                day_order_seq += 1

                # Branch assignment: Branch1 ~55%, Branch2 ~45% (with noise)
                branch = branch1 if random.random() < 0.55 else branch2

                # Build a unique order code
                order_code_candidate = generate_order_code(current_date, day_order_seq)
                attempt = 0
                while order_code_candidate in used_order_codes:
                    attempt += 1
                    order_code_candidate = f"ORD-{current_date.strftime('%Y%m%d')}-{day_order_seq:04d}-X{attempt}"
                used_order_codes.add(order_code_candidate)

                order_dt     = random_order_time_on(current_date)
                user_id      = random.choice(user_ids)
                dining_opt   = random.choice(DINING_OPTIONS)
                pay_method   = random.choice(PAYMENT_METHODS)

                # Number of items per order: weighted toward 2-3
                n_items      = random.choices([1, 2, 3, 4], weights=[10, 40, 38, 12])[0]

                # Select items (no duplicate menu items in the same order)
                chosen_items = []
                available_pool = list(all_menu_items)
                for _ in range(n_items):
                    if not available_pool:
                        break
                    pick = weighted_item_choice(
                        [m for m in bestsellers if m in available_pool],
                        [m for m in regular_items if m in available_pool]
                    )
                    chosen_items.append(pick)
                    available_pool = [m for m in available_pool if m.id != pick.id]

                # Compute total
                total = Decimal('0')
                item_rows = []
                for item in chosen_items:
                    qty   = random.randint(1, 3)
                    price = item.price
                    total += price * qty
                    item_rows.append((item.id, qty, price))

                # Delivery extra
                delivery_fee = Decimal('0')
                delivery_addr = None
                if dining_opt == 'DELIVERY':
                    delivery_fee  = Decimal(str(random.choice([40, 50, 60, 70, 80])))
                    delivery_addr = 'Dummy Delivery Address, Laguna'
                    total        += delivery_fee

                amount_tendered = total + Decimal(str(random.choice([0, 5, 10, 20, 50])))
                change_amount   = amount_tendered - total

                order = Order(
                    order_code       = order_code_candidate,
                    user_id          = user_id,
                    branch           = branch,
                    total_amount     = total,
                    status           = 'COMPLETED',
                    payment_status   = 'PAID',
                    dining_option    = dining_opt,
                    payment_method   = pay_method,
                    amount_tendered  = amount_tendered,
                    change_amount    = change_amount,
                    delivery_fee     = delivery_fee,
                    delivery_address = delivery_addr,
                    notes            = DUMMY_TAG_ORDER,
                    created_at       = order_dt,
                    is_archived      = False,
                )

                db.session.add(order)
                db.session.flush()  # Get the order.id

                for (item_id, qty, price) in item_rows:
                    oi = OrderItem(
                        order_id       = order.id,
                        menu_item_id   = item_id,
                        quantity       = qty,
                        price_at_time  = price,
                        cost_at_time   = None,
                    )
                    db.session.add(oi)
                    total_order_items_created += 1

                total_orders_created += 1
                if branch == branch1:
                    branch1_orders += 1
                else:
                    branch2_orders += 1

            # Commit every 500 orders to avoid memory overload
            if total_orders_created % 500 == 0 and total_orders_created > 0:
                db.session.commit()
                progress_pct = (day_offset + 1) / total_days * 100
                print(f"    ? Progress: {progress_pct:.1f}% | Orders so far: {total_orders_created:,}", end='\r')

        # Final commit for orders
        db.session.commit()
        print(f"\n    ? Orders complete: {total_orders_created:,} orders, {total_order_items_created:,} items")

        # ?? 4. Generate Reservations (2024-01-01 to 2026-01-31) ??????????
        print("\n[3/4] Generating RESERVATIONS (Jan 2024 ? Jan 2026)...")

        res_start = date(2024, 1, 1)
        res_end   = date(2026, 1, 31)

        total_standard_res   = 0
        total_exclusive_res  = 0
        branch1_res          = 0
        branch2_res          = 0
        used_res_codes       = set()

        def _make_reservation(res_date, booking_type, seq):
            nonlocal total_standard_res, total_exclusive_res
            nonlocal branch1_res, branch2_res

            branch = branch1 if random.random() < 0.52 else branch2
            user_id = random.choice(user_ids)

            code_candidate = generate_reservation_code(res_date, seq)
            attempt = 0
            while code_candidate in used_res_codes:
                attempt += 1
                code_candidate = f"RES-{res_date.strftime('%Y%m%d')}-{seq:04d}-X{attempt}"
            used_res_codes.add(code_candidate)

            r = Reservation(
                reservation_code    = code_candidate,
                user_id             = user_id,
                branch              = branch,
                date                = res_date,
                time                = random_reservation_time(),
                guest_count         = random.randint(2, 12) if booking_type == 'EXCLUSIVE' else random.randint(2, 6),
                occasion            = random.choice(OCCASIONS),
                booking_type        = booking_type,
                duration            = 2 if booking_type == 'REGULAR' else random.choice([2, 3, 4]),
                status              = 'COMPLETED',
                cancellation_reason = DUMMY_TAG_RESERVATION,  # used as our dummy flag
                created_at          = datetime(res_date.year, res_date.month, res_date.day,
                                               random.randint(8, 20), random.randint(0, 59)),
            )
            db.session.add(r)

            if booking_type == 'REGULAR':
                total_standard_res += 1
            else:
                total_exclusive_res += 1

            if branch == branch1:
                branch1_res += 1
            else:
                branch2_res += 1

        # Build monthly schedule for standard reservations
        all_dates_in_range = []
        d = res_start
        while d <= res_end:
            all_dates_in_range.append(d)
            d += timedelta(days=1)

        # Group dates by (year, month)
        from collections import defaultdict
        months_map = defaultdict(list)
        for d in all_dates_in_range:
            months_map[(d.year, d.month)].append(d)

        res_seq = 0
        for (yr, mo), month_dates in sorted(months_map.items()):
            # Standard reservations: 20-30 per month with noise
            n_standard = random.randint(20, 30) + random.randint(-3, 3)
            n_standard = max(15, min(35, n_standard))

            chosen_dates = random.choices(month_dates, k=n_standard)
            for cd in chosen_dates:
                res_seq += 1
                _make_reservation(cd, 'REGULAR', res_seq)

        # Exclusive reservations
        # 2024: 8-12 spread across the year
        exclusive_2024_count = random.randint(8, 12)
        dates_2024 = [d for d in all_dates_in_range if d.year == 2024]
        exclusive_2024_dates = random.sample(dates_2024, min(exclusive_2024_count, len(dates_2024)))
        for ed in sorted(exclusive_2024_dates):
            res_seq += 1
            _make_reservation(ed, 'EXCLUSIVE', res_seq)

        # 2025: 10-14 spread across the year
        exclusive_2025_count = random.randint(10, 14)
        dates_2025 = [d for d in all_dates_in_range if d.year == 2025]
        exclusive_2025_dates = random.sample(dates_2025, min(exclusive_2025_count, len(dates_2025)))
        for ed in sorted(exclusive_2025_dates):
            res_seq += 1
            _make_reservation(ed, 'EXCLUSIVE', res_seq)

        # 2026 Jan: exactly 2 exclusive reservations
        dates_2026_jan = [d for d in all_dates_in_range if d.year == 2026 and d.month == 1]
        exclusive_2026_dates = random.sample(dates_2026_jan, min(2, len(dates_2026_jan)))
        for ed in sorted(exclusive_2026_dates):
            res_seq += 1
            _make_reservation(ed, 'EXCLUSIVE', res_seq)

        db.session.commit()
        print(f"    ? Reservations complete")

        # ?? 5. Print Summary ??????????????????????????????????????????????
        print("\n[4/4] SUMMARY")
        print("="*65)
        print(f"  ORDERS (2018-01-01 ? 2026-01-31)")
        print(f"    Total Orders Created    : {total_orders_created:,}")
        print(f"    Total Order Items       : {total_order_items_created:,}")
        print(f"    Avg Items per Order     : {total_order_items_created / max(1, total_orders_created):.2f}")
        print(f"    {branch1} (Branch 1)  : {branch1_orders:,} orders")
        print(f"    {branch2} (Branch 2)  : {branch2_orders:,} orders")
        print()
        print(f"  RESERVATIONS (2024-01-01 ? 2026-01-31)")
        print(f"    Total Standard          : {total_standard_res:,}")
        print(f"    Total Exclusive         : {total_exclusive_res:,}")
        print(f"    Grand Total Reservations: {total_standard_res + total_exclusive_res:,}")
        print(f"    {branch1} (Branch 1)  : {branch1_res:,} reservations")
        print(f"    {branch2} (Branch 2)  : {branch2_res:,} reservations")
        print()
        print(f"  DUMMY TAG (for cleanup):")
        print(f"    Orders       ? notes = '{DUMMY_TAG_ORDER}'")
        print(f"    Reservations ? cancellation_reason = '{DUMMY_TAG_RESERVATION}'")
        print("="*65)
        print("  ?  Done! All dummy data successfully inserted.\n")


if __name__ == '__main__':
    random.seed()  # Use a fresh random seed every run
    run()

