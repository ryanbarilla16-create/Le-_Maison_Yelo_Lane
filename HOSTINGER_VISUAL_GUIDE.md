# 🎨 HOSTINGER VISUAL DEPLOYMENT GUIDE

## Para sa mga Visual Learners! 👀

---

## 📍 CURRENT STATUS: Where are you now?

```
┌─────────────────────────────────────────────────────────┐
│  YOUR COMPUTER (Local)                                  │
│  ├── 📁 Restaurant System Code                          │
│  ├── 📁 Database (SQLite - Development)                 │
│  └── 🌐 Running on localhost:5000                       │
└─────────────────────────────────────────────────────────┘
                         ⬇️
                    GOAL: Move to
                         ⬇️
┌─────────────────────────────────────────────────────────┐
│  HOSTINGER SERVER (Production)                          │
│  ├── 📁 Restaurant System Code                          │
│  ├── 🗄️ Database (PostgreSQL - Production)             │
│  └── 🌐 Running on YOUR_DOMAIN.com                      │
└─────────────────────────────────────────────────────────┘
```

---

## 🗺️ DEPLOYMENT ROADMAP

```
START HERE
    ↓
[1] 🔐 Connect to Hostinger Server
    ↓
[2] 🛠️ Install Software (Python, PostgreSQL, Nginx)
    ↓
[3] 📤 Upload Your Code
    ↓
[4] 🗄️ Setup Database
    ↓
[5] ⚙️ Configure Settings (.env file)
    ↓
[6] 🐍 Install Python Packages
    ↓
[7] 🌐 Setup Web Server (Nginx)
    ↓
[8] 🔄 Setup Auto-Start Service
    ↓
[9] 🌍 Point Domain to Server
    ↓
[10] 🔒 Add SSL Certificate (HTTPS)
    ↓
✅ DONE! Website is LIVE!
```

---

## 📋 STEP-BY-STEP WITH VISUALS

### 🔐 STEP 1: Connect to Server

```
┌──────────────────┐         SSH Connection         ┌──────────────────┐
│  YOUR COMPUTER   │ ─────────────────────────────> │ HOSTINGER SERVER │
│   (Windows)      │  ssh root@123.45.67.89         │   (Linux)        │
└──────────────────┘                                 └──────────────────┘
```

**What to do:**
1. Open PowerShell or CMD
2. Type: `ssh root@YOUR_SERVER_IP`
3. Enter password
4. You're in! 🎉

**You'll see:**
```
root@server:~#
```

---

### 🛠️ STEP 2: Install Software

```
┌─────────────────────────────────────────┐
│  HOSTINGER SERVER (Empty)               │
│                                         │
│  ❌ No Python                           │
│  ❌ No PostgreSQL                       │
│  ❌ No Nginx                            │
└─────────────────────────────────────────┘
            ⬇️ Install
┌─────────────────────────────────────────┐
│  HOSTINGER SERVER (Ready)               │
│                                         │
│  ✅ Python 3.12                         │
│  ✅ PostgreSQL                          │
│  ✅ Nginx                               │
└─────────────────────────────────────────┘
```

**Commands to run:**
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3.12 python3.12-venv python3-pip -y
sudo apt install postgresql postgresql-contrib libpq-dev -y
sudo apt install nginx -y
sudo apt install git -y
```

**Progress bar:**
```
Installing... [████████████████████] 100%
```

---

### 📤 STEP 3: Upload Code

```
┌──────────────────┐                      ┌──────────────────┐
│  YOUR COMPUTER   │                      │ HOSTINGER SERVER │
│                  │                      │                  │
│  📁 app.py       │ ──────────────────>  │  📁 app.py       │
│  📁 models.py    │      Git Clone       │  📁 models.py    │
│  📁 routes/      │         or           │  📁 routes/      │
│  📁 templates/   │     FileZilla        │  📁 templates/   │
│  📁 static/      │                      │  📁 static/      │
└──────────────────┘                      └──────────────────┘
```

**Option A: Git (Recommended)**
```bash
# On YOUR COMPUTER first:
git init
git add .
git commit -m "Deploy to Hostinger"
git push origin main

# Then on SERVER:
cd /var/www
sudo mkdir lemaison
cd lemaison
git clone https://github.com/YOUR_USERNAME/your-repo.git .
```

**Option B: FileZilla**
1. Download FileZilla
2. Connect: `sftp://YOUR_SERVER_IP`
3. Drag and drop files to `/var/www/lemaison`

---

### 🗄️ STEP 4: Setup Database

```
BEFORE:
┌─────────────────────────────────┐
│  PostgreSQL (Empty)             │
│                                 │
│  No databases                   │
│  No users                       │
└─────────────────────────────────┘

AFTER:
┌─────────────────────────────────┐
│  PostgreSQL                     │
│                                 │
│  ✅ Database: lemaison_db       │
│  ✅ User: lemaison_user         │
│  ✅ Password: ********          │
└─────────────────────────────────┘
```

**Commands:**
```bash
sudo -u postgres psql

CREATE USER lemaison_user WITH PASSWORD 'YourPassword123!';
CREATE DATABASE lemaison_db OWNER lemaison_user;
GRANT ALL PRIVILEGES ON DATABASE lemaison_db TO lemaison_user;
\q
```

**Save this connection string:**
```
postgresql://lemaison_user:YourPassword123!@localhost:5432/lemaison_db
```

---

### ⚙️ STEP 5: Configure .env File

```
┌─────────────────────────────────────────┐
│  .env File (Configuration)              │
│                                         │
│  DATABASE_URL=postgresql://...          │
│  SECRET_KEY=random_secret_key           │
│  MAIL_USERNAME=your@email.com           │
│  MAIL_PASSWORD=your_password            │
│  XENDIT_SECRET_KEY=xnd_...              │
└─────────────────────────────────────────┘
```

**Create file:**
```bash
cd /var/www/lemaison
nano .env
```

**Paste configuration** (see HOSTINGER_QUICK_DEPLOY.md for full .env)

**Save:** `Ctrl+X`, `Y`, `Enter`

---

### 🐍 STEP 6: Install Python Packages

```
┌─────────────────────────────────────────┐
│  Virtual Environment                    │
│                                         │
│  📦 Flask                               │
│  📦 SQLAlchemy                          │
│  📦 Gunicorn                            │
│  📦 ... (all dependencies)              │
└─────────────────────────────────────────┘
```

**Commands:**
```bash
cd /var/www/lemaison
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

**Initialize database:**
```bash
python3 -c "from app import app, db; app.app_context().push(); db.create_all(); print('✅ Database ready!')"
```

---

### 🌐 STEP 7: Setup Nginx (Web Server)

```
INTERNET
    ↓
┌─────────────────┐
│  NGINX          │  Port 80/443 (HTTP/HTTPS)
│  (Web Server)   │
└─────────────────┘
    ↓
┌─────────────────┐
│  GUNICORN       │  Port 5000
│  (App Server)   │
└─────────────────┘
    ↓
┌─────────────────┐
│  FLASK APP      │
│  (Your Code)    │
└─────────────────┘
```

**Create Nginx config:**
```bash
sudo nano /etc/nginx/sites-available/lemaison
```

**Paste config** (see HOSTINGER_QUICK_DEPLOY.md)

**Enable:**
```bash
sudo ln -s /etc/nginx/sites-available/lemaison /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

### 🔄 STEP 8: Setup Auto-Start

```
SERVER BOOTS UP
    ↓
┌─────────────────────────────────────────┐
│  Systemd Service                        │
│  (Automatically starts your app)        │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  Your Restaurant System                 │
│  ✅ Running on port 5000                │
└─────────────────────────────────────────┘
```

**Create service:**
```bash
sudo nano /etc/systemd/system/lemaison.service
```

**Paste config** (see HOSTINGER_QUICK_DEPLOY.md)

**Start service:**
```bash
sudo chown -R www-data:www-data /var/www/lemaison
sudo systemctl daemon-reload
sudo systemctl enable lemaison
sudo systemctl start lemaison
sudo systemctl status lemaison
```

**You should see:**
```
● lemaison.service - Le Maison Restaurant System
   Active: active (running) ✅
```

---

### 🌍 STEP 9: Point Domain

```
BEFORE:
YOUR_DOMAIN.com ──❌──> Nowhere

AFTER:
YOUR_DOMAIN.com ──✅──> YOUR_SERVER_IP ──> Your Website
```

**In Hostinger hPanel:**
1. Go to **Domains**
2. Click your domain
3. Go to **DNS/Nameservers**
4. Add A Records:

```
┌──────────┬─────────┬──────────────────┐
│   Type   │  Name   │   Points To      │
├──────────┼─────────┼──────────────────┤
│    A     │    @    │  YOUR_SERVER_IP  │
│    A     │   www   │  YOUR_SERVER_IP  │
└──────────┴─────────┴──────────────────┘
```

**Wait 15-30 minutes for DNS propagation**

---

### 🔒 STEP 10: Add SSL (HTTPS)

```
BEFORE:
http://YOUR_DOMAIN.com ⚠️ Not Secure

AFTER:
https://YOUR_DOMAIN.com 🔒 Secure
```

**Install SSL:**
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d YOUR_DOMAIN.com -d www.YOUR_DOMAIN.com
```

**Follow prompts:**
```
Enter email: your@email.com
Agree to terms: Y
Redirect HTTP to HTTPS: 2 (Yes)
```

**Done!** 🎉

---

## ✅ VERIFICATION CHECKLIST

```
┌─────────────────────────────────────────┐
│  ✅ Service running                     │
│     sudo systemctl status lemaison      │
│                                         │
│  ✅ Nginx running                       │
│     sudo systemctl status nginx         │
│                                         │
│  ✅ Database connected                  │
│     psql -U lemaison_user -d lemaison_db│
│                                         │
│  ✅ Domain working                      │
│     Visit: http://YOUR_DOMAIN.com       │
│                                         │
│  ✅ HTTPS working                       │
│     Visit: https://YOUR_DOMAIN.com      │
└─────────────────────────────────────────┘
```

---

## 🎉 SUCCESS! Your Website is LIVE!

```
        🎊 CONGRATULATIONS! 🎊
        
┌─────────────────────────────────────────┐
│                                         │
│   Your Restaurant Management System     │
│   is now LIVE on Hostinger!             │
│                                         │
│   🌐 https://YOUR_DOMAIN.com            │
│                                         │
│   ✅ Fast                               │
│   ✅ Secure (HTTPS)                     │
│   ✅ Professional                       │
│   ✅ Always Online                      │
│                                         │
└─────────────────────────────────────────┘
```

---

## 🔧 MAINTENANCE COMMANDS

### Check if everything is running:
```bash
sudo systemctl status lemaison
sudo systemctl status nginx
sudo systemctl status postgresql
```

### View logs:
```bash
sudo journalctl -u lemaison -f
```

### Restart app:
```bash
sudo systemctl restart lemaison
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

## 🆘 NEED HELP?

**Check these files:**
- 📄 `HOSTINGER_QUICK_DEPLOY.md` - Quick deployment guide
- 📄 `HOSTINGER_DEPLOYMENT_GUIDE.md` - Detailed guide
- 📄 `HOSTINGER_CHECKLIST.md` - Step-by-step checklist
- 📄 `HOSTINGER_TROUBLESHOOTING.md` - Fix common problems

**Still stuck?**
```bash
# Get logs:
sudo journalctl -u lemaison -n 100

# Check status:
sudo systemctl status lemaison
```

---

**Good luck with your deployment! 🚀**

