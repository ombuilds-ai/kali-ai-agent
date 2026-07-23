#!/bin/bash
# ╔═══════════════════════════════════════════════════════════════╗
# ║  Kali-AI Agent (OmniControl) — One-Click Launcher v2.0      ║
# ║  Just run: chmod +x run.sh && ./run.sh                       ║
# ║  Or double-click this file in your file manager               ║
# ╚═══════════════════════════════════════════════════════════════╝

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Get script directory (works even if script is symlinked)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/venv"
DESKTOP_FILE="$HOME/.local/share/applications/kali-ai-agent.desktop"

echo ""
echo -e "${CYAN}${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║       🐉 Kali-AI Agent (OmniControl) v2.0       ║${NC}"
echo -e "${CYAN}${BOLD}║       AI-Powered Kali Linux Controller           ║${NC}"
echo -e "${CYAN}${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
echo ""

# ── Step 1: Check Python 3 ─────────────────────────────────────────────────────
echo -e "${BLUE}[1/5]${NC} Checking Python 3..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ python3 not found. Please install Python 3.10+${NC}"
    echo "   Try: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}✅ Python $PYTHON_VERSION found${NC}"

# ── Step 2: Install system dependencies ────────────────────────────────────────
echo -e "${BLUE}[2/5]${NC} Checking system dependencies..."

MISSING_PKGS=""
NEEDED_CMDS=("scrot" "xclip")
NEEDED_PKGS=("python3-venv" "python3-pyqt6" "scrot" "xclip" "xsel" "libxcb-cursor0" "libxkbcommon-x11-0")

for cmd in "${NEEDED_CMDS[@]}"; do
    if ! command -v "$cmd" &> /dev/null; then
        MISSING_PKGS="yes"
        break
    fi
done

# Check if PyQt6 system package exists
if ! python3 -c "import PyQt6" 2>/dev/null; then
    MISSING_PKGS="yes"
fi

if [ -n "$MISSING_PKGS" ]; then
    echo -e "${YELLOW}📦 Installing system packages (may need sudo)...${NC}"
    if [ "$EUID" -ne 0 ]; then
        sudo apt update -qq 2>/dev/null && sudo apt install -y -qq \
            python3-venv python3-pyqt6 scrot xclip xsel \
            libxcb-cursor0 libxkbcommon-x11-0 libegl1 libdbus-1-3 \
            2>/dev/null || echo -e "${YELLOW}⚠ Some system packages may need manual install${NC}"
    else
        apt update -qq 2>/dev/null && apt install -y -qq \
            python3-venv python3-pyqt6 scrot xclip xsel \
            libxcb-cursor0 libxkbcommon-x11-0 libegl1 libdbus-1-3 \
            2>/dev/null || echo -e "${YELLOW}⚠ Some system packages may need manual install${NC}"
    fi
    echo -e "${GREEN}✅ System packages checked${NC}"
else
    echo -e "${GREEN}✅ All system dependencies present${NC}"
fi

# ── Step 3: Setup Virtual Environment ──────────────────────────────────────────
echo -e "${BLUE}[3/5]${NC} Setting up Python environment..."

if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}   Creating virtual environment...${NC}"
    python3 -m venv "$VENV_DIR" --system-site-packages
    echo -e "${GREEN}   ✅ Virtual environment created${NC}"
else
    echo -e "${GREEN}   ✅ Virtual environment exists${NC}"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# ── Step 4: Install Python dependencies ────────────────────────────────────────
echo -e "${BLUE}[4/5]${NC} Installing Python packages..."

# Check if packages need installation
NEEDS_INSTALL=""
for pkg in openai google-generativeai pyautogui Pillow mss; do
    if ! python3 -c "import $(echo $pkg | tr '-' '_' | tr '[:upper:]' '[:lower:]')" 2>/dev/null; then
        NEEDS_INSTALL="yes"
        break
    fi
done

if [ -n "$NEEDS_INSTALL" ]; then
    echo -e "${YELLOW}   Installing required Python packages (openai, google-generativeai, pyautogui, Pillow, mss)...${NC}"
    pip install --upgrade pip --break-system-packages 2>/dev/null || true
    pip install openai google-generativeai pyautogui Pillow mss --break-system-packages 2>/dev/null || echo -e "${YELLOW}⚠ Network offline or pip warning. Continuing with system packages...${NC}"
    echo -e "${GREEN}✅ Python package check completed${NC}"
else
    echo -e "${GREEN}✅ All Python packages present${NC}"
fi

# ── Step 5: Create desktop shortcut ───────────────────────────────────────────
echo -e "${BLUE}[5/5]${NC} Setting up desktop integration..."

mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" << DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=Kali-AI Agent
Comment=AI-Powered Kali Linux Controller — OmniControl
Exec=bash -c 'cd "$SCRIPT_DIR" && source venv/bin/activate && python3 main.py'
Icon=utilities-terminal
Terminal=false
Categories=Security;System;Utility;
Keywords=ai;kali;security;pentest;hacking;
StartupNotify=true
DESKTOP_EOF

chmod +x "$DESKTOP_FILE" 2>/dev/null || true
echo -e "${GREEN}✅ Desktop shortcut created${NC}"

# ── Launch ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}🚀 Launching Kali-AI Agent...${NC}"
echo -e "${CYAN}   Tip: Find 'Kali-AI Agent' in your application menu next time!${NC}"
echo ""

export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-xcb}
export DISPLAY=${DISPLAY:-:0}
xhost +local:root 2>/dev/null || true

python3 main.py