# 🚀 Hostinger Deployment Guide - Le Maison Restaurant System

## Pag-deploy sa Hostinger.com

Gabay ito para ma-deploy ang inyong restaurant management system sa Hostinger.

---

## 📋 Pre-requisites (Kailangan Muna)

1. ✅ Hostinger account (naka-bili na kayo)
2. ✅ Python hosting plan (VPS o Cloud Hosting)
3. ✅ SSH access sa server
4. ✅ Domain name (kung meron)

---

## 🎯 Step 1: Prepare ang Hostinger Server

### 1.1 Login sa Hostinger hPanel
1. Pumunta sa https://hostinger.com
2. Login gamit ang inyong account
3. Pumunta sa **VPS** o **Cloud Hosting** section

### 1.2 Access SSH Terminal
1. Sa Hostinger hPanel, hanapin ang **SSH Access**
2. I-enable ang SSH access
3. I-copy ang SSH credentials:
   - Hostname
   - Port
   - Username
   - Password

### 1.3 Connect via SSH
```bash
ssh username@your-server-ip -p port
```

---

## 🔧 Step 2: Install Dependencies sa Server

### 2.1 Update System
```bash
sudo apt update && sudo apt upgrade -y
```

### 2.2 Install Python 3.12
```bash
sudo apt install python3.12 python3.12-venv python3-pip -y
```

### 2.3 Install PostgreSQL
```bash
sudo apt install postgresql postgresql-contrib libpq-dev -y
```

### 2.4 Install Nginx (Web Server)
```bash
sudo apt install nginx -y
```

### 2.5 Install Git
```bash
sudo apt install git -y
```

---

## 📦 Step 3: Upload ang Code sa Server

### Option A: Via Git (Recommended)
```bash
# Create project directory
cd /var/www
sudo mkdir lemaison
sudo chown $USER:$USER lemaison
cd lemaison

# Clone your repository (kung naka-push sa GitHub/GitLab)
git clone https://github.com/your-username/your-repo.git .

# OR kung wala pang git repo, gawin muna:
# 1. Create GitHub repository
# 2. Push code:
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/your-username/your-repo.git
git push -u origin main
```

### Option B: Via FTP/SFTP
1. Download FileZilla o WinSCP
2. Connect sa server gamit ang SSH credentials
3. Upload lahat ng files sa `/var/www/lemaison`

---

## 🗄️ Step 4: Setup PostgreSQL Database

### 4.1 Create Database User
```bash
sudo -u postgres psql

# Sa PostgreSQL prompt:
CREATE USER lemaison_user WITH PASSWORD 'your_strong_password_here';
CREATE DATABASE lemaison_db OWNER lemaison_user;
GRANT ALL PRIVILEGES ON DATABASE lemaison_db TO lemaison_user;
\q
```

### 4.2 Get Database Connection String
```
postgresql://lemaison_user:your_strong_password_here@localhost:5432/lemaison_db
```

---

## ⚙️ Step 5: Configure Environment Variables

### 5.1 Create Production .env File
```bash
cd /var/www/lemaison
nano .env.production
```

### 5.2 Paste ang Configuration (I-edit ang values)
```env
# ======== DATABASE SETTINGS ========
DATABASE_URL=postgresql://lemaison_user:your_strong_password_here@localhost:5432/lemaison_db

# ======== FLASK APP SETTINGS ========
SECRET_KEY=GENERATE_NEW_RANDOM_SECRET_KEY_HERE_VERY_LONG_AND_SECURE
FLASK_ENV=production
FLASK_RUN_HOST=0.0.0.0

# ======== EMAIL (OTP) ========
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=ryanbarilla254@gmail.com
MAIL_PASSWORD=smqnvgtyfgwzipqr

# ======== SUPABASE (OPTIONAL) ========
SUPABASE_URL=https://rnmeiclskivuyzvyxmpp.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJubWVpY2xza2l2dXl6dnl4bXBwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIyOTUyNTUsImV4cCI6MjA4Nzg3MTI1NX0.zCHJRQgsXWyTpONeqKIPyu0sfGyAFyGdXW2gb-W6x_Q

# ======== XENDIT PAYMENT ========
XENDIT_PUBLIC_KEY=xnd_public_development_Zp6Dnri0CUwWCfZyUJ7sA3eY2WY51AT_VFPpHB80wF3phCuFsxBWo3dvfNPiK0k
XENDIT_SECRET_KEY=xnd_development_0nBIOfz73fnTN4clGigTE3KeW3bNNpCsC1NG48WEf5Csbzo2tn4pLw5SeGs69

# ======== SOCIAL LOGIN ========
FACEBOOK_APP_ID=2031079187624124
FACEBOOK_APP_SECRET=0c42c26fc51c640497fb3ecc5ffbdaf0
GOOGLE_CLIENT_ID=77851915575-o74qqe52iomde0m4u82fcara28l0n00e.apps.googleusercontent.com
```

**IMPORTANTE:** Generate new SECRET_KEY:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 5.3 Rename to .env
```bash
mv .env.production .env
```

---

## 🐍 Step 6: Setup Python Virtual Environment

```bash
cd /var/www/lemaison

# Create virtual environment
python3.12 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

---

## 🗃️ Step 7: Initialize Database

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Initialize database tables
python3 -c "from app import app, db; app.app_context().push(); db.create_all(); print('Database initialized!')"

# Run migrations (if any)
flask db upgrade
```

---

## 🌐 Step 8: Configure Nginx

### 8.1 Create Nginx Configuration
```bash
sudo nano /etc/nginx/sites-available/lemaison
```

### 8.2 Paste Configuration (I-edit ang domain)
```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;  # I-edit ito

    # Increase timeouts for long-running requests
    proxy_connect_timeout 600;
    proxy_send_timeout 600;
    proxy_read_timeout 600;
    send_timeout 600;

    # Increase buffer sizes
    client_max_body_size 50M;
    client_body_buffer_size 128k;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for Socket.IO
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /static {
        alias /var/www/lemaison/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
}
```

### 8.3 Enable Site
```bash
sudo ln -s /etc/nginx/sites-available/lemaison /etc/nginx/sites-enabled/
sudo nginx -t  # Test configuration
sudo systemctl restart nginx
```

---

## 🔄 Step 9: Setup Systemd Service (Auto-start)

### 9.1 Create Service File
```bash
sudo nano /etc/systemd/system/lemaison.service
```

### 9.2 Paste Configuration
```ini
[Unit]
Description=Le Maison Restaurant Management System
After=network.target postgresql.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/lemaison
Environment="PATH=/var/www/lemaison/venv/bin"
ExecStart=/var/www/lemaison/venv/bin/gunicorn \
    --worker-class eventlet \
    -w 1 \
    --bind 127.0.0.1:5000 \
    --access-logfile /var/log/lemaison/access.log \
    --error-logfile /var/log/lemaison/error.log \
    --timeout 600 \
    app:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 9.3 Create Log Directory
```bash
sudo mkdir -p /var/log/lemaison
sudo chown www-data:www-data /var/log/lemaison
```

### 9.4 Set Permissions
```bash
sudo chown -R www-data:www-data /var/www/lemaison
sudo chmod -R 755 /var/www/lemaison
```

### 9.5 Start Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable lemaison
sudo systemctl start lemaison
sudo systemctl status lemaison
```

---

## 🔒 Step 10: Setup SSL Certificate (HTTPS)

### 10.1 Install Certbot
```bash
sudo apt install certbot python3-certbot-nginx -y
```

### 10.2 Get SSL Certificate
```bash
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

### 10.3 Auto-renewal
```bash
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

---

## 🌍 Step 11: Configure Domain sa Hostinger

### 11.1 Point Domain to Server
1. Login sa Hostinger hPanel
2. Go to **Domains** → **DNS/Nameservers**
3. Add A Record:
   - Type: `A`
   - Name: `@`
   - Points to: `YOUR_SERVER_IP`
   - TTL: `14400`
4. Add A Record for www:
   - Type: `A`
   - Name: `www`
   - Points to: `YOUR_SERVER_IP`
   - TTL: `14400`

### 11.2 Wait for DNS Propagation (15-30 minutes)

---

## ✅ Step 12: Verify Deployment

### 12.1 Check Service Status
```bash
sudo systemctl status lemaison
sudo systemctl status nginx
```

### 12.2 Check Logs
```bash
# Application logs
sudo tail -f /var/log/lemaison/error.log

# Nginx logs
sudo tail -f /var/log/nginx/error.log
```

### 12.3 Test Website
```bash
curl http://localhost:5000
curl http://your-domain.com
```

---

## 🔧 Maintenance Commands

### Restart Application
```bash
sudo systemctl restart lemaison
```

### Update Code
```bash
cd /var/www/lemaison
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart lemaison
```

### View Logs
```bash
# Real-time logs
sudo journalctl -u lemaison -f

# Application logs
sudo tail -f /var/log/lemaison/error.log
```

### Database Backup
```bash
pg_dump -U lemaison_user lemaison_db > backup_$(date +%Y%m%d).sql
```

---

## 🆘 Troubleshooting

### Problem: Service won't start
```bash
# Check logs
sudo journalctl -u lemaison -n 50

# Check permissions
ls -la /var/www/lemaison

# Test gunicorn manually
cd /var/www/lemaison
source venv/bin/activate
gunicorn --worker-class eventlet -w 1 --bind 127.0.0.1:5000 app:app
```

### Problem: Database connection error
```bash
# Test database connection
psql -U lemaison_user -d lemaison_db -h localhost

# Check PostgreSQL status
sudo systemctl status postgresql
```

### Problem: 502 Bad Gateway
```bash
# Check if app is running
sudo systemctl status lemaison

# Check Nginx configuration
sudo nginx -t

# Restart both services
sudo systemctl restart lemaison
sudo systemctl restart nginx
```

---

## 📞 Support

Kung may problema pa, check ang logs:
```bash
sudo journalctl -u lemaison -n 100
sudo tail -f /var/log/lemaison/error.log
sudo tail -f /var/log/nginx/error.log
```

---

## 🎉 Tapos na!

Ang inyong restaurant management system ay live na sa Hostinger! 🚀

Access it at: **https://your-domain.com**

---

**Created by:** Kiro AI Assistant
**Date:** May 31, 2026
