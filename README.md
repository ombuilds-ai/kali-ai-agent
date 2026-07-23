# 🐉 Kali-AI Agent by Om v2.0

> **Autonomous Penetration Testing Co-Pilot & Security Operations AI for Kali Linux**  
> Control, audit, and analyze your entire Kali Linux environment through natural language pair-programming with Gemini, OpenRouter, AgentRouter, or any OpenAI-compatible LLM.

![Version](https://img.shields.io/badge/version-2.0-blue?style=for-the-badge&logo=kali-linux)
![Author](https://img.shields.io/badge/author-Om-orange?style=for-the-badge)
![Platform](https://img.shields.io/badge/platform-Kali%20Linux%20%7C%20Linux-purple?style=for-the-badge&logo=linux)
![Python](https://img.shields.io/badge/python-3.10%2B-green?style=for-the-badge&logo=python)
![License](https://img.shields.io/badge/license-MIT-red?style=for-the-badge)

---

## 📸 Overview & Dashboard Preview

**Kali-AI Agent by Om v2.0** is a state-of-the-art cybersecurity desktop co-pilot engineered specifically for Kali Linux. It operates shoulder-to-shoulder with security researchers, ethical hackers, and penetration testers—combining autonomous tool execution, intelligent RAG documentation lookup, real-time target inventory management, self-learning user memory, and strict human-in-the-loop safety guardrails.

---

## ✨ Key Features & Technical Highlights

### 🤝 1. Pair-Programming & Human-Like Co-Pilot Partner
* **Talk First, Align, Then Execute**: Kali-AI does NOT jump into command execution blindly. It first discusses goals, clarifies requirements, and presents strategic options in natural language (Hindi, Hinglish, or English).
* **Interactive Option Decision Buttons**: When a scan or tool output returns multiple targets or choices, clickable decision option buttons (`⚡ Select Option`) are rendered directly inside the chat interface.

### 🧠 2. Persistent Self-Learning Engine (`memory.py`)
* **User Habit & Preference Adaptation**: Automatically tracks and stores user preferences, preferred network tools, allowed scopes, and historical corrections in `~/.config/kali-ai/memory.json`.
* **System Prompt Injection**: Dynamically injects `[Persistent Self-Learning Memory & User Profile]` into every AI turn so Kali-AI gets smarter with every engagement.

### 💾 3. Real-Time & Exit Session Auto-Persistence (`sessions.py`)
* **Instant Real-Time Auto-Save**: Ongoing conversations are saved to disk (`~/.config/kali-ai/sessions.json`) after every single message.
* **Window Exit Protection (`closeEvent`)**: Closing the app window abruptely (`✖`) auto-saves the active session so chat history is never lost.
* **Session Management Sidebar**: Left sidebar with 1-click historical session reload and right-click context menu (`🗑 Delete Session`).

### 🎛️ 4. Dynamic Auto-Fetch & Dashboard Model Switcher
* **API Model Auto-Discovery**: Auto-detects models from OpenAI/OpenRouter/AgentRouter `/v1/models` endpoints and Google Gemini `genai.list_models()`.
* **Dashboard Dropdown Selector**: Interactive 1-click model switcher (`QComboBox`) directly on the bottom input bar with expanded popup menu (`min-width: 340px`) to display full model names without truncation.
* **Custom Gateway Error Protection**: Crash-proof response parser handling string, dictionary, or Pydantic responses from custom API proxies.

### 📊 5. Target Scope Guard & Interactive Asset Inventory
* **🎯 Target Scope Guard (`guardrails.py`)**: Restrict operations to authorized CIDR blocks, IP ranges, or domains. Blanking the scope restores standard open mode.
* **📊 Target Inventory Dashboard Widget**: Top header toggle launching a structured asset management table featuring IP hosts, open ports, service banners, risk badges (`Low`, `Medium`, `High`), and 1-click quick vulnerability audit actions.

### ⚡ 6. Non-Blocking Terminal Execution & Freeze Prevention (`executor.py`)
* **Stdin Pipe Protection (`stdin=subprocess.DEVNULL`)**: Prevents interactive commands (`sudo`, `wifite`, `airmon-ng`) from hanging indefinitely waiting for stdin input.
* **Streaming Tool Auto-Timeout (`timeout 15`)**: Automatically wraps continuous streaming tools (`airodump-ng`, `tcpdump`, `tshark`, `top`) with `timeout 15` to capture data without locking the terminal.
* **45s Hard Network Timeout**: Enforces 45-second socket timeouts on all AI provider network requests.

### 📶 7. Internet Connection Preservation (Wireless Audit Rule)
* **Preserve VirtualBox Network Connection**: Explicit system prompt instruction forbidding global `airmon-ng check kill` or `systemctl stop NetworkManager` to prevent cutting primary `eth0` internet connections during Wi-Fi audits.

### 🔤 8. Font Scaling Controls (`A-` / `13px` / `A+`) & Keyboard Shortcuts
* **Live Text Scaling**: Top header controls (`A-` / `13px` / `A+`) and keyboard shortcuts (`Ctrl +` / `Ctrl -`) dynamically resize chat bubbles, code blocks, and terminal logs in real-time.

### 🟥 9. Abort Execution Button & Emerald Activity Spinner
* **Instant Abort (`🟥`)**: Dedicated stop button that immediately terminates the active AI worker thread (`worker.terminate()`) and cancels background tasks.
* **Neon Circular Spinner**: Custom 33 FPS custom-painted emerald spinning arc indicator active during processing.

### 💬 10. Concurrent Mid-Execution Steering Notes
* **Unlocked Input Bar**: Input field remains active during background execution, queuing mid-execution steering notes into `self._pending_steering_notes` and appending them to the next turn automatically.

---

## 📁 Repository Structure

```
kali-ai/
├── main.py            # Main application launcher & entry point
├── gui.py             # Glassmorphism PyQt6 GUI, ChatBubbles, Inventory & Dialogs
├── ai_engine.py       # Dual AI Provider (Gemini + OpenAI/OpenRouter), RAG & Prompts
├── executor.py        # Safe command execution engine & non-blocking subprocesses
├── guardrails.py      # Security command filter & Target Scope compliance checker
├── memory.py          # Persistent self-learning user profile & habit memory engine
├── sessions.py        # Persistent disk storage manager for conversation sessions
├── config.py          # Config management (~/.config/kali-ai/config.json)
├── screenshot.py      # Multi-backend screenshot capture (PyAutoGUI, Scrot, xfce4-screenshooter)
├── requirements.txt   # Required Python packages
├── install.sh         # Self-contained single-file installer & uninstaller
├── run.sh             # Virtualenv auto-management launcher
├── build.sh           # Standalone binary compiler (PyInstaller)
├── build_installer.ps1# Installer bundler script
└── README.md          # Project documentation
```

---

## 🚀 Installation & Usage Guide

### Method 1: Single-File Installer (Recommended)

Simply download `install.sh` to your Kali Linux machine and execute:

```bash
bash install.sh
```

- ✅ Automatically extracts all embedded source files into `~/KaliAI/`
- ✅ Installs system dependencies (`python3-venv`, `scrot`, `xclip`, `qt6-base-dev`)
- ✅ Creates isolated virtual environment & installs pip requirements
- ✅ Generates Kali Linux Application Menu & Desktop shortcut
- 🗑️ **Uninstall anytime**: `bash install.sh --uninstall`

---

### Method 2: Direct Project Run (`run.sh`)

If you cloned the repository:

```bash
git clone https://github.com/your-username/kali-ai.git
cd kali-ai
chmod +x run.sh
./run.sh
```

---

### Method 3: Standalone Binary Compiler (`build.sh`)

To compile Kali-AI into a standalone portable executable binary (~100MB) that runs without Python installed:

```bash
chmod +x build.sh
./build.sh
```

The resulting executable is generated at `dist/KaliAI-OmniControl`.

---

## ⚙️ Configuration & API Setup

Kali-AI supports dual AI provider backends:

1. **Google Gemini (Recommended / Free)**:
   * Obtain a free API Key from [Google AI Studio](https://aistudio.google.com/).
   * Models supported: `gemini-2.0-flash`, `gemini-2.0-flash-lite`, `gemini-1.5-flash`, `gemini-1.5-pro`.

2. **OpenAI / OpenRouter / Custom Local APIs**:
   * Works with OpenRouter, AgentRouter, Local Ollama, vLLM, LM Studio, or OpenAI.
   * Default Base URL: `https://openrouter.ai/api/v1` or custom endpoints.

Configuration settings are stored securely with `0700` permissions at `~/.config/kali-ai/config.json`.

---

## 🛡️ Security Guardrails & Safety Architecture

> [!IMPORTANT]
> Kali-AI operates with strict **Human-in-the-Loop Interception Guardrails**.

* **Approval Banner**: Every shell command generated by the AI requires explicit user review (`[Approve Execution]` / `[Reject]`).
* **Blacklisted Destructive Commands**: Auto-blocks destructive system commands (`rm -rf /`, `:(){ :|:& };:`, disk formatting, raw block device writes).
* **Target Scope Enforcement**: Rejects command execution against IP targets outside the user-defined allowed target scope.

---

## 📄 License

This project is licensed under the MIT License - see the `LICENSE` file for details.

---

<p center="align">
  <b>Developed for Ethical Hackers, Security Analysts, and Penetration Testers.</b><br>
  <i>Use responsibly and only on networks/systems you have explicit authorization to audit.</i>
</p>
