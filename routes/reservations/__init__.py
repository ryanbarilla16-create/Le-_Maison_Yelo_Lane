from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Reservation
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

        try:
            res_date = datetime.strptime(res_date_str, '%Y-%m-%d').date()
            hour, minute = map(int, res_time_str.split(':'))
            res_time = dtime(hour, minute)
            guest_count = int(guest_count_str)
        except ValueError:
            flash("Invalid data format provided.", "danger")
            return redirect(url_for('main.reserve'))

        today = date.today()
        diff = (res_date - today).days
        if diff < 1:
            flash("Reservation must be at least 1 day in advance.", "danger")
            return redirect(url_for('main.reserve'))
        if diff > 14:
            flash("Reservation can be max 14 days in advance.", "danger")
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

        current_res_datetime = datetime.combine(res_date, res_time)
        close_time = dtime(20, 30)
        
        if booking_type == 'EXCLUSIVE':
            conflict = False
            for r in active_res:
                if r.time >= res_time and r.time <= close_time:
                    conflict = True
                    break
                if r.booking_type == 'EXCLUSIVE' and r.time <= res_time:
                    conflict = True
                    break
            if conflict:
                flash("Cannot book Exclusive Venue. There are conflicting reservations in your requested time block.", "danger")
                return redirect(url_for('main.reserve'))
        else:
            conflict_excl = False
            for r in active_res:
                if r.booking_type == 'EXCLUSIVE' and r.time <= res_time:
                    conflict_excl = True
                    break
            if conflict_excl:
                flash("Time slot blocked by an Exclusive Venue booking.", "danger")
                return redirect(url_for('main.reserve'))
            
            total_guests_at_time = sum([r.guest_count for r in active_res if r.time == res_time])
            if total_guests_at_time + guest_count > 50:
                flash("Capacity Guard: Time slot is fully booked. Not enough seats.", "danger")
                return redirect(url_for('main.reserve'))

        new_res = Reservation(
            user_id=current_user.id,
            date=res_date,
            time=res_time,
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

    return render_template('reserve.html')
