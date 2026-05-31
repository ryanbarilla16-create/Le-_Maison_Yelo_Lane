# 🚀 HOSTINGER QUICK DEPLOY - Le Maison Restaurant System

## Mabilis na Gabay para sa Deployment

---

## ✅ STEP 1: Check Your Hostinger Plan

Pumunta sa https://hostinger.com at login. Check kung ano ang hosting plan mo:

### Option A: VPS Hosting (Recommended)
- ✅ Full control
- ✅ Can install Python, PostgreSQL
- ✅ SSH access
- **Follow FULL GUIDE below**

### Option B: Shared Hosting
- ❌ Limited Python support
- ❌ Cannot install PostgreSQL
- **NOT RECOMMENDED for this system**
- **Upgrade to VPS or use Render.com instead**

### Option C: Cloud Hosting
- ✅ Similar to VPS
- ✅ Can install Python, PostgreSQL
- **Follow FULL GUIDE below**

---

## 🎯 STEP 2: Get Your Server Details

1. Login sa Hostinger hPanel
2. Go to **VPS** or **Cloud Hosting**
3. Click on your server
4. Get these details:
   - **Server IP Address**: `_______________`
   - **SSH Username**: `_______________`
   - **SSH Password**: `_______________`
   - **SSH Port**: Usually `22`

---

## 💻 STEP 3: Connect to Your Server

### Windows (Using PowerShell or CMD):
```bash
ssh root@YOUR_SERVER_IP
# Enter password when prompted
```

### Or use PuTTY:
1. Download PuTTY from https://putty.org
2. Enter your server IP
3. Click "Open"
4. Login with username and password

---

## 🔧 STEP 4: Install Required Software

Copy-paste these commands one by one:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.12
sudo apt install python3.12 python3.12-venv python3-pip -y

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib libpq-dev -y

# Install Nginx
sudo apt install nginx -y

# Install Git
sudo apt install git -y
```

---

## 📦 STEP 5: Upload Your Code

### Option A: Using Git (Easiest)

First, push your code to GitHub:

```bash
# On your LOCAL computer (not server), sa folder ng project:
git init
git add .
git commit -m "Initial commit for Hostinger"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/lemaison-restaurant.git
git push -u origin main
```

Then on your SERVER:

```bash
# Create directory
cd /var/www
sudo mkdir lemaison
sudo chown $USER:$USER lemaison
cd lemaison

# Clone your code
git clone https://github.com/YOUR_USERNAME/lemaison-restaurant.git .
```

### Option B: Using FileZilla (If no Git)

1. Download FileZilla: https://filezilla-project.org
2. Connect using SFTP:
   - Host: `sftp://YOUR_SERVER_IP`
   - Username: Your SSH username
   - Password: Your SSH password
   - Port: `22`
3. Upload all files to `/var/www/lemaison`

---

## 🗄️ STEP 6: Setup Database

```bash
# Login to PostgreSQL
sudo -u postgres psql

# Create database and user (copy-paste all 4 lines)
CREATE USER lemaison_user WITH PASSWORD 'YourStrongPassword123!';
CREATE DATABASE lemaison_db OWNER lemaison_user;
GRANT ALL PRIVILEGES ON DATABASE lemaison_db TO lemaison_user;
\q
```

**IMPORTANTE:** Save this connection string:
```
postgresql://lemaison_user:YourStrongPassword123!@localhost:5432/lemaison_db
```

---

## ⚙️ STEP 7: Configure Environment Variables

```bash
cd /var/www/lemaison
nano .env
```

Paste this (I-EDIT ang values):

```env
# Database
DATABASE_URL=postgresql://lemaison_user:YourStrongPassword123!@localhost:5432/lemaison_db

# Flask
SECRET_KEY=GENERATE_NEW_SECRET_KEY_HERE_VERY_LONG_AND_RANDOM
FLASK_ENV=production
FLASK_RUN_HOST=0.0.0.0

# Email (OTP)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=ryanbarilla254@gmail.com
MAIL_PASSWORD=smqnvgtyfgwzipqr

# Supabase (Optional)
SUPABASE_URL=https://rnmeiclskivuyzvyxmpp.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJubWVpY2xza2l2dXl6dnl4bXBwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIyOTUyNTUsImV4cCI6MjA4Nzg3MTI1NX0.zCHJRQgsXWyTpONeqKIPyu0sfGyAFyGdXW2gb-W6x_Q

# Xendit Payment
XENDIT_PUBLIC_KEY=xnd_public_development_Zp6Dnri0CUwWCfZyUJ7sA3eY2WY51AT_VFPpHB80wF3phCuFsxBWo3dvfNPiK0k
XENDIT_SECRET_KEY=xnd_development_0nBIOfz73fnTN4clGigTE3KeW3bNNpCsC1NG48WEf5Csbzo2tn4pLw5SeGs69

# Social Login
FACEBOOK_APP_ID=2031079187624124
FACEBOOK_APP_SECRET=0c42c26fc51c640497fb3ecc5ffbdaf0
GOOGLE_CLIENT_ID=77851915575-o74qqe52iomde0m4u82fcara28l0n00e.apps.googleusercontent.com
```

**Generate SECRET_KEY:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Save file: `Ctrl+X`, then `Y`, then `Enter`

---

## 🐍 STEP 8: Install Python Dependencies

```bash
cd /var/www/lemaison

# Create virtual environment
python3.12 -m venv venv

# Activate it
source venv/bin/activate

# Install packages
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

---

## 🗃️ STEP 9: Initialize Database

```bash
# Make sure venv is activated
source venv/bin/activate

# Create tables
python3 -c "from app import app, db; app.app_context().push(); db.create_all(); print('Database initialized!')"
```

---

## 🌐 STEP 10: Configure Nginx

```bash
sudo nano /etc/nginx/sites-available/lemaison
```

Paste this (I-EDIT ang domain mo):

```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN.com www.YOUR_DOMAIN.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /static {
        alias /var/www/lemaison/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/lemaison /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 🔄 STEP 11: Setup Auto-Start Service

```bash
sudo nano /etc/systemd/system/lemaison.service
```

Paste this:

```ini
[Unit]
Description=Le Maison Restaurant System
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
    --timeout 600 \
    app:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Set permissions and start:
```bash
sudo chown -R www-data:www-data /var/www/lemaison
sudo chmod -R 755 /var/www/lemaison

sudo systemctl daemon-reload
sudo systemctl enable lemaison
sudo systemctl start lemaison
sudo systemctl status lemaison
```

---

## 🌍 STEP 12: Point Domain to Server

1. Login sa Hostinger hPanel
2. Go to **Domains** → Select your domain
3. Click **DNS/Nameservers**
4. Add these records:

**A Record 1:**
- Type: `A`
- Name: `@`
- Points to: `YOUR_SERVER_IP`
- TTL: `14400`

**A Record 2:**
- Type: `A`
- Name: `www`
- Points to: `YOUR_SERVER_IP`
- TTL: `14400`

5. Wait 15-30 minutes for DNS propagation

---

## 🔒 STEP 13: Add SSL Certificate (HTTPS)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get certificate
sudo certbot --nginx -d YOUR_DOMAIN.com -d www.YOUR_DOMAIN.com

# Follow prompts, enter your email
```

---

## ✅ STEP 14: Test Your Website

```bash
# Check if service is running
sudo systemctl status lemaison

# Check logs
sudo journalctl -u lemaison -n 50

# Test locally
curl http://localhost:5000

# Test from browser
# Visit: http://YOUR_DOMAIN.com
```

---

## 🎉 TAPOS NA!

Your restaurant system is now live at:
- **http://YOUR_DOMAIN.com** (or https:// if SSL is setup)

---

## 🔧 Common Commands

### Restart app:
```bash
sudo systemctl restart lemaison
```

### View logs:
```bash
sudo journalctl -u lemaison -f
```

### Update code:
```bash
cd /var/www/lemaison
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart lemaison
```

---

## 🆘 Troubleshooting

### Service won't start:
```bash
sudo journalctl -u lemaison -n 100
```

### Database error:
```bash
psql -U lemaison_user -d lemaison_db -h localhost
```

### 502 Bad Gateway:
```bash
sudo systemctl restart lemaison
sudo systemctl restart nginx
```

---

**Need help?** Check the full guide: `HOSTINGER_DEPLOYMENT_GUIDE.md`

