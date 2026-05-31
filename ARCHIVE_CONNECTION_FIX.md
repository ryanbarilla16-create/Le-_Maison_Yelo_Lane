# Archive Database Connection Error Fix

## Problem
The archive system was experiencing PostgreSQL connection errors:
```
(psycopg2.OperationalError) server closed the connection unexpectedly
This probably means the server terminated abnormally before or while processing the request.
```

## Root Causes
1. **Connection Pool Exhaustion**: The default connection pool settings were too conservative
2. **Stale Connections**: Long-running connections were timing out without proper keepalive
3. **No Retry Logic**: Failed queries weren't being retried after connection errors
4. **Session Cleanup**: Database sessions weren't being properly cleaned up after errors

## Fixes Applied

### 1. Enhanced Connection Pool Configuration (`config.py`)
```python
SQLALCHEMY_ENGINE_OPTIONS = {
    "pool_pre_ping": True,          # Test connections before using them
    "pool_recycle": 300,            # Recycle connections after 5 minutes
    "pool_size": 10,                # Increase pool size from default 5
    "max_overflow": 20,             # Allow up to 20 overflow connections
    "pool_timeout": 30,             # Wait up to 30 seconds for a connection
    "connect_args": {
        "connect_timeout": 10,      # Connection timeout
        "keepalives": 1,            # Enable TCP keepalives
        "keepalives_idle": 30,      # Start keepalives after 30s idle
        "keepalives_interval": 10,  # Send keepalive every 10s
        "keepalives_count": 5,      # Retry 5 times before giving up
    }
}
```

### 2. Retry Logic in Archive Manager (`archive/manager.py`)
Added automatic retry logic for all database queries:
- Retries failed queries up to 3 times
- Automatically reconnects after connection errors
- Gracefully handles failures with default values

### 3. Session Cleanup (`app.py`)
Added proper session cleanup:
```python
@app.teardown_appcontext
def shutdown_session(exception=None):
    if exception:
        db.session.rollback()
    db.session.remove()
```

### 4. Error Handling in Routes (`routes/admin/__init__.py`)
Added try-catch blocks with proper error handling:
- Catches `OperationalError` specifically
- Rolls back and removes stale sessions
- Shows user-friendly error messages

## Testing

### Test Connection
Run the connection test script:
```bash
python test_archive_connection.py
```

This will:
- ✅ Test database connection
- ✅ Verify archive schema exists
- ✅ List all archive tables
- ✅ Count archive run records

### Fix Connection Issues
If you encounter connection problems:
```bash
python fix_archive_connection.py
```

This will:
- Recreate the archive schema if needed
- Recreate all archive tables
- Verify the setup

## Monitoring

### Check Archive Status
1. Go to Admin Panel → Data Archive
2. View statistics and recent runs
3. Monitor for any connection errors

### Database Connection Health
Monitor these metrics:
- Connection pool usage
- Query execution time
- Failed connection attempts
- Session cleanup frequency

## Best Practices

### 1. Regular Maintenance
- Run archive operations during low-traffic periods
- Monitor database connection pool usage
- Keep PostgreSQL server updated

### 2. Connection Management
- Always use `db.session.remove()` after errors
- Don't hold connections open unnecessarily
- Use connection pooling effectively

### 3. Error Handling
- Always catch `OperationalError` for connection issues
- Implement retry logic for transient failures
- Log errors for debugging

### 4. Performance
- Use batch operations for large datasets
- Limit query result sizes
- Use indexes on frequently queried columns

## Troubleshooting

### Error: "server closed the connection unexpectedly"
**Solution**: The fixes above should resolve this. If it persists:
1. Check if your database server is under heavy load
2. Verify network connectivity to the database
3. Check PostgreSQL logs for server-side errors
4. Increase `pool_size` and `max_overflow` if needed

### Error: "too many connections"
**Solution**: 
1. Reduce `pool_size` and `max_overflow`
2. Ensure sessions are being cleaned up properly
3. Check for connection leaks in your code

### Error: "SSL connection has been closed unexpectedly"
**Solution**:
1. Verify SSL/TLS settings in your database URL
2. Check if your database provider requires specific SSL modes
3. Update `sslmode` parameter if needed

### Slow Archive Operations
**Solution**:
1. Reduce `batch_size` in archive config
2. Run archive during off-peak hours
3. Add indexes to frequently queried columns
4. Consider archiving in smaller chunks

## Configuration

### Archive Config (`archive/config.json`)
```json
{
  "retention_days": {
    "orders": 180,
    "reservations": 365,
    "audit_logs": 90,
    "inventory_logs": 90,
    "notifications": 60,
    "permission_audit_logs": 90
  },
  "eligible_order_statuses": ["COMPLETED", "CANCELLED"],
  "eligible_reservation_statuses": ["COMPLETED", "REJECTED", "CANCELLED"],
  "batch_size": 200
}
```

Adjust `batch_size` if you experience connection timeouts:
- Smaller batch size = more stable but slower
- Larger batch size = faster but more prone to timeouts

## Additional Resources

- [PostgreSQL Connection Pooling](https://www.postgresql.org/docs/current/runtime-config-connection.html)
- [SQLAlchemy Engine Configuration](https://docs.sqlalchemy.org/en/14/core/engines.html)
- [psycopg2 Connection Parameters](https://www.psycopg.org/docs/module.html#psycopg2.connect)

## Support

If you continue to experience issues:
1. Check the application logs for detailed error messages
2. Run `python test_archive_connection.py` to diagnose
3. Review PostgreSQL server logs
4. Contact your database provider's support if needed
