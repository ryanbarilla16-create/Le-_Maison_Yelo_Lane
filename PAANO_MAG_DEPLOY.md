# 🚀 PAANO MAG-DEPLOY SA HOSTINGER (AUTOMATIC!)

## Super Simple - 3 Steps Lang! 🎉

---

## 📥 STEP 1: I-DOWNLOAD ANG SCRIPT

### Option A: Kung naka-connect ka na sa server via SSH

```bash
# Connect to your Hostinger server
ssh root@YOUR_SERVER_IP

# Download the script
cd ~
curl -O https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/deploy_to_hostinger.sh

# Or kung nandito na ang code mo:
cd /path/to/your/code
cp deploy_to_hostinger.sh ~
```

### Option B: Kung wala pang code sa server

1. **I-download ang file na ito sa computer mo:**
   - `deploy_to_hostinger.sh`

2. **I-upload sa Hostinger gamit ang FileZilla:**
   - Host: `sftp://YOUR_SERVER_IP`
   - Username: `root` (or your SSH username)
   - Password: Your SSH password
   - Port: `22`
   - Upload ang file sa `/root/` folder

---

## ⚙️ STEP 2: I-RUN ANG SCRIPT

### Connect sa server:
```bash
ssh root@YOUR_SERVER_IP
```

### Run the automatic deployment script:
```bash
cd ~
chmod +x deploy_to_hostinger.sh
sudo bash deploy_to_hostinger.sh
```

### Sasagutin mo lang ang mga tanong:
```
Enter your domain name: lemaison.com
Enter your email for SSL: your@email.com
Enter database password: YourStrongPassword123!
Enter GitHub repo URL: https://github.com/username/repo.git
```

**Tapos na!** Automatic na ang lahat! ⏱️ 10-15 minutes

---

## ✅ STEP 3: I-POINT ANG DOMAIN

### Sa Hostinger hPanel:

1. Login sa https://hostinger.com
2. Go to **Domains**
3. Click your domain
4. Go to **DNS/Nameservers**
5. Add these records:

**A Record 1:**
- Type: `A`
- Name: `@`
- Points to: `YOUR_SERVER_IP`

**A Record 2:**
- Type: `A`
- Name: `www`
- Points to: `YOUR_SERVER_IP`

6. **Wait 15-30 minutes** for DNS propagation

---

## 🎉 TAPOS NA!

Visit your website:
- **http://YOUR_DOMAIN.com**
- **https://YOUR_DOMAIN.com** (with SSL!)

---

## 📋 ANO ANG GINAGAWA NG SCRIPT?

Automatic na ginagawa nito:

1. ✅ Update system
2. ✅ Install Python 3.12
3. ✅ Install PostgreSQL
4. ✅ Install Nginx
5. ✅ Create database
6. ✅ Clone your code (kung may GitHub)
7. ✅ Generate secret key
8. ✅ Create .env file
9. ✅ Install Python packages
10. ✅ Initialize database tables
11. ✅ Configure Nginx
12. ✅ Setup auto-start service
13. ✅ Install SSL certificate
14. ✅ Start everything!

**Hindi mo na kailangan mag-type ng maraming commands!** 🎊

---

## 🔧 KUNG WALANG GITHUB REPO

Kung hindi mo pa na-push ang code sa GitHub:

### Option 1: Push to GitHub first (Recommended)

```bash
# Sa local computer mo:
cd /path/to/your/project
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/lemaison-restaurant.git
git push -u origin main
```

Then run the deployment script with your GitHub URL.

### Option 2: Upload manually

1. Run the script WITHOUT GitHub URL (just press Enter)
2. Script will pause and wait
3. Upload your code to `/var/www/lemaison` using FileZilla
4. Press Enter to continue

---

## 🆘 KUNG MAY PROBLEMA

### Script failed?

```bash
# Check what went wrong:
sudo journalctl -u lemaison -n 50

# Try restarting:
sudo systemctl restart lemaison
sudo systemctl restart nginx
```

### Service won't start?

```bash
# Check logs:
sudo journalctl -u lemaison -f

# Check permissions:
sudo chown -R www-data:www-data /var/www/lemaison
sudo systemctl restart lemaison
```

### Database error?

```bash
# Test connection:
psql -U lemaison_user -d lemaison_db -h localhost
# Enter the password you provided
```

---

## 📝 IMPORTANT FILES CREATED

After deployment, these files are created:

1. **Code:** `/var/www/lemaison/`
2. **Config:** `/var/www/lemaison/.env`
3. **Nginx:** `/etc/nginx/sites-available/lemaison`
4. **Service:** `/etc/systemd/system/lemaison.service`
5. **Credentials:** `/root/lemaison_credentials.txt` ⚠️ KEEP SAFE!

---

## 🔄 PAANO MAG-UPDATE NG CODE

### Kung naka-GitHub:

```bash
ssh root@YOUR_SERVER_IP
cd /var/www/lemaison
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart lemaison
```

### Kung manual upload:

1. Upload new files via FileZilla to `/var/www/lemaison`
2. Restart service:
```bash
sudo systemctl restart lemaison
```

---

## 📊 USEFUL COMMANDS

```bash
# Check if running
sudo systemctl status lemaison

# View live logs
sudo journalctl -u lemaison -f

# Restart app
sudo systemctl restart lemaison

# Restart Nginx
sudo systemctl restart nginx

# Check database
psql -U lemaison_user -d lemaison_db -h localhost
```

---

## 💰 WHAT YOU NEED

Before running the script:

- ✅ Hostinger VPS or Cloud Hosting (NOT shared hosting)
- ✅ Server IP address
- ✅ SSH access (root or sudo user)
- ✅ Domain name (optional but recommended)
- ✅ Your code (on GitHub or ready to upload)

---

## ⏱️ TIME ESTIMATE

- **Script runtime:** 10-15 minutes
- **DNS propagation:** 15-30 minutes
- **Total:** 30-45 minutes

**Much faster than manual deployment!** 🚀

---

## 🎯 SUMMARY

```
1. Download: deploy_to_hostinger.sh
2. Upload to server (if needed)
3. Run: sudo bash deploy_to_hostinger.sh
4. Answer questions
5. Wait 10-15 minutes
6. Point domain DNS
7. Done! 🎉
```

---

## 🎊 ADVANTAGES OF THIS SCRIPT

✅ **Automatic** - No need to type many commands
✅ **Fast** - 10-15 minutes only
✅ **Safe** - Checks for errors
✅ **Complete** - Does everything for you
✅ **Easy** - Just answer a few questions

---

## 📞 NEED HELP?

If the script fails or you have problems:

1. Check the logs: `sudo journalctl -u lemaison -n 100`
2. Read: `HOSTINGER_TROUBLESHOOTING.md`
3. Contact Hostinger support
4. Ask for help with the error message

---

## 🎉 READY?

**Download the script and run it!**

```bash
sudo bash deploy_to_hostinger.sh
```

**Good luck!** 🚀

---

**Created by:** Kiro AI Assistant
**For:** Le Maison Restaurant Management System
**Date:** May 31, 2026

