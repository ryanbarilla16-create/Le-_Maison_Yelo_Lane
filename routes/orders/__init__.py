from flask import render_template, request, session, redirect, url_for, flash
from flask_login import login_required, current_user
from .. import main_bp
from models import db, MenuItem, Order, OrderItem, Review, User
from datetime import datetime
from utils import get_ph_time, create_notification, validate_order
import os
import requests
import base64
from decimal import Decimal

@main_bp.route('/cart')
def view_cart():
    cart = session.get('cart', {})
    cart_items = []
    total = 0
    for item_id, quantity in cart.items():
        menu_item = MenuItem.query.get(int(item_id))
        if menu_item and not menu_item.is_deleted:
            subtotal = menu_item.price * quantity
            total += subtotal
            cart_items.append({
                'item': menu_item,
                'quantity': quantity,
                'subtotal': subtotal
            })
    return render_template('cart.html', cart_items=cart_items, total=total)

@main_bp.route('/cart/add/<int:item_id>', methods=['POST'])
def add_to_cart(item_id):
    if not current_user.is_authenticated:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"status": "error", "message": "Please log in to add items to your cart."}, 401
        flash("Please log in to add items to your cart.", "warning")
        return redirect(url_for('main.menu_page'))

    quantity = int(request.form.get('quantity', 1))
    cart = session.get('cart', {})
    
    item_id_str = str(item_id)
    menu_item = MenuItem.query.get(item_id)
    
    if not menu_item or menu_item.is_deleted or not menu_item.is_available:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            msg = "This item is currently sold out." if not menu_item.is_available else "Product is no longer available."
            return {"status": "error", "message": msg}, 404
        flash("This product is no longer available.", "danger")
        return redirect(url_for('main.menu_page'))

    if item_id_str in cart:
        cart[item_id_str] += quantity
    else:
        cart[item_id_str] = quantity
        
    session['cart'] = cart
    session.modified = True
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        total_items = sum(cart.values())
        return {"status": "success", "message": "Item added to cart!", "cart_count": total_items}

    flash("Item added to cart!", "success")
    # Redirect back to menu or wherever they came from
    return redirect(request.referrer or url_for('main.menu_page'))

@main_bp.route('/cart/update/<int:item_id>', methods=['POST'])
def update_cart(item_id):
    cart = session.get('cart', {})
    item_id_str = str(item_id)
    
    if item_id_str in cart:
        action = request.form.get('cart_action')
        if action == 'increment':
            cart[item_id_str] += 1
        elif action == 'decrement' and cart[item_id_str] > 1:
            cart[item_id_str] -= 1
        
        session['cart'] = cart
        session.modified = True
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            total_items = sum(cart.values())
            
            # Recalculate totals for immediate UI feedback
            new_subtotal = 0
            grand_total = 0
            for id_str, qty in cart.items():
                m_item = MenuItem.query.get(int(id_str))
                if m_item and not m_item.is_deleted:
                    item_sub = m_item.price * qty
                    grand_total += item_sub
                    if id_str == item_id_str:
                        new_subtotal = item_sub
            
            return {
                "status": "success", 
                "cart_count": total_items, 
                "new_quantity": cart[item_id_str],
                "item_subtotal": f"₱{new_subtotal:,.2f}",
                "grand_total": f"₱{grand_total:,.2f}"
            }
            
    return redirect(url_for('main.view_cart'))

@main_bp.route('/cart/remove/<int:item_id>', methods=['POST'])
def remove_from_cart(item_id):
    cart = session.get('cart', {})
    item_id_str = str(item_id)
    if item_id_str in cart:
        del cart[item_id_str]
        session['cart'] = cart
        session.modified = True
        flash("Item removed from cart.", "success")
    return redirect(url_for('main.view_cart'))

@main_bp.route('/cart/remove_multiple', methods=['POST'])
def remove_multiple_from_cart():
    cart = session.get('cart', {})
    item_ids = request.form.getlist('item_ids[]')
    removed_any = False
    for i_id in item_ids:
        if str(i_id) in cart:
            del cart[str(i_id)]
            removed_any = True
    if removed_any:
        session['cart'] = cart
        session.modified = True
        return {"status": "success", "message": "Selected items removed."}
    return {"status": "error", "message": "No items removed."}

@main_bp.route('/checkout', methods=['POST'])
@login_required
def checkout():
    cart = session.get('cart', {})
    if not cart:
        flash("Your cart is empty!", "danger")
        return redirect(url_for('main.view_cart'))
        
    selected_items = request.form.getlist('selected_items')
    if not selected_items:
        flash("Please select at least one item to checkout.", "warning")
        return redirect(url_for('main.view_cart'))
        
    items_to_checkout = {}
    for i_id in selected_items:
        if str(i_id) in cart:
            items_to_checkout[str(i_id)] = cart[str(i_id)]
            
    if not items_to_checkout:
        flash("No valid items selected for checkout.", "danger")
        return redirect(url_for('main.view_cart'))
        
    notes = request.form.get('notes', '')
    dining_option = request.form.get('dining_option', 'DINE_IN')
    payment_method = request.form.get('payment_method', 'COUNTER')
    
    delivery_area = request.form.get('delivery_area', '')
    delivery_address_input = request.form.get('delivery_address', '')
    
    # --- ORDER VALIDATION LOGIC ---
    items_data = [{'menu_item_id': int(id), 'quantity': qty} for id, qty in items_to_checkout.items()]
    is_valid, msg, status_override = validate_order(items_data, dining_option, payment_method, is_pos=False)
    
    if not is_valid:
        flash(msg, "danger")
        return redirect(url_for('main.view_cart'))
    # ------------------------------

    total = 0
    order_items = []
    
    for item_id, quantity in items_to_checkout.items():
        menu_item = MenuItem.query.get(int(item_id))
        if menu_item and menu_item.is_available and not menu_item.is_deleted:
            price = menu_item.price
            subtotal = price * quantity
            total += subtotal
            
            order_item = OrderItem(
                menu_item_id=menu_item.id,
                quantity=quantity,
                price_at_time=price
            )
            order_items.append(order_item)
            
    # Add Delivery Fee if applicable
    if dining_option == 'DELIVERY':
        total += Decimal('50.0')  # Flat delivery fee
            
    if not order_items:
        flash("Items in your cart are no longer available.", "danger")
        session['cart'] = {}
        return redirect(url_for('main.view_cart'))
        
    new_order = Order(
        user_id=current_user.id,
        total_amount=total,
        status=status_override or 'PENDING', # Use status_override (e.g., 'HOLD')
        dining_option=dining_option,
        payment_method=payment_method,
        notes=notes
    )
    
    if dining_option == 'DELIVERY':
        new_order.delivery_address = f"{delivery_address_input}, {delivery_area}"
        new_order.delivery_status = 'WAITING'
    
    db.session.add(new_order)
    db.session.flush() # get new_order.id
    
    for oi in order_items:
        oi.order_id = new_order.id
        db.session.add(oi)
        
    db.session.commit()
    
    # Remove checked out items from cart
    for item_id in items_to_checkout:
        del cart[item_id]
    session['cart'] = cart
    session.modified = True
    
    if payment_method == 'COUNTER':
        msg = "Order placed successfully! Please pay at the counter." if dining_option != 'DELIVERY' else "Order placed successfully! Please prepare exact payment upon delivery."
        flash(msg, "success")
        return redirect(url_for('main.index'))
    
    # Generate Xendit Invoice
    xendit_secret_key = os.environ.get('XENDIT_SECRET_KEY')
    if xendit_secret_key and xendit_secret_key != 'add_your_xendit_secret_key_here':
        api_key_b64 = base64.b64encode(f"{xendit_secret_key}:".encode('utf-8')).decode('utf-8')
        headers = {
            'Authorization': f'Basic {api_key_b64}',
            'Content-Type': 'application/json'
        }
        
        # Build invoice payload
        success_url = url_for('main.payment_success', order_id=new_order.id, _external=True)
        failure_url = url_for('main.payment_failed', order_id=new_order.id, _external=True)
        
        payload = {
            'external_id': f"order-{new_order.id}-{int(get_ph_time().timestamp())}",
            'amount': float(total),
            'payer_email': current_user.email,
            'description': f"Order #{new_order.id} from Le Maison",
            'success_redirect_url': success_url,
            'failure_redirect_url': failure_url,
            'currency': 'PHP',
            'customer': {
                'given_names': current_user.first_name,
                'surname': current_user.last_name,
                'email': current_user.email
            },
            'payment_methods': ['GCASH', 'PAYMAYA']
        }
        
        try:
            response = requests.post('https://api.xendit.co/v2/invoices', json=payload, headers=headers)
            if response.status_code == 200:
                invoice_data = response.json()
                new_order.xendit_invoice_url = invoice_data.get('invoice_url')
                new_order.xendit_invoice_id = invoice_data.get('id')
                db.session.commit()
                
                return redirect(new_order.xendit_invoice_url)
            else:
                flash(f"Failed to generate payment link: {response.json().get('message')}", "danger")
        except Exception as e:
            flash("An error occurred while connecting to the payment gateway.", "danger")
            print("Xendit Error:", e)
    else:
        # Fallback if no valid API key is present
        flash("Order placed successfully! Note: Payment gateway not configured. We'll contact you for payment.", "warning")

    return redirect(url_for('main.index'))

@main_bp.route('/payment-success/<int:order_id>')
@login_required
def payment_success(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash("Unauthorized", "danger")
        return redirect(url_for('main.index'))
    
    # In a production app, verify payment status with webhook or API.
    # We now set it to 'PENDING' so kitchen has to click "Start Cooking" first.
    order.status = 'PENDING'
    order.payment_status = 'PAID'
    db.session.commit()
    
    # Notify all staff (Admin, Cashier, Kitchen)
    staff_users = User.query.filter(User.role.in_(['ADMIN', 'CASHIER', 'STAFF', 'KITCHEN'])).all()
    for staff in staff_users:
        create_notification(
            staff.id, 
            'New Order Received! 🛍️', 
            f'Order #{order.id} for {current_user.first_name} has been paid and is ready for preparation.', 
            'ORDER'
        )
    
    flash("Payment successful! Your order has been placed.", "success")
    return redirect(url_for('main.index'))

@main_bp.route('/payment-failed/<int:order_id>')
@login_required
def payment_failed(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash("Unauthorized", "danger")
        return redirect(url_for('main.index'))
    
    order.status = 'CANCELLED'
    db.session.commit()
    
    flash("Payment failed or was cancelled.", "danger")
    return redirect(url_for('main.view_cart'))

@main_bp.route('/order/<int:order_id>/review', methods=['POST'])
@login_required
def add_order_review(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash("You are not authorized to review this order.", "danger")
        return redirect(url_for('main.my_orders'))
        
    if order.status != 'COMPLETED':
        flash("You can only review completed orders.", "warning")
        return redirect(url_for('main.my_orders'))

    # Check if a review already exists
    existing_review = Review.query.filter_by(order_id=order.id).first()
    if existing_review:
        flash("You have already reviewed this order.", "info")
        return redirect(url_for('main.my_orders'))

    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()

    if not rating or rating < 1 or rating > 5:
        flash("Please provide a valid star rating (1-5).", "danger")
        return redirect(url_for('main.my_orders'))

    new_review = Review(
        user_id=current_user.id,
        order_id=order.id,
        rating=rating,
        comment=comment,
        status='PENDING' # Requires admin approval by default
    )
    
    db.session.add(new_review)
    db.session.commit()
    
    flash("Thank you for your review! It has been submitted for approval.", "success")
    return redirect(url_for('main.my_orders'))

@main_bp.route('/order/<int:order_id>/receipt')
@login_required
def view_receipt(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash("Unauthorized", "danger")
        return redirect(url_for('main.index'))
    
    if order.payment_status != 'PAID':
        flash("Receipt is only available for paid orders.", "info")
        return redirect(url_for('main.my_orders'))
        
    return render_template('receipt.html', order=order)
