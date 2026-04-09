from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Reservation, MenuItem
from datetime import datetime, date, time as dtime
from .. import main_bp

def check_reservation_time(t):
    if not (dtime(11, 30) <= t <= dtime(20, 30)):
        return False
    if t.minute not in (0, 30):
        return False
    return True

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
                from datetime import datetime as dt
                curr_t = dt.now().time()
                if res_time <= curr_t:
                    flash("You cannot book a time slot that has already passed today.", "danger")
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

        from datetime import timedelta
        current_res_start = datetime.combine(res_date, res_time)
        current_res_end = current_res_start + timedelta(hours=duration)
        
        conflict = False
        conflict_msg = ""
        
        for r in active_res:
            r_start = datetime.combine(r.date, r.time)
            # handle old rows where duration might be None by defaulting to 2
            r_dur = r.duration if r.duration is not None else 2
            r_end = r_start + timedelta(hours=r_dur)
            
            # Check overlap logic: (Start A < End B) and (Start B < End A)
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

        new_res = Reservation(
            user_id=current_user.id,
            date=res_date,
            time=res_time,
            duration=duration,
            guest_count=guest_count,
            occasion=occasion,
            booking_type=booking_type
        )
        db.session.add(new_res)
        db.session.commit()
        
        # Notify all admins
        from models import User
        from utils import create_notification
        admin_users = User.query.filter(User.role == 'ADMIN').all()
        for admin in admin_users:
            create_notification(
                admin.id,
                'New Reservation Request! 📅',
                f'A new reservation for {res_date.strftime("%b %d, %Y")} at {res_time.strftime("%I:%M %p")} needs your approval.',
                'RESERVATION'
            )
            
        flash("Reservation submitted successfully and is pending admin approval.", "success")
        return redirect(url_for('main.reserve'))

    menu_items = MenuItem.query.filter_by(is_available=True).all()
    return render_template('reserve.html', menu_items=menu_items)
