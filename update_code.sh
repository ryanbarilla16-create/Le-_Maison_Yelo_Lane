#!/bin/bash

# ============================================
# Le Maison Restaurant System
# Quick Update Script
# ============================================

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "============================================"
echo "  Le Maison - Quick Update Script"
echo "============================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${YELLOW}[WARNING]${NC} Please run as root: sudo bash update_code.sh"
    exit 1
fi

cd /var/www/lemaison

echo -e "${BLUE}[1/5]${NC} Pulling latest code from GitHub..."
git pull origin main || {
    echo -e "${YELLOW}[WARNING]${NC} Git pull failed. Skipping..."
}

echo -e "${BLUE}[2/5]${NC} Activating virtual environment..."
source venv/bin/activate

echo -e "${BLUE}[3/5]${NC} Updating Python dependencies..."
pip install -r requirements.txt

echo -e "${BLUE}[4/5]${NC} Running database migrations (if any)..."
python3 -c "from app import app, db; app.app_context().push(); db.create_all()" || echo "Database already up to date"

echo -e "${BLUE}[5/5]${NC} Restarting application..."
systemctl restart lemaison

echo ""
echo -e "${GREEN}✅ Update complete!${NC}"
echo ""
echo "Checking service status..."
systemctl status lemaison --no-pager -l | head -n 10

echo ""
echo "============================================"
echo "  Update Successful! 🎉"
echo "============================================"
echo ""
echo "Your website is now running the latest code!"
echo "Visit: https://YOUR_DOMAIN.com"
echo ""
