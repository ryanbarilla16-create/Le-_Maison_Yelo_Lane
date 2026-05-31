#!/bin/bash

# ============================================
# Le Maison Restaurant System
# Hostinger Automatic Deployment Script
# ============================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Banner
echo ""
echo "============================================"
echo "  Le Maison Restaurant System"
echo "  Hostinger Automatic Deployment"
echo "============================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root (use: sudo bash deploy_to_hostinger.sh)"
    exit 1
fi

# Get user input
print_status "Please provide the following information:"
echo ""

read -p "Enter your domain name (e.g., lemaison.com): " DOMAIN_NAME
read -p "Enter your email for SSL certificate: " SSL_EMAIL
read -p "Enter database password (strong password): " DB_PASSWORD
read -p "Enter your GitHub repository URL (or press Enter to skip): " GIT_REPO

echo ""
print_status "Starting deployment..."
sleep 2

# ============================================
# STEP 1: Update System
# ============================================
print_status "Step 1/10: Updating system packages..."
apt update && apt upgrade -y
print_success "System updated!"

# ============================================
# STEP 2: Install Required Software
# ============================================
print_status "Step 2/10: Installing required software..."
apt install -y python3.12 python3.12-venv python3-pip
apt install -y postgresql postgresql-contrib libpq-dev
apt install -y nginx
apt install -y git
apt install -y certbot python3-certbot-nginx
print_success "All software installed!"

# ============================================
# STEP 3: Setup PostgreSQL Database
# ============================================
print_status "Step 3/10: Setting up PostgreSQL database..."
sudo -u postgres psql <<EOF
DROP DATABASE IF EXISTS lemaison_db;
DROP USER IF EXISTS lemaison_user;
CREATE USER lemaison_user WITH PASSWORD '$DB_PASSWORD';
CREATE DATABASE lemaison_db OWNER lemaison_user;
GRANT ALL PRIVILEGES ON DATABASE lemaison_db TO lemaison_user;
EOF
print_success "Database created!"

# ============================================
# STEP 4: Create Project Directory
# ============================================
print_status "Step 4/10: Creating project directory..."
mkdir -p /var/www/lemaison
cd /var/www/lemaison
print_success "Directory created!"

# ============================================
# STEP 5: Clone/Upload Code
# ============================================
print_status "Step 5/10: Getting application code..."
if [ -n "$GIT_REPO" ]; then
    print_status "Cloning from GitHub..."
    git clone "$GIT_REPO" .
    print_success "Code cloned from GitHub!"
else
    print_warning "No GitHub repo provided. Please upload your code manually to /var/www/lemaison"
    print_warning "You can use FileZilla or SCP to upload files."
    read -p "Press Enter after you've uploaded the code..."
fi

# ============================================
# STEP 6: Generate Secret Key
# ============================================
print_status "Step 6/10: Generating secret key..."
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
print_success "Secret key generated!"

# ============================================
# STEP 7: Create .env File
# ============================================
print_status "Step 7/10: Creating .env configuration file..."
cat > /var/www/lemaison/.env <<EOF
# ======== DATABASE SETTINGS ========
DATABASE_URL=postgresql://lemaison_user:$DB_PASSWORD@localhost:5432/lemaison_db

# ======== FLASK APP SETTINGS ========
SECRET_KEY=$SECRET_KEY
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
EOF
chmod 600 /var/www/lemaison/.env
print_success ".env file created!"

# ============================================
# STEP 8: Setup Python Virtual Environment
# ============================================
print_status "Step 8/10: Setting up Python virtual environment..."
cd /var/www/lemaison
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
print_success "Python environment ready!"

# ============================================
# STEP 9: Initialize Database
# ============================================
print_status "Step 9/10: Initializing database tables..."
python3 -c "from app import app, db; app.app_context().push(); db.create_all(); print('Database initialized!')"
print_success "Database tables created!"

# ============================================
# STEP 10: Configure Nginx
# ============================================
print_status "Step 10/10: Configuring Nginx web server..."
cat > /etc/nginx/sites-available/lemaison <<EOF
server {
    listen 80;
    server_name $DOMAIN_NAME www.$DOMAIN_NAME;

    # Increase timeouts
    proxy_connect_timeout 600;
    proxy_send_timeout 600;
    proxy_read_timeout 600;
    send_timeout 600;

    # Increase buffer sizes
    client_max_body_size 50M;
    client_body_buffer_size 128k;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
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
EOF

ln -sf /etc/nginx/sites-available/lemaison /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
print_success "Nginx configured!"

# ============================================
# STEP 11: Create Systemd Service
# ============================================
print_status "Creating systemd service..."
cat > /etc/systemd/system/lemaison.service <<EOF
[Unit]
Description=Le Maison Restaurant Management System
After=network.target postgresql.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/lemaison
Environment="PATH=/var/www/lemaison/venv/bin"
ExecStart=/var/www/lemaison/venv/bin/gunicorn \\
    --worker-class eventlet \\
    -w 1 \\
    --bind 127.0.0.1:5000 \\
    --timeout 600 \\
    app:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Set permissions
chown -R www-data:www-data /var/www/lemaison
chmod -R 755 /var/www/lemaison

# Start service
systemctl daemon-reload
systemctl enable lemaison
systemctl start lemaison
print_success "Service started!"

# ============================================
# STEP 12: Setup SSL Certificate
# ============================================
print_status "Setting up SSL certificate (HTTPS)..."
certbot --nginx -d "$DOMAIN_NAME" -d "www.$DOMAIN_NAME" --non-interactive --agree-tos --email "$SSL_EMAIL" --redirect || print_warning "SSL setup failed. You can run it manually later: sudo certbot --nginx -d $DOMAIN_NAME"

# ============================================
# FINAL STATUS CHECK
# ============================================
echo ""
echo "============================================"
echo "  DEPLOYMENT COMPLETE!"
echo "============================================"
echo ""

print_success "Your restaurant system is now deployed!"
echo ""
echo "📋 Deployment Summary:"
echo "   Domain: http://$DOMAIN_NAME"
echo "   HTTPS: https://$DOMAIN_NAME"
echo "   Database: lemaison_db"
echo "   Database User: lemaison_user"
echo "   Code Location: /var/www/lemaison"
echo ""

print_status "Checking service status..."
systemctl status lemaison --no-pager -l || true
echo ""

print_status "Checking Nginx status..."
systemctl status nginx --no-pager -l || true
echo ""

echo "============================================"
echo "  NEXT STEPS:"
echo "============================================"
echo ""
echo "1. Point your domain DNS to this server IP"
echo "2. Wait 15-30 minutes for DNS propagation"
echo "3. Visit: https://$DOMAIN_NAME"
echo ""
echo "📝 Important Commands:"
echo "   Restart app:    sudo systemctl restart lemaison"
echo "   View logs:      sudo journalctl -u lemaison -f"
echo "   Restart Nginx:  sudo systemctl restart nginx"
echo ""
echo "🆘 Troubleshooting:"
echo "   Check logs:     sudo journalctl -u lemaison -n 50"
echo "   Test database:  psql -U lemaison_user -d lemaison_db -h localhost"
echo ""
echo "============================================"
echo "  DEPLOYMENT SUCCESSFUL! 🎉"
echo "============================================"
echo ""

# Save credentials to file
cat > /root/lemaison_credentials.txt <<EOF
Le Maison Restaurant System - Deployment Credentials
====================================================

Domain: $DOMAIN_NAME
Database Name: lemaison_db
Database User: lemaison_user
Database Password: $DB_PASSWORD
Secret Key: $SECRET_KEY

Code Location: /var/www/lemaison
Service Name: lemaison

Commands:
- Restart: sudo systemctl restart lemaison
- Logs: sudo journalctl -u lemaison -f
- Status: sudo systemctl status lemaison

Generated: $(date)
EOF

print_success "Credentials saved to: /root/lemaison_credentials.txt"
echo ""
print_warning "IMPORTANT: Keep your credentials safe!"
echo ""
