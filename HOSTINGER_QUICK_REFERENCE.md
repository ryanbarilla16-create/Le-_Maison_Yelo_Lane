# 📋 HOSTINGER QUICK REFERENCE CARD

## Keep this open while deploying! 👀

---

## 🔑 YOUR CREDENTIALS (Fill this in!)

```
Server IP: _______________________
SSH Username: _____________________
SSH Password: _____________________
Domain Name: ______________________

Database Name: lemaison_db
Database User: lemaison_user
Database Password: ________________
```

---

## 🚀 ESSENTIAL COMMANDS

### Connect to Server:
```bash
ssh root@YOUR_SERVER_IP
```

### Check Service Status:
```bash
sudo systemctl status lemaison
sudo systemctl status nginx
sudo systemctl status postgresql
```

### Restart Services:
```bash
sudo systemctl restart lemaison
sudo systemctl restart nginx
```

### View Logs:
```bash
# Live logs
sudo journalctl -u lemaison -f

# Last 50 lines
sudo journalctl -u lemaison -n 50
```

### Update Code:
```bash
cd /var/www/lemaison
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart lemaison
```

---

## 📁 IMPORTANT PATHS

```
Code Location:
/var/www/lemaison

Virtual Environment:
/var/www/lemaison/venv

Configuration File:
/var/www/lemaison/.env

Nginx Config:
/etc/nginx/sites-available/lemaison

Service File:
/etc/systemd/system/lemaison.service

Logs:
/var/log/nginx/error.log
sudo journalctl -u lemaison
```

---

## 🗄️ DATABASE COMMANDS

### Connect to Database:
```bash
psql -U lemaison_user -d lemaison_db -h localhost
```

### List Databases:
```bash
sudo -u postgres psql -l
```

### Backup Database:
```bash
pg_dump -U lemaison_user lemaison_db > backup.sql
```

### Restore Database:
```bash
psql -U lemaison_user -d lemaison_db < backup.sql
```

---

## 🌐 NGINX COMMANDS

### Test Configuration:
```bash
sudo nginx -t
```

### Reload Configuration:
```bash
sudo systemctl reload nginx
```

### View Error Logs:
```bash
sudo tail -f /var/log/nginx/error.log
```

---

## 🔒 SSL COMMANDS

### Get Certificate:
```bash
sudo certbot --nginx -d YOUR_DOMAIN.com -d www.YOUR_DOMAIN.com
```

### Renew Certificate:
```bash
sudo certbot renew
```

### Check Certificates:
```bash
sudo certbot certificates
```

---

## 🐍 PYTHON COMMANDS

### Activate Virtual Environment:
```bash
cd /var/www/lemaison
source venv/bin/activate
```

### Install Dependencies:
```bash
pip install -r requirements.txt
```

### Initialize Database:
```bash
python3 -c "from app import app, db; app.app_context().push(); db.create_all()"
```

---

## 🔧 TROUBLESHOOTING QUICK FIXES

### Service Won't Start:
```bash
sudo journalctl -u lemaison -n 100
sudo chown -R www-data:www-data /var/www/lemaison
sudo systemctl restart lemaison
```

### 502 Bad Gateway:
```bash
sudo systemctl restart lemaison
sudo systemctl restart nginx
```

### Database Connection Error:
```bash
sudo systemctl restart postgresql
psql -U lemaison_user -d lemaison_db -h localhost
```

### Permission Denied:
```bash
sudo chown -R www-data:www-data /var/www/lemaison
sudo chmod -R 755 /var/www/lemaison
```

---

## 📊 MONITORING COMMANDS

### Check Disk Space:
```bash
df -h
```

### Check Memory:
```bash
free -h
```

### Check CPU:
```bash
top
# Press 'q' to quit
```

### Check Running Processes:
```bash
ps aux | grep gunicorn
```

### Check Open Ports:
```bash
sudo netstat -tulpn | grep -E ':(80|443|5000)'
```

---

## 🔄 DEPLOYMENT WORKFLOW

```
1. Make changes on local computer
2. Test locally
3. Commit to Git:
   git add .
   git commit -m "Description"
   git push origin main

4. SSH to server:
   ssh root@YOUR_SERVER_IP

5. Update code:
   cd /var/www/lemaison
   git pull origin main
   source venv/bin/activate
   pip install -r requirements.txt

6. Restart service:
   sudo systemctl restart lemaison

7. Check logs:
   sudo journalctl -u lemaison -n 20

8. Test website:
   Visit: https://YOUR_DOMAIN.com
```

---

## 🆘 EMERGENCY COMMANDS

### Restart Everything:
```bash
sudo systemctl restart postgresql
sudo systemctl restart lemaison
sudo systemctl restart nginx
```

### Check All Services:
```bash
sudo systemctl status postgresql
sudo systemctl status lemaison
sudo systemctl status nginx
```

### Get All Logs:
```bash
sudo journalctl -u lemaison -n 200 > ~/logs.txt
sudo tail -n 100 /var/log/nginx/error.log >> ~/logs.txt
cat ~/logs.txt
```

---

## 📞 SUPPORT CONTACTS

### Hostinger Support:
- Website: https://hostinger.com/support
- Live Chat: Available in hPanel
- Email: support@hostinger.com

### Documentation:
- Hostinger Docs: https://support.hostinger.com
- Flask Docs: https://flask.palletsprojects.com
- PostgreSQL Docs: https://postgresql.org/docs
- Nginx Docs: https://nginx.org/en/docs

---

## ✅ DEPLOYMENT CHECKLIST

```
□ Server connected via SSH
□ Software installed (Python, PostgreSQL, Nginx)
□ Code uploaded to /var/www/lemaison
□ Database created
□ .env file configured
□ Virtual environment created
□ Dependencies installed
□ Database tables created
□ Nginx configured
□ Service file created
□ Service started and enabled
□ Domain DNS configured
□ SSL certificate installed
□ Website accessible
□ HTTPS working
```

---

## 🎯 COMMON ISSUES & SOLUTIONS

| Problem | Solution |
|---------|----------|
| Can't connect SSH | Check IP, username, password |
| Service won't start | Check logs: `journalctl -u lemaison -n 50` |
| 502 Bad Gateway | Restart: `systemctl restart lemaison nginx` |
| Database error | Check .env DATABASE_URL |
| Domain not working | Wait for DNS (15-30 min) |
| SSL error | Run: `certbot --nginx -d domain.com` |
| Permission denied | Run: `chown -R www-data:www-data /var/www/lemaison` |

---

## 💡 PRO TIPS

1. **Always check logs first:**
   ```bash
   sudo journalctl -u lemaison -f
   ```

2. **Test Nginx config before restart:**
   ```bash
   sudo nginx -t
   ```

3. **Backup before major changes:**
   ```bash
   pg_dump -U lemaison_user lemaison_db > backup_$(date +%Y%m%d).sql
   ```

4. **Keep .env file secure:**
   ```bash
   chmod 600 /var/www/lemaison/.env
   ```

5. **Monitor disk space:**
   ```bash
   df -h
   ```

---

## 🔗 USEFUL LINKS

- **Your Website:** https://YOUR_DOMAIN.com
- **Hostinger hPanel:** https://hpanel.hostinger.com
- **GitHub Repo:** https://github.com/YOUR_USERNAME/your-repo
- **SSL Check:** https://ssllabs.com/ssltest/

---

## 📝 NOTES SECTION

Use this space to write down important info:

```
Server IP: ___________________________

Database Password: ____________________

Domain: _______________________________

SSL Installed: ________________________

Last Updated: _________________________

Issues Encountered:
_______________________________________
_______________________________________
_______________________________________

Solutions Applied:
_______________________________________
_______________________________________
_______________________________________
```

---

## 🎉 SUCCESS INDICATORS

Your deployment is successful when:

✅ `sudo systemctl status lemaison` shows "active (running)"
✅ `sudo systemctl status nginx` shows "active (running)"
✅ Website loads at http://YOUR_DOMAIN.com
✅ HTTPS works at https://YOUR_DOMAIN.com
✅ Can login to admin panel
✅ Database connections work
✅ No errors in logs

---

**Print this page and keep it handy!** 📄

**Good luck with your deployment!** 🚀

