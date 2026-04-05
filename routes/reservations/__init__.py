from flask import render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_required, current_user
from models import db, Reservation, MenuItem, Order, OrderItem, User
from datetime import datetime, date, time as dtime, timedelta
from decimal import Decimal
from .. import main_bp
import os, base64, requests
from utils import get_ph_time, create_notification

def check_reservation_time(t):
    if not (dtime(11, 30) <= t <= dtime(20, 30)):
        return False
    if t.minute not in (0, 30):
        return False
    return True


# ─── STEP 1: Reservation Details Form ─────────────────────────────────
@main_bp.route('/reserve', methods=['GET', 'POST'])
@login_required
def reserve():
    if request.method == 'POST':
        res_date_str = request.form.get('date')
        res_time_str = request.form.get('time')
        guest_count_str = request.form.get('guest_count')
        occasion = request.form.get('occasion')
        booking_type = request.form.get('booking_type')
        duration_str = request.form.get('duration', '2')

        try:
            res_date = datetime.strptime(res_date_str, '%Y-%m-%d').date()
            hour, minute = map(int, res_time_str.split(':'))
            res_time = dtime(hour, minute)
            guest_count = int(guest_count_str)
            duration = int(duration_str)
        except ValueError:
            flash("Invalid data format provided.", "danger")
            return redirect(url_for('main.reserve'))

        today = date.today()
        diff = (res_date - today).days

        if booking_type == 'EXCLUSIVE':
            if diff < 3:
                flash("Exclusive reservations must be made at least 3 days in advance.", "danger")
                return redirect(url_for('main.reserve'))
        else:
            if diff < 0:
                flash("Cannot book in the past.", "danger")
                return redirect(url_for('main.reserve'))
            if diff == 0:
                curr_t = datetime.now().time()
                if res_time <= curr_t:
                    flash("You cannot book a time slot that has already passed today.", "danger")
                    return redirect(url_for('main.reserve'))
                # Strict cutoff: No new same-day bookings after 8:30 PM
                if curr_t >= dtime(20, 30):
                    flash("Restaurant is now closed for same-day bookings. Please book for tomorrow.", "danger")
                    return redirect(url_for('main.reserve'))


        if diff > 60:
            flash("Reservation can be max 2 months (60 days) in advance.", "danger")
            return redirect(url_for('main.reserve'))

        if not check_reservation_time(res_time):
            flash("Time must be between 11:30 AM - 8:30 PM with 30-minute intervals.", "danger")
            return redirect(url_for('main.reserve'))

        if guest_count <= 0:
            flash("Guest count must be at least 1.", "danger")
            return redirect(url_for('main.reserve'))

        if booking_type == 'EXCLUSIVE':
            if guest_count > 50:
                flash("Exclusive Venue can hold up to 50 guests maximum.", "danger")
                return redirect(url_for('main.reserve'))
        else:
            if guest_count > 20:
                flash("Regular tables max at 20 guests.", "danger")
                return redirect(url_for('main.reserve'))

        active_res = Reservation.query.filter(
            Reservation.date == res_date,
            Reservation.status.in_(['PENDING', 'CONFIRMED'])
        ).all()

        current_res_start = datetime.combine(res_date, res_time)
        current_res_end = current_res_start + timedelta(hours=duration)

        conflict = False
        conflict_msg = ""

        for r in active_res:
            r_start = datetime.combine(r.date, r.time)
            r_dur = r.duration if r.duration is not None else 2
            r_end = r_start + timedelta(hours=r_dur)
            if current_res_start < r_end and r_start < current_res_end:
                if booking_type == 'EXCLUSIVE' or r.booking_type == 'EXCLUSIVE':
                    conflict = True
                    conflict_msg = "Cannot book this slot. It conflicts with an existing Exclusive booking or overlaps with another reservation."
                    break

        if conflict:
            flash(conflict_msg, "danger")
            return redirect(url_for('main.reserve'))

        if booking_type != 'EXCLUSIVE':
            overlapping_guests = 0
            for r in active_res:
                if r.booking_type != 'EXCLUSIVE':
                    r_start = datetime.combine(r.date, r.time)
                    r_dur = r.duration if r.duration is not None else 2
                    r_end = r_start + timedelta(hours=r_dur)
                    if current_res_start < r_end and r_start < current_res_end:
                        overlapping_guests += r.guest_count
            if overlapping_guests + guest_count > 50:
                flash("Capacity Guard: Time slot is too full. Not enough seats.", "danger")
                return redirect(url_for('main.reserve'))

        # ── Save reservation details in session, go to Step 2 (Menu) ──
        session['pending_reservation'] = {
            'date': res_date_str,
            'time': res_time_str,
            'guest_count': guest_count,
            'occasion': occasion or '',
            'booking_type': booking_type,
            'duration': duration
        }
        session.modified = True

        return redirect(url_for('main.reserve_menu'))

    return render_template('reserve.html')


# ─── STEP 2: Menu Selection ────────────────────────────────────────────
@main_bp.route('/reserve/menu', methods=['GET', 'POST'])
@login_required
def reserve_menu():
    pending = session.get('pending_reservation')
    if not pending:
        flash("Please fill in your reservation details first.", "warning")
        return redirect(url_for('main.reserve'))

    if request.method == 'POST':
        # Collect selected menu items
        selected_items = {}
        for key, val in request.form.items():
            if key.startswith('qty_') and int(val) > 0:
                item_id = key.replace('qty_', '')
                selected_items[item_id] = int(val)

        if not selected_items:
            flash("Please select at least one menu item for your reservation.", "warning")
            menu_items = MenuItem.query.order_by(MenuItem.category, MenuItem.name).all()
            categories = {}
            for item in menu_items:
                categories.setdefault(item.category, []).append(item)
            return render_template('reserve_menu.html', pending=pending, categories=categories)

        session['pending_reservation']['menu_items'] = selected_items
        session.modified = True

        return redirect(url_for('main.reserve_payment'))

    menu_items = MenuItem.query.order_by(MenuItem.category, MenuItem.name).all()
    categories = {}
    for item in menu_items:
        categories.setdefault(item.category, []).append(item)

    return render_template('reserve_menu.html', pending=pending, categories=categories)


# ─── STEP 3: Payment (create reservation + order + Xendit invoice) ─────
@main_bp.route('/reserve/payment')
@login_required
def reserve_payment():
    pending = session.get('pending_reservation')
    if not pending or not pending.get('menu_items'):
        flash("Please complete your reservation details and menu selection first.", "warning")
        return redirect(url_for('main.reserve'))

    # Safety check for all required pending data
    required_keys = ['date', 'time', 'guest_count', 'booking_type']
    if not all(k in pending for k in required_keys):
        flash("Reservation details are incomplete. Please start again.", "warning")
        return redirect(url_for('main.reserve'))

    selected_items = pending['menu_items']

    # Calculate totals
    order_items_data = []
    food_total = Decimal('0')
    try:
        for item_id_str, qty in selected_items.items():
            menu_item = MenuItem.query.get(int(item_id_str))
            if menu_item and menu_item.is_available:
                # Use Decimal for all money math
                price = Decimal(str(menu_item.price))
                subtotal = price * Decimal(str(qty))
                food_total += subtotal
                order_items_data.append({'item': menu_item, 'qty': qty, 'subtotal': subtotal})
    except (ValueError, TypeError) as e:
        flash("Error processing your menu selection. Please try again.", "danger")
        return redirect(url_for('main.reserve_menu'))

    if not order_items_data:
        flash("Your selection is empty or items are no longer available.", "warning")
        return redirect(url_for('main.reserve_menu'))

    try:
        res_date = datetime.strptime(pending['date'], '%Y-%m-%d').date()
        res_time_str = pending['time']
        hour, minute = map(int, res_time_str.split(':'))
        res_time = dtime(hour, minute)
    except (ValueError, KeyError, TypeError):
        flash("Invalid date or time format. Please re-enter your details.", "danger")
        return redirect(url_for('main.reserve'))

    return render_template('reserve_payment.html',
        pending=pending,
        order_items_data=order_items_data,
        food_total=food_total,
        res_date=res_date,
        res_time=res_time
    )


# ─── STEP 3b: Confirm Payment → Create Reservation & Order → Xendit ───
@main_bp.route('/reserve/confirm', methods=['POST'])
@login_required
def reserve_confirm():
    pending = session.get('pending_reservation')
    if not pending or not pending.get('menu_items'):
        flash("Session expired. Please start your reservation again.", "warning")
        return redirect(url_for('main.reserve'))

    selected_items = pending['menu_items']
    res_date_str = pending['date']
    res_time_str = pending['time']
    guest_count = pending['guest_count']
    occasion = pending.get('occasion', '')
    booking_type = pending['booking_type']
    duration = pending['duration']

    res_date = datetime.strptime(res_date_str, '%Y-%m-%d').date()
    hour, minute = map(int, res_time_str.split(':'))
    res_time = dtime(hour, minute)

    # Build order items
    order_items_list = []
    food_total = Decimal('0')
    for item_id_str, qty in selected_items.items():
        menu_item = MenuItem.query.get(int(item_id_str))
        if menu_item and menu_item.is_available:
            subtotal = Decimal(str(menu_item.price)) * qty
            food_total += subtotal
            order_items_list.append(OrderItem(
                menu_item_id=menu_item.id,
                quantity=qty,
                price_at_time=menu_item.price
            ))

    if not order_items_list:
        flash("Selected menu items are no longer available. Please re-select.", "danger")
        session.pop('pending_reservation', None)
        return redirect(url_for('main.reserve'))

    try:
        # 1. Create Reservation (status = PENDING, waits for admin confirm after payment)
        new_res = Reservation(
            user_id=current_user.id,
            date=res_date,
            time=res_time,
            duration=duration,
            guest_count=guest_count,
            occasion=occasion,
            booking_type=booking_type,
            status='PENDING'
        )
        db.session.add(new_res)
        db.session.flush()  # Get new_res.id

        # 2. Create Order linked to reservation
        new_order = Order(
            user_id=current_user.id,
            total_amount=food_total,
            status='HOLD',       # Hold until payment confirmed
            payment_status='UNPAID',
            dining_option='DINE_IN',
            payment_method='ONLINE',
            reservation_id=new_res.id,
            notes=f"Reservation Order for {res_date_str} {res_time.strftime('%I:%M %p')} — {booking_type}"
        )
        db.session.add(new_order)
        db.session.flush()  # Get new_order.id

        for oi in order_items_list:
            oi.order_id = new_order.id
            db.session.add(oi)

        db.session.commit()

        # 3. Notify admins of new reservation
        admin_users = User.query.filter(User.role == 'ADMIN').all()
        for admin in admin_users:
            create_notification(
                admin.id,
                'New Reservation Request! 📅',
                f'{current_user.first_name} made a reservation for {res_date.strftime("%b %d, %Y")} at {res_time.strftime("%I:%M %p")} — Payment pending.',
                'RESERVATION'
            )

        # 4. Create Xendit invoice
        xendit_secret_key = os.environ.get('XENDIT_SECRET_KEY')
        if xendit_secret_key and xendit_secret_key not in ('add_your_xendit_secret_key_here', ''):
            api_key_b64 = base64.b64encode(f"{xendit_secret_key}:".encode('utf-8')).decode('utf-8')
            headers = {
                'Authorization': f'Basic {api_key_b64}',
                'Content-Type': 'application/json'
            }
            success_url = url_for('main.reservation_payment_success', res_id=new_res.id, order_id=new_order.id, _external=True)
            failure_url = url_for('main.reservation_payment_failed', res_id=new_res.id, order_id=new_order.id, _external=True)

            payload = {
                'external_id': f"reservation-{new_res.id}-order-{new_order.id}-{int(get_ph_time().timestamp())}",
                'amount': float(food_total),
                'payer_email': current_user.email,
                'description': f"Reservation #{new_res.id} — {booking_type.capitalize()} Booking on {res_date_str} {res_time.strftime('%I:%M %p')} for {guest_count} guests",
                'success_redirect_url': success_url,
                'failure_redirect_url': failure_url,
                'currency': 'PHP'
            }

            response = requests.post('https://api.xendit.co/v2/invoices', json=payload, headers=headers)
            if response.status_code == 200:
                invoice_data = response.json()
                new_order.xendit_invoice_url = invoice_data.get('invoice_url')
                new_order.xendit_invoice_id = invoice_data.get('id')
                db.session.commit()
                session.pop('pending_reservation', None)
                return redirect(new_order.xendit_invoice_url)
            else:
                # Rollback if Xendit fails
                db.session.delete(new_order)
                db.session.delete(new_res)
                db.session.commit()
                flash(f"Payment gateway error: {response.json().get('message', 'Unknown error')}. Please try again.", "danger")
                return redirect(url_for('main.reserve'))
        else:
            # No Xendit key configured (dev mode)
            new_order.payment_status = 'PAID'
            new_order.status = 'PENDING'
            db.session.commit()
            session.pop('pending_reservation', None)
            flash("Reservation submitted! (Payment gateway not configured — dev mode). Awaiting admin approval.", "warning")
            return redirect(url_for('main.index'))

    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for('main.reserve'))


# ─── Payment Success (Xendit callback) ───────────────────────────────
@main_bp.route('/reserve/payment-success/<int:res_id>/<int:order_id>')
@login_required
def reservation_payment_success(res_id, order_id):
    reservation = Reservation.query.get_or_404(res_id)
    order = Order.query.get_or_404(order_id)

    if reservation.user_id != current_user.id or order.user_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for('main.index'))

    # Mark order as PAID and PENDING (kitchen needs to prepare on reservation day)
    order.payment_status = 'PAID'
    order.status = 'PENDING'
    db.session.commit()

    # Notify admins & cashier
    staff_users = User.query.filter(User.role.in_(['ADMIN', 'CASHIER', 'STAFF'])).all()
    for staff in staff_users:
        create_notification(
            staff.id,
            'Reservation Payment Received! 💳',
            f'Reservation #{reservation.id} for {current_user.first_name} on {reservation.date.strftime("%b %d, %Y")} at {reservation.time.strftime("%I:%M %p")} is now paid. Please confirm the booking.',
            'RESERVATION'
        )

    # Notify user
    create_notification(
        current_user.id,
        'Reservation Payment Successful! 🎉',
        f'Your payment for your {reservation.date.strftime("%b %d, %Y")} {reservation.time.strftime("%I:%M %p")} reservation has been received. Awaiting admin confirmation.',
        'RESERVATION'
    )

    flash("Payment successful! Your reservation is pending admin confirmation. We'll notify you once confirmed.", "success")
    return redirect(url_for('main.index'))


# ─── Payment Failed (Xendit callback) ──────────────────────────────
@main_bp.route('/reserve/payment-failed/<int:res_id>/<int:order_id>')
@login_required
def reservation_payment_failed(res_id, order_id):
    reservation = Reservation.query.get_or_404(res_id)
    order = Order.query.get_or_404(order_id)

    if reservation.user_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for('main.index'))

    # Cancel both reservation and order
    reservation.status = 'REJECTED'
    order.status = 'CANCELLED'
    db.session.commit()

    flash("Payment was cancelled or failed. Your reservation has not been submitted. Please try again.", "danger")
    return redirect(url_for('main.reserve'))
@main_bp.route('/reserve/cancel/<int:res_id>', methods=['POST'])
@login_required
def cancel_reservation(res_id):
    reservation = Reservation.query.get_or_404(res_id)
    
    if reservation.user_id != current_user.id:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    if reservation.status != 'PENDING':
        return jsonify({"success": False, "message": "Only pending reservations can be cancelled."}), 400
    
    reason = request.form.get('reason')
    other_reason = request.form.get('other_reason')
    
    final_reason = other_reason if reason == 'Others' else reason
    
    reservation.status = 'REJECTED' # Equivalent to cancelled in this flow
    reservation.cancellation_reason = final_reason
    
    # Also cancel linked order if any
    linked_order = reservation.linked_order
    if linked_order:
        linked_order.status = 'CANCELLED'
    
    db.session.commit()
    
    # Notify admins
    staff_users = User.query.filter(User.role.in_(['ADMIN', 'CASHIER'])).all()
    for staff in staff_users:
        create_notification(
            staff.id,
            'Reservation Cancelled ❌',
            f'Reservation #{reservation.id} for {current_user.first_name} on {reservation.date.strftime("%b %d, %Y")} has been cancelled by the user. Reason: {final_reason}',
            'RESERVATION'
        )
        
    flash("Reservation cancelled successfully.", "success")
    return redirect(url_for('main.my_reservations'))


@main_bp.route('/reserve/update-cart', methods=['POST'])
@login_required
def reserve_update_cart():
    data = request.get_json()
    item_id = str(data.get('item_id'))
    qty = int(data.get('qty'))
    
    pending = session.get('pending_reservation')
    if not pending or 'menu_items' not in pending:
        return jsonify({"success": False, "message": "No pending reservation"}), 400
    
    if qty > 0:
        pending['menu_items'][item_id] = qty
    else:
        pending['menu_items'].pop(item_id, None)
    
    session.modified = True
    return jsonify({"success": True})


@main_bp.route('/reserve/clear-cart', methods=['POST'])
@login_required
def reserve_clear_cart():
    pending = session.get('pending_reservation')
    if pending and 'menu_items' in pending:
        pending['menu_items'] = {}
        session.modified = True
    return jsonify({"success": True})
