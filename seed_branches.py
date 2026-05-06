"""
Seed Script: Multi-Branch Accounts
Creates the Super Admin, Lucban Admin, and Lucban Staff accounts.
Also updates existing Pagsanjan admin/staff to have the 'Pagsanjan' branch tag.

Run: python seed_branches.py
"""
from app import app, db
from models import User

ACCOUNTS = [
    {
        "first_name": "Super",
        "last_name": "Admin",
        "username": "superadmin",
        "email": "superadmin@lemaisonyelo.com",
        "password": "SuperAdmin@2026",
        "role": "SUPER_ADMIN",
        "branch": "ALL",
        "status": "ACTIVE",
        "is_verified": True,
    },
    {
        "first_name": "Lucban",
        "last_name": "Admin",
        "username": "lucbanadmin",
        "email": "admin.lucban@lemaisonyelo.com",
        "password": "LucbanAdmin@2026",
        "role": "ADMIN",
        "branch": "Lucban",
        "status": "ACTIVE",
        "is_verified": True,
    },
    {
        "first_name": "Lucban",
        "last_name": "Kitchen",
        "username": "lucbankitchen",
        "email": "kitchen.lucban@lemaisonyelo.com",
        "password": "LucbanKitchen@2026",
        "role": "KITCHEN",
        "branch": "Lucban",
        "status": "ACTIVE",
        "is_verified": True,
    },
    {
        "first_name": "Lucban",
        "last_name": "Cashier",
        "username": "lucbancashier",
        "email": "cashier.lucban@lemaisonyelo.com",
        "password": "LucbanCashier@2026",
        "role": "CASHIER",
        "branch": "Lucban",
        "status": "ACTIVE",
        "is_verified": True,
    },
    {
        "first_name": "Lucban",
        "last_name": "Inventory",
        "username": "lucbaninventory",
        "email": "inventory.lucban@lemaisonyelo.com",
        "password": "LucbanInventory@2026",
        "role": "INVENTORY_STAFF",
        "branch": "Lucban",
        "status": "ACTIVE",
        "is_verified": True,
    },
    {
        "first_name": "Lucban",
        "last_name": "Rider",
        "username": "lucbanrider",
        "email": "rider.lucban@lemaisonyelo.com",
        "password": "LucbanRider@2026",
        "role": "RIDER",
        "branch": "Lucban",
        "status": "ACTIVE",
        "is_verified": True,
    },
]

def seed():
    with app.app_context():
        # Tag existing staff as Pagsanjan if they don't have a branch yet
        existing_staff = User.query.filter(
            User.role.in_(['ADMIN', 'CASHIER', 'KITCHEN', 'INVENTORY_STAFF', 'INVENTORY', 'STAFF', 'RIDER']),
            User.branch.is_(None)
        ).all()
        
        for user in existing_staff:
            user.branch = 'Pagsanjan'
            print(f"  [TAG] Existing {user.role} '{user.email}' -> Pagsanjan branch")
        
        # Create new accounts
        for acc in ACCOUNTS:
            existing = User.query.filter_by(email=acc["email"]).first()
            if existing:
                print(f"  [SKIP] Account '{acc['email']}' already exists.")
                continue
            
            user = User(
                first_name=acc["first_name"],
                last_name=acc["last_name"],
                username=acc["username"],
                email=acc["email"],
                role=acc["role"],
                branch=acc["branch"],
                status=acc["status"],
                is_verified=acc["is_verified"],
            )
            user.set_password(acc["password"])
            db.session.add(user)
            print(f"  [NEW] Created {acc['role']} -> {acc['email']} (Branch: {acc['branch']})")
        
        db.session.commit()
        print("\n" + "=" * 60)
        print("[DONE] Multi-Branch Seeding Complete!")
        print("=" * 60)
        print("\nAccount Summary:")
        print("-" * 80)
        print(f"{'Role':<20} {'Email':<40} {'Password'}")
        print("-" * 80)
        for acc in ACCOUNTS:
            print(f"{acc['role']:<20} {acc['email']:<40} {acc['password']}")
        print("-" * 80)

if __name__ == '__main__':
    seed()
