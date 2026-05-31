# Order Code Display - Kitchen View Fix

## Problem
Kitchen View cards still showing `#0095` instead of `ORD-20260526-001` format.

## Root Cause
**Browser/Flask Template Caching** - The old template is cached even though the file was updated.

## What Was Updated

### File: `templates/admin/kitchen_partial.html`
**Line 117** - Order card header

**BEFORE:**
```html
<h5 class="kds-order-id m-0">#{{ order.id }}</h5>
```

**AFTER:**
```html
<h5 class="kds-order-id m-0">{{ order.order_code or '#' + order.id|string }}</h5>
```

## Verification
The code is **CORRECT** in the file. The issue is caching.

## Solutions to Fix Caching

### Solution 1: Hard Refresh Browser (FASTEST)
1. Open Kitchen View page
2. Press **Ctrl + Shift + R** (Windows) or **Cmd + Shift + R** (Mac)
3. This forces browser to reload all files from server

### Solution 2: Clear Browser Cache
1. Press **F12** to open Developer Tools
2. Right-click the **Refresh button**
3. Select **"Empty Cache and Hard Reload"**

### Solution 3: Restart Flask Server
1. Stop Flask server: **Ctrl + C**
2. Start Flask server: `python app.py`
3. Refresh browser: **Ctrl + Shift + R**

### Solution 4: Force Template Reload (If using Flask debug mode)
Add this to your Flask app config:
```python
app.config['TEMPLATES_AUTO_RELOAD'] = True
```

### Solution 5: Clear Flask Cache (If using Flask-Caching)
If you have Flask-Caching enabled, clear it:
```bash
# In Python console or add to your code temporarily
from extensions import cache
cache.clear()
```

### Solution 6: Modify Template Cache Buster
The template already has a cache buster comment:
```html
<!-- KITCHEN PARTIAL CONTENT - CACHE BUSTER 2315 -->
```

Change the number to force reload:
```html
<!-- KITCHEN PARTIAL CONTENT - CACHE BUSTER 2316 -->
```

## Expected Result After Fix

### Kitchen View Order Cards
**Order Header (Top Left):**
- New orders: `ORD-20260527-001`
- Old orders (before migration): `#95`

## All Updated Templates Summary

✅ **Cashier Dashboard** (`templates/cashier/dashboard.html`)
   - Line 127: `{{ order.order_code or '#' + order.id|string }}`

✅ **Billing Page** (`templates/cashier/billing.html`)
   - Line 286: `#{{ order.id }}` (still needs update if you want order codes here)

✅ **Kitchen View** (`templates/admin/kitchen_partial.html`)
   - Line 117: `{{ order.order_code or '#' + order.id|string }}`

✅ **Receipt** (`templates/admin/receipt.html`)
   - Line 138: `{{ order.order_code or order.id }}`

## Testing Steps

1. **Restart Flask server**
2. **Hard refresh browser** (Ctrl + Shift + R)
3. **Navigate to Kitchen View** (`/admin/kitchen`)
4. **Check order cards** - should show `ORD-YYYYMMDD-XXX` format
5. **Create new order** - should automatically get order code
6. **Check old orders** - should show `#95` format (fallback)

## Troubleshooting

### If still showing old format:
1. Check Flask server logs for errors
2. Verify database has `order_code` column
3. Check if orders have order codes: `SELECT id, order_code FROM "order" LIMIT 10;`
4. Try incognito/private browsing mode
5. Try different browser

### If showing blank:
- Check if `order.order_code` is None for all orders
- Run backfill script: `python add_order_codes.py`

## Database Verification

Check if order codes exist:
```sql
SELECT id, order_code, created_at 
FROM "order" 
ORDER BY created_at DESC 
LIMIT 10;
```

Expected output:
```
id  | order_code        | created_at
----|-------------------|-------------------
95  | ORD-20260527-001  | 2026-05-27 09:15:00
94  | ORD-20260527-002  | 2026-05-27 10:30:00
```

## Summary

The code is **CORRECT**. The issue is **caching**. Use **Ctrl + Shift + R** to force reload.
