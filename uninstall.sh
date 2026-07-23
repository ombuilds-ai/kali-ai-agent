#!/bin/bash
# ╔═══════════════════════════════════════════════════════════════╗
# ║  Kali-AI Agent (OmniControl) — Complete Uninstaller          ║
# ║  Run: chmod +x uninstall.sh && ./uninstall.sh                ║
# ╚═══════════════════════════════════════════════════════════════╝

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Paths to clean
CONFIG_DIR="$HOME/.config/kali-ai"
DESKTOP_FILE="$HOME/.local/share/applications/kali-ai-agent.desktop"
LEGACY_CONFIG="$SCRIPT_DIR/.kali_ai_config.json"
VENV_DIR="$SCRIPT_DIR/venv"
PYCACHE_DIR="$SCRIPT_DIR/__pycache__"
DIST_DIR="$SCRIPT_DIR/dist"
BUILD_DIR="$SCRIPT_DIR/build"
DESKTOP_BINARY="$HOME/Desktop/KaliAI-OmniControl"

echo ""
echo -e "${CYAN}${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║     🗑  Kali-AI Agent (OmniControl) Uninstaller  ║${NC}"
echo -e "${CYAN}${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}This will remove:${NC}"
echo ""

# Show what will be removed
ITEMS_FOUND=0

if [ -d "$CONFIG_DIR" ]; then
    echo -e "  ${RED}✖${NC}  Config directory:    $CONFIG_DIR"
    ITEMS_FOUND=$((ITEMS_FOUND + 1))
fi

if [ -f "$LEGACY_CONFIG" ]; then
    echo -e "  ${RED}✖${NC}  Legacy config:       $LEGACY_CONFIG"
    ITEMS_FOUND=$((ITEMS_FOUND + 1))
fi

if [ -f "$DESKTOP_FILE" ]; then
    echo -e "  ${RED}✖${NC}  Desktop shortcut:    $DESKTOP_FILE"
    ITEMS_FOUND=$((ITEMS_FOUND + 1))
fi

if [ -d "$VENV_DIR" ]; then
    VENV_SIZE=$(du -sh "$VENV_DIR" 2>/dev/null | cut -f1)
    echo -e "  ${RED}✖${NC}  Virtual environment: $VENV_DIR ($VENV_SIZE)"
    ITEMS_FOUND=$((ITEMS_FOUND + 1))
fi

if [ -d "$PYCACHE_DIR" ]; then
    echo -e "  ${RED}✖${NC}  Python cache:        $PYCACHE_DIR"
    ITEMS_FOUND=$((ITEMS_FOUND + 1))
fi

if [ -d "$DIST_DIR" ]; then
    DIST_SIZE=$(du -sh "$DIST_DIR" 2>/dev/null | cut -f1)
    echo -e "  ${RED}✖${NC}  Build output:        $DIST_DIR ($DIST_SIZE)"
    ITEMS_FOUND=$((ITEMS_FOUND + 1))
fi

if [ -d "$BUILD_DIR" ]; then
    echo -e "  ${RED}✖${NC}  Build cache:         $BUILD_DIR"
    ITEMS_FOUND=$((ITEMS_FOUND + 1))
fi

if [ -f "$DESKTOP_BINARY" ]; then
    echo -e "  ${RED}✖${NC}  Desktop binary:      $DESKTOP_BINARY"
    ITEMS_FOUND=$((ITEMS_FOUND + 1))
fi

if [ $ITEMS_FOUND -eq 0 ]; then
    echo -e "  ${GREEN}✅  Nothing to clean up — already uninstalled!${NC}"
    echo ""
    echo -e "  To completely remove the application, delete this folder:"
    echo -e "  ${YELLOW}rm -rf '$SCRIPT_DIR'${NC}"
    echo ""
    exit 0
fi

echo ""
echo -e "${YELLOW}${BOLD}⚠  WARNING: This action cannot be undone!${NC}"
echo -e "${YELLOW}   Your API keys in config will be permanently deleted.${NC}"
echo ""
read -p "Are you sure you want to uninstall? (y/N): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo -e "${GREEN}Uninstall cancelled. No changes made.${NC}"
    echo ""
    exit 0
fi

echo ""
echo -e "${BLUE}Starting cleanup...${NC}"
echo ""

# Remove config directory
if [ -d "$CONFIG_DIR" ]; then
    echo -e "  ${YELLOW}🗑${NC}  Removing config directory..."
    rm -rf "$CONFIG_DIR"
    echo -e "  ${GREEN}✅${NC}  Config directory removed"
fi

# Remove legacy config
if [ -f "$LEGACY_CONFIG" ]; then
    echo -e "  ${YELLOW}🗑${NC}  Removing legacy config..."
    rm -f "$LEGACY_CONFIG"
    echo -e "  ${GREEN}✅${NC}  Legacy config removed"
fi

# Remove desktop shortcut
if [ -f "$DESKTOP_FILE" ]; then
    echo -e "  ${YELLOW}🗑${NC}  Removing desktop shortcut..."
    rm -f "$DESKTOP_FILE"
    # Update desktop database if available
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database "$HOME/.local/share/applications/" 2>/dev/null || true
    fi
    echo -e "  ${GREEN}✅${NC}  Desktop shortcut removed"
fi

# Remove virtual environment
if [ -d "$VENV_DIR" ]; then
    echo -e "  ${YELLOW}🗑${NC}  Removing virtual environment..."
    rm -rf "$VENV_DIR"
    echo -e "  ${GREEN}✅${NC}  Virtual environment removed"
fi

# Remove Python cache
if [ -d "$PYCACHE_DIR" ]; then
    echo -e "  ${YELLOW}🗑${NC}  Removing Python cache..."
    rm -rf "$PYCACHE_DIR"
    echo -e "  ${GREEN}✅${NC}  Python cache removed"
fi

# Remove any other __pycache__ directories
find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Remove dist (build output)
if [ -d "$DIST_DIR" ]; then
    echo -e "  ${YELLOW}🗑${NC}  Removing build output..."
    rm -rf "$DIST_DIR"
    echo -e "  ${GREEN}✅${NC}  Build output removed"
fi

# Remove build cache
if [ -d "$BUILD_DIR" ]; then
    echo -e "  ${YELLOW}🗑${NC}  Removing build cache..."
    rm -rf "$BUILD_DIR"
    echo -e "  ${GREEN}✅${NC}  Build cache removed"
fi

# Remove .spec file
rm -f "$SCRIPT_DIR"/*.spec 2>/dev/null || true

# Remove desktop binary
if [ -f "$DESKTOP_BINARY" ]; then
    echo -e "  ${YELLOW}🗑${NC}  Removing desktop binary..."
    rm -f "$DESKTOP_BINARY"
    echo -e "  ${GREEN}✅${NC}  Desktop binary removed"
fi

echo ""
echo -e "${GREEN}${BOLD}✅ Uninstall Complete!${NC}"
echo ""
echo -e "${CYAN}To completely remove the application source code, delete this folder:${NC}"
echo -e "  ${YELLOW}rm -rf '$SCRIPT_DIR'${NC}"
echo ""
echo -e "${CYAN}Thank you for using Kali-AI Agent! 👋${NC}"
echo ""
