"""
Seed script: Creates 8 realistic Filipino customer reviews with food/cafe photos,
all APPROVED and featured in the homepage gallery.
Run once: python seed_reviews.py
"""
import os
import sys

# Make sure Flask app context is loaded
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import User, Review
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import random

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

FILIPINO_REVIEWERS = [
    {
        "first_name": "Kristine",
        "last_name": "Bautista",
        "username": "kristine.bautista",
        "email": "kristine.bautista@gmail.com",
        "rating": 5,
        "comment": "Sobrang sarap ng pagkain dito! Lalo na yung French toast nila, best talaga sa buong Laguna. Malambot, mabango, at sulit na sulit ang presyo. Siguradong babalik kami ulit!",
        "photo_url": "https://images.unsplash.com/photo-1504674900247-0877df9cc836?q=80&w=600&auto=format&fit=crop",
        "days_ago": 3,
    },
    {
        "first_name": "Patrick",
        "last_name": "Mendoza",
        "username": "patrick.mendoza",
        "email": "patrick.mendoza@gmail.com",
        "rating": 5,
        "comment": "Ang ganda ng ambiance at ang bilis ng service! Para kang nasa maliit na coffee shop sa France. Perfect para mag-relax pagkatapos ng mahabang araw. Highly recommended sa lahat!",
        "photo_url": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?q=80&w=600&auto=format&fit=crop",
        "days_ago": 7,
    },
    {
        "first_name": "Sophia",
        "last_name": "Villanueva",
        "username": "sophia.villanueva",
        "email": "sophia.villanueva@gmail.com",
        "rating": 5,
        "comment": "Pinakamasarap na pasta na natikman ko sa Laguna! Ang laki pa ng serving at reasonable ang presyo. Yung creamy carbonara nila ay napakalambot ng noodles at sobrang sarap ng sauce. 10/10!",
        "photo_url": "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?q=80&w=600&auto=format&fit=crop",
        "days_ago": 12,
    },
    {
        "first_name": "Emmanuel",
        "last_name": "Garcia",
        "username": "emmanuel.garcia",
        "email": "emmanuel.garcia@gmail.com",
        "rating": 5,
        "comment": "Date night namin dito sa Le Maison at sobrang naging masaya kami! Ang serbisyo ay napaka-friendly at attentive. Yung chicken cordon bleu nila ay talaga namang masarap. Babalik kami for our anniversary!",
        "photo_url": "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?q=80&w=600&auto=format&fit=crop",
        "days_ago": 18,
    },
    {
        "first_name": "Maricel",
        "last_name": "Santos",
        "username": "maricel.santos",
        "email": "maricel.santos@gmail.com",
        "rating": 5,
        "comment": "Ang ganda ng interior design! Parang nasa ibang bansa ka talaga. Yung coffee nila, especially yung caramel latte, ay sobrang sarap at hindi masyadong matamis. Perfect siya para umaga!",
        "photo_url": "https://images.unsplash.com/photo-1509042239860-f550ce710b93?q=80&w=600&auto=format&fit=crop",
        "days_ago": 25,
    },
    {
        "first_name": "Joshua",
        "last_name": "Reyes",
        "username": "joshua.reyes",
        "email": "joshua.reyes@gmail.com",
        "rating": 5,
        "comment": "Nagpunta kami dito para sa birthday ng nanay ko at hindi kami nabigo! Ang desserts nila ay sobrang sarap, lalo na yung tiramisu. Masarap at presentable pa! Maraming salamat Le Maison!",
        "photo_url": "https://images.unsplash.com/photo-1551218808-94e220e084d2?q=80&w=600&auto=format&fit=crop",
        "days_ago": 32,
    },
    {
        "first_name": "Angeline",
        "last_name": "dela Cruz",
        "username": "angeline.delacruz",
        "email": "angeline.delacruz@gmail.com",
        "rating": 5,
        "comment": "Nag-order kami ng delivery at grabe, mainit pa ang pagkain nung dumating! Yung packaging nila ay napakaganda at safe. Ang steak nila ay sobrang tender at juicy. Definitely oorder ulit!",
        "photo_url": "https://images.unsplash.com/photo-1559339352-11d035aa65de?q=80&w=600&auto=format&fit=crop",
        "days_ago": 40,
    },
    {
        "first_name": "Rommel",
        "last_name": "Flores",
        "username": "rommel.flores",
        "email": "rommel.flores@gmail.com",
        "rating": 5,
        "comment": "Best breakfast spot sa Pagsanjan! Yung French toast at freshly brewed coffee ay perpektong pang-umaga. Ang staff ay napaka-welcoming at palaging nakangiti. Lagi na kaming dito tuwing weekend!",
        "photo_url": "https://images.unsplash.com/photo-1497935586351-b67a49e012bf?q=80&w=600&auto=format&fit=crop",
        "days_ago": 48,
    },
]

def run_seed():
    with app.app_context():
        added = 0
        skipped = 0

        base_date = datetime.utcnow()

        for data in FILIPINO_REVIEWERS:
            # Skip if a review with this photo_url already exists
            existing_review = Review.query.filter_by(photo_url=data["photo_url"]).first()
            if existing_review:
                print(f"  [SKIP] Review for {data['first_name']} {data['last_name']} already exists.")
                skipped += 1
                continue

            # Get or create user
            user = User.query.filter_by(email=data["email"]).first()
            if not user:
                user = User(
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    username=data["username"],
                    email=data["email"],
                    password_hash=generate_password_hash("SamplePass123!", method="pbkdf2:sha256"),
                    status="ACTIVE",
                    is_verified=True,
                    role="USER",
                    phone_number="09" + str(random.randint(100000000, 999999999)),
                )
                db.session.add(user)
                db.session.flush()  # Get user.id
                print(f"  [USER] Created user: {user.first_name} {user.last_name} (id={user.id})")
            else:
                print(f"  [USER] Using existing user: {user.first_name} {user.last_name} (id={user.id})")

            review_date = base_date - timedelta(days=data["days_ago"])

            review = Review(
                user_id=user.id,
                order_id=None,
                rating=data["rating"],
                comment=data["comment"],
                photo_url=data["photo_url"],
                status="APPROVED",
                is_featured_in_gallery=True,
                created_at=review_date,
            )
            db.session.add(review)
            added += 1
            print(f"  [REVIEW] Added review for {data['first_name']} {data['last_name']} - '{data['photo_url'][:60]}...'")

        db.session.commit()
        print(f"\n[SUCCESS] Done! Added {added} reviews, skipped {skipped} duplicates.")
        print("   The homepage gallery will now display the customer photos.")

if __name__ == "__main__":
    run_seed()
