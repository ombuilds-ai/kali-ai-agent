"""
Builder script — generates a self-extracting install.sh
Run this with: python builder.py
"""
import os
import sys

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTALLER_PATH = os.path.join(SOURCE_DIR, 'install.sh')

# Files to embed in the installer (must include EVERY runtime module or the
# extracted install will crash with ImportError at startup).
files_to_embed = [
    'config.py',
    'guardrails.py',
    'screenshot.py',
    'environment.py',
    'shell_session.py',
    'tools.py',
    'jobs.py',
    'ghidra.py',
    'executor.py',
    'memory.py',
    'sessions.py',
    'plugins.py',
    'ai_engine.py',
    'gui.py',
    'main.py',
    'requirements.txt',
    'build.sh',
    'run.sh',
    'uninstall.sh',
]

header = r'''#!/bin/bash
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║           🐉 Kali-AI Agent (OmniControl) — Self-Extracting Installer    ║
# ║                                                                         ║
# ║   Usage:  bash install.sh           (install)                           ║
# ║           bash install.sh --uninstall  (remove everything)              ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# This single file contains the ENTIRE application.
# No internet connection needed for source code — only for pip packages.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

APP_DIR="$HOME/KaliAI"

# ── Handle --uninstall ─────────────────────────────────────────────────────────
if [ "$1" = "--uninstall" ]; then
    echo ""
    echo -e "${CYAN}${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}${BOLD}║     🗑  Kali-AI Agent — Uninstaller              ║${NC}"
    echo -e "${CYAN}${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
    echo ""
    
    ITEMS=0
    [ -d "$APP_DIR" ] && echo -e "  ${RED}✖${NC}  App directory: $APP_DIR" && ITEMS=$((ITEMS+1))
    [ -d "$HOME/.config/kali-ai" ] && echo -e "  ${RED}✖${NC}  Config: ~/.config/kali-ai/" && ITEMS=$((ITEMS+1))
    [ -f "$HOME/.local/share/applications/kali-ai-agent.desktop" ] && echo -e "  ${RED}✖${NC}  Desktop shortcut" && ITEMS=$((ITEMS+1))
    [ -f "$HOME/Desktop/KaliAI-OmniControl" ] && echo -e "  ${RED}✖${NC}  Desktop binary" && ITEMS=$((ITEMS+1))
    
    if [ $ITEMS -eq 0 ]; then
        echo -e "  ${GREEN}✅ Nothing to remove — not installed!${NC}"
        exit 0
    fi
    
    echo ""
    read -p "Remove all? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$APP_DIR" "$HOME/.config/kali-ai" "$HOME/.local/share/applications/kali-ai-agent.desktop" "$HOME/Desktop/KaliAI-OmniControl" 2>/dev/null
        echo -e "${GREEN}${BOLD}✅ Uninstalled successfully!${NC}"
    else
        echo "Cancelled."
    fi
    exit 0
fi

# ── Main Installation ──────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║   🐉 Kali-AI Agent (OmniControl) — Installer     ║${NC}"
echo -e "${CYAN}${BOLD}║   AI-Powered Kali Linux Controller v2.0          ║${NC}"
echo -e "${CYAN}${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ python3 not found! Install: sudo apt install python3 python3-venv${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python $(python3 --version | cut -d' ' -f2) found${NC}"

# ── Step 1: Create app directory ───────────────────────────────────────────────
echo -e "${BLUE}[1/5]${NC} Creating application directory..."
mkdir -p "$APP_DIR"
echo -e "${GREEN}✅ Created $APP_DIR${NC}"

# ── Step 2: Extract embedded source files ──────────────────────────────────────
echo -e "${BLUE}[2/5]${NC} Extracting application files..."

'''

footer = r'''
chmod +x "$APP_DIR/build.sh" "$APP_DIR/run.sh" "$APP_DIR/uninstall.sh" 2>/dev/null

FILE_COUNT=$(ls -1 "$APP_DIR"/*.py "$APP_DIR"/*.txt "$APP_DIR"/*.sh 2>/dev/null | wc -l)
echo -e "${GREEN}✅ Extracted $FILE_COUNT files to $APP_DIR${NC}"

# ── Step 3: Install system dependencies ────────────────────────────────────────
echo -e "${BLUE}[3/5]${NC} Installing system dependencies..."

NEED_INSTALL=""
for cmd in scrot xclip; do
    command -v "$cmd" &>/dev/null || NEED_INSTALL="yes"
done
python3 -c "import PyQt6" 2>/dev/null || NEED_INSTALL="yes"

if [ -n "$NEED_INSTALL" ]; then
    echo -e "${YELLOW}   Installing packages (may need sudo password)...${NC}"
    if [ "$EUID" -ne 0 ]; then
        sudo apt update -qq 2>/dev/null
        sudo apt install -y -qq \
            python3-venv python3-pyqt6 python3-dev \
            scrot xclip xsel \
            libxcb-cursor0 libxkbcommon-x11-0 libegl1 libdbus-1-3 \
            2>/dev/null || echo -e "${YELLOW}⚠ Some packages may need manual install${NC}"
    else
        apt update -qq 2>/dev/null
        apt install -y -qq \
            python3-venv python3-pyqt6 python3-dev \
            scrot xclip xsel \
            libxcb-cursor0 libxkbcommon-x11-0 libegl1 libdbus-1-3 \
            2>/dev/null || echo -e "${YELLOW}⚠ Some packages may need manual install${NC}"
    fi
fi
echo -e "${GREEN}✅ System dependencies ready${NC}"

# ── Step 4: Python virtual environment + packages ─────────────────────────────
echo -e "${BLUE}[4/5]${NC} Setting up Python environment..."
cd "$APP_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv --system-site-packages
fi
source venv/bin/activate

pip install --quiet --upgrade pip 2>/dev/null
pip install --quiet openai google-generativeai pyautogui Pillow mss 2>/dev/null
echo -e "${GREEN}✅ Python packages installed${NC}"

# ── Step 5: Desktop integration ───────────────────────────────────────────────
echo -e "${BLUE}[5/5]${NC} Creating desktop shortcut..."

DESKTOP_FILE="$HOME/.local/share/applications/kali-ai-agent.desktop"
mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" << SHORTCUT_EOF
[Desktop Entry]
Type=Application
Name=Kali-AI Agent
Comment=AI-Powered Kali Linux Controller — OmniControl v2.0
Exec=bash -c 'cd "$APP_DIR" && source venv/bin/activate && python3 main.py'
Icon=utilities-terminal
Terminal=false
Categories=Security;System;Utility;
Keywords=ai;kali;security;pentest;hacking;
StartupNotify=true
SHORTCUT_EOF
chmod +x "$DESKTOP_FILE" 2>/dev/null
echo -e "${GREEN}✅ Desktop shortcut created${NC}"

# ── Done! ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║   ✅ INSTALLATION COMPLETE!                      ║${NC}"
echo -e "${GREEN}${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}   📂 Installed at:${NC}    $APP_DIR"
echo -e "${CYAN}   🚀 Launch:${NC}          bash $APP_DIR/run.sh"
echo -e "${CYAN}   🔨 Build binary:${NC}    bash $APP_DIR/build.sh"
echo -e "${CYAN}   🗑  Uninstall:${NC}      bash install.sh --uninstall"
echo -e "${CYAN}   📱 App Menu:${NC}        Search 'Kali-AI' in applications"
echo ""

read -p "Launch Kali-AI Agent now? (Y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo -e "${GREEN}🚀 Launching...${NC}"
    cd "$APP_DIR"
    source venv/bin/activate
    python3 main.py
else
    echo -e "${CYAN}Run it anytime: ${GREEN}bash ~/KaliAI/run.sh${NC}"
fi
'''

# ── Build the installer ────────────────────────────────────────────────────────
print("🔨 Building self-extracting installer...")
print(f"   Source: {SOURCE_DIR}")
print(f"   Output: {INSTALLER_PATH}")
print()

with open(INSTALLER_PATH, 'w', encoding='utf-8', newline='\n') as out:
    out.write(header)
    
    for filename in files_to_embed:
        filepath = os.path.join(SOURCE_DIR, filename)
        if not os.path.exists(filepath):
            print(f"   ❌ ERROR: {filename} not found at {filepath}")
            sys.exit(1)
        
        with open(filepath, 'r', encoding='utf-8') as src:
            content = src.read()
        
        # Create unique heredoc delimiter
        delim = filename.replace('.', '_').replace('-', '_').upper() + '_HEREDOC'
        
        out.write(f"cat << '{delim}' > \"$APP_DIR/{filename}\"\n")
        out.write(content)
        if not content.endswith('\n'):
            out.write('\n')
        out.write(f"{delim}\n\n")
        
        lines = content.count('\n') + 1
        size = len(content)
        print(f"   ✅ Embedded: {filename} ({lines} lines, {size:,} bytes)")
    
    out.write(footer)

installer_size = os.path.getsize(INSTALLER_PATH)
print()
print(f"✅ install.sh generated successfully!")
print(f"   Size: {installer_size:,} bytes ({installer_size // 1024} KB)")
print()
print("📋 Now copy install.sh to Kali Linux and run:")
print("   bash install.sh")
