# Quick Fix Guide: Archive Connection Error

## ⚡ Immediate Solution

If you're seeing the error:
```
(psycopg2.OperationalError) server closed the connection unexpectedly
```

### Step 1: Test the Connection
```bash
python test_archive_connection.py
```

### Step 2: If Test Fails, Run the Fix
```bash
python fix_archive_connection.py
```

### Step 3: Restart Your Application
```bash
# Stop the current Flask app (Ctrl+C)
# Then restart it
python app.py
```

## ✅ What Was Fixed

1. **Better Connection Pooling** - Increased pool size and added keepalive settings
2. **Automatic Retries** - Queries now retry up to 3 times on connection errors
3. **Session Cleanup** - Stale connections are properly cleaned up
4. **Error Handling** - Better error messages and graceful degradation

## 🔍 Verify the Fix

1. Go to Admin Panel → Data Archive
2. Try running an archive operation
3. Check if the error is gone

## 📊 Monitor Health

The test script shows:
- ✅ Connection status
- ✅ Archive schema status
- ✅ Table count
- ✅ Record count

Run it anytime to check health:
```bash
python test_archive_connection.py
```

## 🆘 Still Having Issues?

1. Check your `.env` file has correct `DATABASE_URL`
2. Verify your database server is running
3. Check if your IP is whitelisted (for cloud databases)
4. Review `ARCHIVE_CONNECTION_FIX.md` for detailed troubleshooting

## 📝 Configuration Tips

If archive operations are slow or timing out, edit `archive/config.json`:

```json
{
  "batch_size": 100  // Reduce from 200 to 100 for more stability
}
```

Smaller batch size = more stable but slower archiving.
