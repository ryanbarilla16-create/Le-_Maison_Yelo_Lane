from flask import render_template
from flask_login import current_user, login_required
from .. import main_bp
from models import db, MenuItem, Reservation
from utils import load_site_settings
from sqlalchemy import func
from datetime import date

@main_bp.route('/')
def index():
    site = load_site_settings()
    menu_items = MenuItem.query.filter_by(is_available=True).limit(4).all()
    categories = db.session.query(
        MenuItem.category,
        func.count(MenuItem.id).label('count'),
        func.min(MenuItem.image_url).label('sample_image')
    ).filter(MenuItem.is_available == True).group_by(MenuItem.category).all()

    if current_user.is_authenticated and current_user.role != 'ADMIN':
        # Personalized user dashboard
        today = date.today()
        upcoming = Reservation.query.filter(
            Reservation.user_id == current_user.id,
            Reservation.date >= today,
            Reservation.status.in_(['PENDING', 'CONFIRMED'])
        ).order_by(Reservation.date.asc(), Reservation.time.asc()).limit(3).all()

        past = Reservation.query.filter(
            Reservation.user_id == current_user.id,
            Reservation.status.in_(['COMPLETED', 'REJECTED'])
        ).order_by(Reservation.created_at.desc()).limit(3).all()

        total_visits = Reservation.query.filter(
            Reservation.user_id == current_user.id,
            Reservation.status == 'COMPLETED'
        ).count()

        featured = MenuItem.query.filter_by(is_available=True).order_by(func.random()).limit(6).all()

        # Bestsellers - items from the 'Best Sellers' category
        bestsellers = MenuItem.query.filter_by(is_available=True, category='Best Sellers').all()

        from models import Order
        
        recent_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(5).all()
        
        from models import Review
        user_reviews = Review.query.filter_by(user_id=current_user.id).all()
        user_reviews_by_order = {r.order_id: r for r in user_reviews if r.order_id}

        return render_template('user_home.html',
            site=site,
            upcoming=upcoming,
            past=past,
            total_visits=total_visits,
            featured=featured,
            bestsellers=bestsellers,
            categories=categories,
            menu_items=menu_items,
            recent_orders=recent_orders,
            user_reviews_by_order=user_reviews_by_order
        )

    from models import Review
    approved_reviews = Review.query.filter_by(status='APPROVED').order_by(Review.rating.desc(), Review.created_at.desc()).all()

    return render_template('index.html', menu_items=menu_items, site=site, categories=categories, approved_reviews=approved_reviews)

@main_bp.route('/my-orders')
@login_required
def my_orders():
    from models import Order, Review

    all_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    
    for o in all_orders:
        if o.dining_option == 'DELIVERY' and o.status == 'COMPLETED' and o.delivery_status != 'DELIVERED':
            if o.delivery_status in ['WAITING', 'PICKED_UP']:
                o.overall_status = 'PREPARING' # still in progress
            else:
                o.overall_status = o.delivery_status # ON_THE_WAY
        elif o.dining_option == 'DELIVERY' and o.delivery_status == 'DELIVERED':
             o.overall_status = 'COMPLETED'
        else:
            o.overall_status = o.status

    pending_count = sum(1 for o in all_orders if o.overall_status == 'PENDING')
    preparing_count = sum(1 for o in all_orders if o.overall_status in ['PREPARING', 'WAITING', 'PICKED_UP'])
    on_the_way_count = sum(1 for o in all_orders if o.overall_status == 'ON_THE_WAY')
    completed_count = sum(1 for o in all_orders if o.overall_status == 'COMPLETED')
    
    user_reviews = Review.query.filter_by(user_id=current_user.id).all()
    user_reviews_by_order = {r.order_id: r for r in user_reviews if r.order_id}

    return render_template('my_orders.html',
        all_orders=all_orders,
        pending_count=pending_count,
        preparing_count=preparing_count,
        on_the_way_count=on_the_way_count,
        completed_count=completed_count,
        user_reviews_by_order=user_reviews_by_order
    )

@main_bp.route('/menu')
def menu_page():
    # Show all available items on the full menu page
    menu_items = MenuItem.query.filter_by(is_available=True).all()
    return render_template('menu_page.html', menu_items=menu_items)

@main_bp.route('/about')
def about_page():
    return render_template('about_page.html')

@main_bp.route('/reviews')
def reviews_page():
    site = load_site_settings()
    menu_items = MenuItem.query.filter_by(is_available=True).limit(4).all()
    categories = db.session.query(
        MenuItem.category,
        func.count(MenuItem.id).label('count'),
        func.min(MenuItem.image_url).label('sample_image')
    ).filter(MenuItem.is_available == True).group_by(MenuItem.category).all()
    
    from models import Review
    approved_reviews = Review.query.filter_by(status='APPROVED').order_by(Review.rating.desc(), Review.created_at.desc()).all()

    return render_template('index.html', title="Reviews", site=site, menu_items=menu_items, categories=categories, approved_reviews=approved_reviews)
