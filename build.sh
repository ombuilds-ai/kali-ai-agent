#!/bin/bash
# ╔═══════════════════════════════════════════════════════════════╗
# ║  Kali-AI Agent — Standalone Binary Builder                    ║
# ║  Creates a single portable executable for Kali Linux          ║
# ║  Run: chmod +x build.sh && ./build.sh                         ║
# ╚═══════════════════════════════════════════════════════════════╝

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/venv"
OUTPUT_NAME="KaliAI-Agent"
DIST_DIR="$SCRIPT_DIR/dist"

echo ""
echo -e "${CYAN}${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║   🔨 Kali-AI Agent — Standalone Builder v2.0     ║${NC}"
echo -e "${CYAN}${BOLD}║   Building portable executable...                 ║${NC}"
echo -e "${CYAN}${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
echo ""

# ── Check OS ────────────────────────────────────────────────────────────────────
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}❌ This build script must run on Linux (Kali/Debian).${NC}"
    echo -e "${YELLOW}   PyInstaller builds for the current OS only.${NC}"
    exit 1
fi

# ── Step 1: Python check ──────────────────────────────────────────────────────
echo -e "${BLUE}[1/5]${NC} Checking Python 3..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ python3 not found. Install: sudo apt install python3 python3-venv${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python $(python3 --version | cut -d' ' -f2) found${NC}"

# ── Step 2: System dependencies ───────────────────────────────────────────────
echo -e "${BLUE}[2/5]${NC} Checking system dependencies..."
NEEDS_INSTALL=""
for pkg in python3-venv python3-dev; do
    if ! dpkg -s "$pkg" &> /dev/null 2>&1; then
        NEEDS_INSTALL="$NEEDS_INSTALL $pkg"
    fi
done

if [ -n "$NEEDS_INSTALL" ]; then
    echo -e "${YELLOW}📦 Installing build dependencies:${NEEDS_INSTALL}${NC}"
    sudo apt update -qq 2>/dev/null
    sudo apt install -y -qq $NEEDS_INSTALL python3-pyqt6 scrot xclip 2>/dev/null
fi
echo -e "${GREEN}✅ Build dependencies ready${NC}"

# ── Step 3: Virtual environment ──────────────────────────────────────────────
echo -e "${BLUE}[3/5]${NC} Setting up build environment..."

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR" --system-site-packages
fi
source "$VENV_DIR/bin/activate"

# Install all dependencies + PyInstaller
pip install --quiet --upgrade pip 2>/dev/null
pip install --quiet openai google-generativeai pyautogui Pillow mss pyinstaller 2>/dev/null
echo -e "${GREEN}✅ Build environment ready${NC}"

# ── Step 4: Build with PyInstaller ─────────────────────────────────────────────
echo -e "${BLUE}[4/5]${NC} Building standalone binary..."
echo -e "${YELLOW}   This may take 2-5 minutes...${NC}"

# Clean previous builds
rm -rf "$SCRIPT_DIR/build" "$DIST_DIR" "$SCRIPT_DIR/${OUTPUT_NAME}.spec" 2>/dev/null

pyinstaller \
    --onefile \
    --name "$OUTPUT_NAME" \
    --windowed \
    --noconfirm \
    --clean \
    --add-data "guardrails.py:." \
    --add-data "screenshot.py:." \
    --add-data "config.py:." \
    --add-data "executor.py:." \
    --add-data "ai_engine.py:." \
    --hidden-import "PyQt6.QtCore" \
    --hidden-import "PyQt6.QtGui" \
    --hidden-import "PyQt6.QtWidgets" \
    --hidden-import "google.generativeai" \
    --hidden-import "openai" \
    --hidden-import "pyautogui" \
    --hidden-import "PIL" \
    --hidden-import "mss" \
    --hidden-import "PIL.ImageGrab" \
    --hidden-import "google.ai.generativelanguage" \
    --hidden-import "google.auth" \
    --hidden-import "google.api_core" \
    --collect-all "google.generativeai" \
    --collect-submodules "google" \
    main.py

echo -e "${GREEN}✅ Build complete!${NC}"

# ── Step 5: Package result ──────────────────────────────────────────────────
echo -e "${BLUE}[5/5]${NC} Packaging..."

BINARY_PATH="$DIST_DIR/$OUTPUT_NAME"

if [ -f "$BINARY_PATH" ]; then
    chmod +x "$BINARY_PATH"
    BINARY_SIZE=$(du -sh "$BINARY_PATH" | cut -f1)

    # Clean build artifacts
    rm -rf "$SCRIPT_DIR/build" "$SCRIPT_DIR/${OUTPUT_NAME}.spec" 2>/dev/null

    echo ""
    echo -e "${GREEN}${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║   ✅ BUILD SUCCESSFUL!                            ║${NC}"
    echo -e "${GREEN}${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}   Binary:${NC}  $BINARY_PATH"
    echo -e "${CYAN}   Size:${NC}    $BINARY_SIZE"
    echo ""
    echo -e "${YELLOW}${BOLD}   Usage:${NC}"
    echo -e "   ${GREEN}./dist/$OUTPUT_NAME${NC}              # Run from terminal"
    echo -e "   ${GREEN}Double-click${NC} the file            # Run from file manager"
    echo ""
    echo -e "${YELLOW}${BOLD}   Share it:${NC}"
    echo -e "   Copy ${GREEN}dist/$OUTPUT_NAME${NC} to any Kali machine and run!"
    echo -e "   No Python, no pip, no venv needed. Just run it. 🚀"
    echo ""

    # Optionally copy to Desktop
    read -p "Copy to Desktop? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        DESKTOP_DIR="$HOME/Desktop"
        if [ -d "$DESKTOP_DIR" ]; then
            cp "$BINARY_PATH" "$DESKTOP_DIR/"
            chmod +x "$DESKTOP_DIR/$OUTPUT_NAME"
            echo -e "${GREEN}✅ Copied to $DESKTOP_DIR/$OUTPUT_NAME${NC}"
        else
            mkdir -p "$DESKTOP_DIR"
            cp "$BINARY_PATH" "$DESKTOP_DIR/"
            chmod +x "$DESKTOP_DIR/$OUTPUT_NAME"
            echo -e "${GREEN}✅ Copied to $DESKTOP_DIR/$OUTPUT_NAME${NC}"
        fi
    fi
else
    echo -e "${RED}❌ Build failed! Binary not found at $BINARY_PATH${NC}"
    echo -e "${YELLOW}   Check the PyInstaller output above for errors.${NC}"
    exit 1
fi

echo ""
echo -e "${CYAN}Done! 🎉${NC}"
