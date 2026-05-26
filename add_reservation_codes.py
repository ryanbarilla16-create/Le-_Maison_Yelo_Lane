"""
Backfill script to add reservation codes to existing reservations.
Run this after applying the migration.
"""
from app import app
from models import db, Reservation
from datetime import datetime
from collections import defaultdict

def generate_reservation_code_for_date(reservation_date, sequence):
    """
    Generate reservation code for a specific date and sequence.
    Format: YYYYMMDD-SEQUENCE (e.g., 20240526-001)
    """
    date_str = reservation_date.strftime('%Y%m%d')
    return f"{date_str}-{sequence:03d}"

def backfill_reservation_codes():
    """Add reservation codes to all existing reservations that don't have one."""
    with app.app_context():
        # Get all reservations without reservation_code, ordered by created_at
        reservations = Reservation.query.filter(
            (Reservation.reservation_code == None) | (Reservation.reservation_code == '')
        ).order_by(Reservation.created_at.asc()).all()
        
        if not reservations:
            print("✅ All reservations already have codes!")
            return
        
        print(f"📋 Found {len(reservations)} reservations without codes.")
        print("🔄 Generating codes based on creation date...\n")
        
        # Group reservations by date (using created_at date)
        reservations_by_date = defaultdict(list)
        for res in reservations:
            # Use the date part of created_at for grouping
            reservation_date = res.created_at.date()
            reservations_by_date[reservation_date].append(res)
        
        updated_count = 0
        
        # Process each date group
        for reservation_date in sorted(reservations_by_date.keys()):
            date_reservations = reservations_by_date[reservation_date]
            
            # Check if there are existing reservations with codes for this date
            existing_codes = Reservation.query.filter(
                Reservation.reservation_code.like(f'{reservation_date.strftime("%Y%m%d")}-%')
            ).order_by(Reservation.reservation_code.desc()).first()
            
            # Determine starting sequence
            if existing_codes and existing_codes.reservation_code:
                try:
                    last_seq = int(existing_codes.reservation_code.split('-')[-1])
                    starting_seq = last_seq + 1
                except (ValueError, IndexError):
                    starting_seq = 1
            else:
                starting_seq = 1
            
            # Assign codes to reservations for this date
            for idx, res in enumerate(date_reservations, start=starting_seq):
                res.reservation_code = generate_reservation_code_for_date(reservation_date, idx)
                print(f"  ✓ Reservation #{res.id} → {res.reservation_code}")
                updated_count += 1
        
        # Commit all changes
        try:
            db.session.commit()
            print(f"\n✅ Successfully added codes to {updated_count} reservations!")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error: {str(e)}")
            raise

if __name__ == '__main__':
    print("=" * 60)
    print("🎫 RESERVATION CODE BACKFILL SCRIPT")
    print("=" * 60)
    print()
    
    backfill_reservation_codes()
    
    print()
    print("=" * 60)
    print("✨ Done!")
    print("=" * 60)
