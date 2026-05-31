# 🚀 Archive System - Quick Start Guide

## ✅ TAPOS NA! SYSTEM IS READY!

---

## 📊 Current Status

### Main Database (Fast - For Daily Operations)
- Orders: **83**
- Reservations: **22**
- Inventory Logs: **0** ✅ (cleaned!)
- Notifications: **260** ✅ (cleaned!)

### Archive Database (Storage - For History)
- Orders: **13**
- Reservations: **9**
- Inventory Logs: **73** ✅ (archived!)
- Notifications: **74** ✅ (archived!)

**Result:** Main Database is now **FASTER** and **CLEANER**! 🎉

---

## 🎯 How It Works (Simple Explanation)

1. **Completed orders/reservations** stay in Main Database for **1 day**
2. After 1 day, they become **eligible for archiving**
3. When you click **"Run Archive Now"**:
   - ✅ Data is **COPIED** to Archive Database
   - ✅ Data is **REMOVED** from Main Database
4. **Staff** won't see old data (faster dashboards!)
5. **Admins** can still browse archived data anytime

---

## 🖥️ How to Use

### Option 1: Web Interface (Easiest!)

1. **Login** as Super Admin
2. **Go to:** http://localhost:5000/admin/archive
3. **Click:** "Run Archive Now" button
4. **Done!** Old data moved to archive

### Option 2: Command Line

```bash
# View statistics
flask archive stats

# Run archive job
flask archive run
```

### Option 3: Python Script

```bash
# View statistics
python test_archive_system.py

# Run archive now
python run_archive_now.py
```

---

## ⏰ When to Run Archive?

### Recommended Schedule:
- **Weekly** - For active restaurants
- **Monthly** - For moderate traffic
- **As needed** - Check `/admin/archive` dashboard

### Signs You Need to Archive:
- Main Database has many old completed orders
- Staff dashboards loading slowly
- "Eligible Now" counter shows high numbers

---

## ⚙️ Change Retention Period

**File:** `archive/config.json`

```json
{
  "retention_days": {
    "orders": 1,           // Change to 7, 30, 90 days
    "reservations": 1,
    "notifications": 1
  }
}
```

**Recommended:**
- Orders: **30 days** (1 month)
- Reservations: **90 days** (3 months)
- Notifications: **7 days** (1 week)

---

## 🔍 Browse Archived Data

1. Go to: http://localhost:5000/admin/archive
2. Click: **"Browse Archived Orders"**
3. Filter by branch or status
4. View full order details

---

## ✅ What's Included?

The archive system handles:
- ✅ Orders (with items, chats, reviews)
- ✅ Reservations
- ✅ Audit Logs
- ✅ Inventory Logs
- ✅ Notifications
- ✅ Permission Audit Logs

---

## 🎉 Benefits

### For Staff:
- ✅ **Faster dashboards** (less data to load)
- ✅ **Cleaner views** (only recent orders)
- ✅ **Better performance** (faster queries)

### For Admins:
- ✅ **Historical data preserved** (nothing lost!)
- ✅ **Easy to browse** (web interface)
- ✅ **Audit trail** (all archive runs logged)

### For Customers:
- ✅ **No impact** (can still see their order history)
- ✅ **Faster app** (backend is faster)

---

## 📝 Quick Commands

```bash
# Test the system
python test_archive_system.py

# Run archive now
python run_archive_now.py

# View Flask commands
flask archive --help

# View statistics
flask archive stats

# Run archive job
flask archive run
```

---

## 🆘 Need Help?

1. Read: `ARCHIVE_SYSTEM_GUIDE.md` (detailed guide)
2. Run: `python test_archive_system.py` (diagnose issues)
3. Check: Flask logs for errors

---

## 🎊 SUCCESS!

**Archive System Status:** ✅ COMPLETE AND WORKING

**Last Archive Run:**
- ✅ 8 Inventory Logs archived
- ✅ 69 Notifications archived
- ✅ Main Database cleaned
- ✅ Data safely stored in Archive

**You're all set!** Just run the archive job regularly to keep your system fast! 🚀

---

**Date:** May 27, 2026
**Status:** ✅ OPERATIONAL
