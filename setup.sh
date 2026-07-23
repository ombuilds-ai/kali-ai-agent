#!/bin/bash
# Kali-AI Agent Setup Script (Legacy — use run.sh instead)
# run.sh now handles everything automatically.
# This script is kept for manual setup if needed.

echo "╔═══════════════════════════════════════════════════╗"
echo "║     Kali-AI Agent (OmniControl) Setup             ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""
echo "💡 TIP: Use ./run.sh instead — it does everything automatically!"
echo ""

# Ensure we are running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "⚠ Warning: This script is designed for Kali Linux / Debian-based systems."
fi

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed."
    echo "   Try: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

echo "📦 Installing system dependencies..."
sudo apt update
sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-pyqt6 \
    python3-xlib \
    python3-pyautogui \
    scrot \
    xclip \
    xsel \
    libxcb-cursor0 \
    libxkbcommon-x11-0 \
    libegl1 \
    libdbus-1-3 \
    libgl1-mesa-glx 2>/dev/null || true

echo "📦 Setting up virtual environment..."
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

python3 -m venv venv --system-site-packages
source venv/bin/activate

echo "📦 Installing Python packages..."
pip install --upgrade pip
pip install PyQt6 openai google-generativeai pyautogui Pillow mss

echo ""
echo "✅ Setup Complete!"
echo ""
echo "🎯 Now run:"
echo "   ./run.sh"
echo ""
echo "   Or directly:"
echo "   source venv/bin/activate && python3 main.py"
echo ""
