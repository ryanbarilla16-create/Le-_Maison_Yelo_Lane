from flask import render_template, jsonify, current_app
from flask_login import current_user, login_required
from .. import main_bp
from models import db, MenuItem, Reservation, MenuItemIngredient
from utils import load_site_settings, get_ph_time
from sqlalchemy import func
from datetime import date
from sqlalchemy.orm import load_only, selectinload
import time
import random

_MENU_CACHE_KEY = 'public_menu_items'
_MENU_CACHE_TTL = 120  # seconds

def _get_menu_items_for_menu_page():
    """Fetch menu items with a 2-minute in-memory cache to avoid repeated DB hits."""
    try:
        store = getattr(current_app, '_simple_cache', None)
        if store is not None:
            entry = store.get(_MENU_CACHE_KEY)
            if entry and (time.time() - entry['ts']) < _MENU_CACHE_TTL:
                return entry['data']
    except Exception:
        store = None

    items = (
        MenuItem.query.options(
            selectinload(MenuItem.ingredients).selectinload(MenuItemIngredient.ingredient)
        )
        .filter(MenuItem.is_deleted == False)
        .order_by(MenuItem.category, MenuItem.name)
        .all()
    )

    try:
        if store is not None:
            store[_MENU_CACHE_KEY] = {'data': items, 'ts': time.time()}
    except Exception:
        pass

    return items

def _get_featured_items_cached():
    total_available = MenuItem.query.filter_by(is_available=True, is_deleted=False).count()
    if total_available <= 0:
        return []

    # Avoid `ORDER BY RANDOM()` (slow on large tables). We pick an indexed slice by offset.
    offset = 0
    if total_available > 6:
        offset = random.randint(0, total_available - 6)

    items = (
        MenuItem.query.filter_by(is_available=True, is_deleted=False)
        .order_by(MenuItem.id.asc())
        .offset(offset)
        .limit(6)
        .all()
    )
    return items

@main_bp.route('/api/public/branches')
def public_branches():
    """Public endpoint — returns all branches for the Bienvenue modal."""
    try:
        from models import Branch as BranchModel
        branches = BranchModel.query.order_by(BranchModel.is_main.desc(), BranchModel.name.asc()).all()
        data = []
        for b in branches:
            label = (b.city or b.name)
            if b.province:
                label += ', ' + b.province
            if not b.is_active:
                label += ' (Coming Soon)'
            if b.is_main:
                label += ' (Main Branch)'
            data.append({
                'name': b.name,
                'label': label,
                'city': b.city or b.name,
                'province': b.province or '',
                'address': b.address or '',
                'phone': b.phone or '',
                'is_active': b.is_active,
                'is_main': b.is_main,
            })
        return jsonify({'success': True, 'branches': data})
    except Exception:
        # Fallback if Branch table doesn't exist yet
        return jsonify({'success': True, 'branches': [
            {'name': 'Lucban', 'label': 'Lucban, Quezon (Main Branch)', 'city': 'Lucban', 'province': 'Quezon',
             'address': 'Fidel Rada St, Lucban', 'phone': '+63 (998) 886-3566', 'is_active': True, 'is_main': True},
            {'name': 'Pagsanjan', 'label': 'Pagsanjan, Laguna', 'city': 'Pagsanjan', 'province': 'Laguna',
             'address': 'National Highway Brgy, Pagsanjan, Laguna', 'phone': '+63 (998) 886-3566', 'is_active': True, 'is_main': False},
            {'name': 'Lucena', 'label': 'Lucena City, Quezon (Coming Soon)', 'city': 'Lucena City', 'province': 'Quezon',
             'address': 'Lucena City', 'phone': '', 'is_active': False, 'is_main': False},
        ]})


@main_bp.route('/')
def index():
    site = load_site_settings()
    menu_items = MenuItem.query.filter_by(is_deleted=False, is_available=True).all()
    categories = db.session.query(
        MenuItem.category,
        func.count(MenuItem.id).label('count'),
        func.min(MenuItem.image_url).label('sample_image')
    ).filter(MenuItem.is_deleted == False).group_by(MenuItem.category).all()

    if current_user.is_authenticated and current_user.role != 'ADMIN':
        # Optimized User Dashboard - Combined queries and added limits
        today = date.today()
        
        # Combined Reservation Fetching
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

        # Efficient Menu Fetching
        featured = _get_featured_items_cached()
        bestsellers = MenuItem.query.filter_by(is_bestseller=True, is_available=True, is_deleted=False).limit(6).all()

        from models import Order, Review, OrderItem
        from sqlalchemy.orm import selectinload
        recent_orders = Order.query.options(
            selectinload(Order.items).selectinload(OrderItem.menu_item)
        ).filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(5).all()
        
        # Optimized Review Lookup
        user_reviews = Review.query.filter_by(user_id=current_user.id).all()
        user_reviews_by_order = {r.order_id: r for r in user_reviews if r.order_id}

        return render_template('customer/user_home.html',
            site=site, upcoming=upcoming, past=past, total_visits=total_visits,
            featured=featured, bestsellers=bestsellers, categories=categories,
            menu_items=menu_items, recent_orders=recent_orders,
            user_reviews_by_order=user_reviews_by_order,
            approved_reviews=Review.query.filter_by(status='APPROVED').order_by(Review.rating.desc(), Review.created_at.desc()).limit(30).all()
        )

    from models import Review
    approved_reviews = Review.query.filter_by(status='APPROVED').order_by(Review.rating.desc(), Review.created_at.desc()).limit(30).all()
    bestsellers = MenuItem.query.filter_by(is_bestseller=True, is_available=True, is_deleted=False).limit(6).all()
    
    # Fetch featured gallery photos (8 photos for 4x2 grid)
    gallery_photos = Review.query.filter_by(
        status='APPROVED',
        is_featured_in_gallery=True
    ).filter(
        Review.photo_url.isnot(None)
    ).order_by(Review.created_at.desc()).limit(8).all()

    # Fetch active branches for branch selector
    from models import Branch as BranchModel
    active_branches = BranchModel.query.filter_by(is_active=True).order_by(BranchModel.is_main.desc(), BranchModel.name.asc()).all()

    return render_template('public/index.html', 
        menu_items=menu_items, 
        site=site, 
        categories=categories, 
        approved_reviews=approved_reviews, 
        bestsellers=bestsellers,
        gallery_photos=gallery_photos,
        active_branches=active_branches
    )

@main_bp.route('/my-orders')
@login_required
def my_orders():
    from models import Order, Review, OrderItem
    from sqlalchemy.orm import selectinload

    # Optimized Order Fetching with Eager Loading (Limit to last 30 to prevent dashboard lag)
    all_orders = Order.query.options(
        selectinload(Order.items).selectinload(OrderItem.menu_item)
    ).filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(30).all()
    
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

    return render_template('customer/my_orders.html',
        all_orders=all_orders,
        pending_count=pending_count,
        preparing_count=preparing_count,
        on_the_way_count=on_the_way_count,
        completed_count=completed_count,
        user_reviews_by_order=user_reviews_by_order
    )


def _customer_order_overall_status(order):
    if order.dining_option == 'DELIVERY' and order.status == 'COMPLETED' and order.delivery_status != 'DELIVERED':
        if order.delivery_status in ['WAITING', 'PICKED_UP']:
            return 'PREPARING'
        return order.delivery_status or order.status
    if order.dining_option == 'DELIVERY' and order.delivery_status == 'DELIVERED':
        return 'COMPLETED'
    return order.status


@main_bp.route('/api/my-orders/status')
@login_required
def api_my_orders_status():
    """JSON polling endpoint for customer order tracking."""
    from models import Order

    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(30).all()
    payload = []
    for o in orders:
        overall = _customer_order_overall_status(o)
        payload.append({
            'id': o.id,
            'order_code': o.display_code,
            'overall_status': overall,
            'status': o.status,
            'delivery_status': o.delivery_status,
            'payment_status': o.payment_status,
            'dining_option': o.dining_option,
            'total_amount': float(o.total_amount or 0),
            'created_at': o.display_date_time,
        })

    pending_count = sum(1 for o in payload if o['overall_status'] == 'PENDING')
    preparing_count = sum(1 for o in payload if o['overall_status'] in ['PREPARING', 'WAITING', 'PICKED_UP'])
    completed_count = sum(1 for o in payload if o['overall_status'] in ['COMPLETED', 'DELIVERED'])

    return jsonify({
        'success': True,
        'time': get_ph_time().strftime('%I:%M:%S %p'),
        'stats': {
            'total': len(payload),
            'pending': pending_count,
            'preparing': preparing_count,
            'completed': completed_count,
        },
        'orders': payload,
    })


@main_bp.route('/my-reservations')
@login_required
def my_reservations():
    from models import Reservation
    # Limit list payload to keep page snappy; counts stay accurate via SQL
    all_res = (
        Reservation.query.filter_by(user_id=current_user.id)
        .order_by(Reservation.date.desc(), Reservation.time.desc())
        .limit(100)
        .all()
    )

    from sqlalchemy import func
    rows = (
        db.session.query(Reservation.status, func.count(Reservation.id))
        .filter(Reservation.user_id == current_user.id)
        .group_by(Reservation.status)
        .all()
    )
    counts = {status: c for status, c in rows}
    pending_count = counts.get('PENDING', 0)
    confirmed_count = counts.get('CONFIRMED', 0)
    completed_count = counts.get('COMPLETED', 0)
    cancelled_count = counts.get('REJECTED', 0)

    return render_template('customer/my_reservations.html',
        all_res=all_res,
        pending_count=pending_count,
        confirmed_count=confirmed_count,
        completed_count=completed_count,
        cancelled_count=cancelled_count
    )

@main_bp.route('/menu')
def menu_page():
    # Show all items (even unavailable ones, which show as 'Sold Out')
    menu_items = _get_menu_items_for_menu_page()
    return render_template('shop/menu_page.html', menu_items=menu_items)

@main_bp.route('/about')
def about_page():
    return render_template('public/about_page.html')

@main_bp.route('/reviews')
def reviews_page():
    site = load_site_settings()
    menu_items = MenuItem.query.filter_by(is_deleted=False).limit(4).all()
    categories = db.session.query(
        MenuItem.category,
        func.count(MenuItem.id).label('count'),
        func.min(MenuItem.image_url).label('sample_image')
    ).filter(MenuItem.is_deleted == False).group_by(MenuItem.category).all()
    
    from models import Review
    approved_reviews = Review.query.filter_by(status='APPROVED').order_by(Review.rating.desc(), Review.created_at.desc()).all()
    
    reviews_with_photos = [r for r in approved_reviews if r.photo_url]
    reviews_without_photos = [r for r in approved_reviews if not r.photo_url]
    # Fallback to all approved reviews if no text-only reviews exist, to ensure Lane 2 remains visible
    if not reviews_without_photos and approved_reviews:
        reviews_without_photos = approved_reviews

    bestsellers = MenuItem.query.filter_by(is_bestseller=True, is_available=True, is_deleted=False).limit(8).all()
    return render_template(
        'public/reviews_page.html', 
        site=site, 
        approved_reviews=approved_reviews,
        reviews_with_photos=reviews_with_photos,
        reviews_without_photos=reviews_without_photos
    )

@main_bp.route('/locations')
def locations_page():
    site = load_site_settings()
    return render_template('public/locations_page.html', site=site)

@main_bp.route('/pages/<page_name>')
def static_page(page_name):
    from utils import load_site_settings
    site = load_site_settings()
    title = page_name.replace('-', ' ').title()
    
    # Fully detailed content with HTML formatting
    content_map = {
        'Stories And News': '''
            <div style="text-align: left; max-width: 800px; margin: 0 auto;">
                <h4 style="color: var(--primary-color); margin-bottom: 1rem;">Welcome to Our Journey</h4>
                <p>Welcome to the Le Maison Yelo Lane blog and updates page! Here we share everything from our humble beginnings to the latest seasonal menu additions.</p>
                <div style="background: rgba(93,64,55,0.03); padding: 1.5rem; border-radius: 12px; border-left: 4px solid var(--primary-color); margin: 2rem 0;">
                    <h5 style="margin-bottom: 0.5rem; font-family: 'Playfair Display', serif;">Our Latest Expansion</h5>
                    <p style="margin-bottom: 0;">We recently opened our doors to a completely revamped dining space, designed to bring you the coziest cafe experience possible. Thank you to everyone who joined our reopening week!</p>
                </div>
                <p>Stay tuned for more updates as we continue introducing new dessert creations and specialty coffee blends tailored just for you.</p>
            </div>
        ''',
        
        'Customer Service': '''
            <div style="text-align: left; max-width: 800px; margin: 0 auto;">
                <p>Your satisfaction is our top priority. We are completely committed to ensuring that every order, whether dine-in, take-out, or delivery, meets your expectations.</p>
                <div class="row mt-4">
                    <div class="col-md-6 mb-3">
                        <div style="background: #fff; border: 1px solid var(--border-color); padding: 1.5rem; border-radius: 12px; height: 100%;">
                            <i class="fas fa-headset fa-2x mb-3" style="color: var(--primary-color);"></i>
                            <h5>Contact Us</h5>
                            <p class="small text-muted mb-1"><i class="fas fa-phone me-2"></i> 09988863566</p>
                            <p class="small text-muted"><i class="fas fa-envelope me-2"></i> support@lemaisonyelo.com</p>
                        </div>
                    </div>
                    <div class="col-md-6 mb-3">
                        <div style="background: #fff; border: 1px solid var(--border-color); padding: 1.5rem; border-radius: 12px; height: 100%;">
                            <i class="fas fa-clock fa-2x mb-3" style="color: var(--primary-color);"></i>
                            <h5>Operating Hours</h5>
                            <p class="small text-muted mb-0">Mon - Sun: 11:30 AM - 8:30 PM</p>
                        </div>
                    </div>
                </div>
            </div>
        ''',
        
        'Careers': '''
            <div style="text-align: left; max-width: 800px; margin: 0 auto;">
                <h4 style="color: var(--primary-color); margin-bottom: 1rem;">Join Our Team</h4>
                <p>Le Maison Yelo Lane isn't just a cafe; it's a family of passionate food lovers and coffee enthusiasts. We are constantly on the lookout for dedicated individuals who want to help us deliver the best dining experience.</p>
                <h5 class="mt-4 mb-3">Open Positions</h5>
                <ul class="list-group list-group-flush mb-4" style="border-radius: 12px; overflow: hidden; border: 1px solid var(--border-color);">
                    <li class="list-group-item d-flex justify-content-between align-items-center p-3">
                        <div>
                            <h6 class="mb-0 fw-bold">Barista</h6>
                            <small class="text-muted">Full-time / Part-time</small>
                        </div>
                        <span class="badge" style="background: var(--primary-color);">Apply</span>
                    </li>
                    <li class="list-group-item d-flex justify-content-between align-items-center p-3">
                        <div>
                            <h6 class="mb-0 fw-bold">Delivery Rider</h6>
                            <small class="text-muted">Freelance</small>
                        </div>
                        <span class="badge" style="background: var(--primary-color);">Apply</span>
                    </li>
                </ul>
                <p class="small text-muted">Send your resume to <strong>careers@lemaisonyelo.com</strong>.</p>
            </div>
        ''',
        
        'Order On The App': '''
            <div style="text-align: center; max-width: 800px; margin: 0 auto;">
                <i class="fas fa-mobile-alt fa-4x mb-4" style="color: var(--primary-color);"></i>
                <h4 style="margin-bottom: 1rem;">Experience Le Maison, Anywhere.</h4>
                <p style="margin-bottom: 2rem;">Ordering your favorite coffee and meals is faster and more convenient with our official mobile application. Get real-time delivery tracking, exclusive app-only vouchers, and a seamless checkout process.</p>
                <div class="d-flex justify-content-center gap-3">
                    <button class="btn btn-dark px-4 py-2" style="border-radius: 8px;"><i class="fab fa-apple me-2"></i>App Store</button>
                    <button class="btn px-4 py-2" style="background: #34A853; color: white; border-radius: 8px;"><i class="fab fa-google-play me-2"></i>Play Store</button>
                </div>
            </div>
        ''',
        
        'Faqs': '''
            <div style="text-align: left; max-width: 800px; margin: 0 auto;">
                <h4 style="color: var(--primary-color); margin-bottom: 1.5rem;">Frequently Asked Questions</h4>
                
                <div class="mb-4">
                    <h6 class="fw-bold"><i class="fas fa-question-circle me-2" style="color: var(--primary-color);"></i>Do you have vegetarian options?</h6>
                    <p class="text-muted" style="padding-left: 1.6rem;">Yes, we have several vegetarian dishes available on our main menu.</p>
                </div>
                
                <div class="mb-4">
                    <h6 class="fw-bold"><i class="fas fa-question-circle me-2" style="color: var(--primary-color);"></i>What are your delivery areas?</h6>
                    <p class="text-muted" style="padding-left: 1.6rem;">We currently deliver entirely to Santa Cruz, Magdalena, Los Baños, and Cavinti Laguna areas.</p>
                </div>
                
                <div class="mb-4">
                    <h6 class="fw-bold"><i class="fas fa-question-circle me-2" style="color: var(--primary-color);"></i>How do reservations work?</h6>
                    <p class="text-muted" style="padding-left: 1.6rem;">You can book tables or our Exclusive Venue at least 1 day in advance through the portal. Admin approval is required for all bookings.</p>
                </div>
            </div>
        ''',
        
        'Community': '''
            <div style="text-align: left; max-width: 800px; margin: 0 auto;">
                <p>We believe that a cafe is more than just a place to eat—it's the heart of the community. At Le Maison Yelo Lane, we actively work to foster meaningful relationships with the people around us.</p>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-top: 2rem;">
                    <div style="background: rgba(93,64,55,0.04); padding: 1.5rem; border-radius: 12px; text-align: center;">
                        <i class="fas fa-hand-holding-heart fa-2x mb-3" style="color: var(--primary-color);"></i>
                        <h6 class="fw-bold">Local Sourcing</h6>
                        <p class="small text-muted mb-0">We work directly with local farmers and suppliers in Laguna to guarantee fresh ingredients while supporting local livelihoods.</p>
                    </div>
                    <div style="background: rgba(93,64,55,0.04); padding: 1.5rem; border-radius: 12px; text-align: center;">
                        <i class="fas fa-users fa-2x mb-3" style="color: var(--primary-color);"></i>
                        <h6 class="fw-bold">Events & Gatherings</h6>
                        <p class="small text-muted mb-0">Our venue is open to local artists, study groups, and community seminars, providing a safe and cozy space for connection.</p>
                    </div>
                </div>
            </div>
        ''',
        
        'Sustainability': '''
            <div style="text-align: left; max-width: 800px; margin: 0 auto;">
                <h4 style="color: var(--primary-color); margin-bottom: 1rem;">Our Green Commitment</h4>
                <p>Minimizing our environmental footprint is one of our core philosophies. We aim to ensure that our operations are as sustainable as possible.</p>
                <ul style="line-height: 1.8; color: var(--text-muted);">
                    <li><strong>Eco-Friendly Packaging:</strong> We use biodegradable and recyclable materials for all our take-out and delivery orders.</li>
                    <li><strong>Waste Reduction:</strong> Leftover ingredients that are safe for consumption are donated or composted to minimize food waste.</li>
                    <li><strong>Energy Efficiency:</strong> Our cafe utilizes energy-efficient lighting and appliances to drastically reduce our carbon footprint.</li>
                </ul>
            </div>
        ''',
        
        'Web Accessibility': '''
            <div style="text-align: left; max-width: 800px; margin: 0 auto;">
                <p>We are constantly working to ensure that our digital presence is accessible to all individuals, including those with disabilities.</p>
                <p>We strive to adhere strictly to the Web Content Accessibility Guidelines (WCAG) 2.1 to ensure our site operates flawlessly with screen readers, keyboard navigation, and other assistive technologies.</p>
                <p class="small text-muted mt-4">If you experience any difficulties accessing our content, please email <strong style="color: var(--text-main);">support@lemaisonyelo.com</strong>.</p>
            </div>
        ''',
        
        'Privacy Policy': '''
            <div style="text-align: left; max-width: 800px; margin: 0 auto; color: var(--text-muted);">
                <h5 style="color: var(--text-main); margin-bottom: 1rem;">1. Information We Collect</h5>
                <p>We collect personal information such as your name, email address, phone number, and delivery address when you register or place an order with us.</p>
                <h5 style="color: var(--text-main); margin-bottom: 1rem; margin-top: 2rem;">2. Use of Information</h5>
                <p>Your information is used strictly to process orders, manage your reservations, and send you critical updates regarding your account or our services.</p>
                <h5 style="color: var(--text-main); margin-bottom: 1rem; margin-top: 2rem;">3. Data Security</h5>
                <p>We employ enterprise-grade security protocols to protect your password and personal data. We never sell or share your data with 3rd-party marketing agencies without your explicit consent.</p>
            </div>
        ''',
        
        'Terms Of Use': '''
            <div style="text-align: left; max-width: 800px; margin: 0 auto; color: var(--text-muted);">
                <p><strong>Effective Date: March 2026</strong></p>
                <h5 style="color: var(--text-main); margin-bottom: 1rem; margin-top: 1.5rem;">User Conduct</h5>
                <p>By accessing the Le Maison Yelo Lane platform, you agree to use the site exclusively for lawful purposes. You must not use the platform for any fraudulent activities, including creating dummy accounts or submitting false reservations.</p>
                <h5 style="color: var(--text-main); margin-bottom: 1rem; margin-top: 1.5rem;">Orders and Cancellations</h5>
                <p>Once an order has entered the "PREPARING" phase, it can no longer be cancelled. Refunds for online payments are subject to review by management.</p>
                <h5 style="color: var(--text-main); margin-bottom: 1rem; margin-top: 1.5rem;">Account Suspensions</h5>
                <p>We reserve the right to suspend or terminate any accounts caught abusing our policies, including repeated failure to pay and receive Cash on Delivery (COD) orders.</p>
            </div>
        '''
    }
    
    # Provide a fallback generic text just in case
    content = content_map.get(title, f'<div style="text-align:center;"><p>Welcome to the {title} page. Full details will be available soon.</p></div>')
    
    return render_template('public/generic_page.html', title=title, site=site, content=content)

@main_bp.route('/contact', methods=['GET', 'POST'])
def contact_page():
    site = load_site_settings()
    from flask import request, flash, redirect, url_for, jsonify
    from models import db, ContactMessage

    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone_number = request.form.get('phone_number')
        message = request.form.get('message')

        new_message = ContactMessage(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone_number=phone_number,
            message=message
        )
        db.session.add(new_message)
        db.session.commit()
        
        # Check if it's an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': 'Your message has been sent successfully! We will get back to you soon.'
            })
        
        flash('Your message has been sent successfully! We will get back to you soon.', 'success')
        return redirect(url_for('main.contact_page'))

    return render_template('public/contact_page.html', site=site)


@main_bp.route('/home-sections/hero')
def home_section_hero():
    return render_template('home_sections/hero.html')


@main_bp.route('/home-sections/about')
def home_section_about():
    return render_template('home_sections/about.html')


@main_bp.route('/home-sections/menu')
def home_section_menu():
    menu_items = MenuItem.query.filter_by(is_deleted=False, is_available=True).all()
    return render_template('home_sections/menu.html', menu_items=menu_items)


@main_bp.route('/home-sections/reviews')
def home_section_reviews():
    return render_template('home_sections/reviews.html')
