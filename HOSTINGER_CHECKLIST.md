# ✅ HOSTINGER DEPLOYMENT CHECKLIST

## Pre-Deployment
- [ ] Hostinger account active
- [ ] VPS or Cloud Hosting plan (NOT shared hosting)
- [ ] Domain name ready (optional but recommended)
- [ ] SSH credentials available

---

## Server Setup
- [ ] Connected to server via SSH
- [ ] System updated (`apt update && apt upgrade`)
- [ ] Python 3.12 installed
- [ ] PostgreSQL installed
- [ ] Nginx installed
- [ ] Git installed

---

## Code Upload
- [ ] Code pushed to GitHub (or uploaded via FileZilla)
- [ ] Code cloned/uploaded to `/var/www/lemaison`
- [ ] All files present on server

---

## Database Setup
- [ ] PostgreSQL user created (`lemaison_user`)
- [ ] Database created (`lemaison_db`)
- [ ] Permissions granted
- [ ] Connection string saved

---

## Configuration
- [ ] `.env` file created
- [ ] `DATABASE_URL` configured
- [ ] `SECRET_KEY` generated and set
- [ ] Email settings configured
- [ ] Payment keys configured

---

## Python Environment
- [ ] Virtual environment created (`venv`)
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Gunicorn installed
- [ ] Database tables created (`db.create_all()`)

---

## Web Server
- [ ] Nginx configuration file created
- [ ] Domain name set in Nginx config
- [ ] Nginx configuration enabled
- [ ] Nginx restarted successfully

---

## System Service
- [ ] Systemd service file created
- [ ] File permissions set (`www-data:www-data`)
- [ ] Service enabled
- [ ] Service started
- [ ] Service running (check status)

---

## Domain & DNS
- [ ] A record added for `@` (root domain)
- [ ] A record added for `www`
- [ ] DNS propagated (wait 15-30 minutes)
- [ ] Domain accessible in browser

---

## SSL Certificate
- [ ] Certbot installed
- [ ] SSL certificate obtained
- [ ] HTTPS working
- [ ] Auto-renewal enabled

---

## Testing
- [ ] Website loads at `http://YOUR_DOMAIN.com`
- [ ] HTTPS works (`https://YOUR_DOMAIN.com`)
- [ ] Login page accessible
- [ ] Can create account
- [ ] Database connections working
- [ ] No errors in logs

---

## Post-Deployment
- [ ] Logs checked (`journalctl -u lemaison`)
- [ ] Service auto-starts on reboot
- [ ] Backup plan in place
- [ ] Monitoring setup (optional)

---

## 🎉 DEPLOYMENT COMPLETE!

Your restaurant management system is now live on Hostinger!

**Access URL:** https://YOUR_DOMAIN.com

---

## Quick Reference Commands

```bash
# Check service status
sudo systemctl status lemaison

# View logs
sudo journalctl -u lemaison -f

# Restart service
sudo systemctl restart lemaison

# Restart Nginx
sudo systemctl restart nginx

# Update code
cd /var/www/lemaison
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart lemaison
```

