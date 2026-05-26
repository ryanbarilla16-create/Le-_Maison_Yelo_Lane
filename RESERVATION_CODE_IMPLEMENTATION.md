# Reservation Code Implementation Guide

## Overview
This implementation adds a unique reservation code system to your Le Maison restaurant system.

**Format:** `YYYYMMDD-SEQUENCE` (e.g., `20240526-001`)
- No "RES-" prefix (as requested)
- Date-based with daily sequence counter
- Unique and indexed for fast lookups

---

## Files Modified

### 1. **models.py**
- Added `reservation_code` field to `Reservation` model
- Field is unique, indexed, and nullable (for existing records)

### 2. **utils.py**
- Added `generate_reservation_code()` function
- Similar pattern to existing `generate_order_code()` function
- Generates format: `YYYYMMDD-SEQUENCE`

### 3. **routes/reservations/__init__.py**
- Updated `reserve_confirm()` route
- Now generates reservation code when creating new reservations

### 4. **routes/api/__init__.py**
- Updated mobile API reservation endpoint
- Now generates reservation code for mobile app reservations

---

## New Files Created

### 1. **migrations/versions/add_reservation_code_to_reservation.py**
- Database migration file
- Adds `reservation_code` column to `reservation` table
- Creates unique index for fast lookups

### 2. **add_reservation_codes.py**
- Backfill script for existing reservations
- Generates codes for all reservations that don't have one yet
- Groups by creation date and assigns sequential codes

---

## Installation Steps

### Step 1: Apply Database Migration
```bash
# Run the migration to add the reservation_code column
flask db upgrade
```

### Step 2: Backfill Existing Reservations (Optional)
```bash
# Only run this if you have existing reservations without codes
python add_reservation_codes.py
```

### Step 3: Restart Your Application
```bash
# Restart Flask app to load the new code
# If using development server:
flask run

# If using production (gunicorn, etc.):
# Restart your production server
```

---

## How It Works

### New Reservations
When a user creates a new reservation:
1. System calls `generate_reservation_code()` from `utils.py`
2. Function checks the last reservation code for today
3. Increments the sequence number
4. Returns format: `20240526-001`, `20240526-002`, etc.
5. Code is saved to the database with the reservation

### Existing Reservations
If you have existing reservations:
1. Run `add_reservation_codes.py` script
2. Script groups reservations by creation date
3. Assigns sequential codes based on creation order
4. Preserves existing codes if any

---

## Code Examples

### Generate Reservation Code
```python
from utils import generate_reservation_code

# Generate a new code
code = generate_reservation_code()
# Returns: "20240526-001" (for first reservation today)
```

### Create Reservation with Code
```python
from models import Reservation
from utils import generate_reservation_code

reservation_code = generate_reservation_code()

new_reservation = Reservation(
    reservation_code=reservation_code,
    user_id=user_id,
    date=res_date,
    time=res_time,
    # ... other fields
)
```

### Query by Reservation Code
```python
from models import Reservation

# Find reservation by code
reservation = Reservation.query.filter_by(
    reservation_code="20240526-001"
).first()
```

---

## Testing

### Test New Reservation Creation
1. Go to `/reserve` on your website
2. Fill in reservation details
3. Complete the reservation process
4. Check the database - new reservation should have a code like `20240526-001`

### Test Backfill Script
```bash
# Run the backfill script
python add_reservation_codes.py

# Expected output:
# 📋 Found X reservations without codes.
# 🔄 Generating codes based on creation date...
#   ✓ Reservation #1 → 20240526-001
#   ✓ Reservation #2 → 20240526-002
# ✅ Successfully added codes to X reservations!
```

### Verify in Database
```sql
-- Check if codes were generated
SELECT id, reservation_code, date, time, status 
FROM reservation 
ORDER BY created_at DESC 
LIMIT 10;
```

---

## Display Reservation Code to Users

### In Templates
```html
<!-- Show reservation code in user's reservation list -->
<p>Reservation Code: <strong>{{ reservation.reservation_code }}</strong></p>
```

### In API Response
```python
# Include in JSON response
return jsonify({
    'success': True,
    'reservation': {
        'id': reservation.id,
        'reservation_code': reservation.reservation_code,
        'date': reservation.date.strftime('%Y-%m-%d'),
        # ... other fields
    }
})
```

---

## Benefits

✅ **Unique Identification** - Each reservation has a unique code  
✅ **Easy Reference** - Users can reference their reservation by code  
✅ **Date-Based** - Code includes date for easy tracking  
✅ **Sequential** - Daily sequence makes it easy to count reservations  
✅ **Indexed** - Fast database lookups  
✅ **Clean Format** - No prefix, just date and number (as requested)

---

## Troubleshooting

### Issue: Migration fails
**Solution:** Check if column already exists
```sql
-- Check if column exists
SELECT column_name 
FROM information_schema.columns 
WHERE table_name='reservation' AND column_name='reservation_code';
```

### Issue: Duplicate codes
**Solution:** This shouldn't happen due to unique constraint, but if it does:
```python
# Re-run backfill script
python add_reservation_codes.py
```

### Issue: Codes not generating for new reservations
**Solution:** Check if `generate_reservation_code()` is imported correctly
```python
# In your route file
from utils import generate_reservation_code
```

---

## Future Enhancements

### Add to Email Notifications
```python
# Include reservation code in confirmation emails
email_body = f"""
Dear {user.first_name},

Your reservation has been confirmed!
Reservation Code: {reservation.reservation_code}
Date: {reservation.date}
Time: {reservation.time}
"""
```

### Add to Admin Dashboard
```python
# Search reservations by code
@admin_bp.route('/reservations/search')
def search_reservation():
    code = request.args.get('code')
    reservation = Reservation.query.filter_by(
        reservation_code=code
    ).first_or_404()
    return render_template('admin/reservation_detail.html', 
                         reservation=reservation)
```

---

## Summary

✨ **Implementation Complete!**

All new reservations will automatically get a unique code in format `YYYYMMDD-SEQUENCE`.

No "RES-" prefix as requested - just clean date + sequence number.

Perfect for tracking, referencing, and managing reservations! 🎉
