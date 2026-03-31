#!/bin/bash
# ============================================================
# Auto Job Applier - Setup Script
# ============================================================

set -e

echo "╔═══════════════════════════════════════════════════════╗"
echo "║        🚀 Auto Job Applier - Setup Script 🚀        ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python $PYTHON_VERSION detected"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi

# Activate venv
source venv/bin/activate
echo "✓ Virtual environment activated"

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✓ Dependencies installed"

# Install Playwright browsers
echo "Installing Playwright browsers (this may take a few minutes)..."
playwright install chromium
echo "✓ Playwright browsers installed"

# Create data directory
mkdir -p data logs

# Create profile.yaml from example if not exists
if [ ! -f "config/profile.yaml" ]; then
    cp config/profile.yaml.example config/profile.yaml
    echo "✓ config/profile.yaml created (edit with your details)"
fi

# Create .env file if not exists
if [ ! -f ".env" ]; then
    cat > .env << 'EOF'
# Auto Job Applier - Environment Variables
# Get your free API key at: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=

# Optional: Telegram notifications
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Optional: Email notifications
SMTP_PASSWORD=
EOF
    echo "✓ .env file created (add your API keys)"
fi

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║                  SETUP COMPLETE! ✓                   ║"
echo "╠═══════════════════════════════════════════════════════╣"
echo "║                                                       ║"
echo "║  Next Steps:                                          ║"
echo "║                                                       ║"
echo "║  1. Edit config/profile.yaml with YOUR details        ║"
echo "║                                                       ║"
echo "║  2. Get free Gemini API key:                          ║"
echo "║     https://aistudio.google.com/app/apikey            ║"
echo "║     Add it to .env file                               ║"
echo "║                                                       ║"
echo "║  3. Place your resume at: data/resume.pdf             ║"
echo "║                                                       ║"
echo "║  4. Login to portals (first time only):               ║"
echo "║     python main.py login                              ║"
echo "║                                                       ║"
echo "║  5. Start applying:                                   ║"
echo "║     python main.py run                                ║"
echo "║                                                       ║"
echo "║  See README.md for full documentation.                ║"
echo "╚═══════════════════════════════════════════════════════╝"
