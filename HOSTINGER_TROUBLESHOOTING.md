# 🔧 HOSTINGER TROUBLESHOOTING GUIDE

## Common Problems and Solutions

---

## ❌ Problem 1: Cannot Connect via SSH

### Symptoms:
- "Connection refused"
- "Connection timed out"
- Cannot login to server

### Solutions:

**Check 1: SSH is enabled**
1. Login to Hostinger hPanel
2. Go to VPS/Cloud Hosting
3. Check if SSH is enabled
4. Enable if disabled

**Check 2: Correct credentials**
```bash
# Use correct format:
ssh username@YOUR_SERVER_IP -p 22

# Example:
ssh root@123.45.67.89 -p 22
```

**Check 3: Firewall blocking**
```bash
# On server, check firewall:
sudo ufw status

# Allow SSH:
sudo ufw allow 22/tcp
```

---

## ❌ Problem 2: Service Won't Start

### Symptoms:
- `systemctl status lemaison` shows "failed"
- Website not accessible
- 502 Bad Gateway error

### Solutions:

**Check 1: View error logs**
```bash
sudo journalctl -u lemaison -n 100
```

**Check 2: Test manually**
```bash
cd /var/www/lemaison
source venv/bin/activate
gunicorn --worker-class eventlet -w 1 --bind 127.0.0.1:5000 app:app
```

**Check 3: File permissions**
```bash
sudo chown -R www-data:www-data /var/www/lemaison
sudo chmod -R 755 /var/www/lemaison
```

**Check 4: Python dependencies**
```bash
cd /var/www/lemaison
source venv/bin/activate
pip install -r requirements.txt
```

---

## ❌ Problem 3: Database Connection Error

### Symptoms:
- "could not connect to server"
- "password authentication failed"
- "database does not exist"

### Solutions:

**Check 1: PostgreSQL is running**
```bash
sudo systemctl status postgresql
sudo systemctl start postgresql
```

**Check 2: Database exists**
```bash
sudo -u postgres psql -l
# Should show lemaison_db in the list
```

**Check 3: User can connect**
```bash
psql -U lemaison_user -d lemaison_db -h localhost
# Enter password when prompted
```

**Check 4: .env file correct**
```bash
cd /var/www/lemaison
cat .env | grep DATABASE_URL
# Should show: postgresql://lemaison_user:password@localhost:5432/lemaison_db
```

**Fix: Recreate database**
```bash
sudo -u postgres psql

DROP DATABASE IF EXISTS lemaison_db;
DROP USER IF EXISTS lemaison_user;
CREATE USER lemaison_user WITH PASSWORD 'YourPassword123!';
CREATE DATABASE lemaison_db OWNER lemaison_user;
GRANT ALL PRIVILEGES ON DATABASE lemaison_db TO lemaison_user;
\q
```

---

## ❌ Problem 4: 502 Bad Gateway

### Symptoms:
- Nginx shows "502 Bad Gateway"
- Website not loading

### Solutions:

**Check 1: Service is running**
```bash
sudo systemctl status lemaison
sudo systemctl start lemaison
```

**Check 2: Port 5000 is listening**
```bash
sudo netstat -tulpn | grep 5000
# Should show gunicorn listening on 127.0.0.1:5000
```

**Check 3: Nginx configuration**
```bash
sudo nginx -t
sudo systemctl restart nginx
```

**Check 4: Firewall**
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

---

## ❌ Problem 5: Domain Not Working

### Symptoms:
- Domain shows "This site can't be reached"
- IP works but domain doesn't

### Solutions:

**Check 1: DNS records**
1. Login to Hostinger hPanel
2. Go to Domains → DNS
3. Verify A records:
   - `@` → YOUR_SERVER_IP
   - `www` → YOUR_SERVER_IP

**Check 2: DNS propagation**
```bash
# Check if DNS is propagated:
nslookup YOUR_DOMAIN.com
# Should show your server IP
```

**Check 3: Wait for propagation**
- DNS changes take 15-30 minutes
- Sometimes up to 24 hours
- Be patient!

**Check 4: Nginx domain config**
```bash
sudo nano /etc/nginx/sites-available/lemaison
# Make sure server_name matches your domain
```

---

## ❌ Problem 6: SSL Certificate Error

### Symptoms:
- "Your connection is not private"
- HTTPS not working
- Certificate expired

### Solutions:

**Check 1: Certificate exists**
```bash
sudo certbot certificates
```

**Check 2: Reinstall certificate**
```bash
sudo certbot --nginx -d YOUR_DOMAIN.com -d www.YOUR_DOMAIN.com --force-renewal
```

**Check 3: Auto-renewal**
```bash
sudo systemctl status certbot.timer
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

---

## ❌ Problem 7: Website Slow or Crashing

### Symptoms:
- Website loads very slowly
- Random crashes
- High memory usage

### Solutions:

**Check 1: Server resources**
```bash
# Check memory:
free -h

# Check CPU:
top

# Check disk:
df -h
```

**Check 2: Increase workers (if enough RAM)**
```bash
sudo nano /etc/systemd/system/lemaison.service
# Change: -w 1 to -w 2 (if you have 2GB+ RAM)
sudo systemctl daemon-reload
sudo systemctl restart lemaison
```

**Check 3: Database optimization**
```bash
sudo -u postgres psql lemaison_db
VACUUM ANALYZE;
\q
```

**Check 4: Clear logs**
```bash
sudo journalctl --vacuum-time=7d
```

---

## ❌ Problem 8: Cannot Upload Files

### Symptoms:
- FileZilla won't connect
- Cannot upload via SFTP

### Solutions:

**Check 1: Use SFTP (not FTP)**
- Protocol: SFTP
- Host: YOUR_SERVER_IP
- Port: 22
- Username: Your SSH username
- Password: Your SSH password

**Check 2: Permissions**
```bash
sudo chown -R $USER:$USER /var/www/lemaison
```

---

## ❌ Problem 9: Git Clone Fails

### Symptoms:
- "Permission denied"
- "Repository not found"

### Solutions:

**Check 1: Repository is public**
- Make sure GitHub repo is public
- Or use SSH key authentication

**Check 2: Use HTTPS URL**
```bash
git clone https://github.com/USERNAME/REPO.git
# NOT: git@github.com:USERNAME/REPO.git
```

**Check 3: Git is installed**
```bash
sudo apt install git -y
```

---

## ❌ Problem 10: Python Module Not Found

### Symptoms:
- "ModuleNotFoundError: No module named 'flask'"
- Import errors

### Solutions:

**Check 1: Virtual environment activated**
```bash
cd /var/www/lemaison
source venv/bin/activate
# Prompt should show (venv)
```

**Check 2: Reinstall dependencies**
```bash
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Check 3: Service uses correct Python**
```bash
sudo nano /etc/systemd/system/lemaison.service
# Make sure Environment="PATH=/var/www/lemaison/venv/bin"
sudo systemctl daemon-reload
sudo systemctl restart lemaison
```

---

## 🔍 Diagnostic Commands

### Check everything at once:
```bash
echo "=== SERVICE STATUS ==="
sudo systemctl status lemaison

echo "=== NGINX STATUS ==="
sudo systemctl status nginx

echo "=== POSTGRESQL STATUS ==="
sudo systemctl status postgresql

echo "=== LISTENING PORTS ==="
sudo netstat -tulpn | grep -E ':(80|443|5000)'

echo "=== DISK SPACE ==="
df -h

echo "=== MEMORY ==="
free -h

echo "=== RECENT LOGS ==="
sudo journalctl -u lemaison -n 20
```

---

## 📞 Still Having Problems?

### Get detailed logs:
```bash
# Application logs
sudo journalctl -u lemaison -n 200 > ~/lemaison_logs.txt

# Nginx logs
sudo tail -n 100 /var/log/nginx/error.log > ~/nginx_logs.txt

# System logs
dmesg | tail -n 100 > ~/system_logs.txt
```

### Contact Hostinger Support:
1. Login to Hostinger hPanel
2. Click "Help" or "Support"
3. Open a ticket
4. Attach the log files above

---

## 🎯 Quick Fixes

### Restart everything:
```bash
sudo systemctl restart postgresql
sudo systemctl restart lemaison
sudo systemctl restart nginx
```

### Reset permissions:
```bash
sudo chown -R www-data:www-data /var/www/lemaison
sudo chmod -R 755 /var/www/lemaison
```

### Clear cache:
```bash
cd /var/www/lemaison
find . -type d -name __pycache__ -exec rm -r {} +
find . -type f -name "*.pyc" -delete
```

---

**Remember:** Most problems are solved by checking logs first!

```bash
sudo journalctl -u lemaison -f
```

