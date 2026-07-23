# PowerShell script to generate install.sh cleanly without garbled characters

$sourceDir = 'c:\Users\princ\Desktop\kali mcp'
$outputFile = Join-Path $sourceDir 'install.sh'

$files = @(
    'config.py',
    'guardrails.py',
    'screenshot.py',
    'executor.py',
    'plugins.py',
    'memory.py',
    'sessions.py',
    'ai_engine.py',
    'gui.py',
    'main.py',
    'requirements.txt',
    'build.sh',
    'run.sh',
    'uninstall.sh'
)

$header = @'
#!/bin/bash
# ==============================================================================
# Kali-AI Agent (OmniControl) — Self-Extracting Installer
# Usage:  bash install.sh              (install)
#         bash install.sh --uninstall  (remove everything)
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

APP_DIR="$HOME/KaliAI"

# Handle --uninstall
if [ "$1" = "--uninstall" ]; then
    echo ""
    echo -e "${CYAN}${BOLD}=== Kali-AI Agent — Uninstaller ===${NC}"
    echo ""
    ITEMS=0
    [ -d "$APP_DIR" ] && echo -e "  ${RED}[X]${NC} App directory: $APP_DIR" && ITEMS=$((ITEMS+1))
    [ -d "$HOME/.config/kali-ai" ] && echo -e "  ${RED}[X]${NC} Config: ~/.config/kali-ai/" && ITEMS=$((ITEMS+1))
    [ -f "$HOME/.local/share/applications/kali-ai-agent.desktop" ] && echo -e "  ${RED}[X]${NC} Desktop shortcut" && ITEMS=$((ITEMS+1))
    [ -f "$HOME/Desktop/KaliAI-OmniControl" ] && echo -e "  ${RED}[X]${NC} Desktop binary" && ITEMS=$((ITEMS+1))
    if [ $ITEMS -eq 0 ]; then
        echo -e "  ${GREEN}Already uninstalled!${NC}"
        exit 0
    fi
    echo ""
    read -p "Remove all? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$APP_DIR" "$HOME/.config/kali-ai" 2>/dev/null
        rm -f "$HOME/.local/share/applications/kali-ai-agent.desktop" 2>/dev/null
        rm -f "$HOME/Desktop/KaliAI-OmniControl" 2>/dev/null
        echo -e "${GREEN}${BOLD}Uninstalled successfully!${NC}"
    else
        echo "Cancelled."
    fi
    exit 0
fi

# Main Installation
echo ""
echo -e "${CYAN}${BOLD}=====================================================${NC}"
echo -e "${CYAN}${BOLD}  Kali-AI Agent (OmniControl) — Installer           ${NC}"
echo -e "${CYAN}${BOLD}  AI-Powered Kali Linux Controller v2.0             ${NC}"
echo -e "${CYAN}${BOLD}=====================================================${NC}"
echo ""

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}python3 not found! Install: sudo apt install python3 python3-venv${NC}"
    exit 1
fi
echo -e "${GREEN}[OK]${NC} Python $(python3 --version | cut -d' ' -f2) found"

# Step 1: Create app directory
echo -e "${BLUE}[1/5]${NC} Creating application directory..."
mkdir -p "$APP_DIR"

# Step 2: Extract embedded source files
echo -e "${BLUE}[2/5]${NC} Extracting application files..."

'@

$footer = @'

chmod +x "$APP_DIR/build.sh" "$APP_DIR/run.sh" "$APP_DIR/uninstall.sh" 2>/dev/null
echo -e "${GREEN}[OK]${NC} All files extracted to $APP_DIR"

# Step 3: Install system dependencies
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
        sudo apt install -y -qq python3-venv python3-pyqt6 python3-dev scrot xclip xsel libxcb-cursor0 libxkbcommon-x11-0 libegl1 libdbus-1-3 2>/dev/null || echo -e "${YELLOW}Some packages may need manual install${NC}"
    else
        apt update -qq 2>/dev/null
        apt install -y -qq python3-venv python3-pyqt6 python3-dev scrot xclip xsel libxcb-cursor0 libxkbcommon-x11-0 libegl1 libdbus-1-3 2>/dev/null || echo -e "${YELLOW}Some packages may need manual install${NC}"
    fi
fi
echo -e "${GREEN}[OK]${NC} System dependencies ready"

# Step 4: Python virtual environment + packages
echo -e "${BLUE}[4/5]${NC} Setting up Python environment..."
cd "$APP_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv --system-site-packages
fi
source venv/bin/activate
pip install --quiet --upgrade pip 2>/dev/null
pip install --quiet openai google-generativeai pyautogui Pillow mss 2>/dev/null
echo -e "${GREEN}[OK]${NC} Python packages installed"

# Step 5: Desktop integration
echo -e "${BLUE}[5/5]${NC} Creating desktop shortcut..."
DESKTOP_FILE="$HOME/.local/share/applications/kali-ai-agent.desktop"
mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" << 'SHORTCUT_HEREDOC'
[Desktop Entry]
Type=Application
Name=Kali-AI Agent
Comment=AI-Powered Kali Linux Controller
Exec=bash -c 'cd ~/KaliAI && source venv/bin/activate && python3 main.py'
Icon=utilities-terminal
Terminal=false
Categories=Security;System;Utility;
Keywords=ai;kali;security;pentest;
StartupNotify=true
SHORTCUT_HEREDOC
chmod +x "$DESKTOP_FILE" 2>/dev/null
echo -e "${GREEN}[OK]${NC} Desktop shortcut created"

# Done!
echo ""
echo -e "${GREEN}${BOLD}=====================================================${NC}"
echo -e "${GREEN}${BOLD}  INSTALLATION COMPLETE!                             ${NC}"
echo -e "${GREEN}${BOLD}=====================================================${NC}"
echo ""
echo -e "   Installed at:    ${CYAN}$APP_DIR${NC}"
echo -e "   Launch:          ${GREEN}bash ~/KaliAI/run.sh${NC}"
echo -e "   Build binary:    ${GREEN}bash ~/KaliAI/build.sh${NC}"
echo -e "   Uninstall:       ${GREEN}bash install.sh --uninstall${NC}"
echo -e "   App Menu:        Search 'Kali-AI' in applications"
echo ""

read -p "Launch Kali-AI Agent now? (Y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo -e "${GREEN}Launching...${NC}"
    cd "$APP_DIR"
    source venv/bin/activate
    python3 main.py
else
    echo -e "Run anytime: ${GREEN}bash ~/KaliAI/run.sh${NC}"
fi
'@

$sb = New-Object System.Text.StringBuilder
[void]$sb.Append($header)
[void]$sb.Append("`n")

foreach ($file in $files) {
    $filePath = Join-Path $sourceDir $file
    if (-not (Test-Path $filePath)) {
        Write-Host "  ERROR: $file not found!" -ForegroundColor Red
        exit 1
    }
    
    $content = [System.IO.File]::ReadAllText($filePath)
    $content = $content.Replace("`r`n", "`n")
    
    $delim = ($file.Replace('.', '_').Replace('-', '_')).ToUpper() + '_HEREDOC'
    
    [void]$sb.Append("cat << '$delim' > `"`$APP_DIR/$file`"`n")
    [void]$sb.Append($content)
    if (-not $content.EndsWith("`n")) {
        [void]$sb.Append("`n")
    }
    [void]$sb.Append("$delim`n`n")
}

[void]$sb.Append($footer)

$finalContent = $sb.ToString()
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($outputFile, $finalContent, $utf8NoBom)
Write-Host "Clean install.sh created successfully!"
