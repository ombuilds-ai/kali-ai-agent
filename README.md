# 🐉 Kali-AI Agent by Om v3.0

> **Autonomous Penetration Testing Co-Pilot & Security Operations AI for Kali Linux**
> Control, audit, and analyze your entire Kali Linux environment through natural language pair-programming with Gemini, OpenRouter, AgentRouter, or any OpenAI-compatible LLM.

![Version](https://img.shields.io/badge/version-3.0-blue?style=for-the-badge&logo=kali-linux)
![Author](https://img.shields.io/badge/author-Om-orange?style=for-the-badge)
![Platform](https://img.shields.io/badge/platform-Kali%20Linux%20%7C%20Linux-purple?style=for-the-badge&logo=linux)
![Python](https://img.shields.io/badge/python-3.10%2B-green?style=for-the-badge&logo=python)
![License](https://img.shields.io/badge/license-MIT-red?style=for-the-badge)

---

## 📸 Overview

**Kali-AI Agent by Om v3.0** is a cybersecurity desktop co-pilot engineered for Kali Linux. It works shoulder-to-shoulder with security researchers — combining a **real terminal-grade execution engine**, autonomous tool execution, live system & tool awareness, self-learning memory, and tiered human-in-the-loop safety.

v3.0 is a major engine overhaul focused on actually controlling Linux like a human operator at a terminal.

---

## ✨ Key Features

### 🖥️ 1. Persistent Terminal Engine (`shell_session.py`)
The agent drives **one long-lived bash session attached to a PTY**, so it behaves like a real terminal user:
* **State persists** across commands — `cd`, `export`, `source`, venv activation and shell variables all survive between turns.
* **Real TTY** — `sudo`, `apt`, `ssh` and other interactive tools work because they get a genuine terminal.
* **Live streaming** — command output appears in the terminal panel as it is produced, not after the command finishes.
* **Interrupt without killing the shell** — the Stop button sends Ctrl-C to the running command; the session stays alive with its state intact.
* **Real exit codes** — each command's true exit status is captured and fed back to the AI.

### 🔐 2. Automatic Sudo Handling
When a command needs root, the agent prompts you once per session for your sudo password (kept **only in memory**, never written to disk) and auto-supplies it whenever `sudo` asks. If you are already root, it skips sudo entirely.

### 🧰 3. Structured Tools & Interactive Control
Beyond plain shell commands, the agent has dedicated tools:
* **`read_file` / `write_file`** — reliable structured file I/O instead of fragile `cat`/`echo >`/heredocs.
* **`send_input`** — drive interactive programs (msfconsole, python3 REPL, `[y/n]` prompts, menus). When a command pauses waiting for input, the agent can answer and the command continues in the same session.

### 🧠 4. Live Environment & Tool Awareness (`environment.py`)
Every turn the AI is grounded with real facts about the host: distribution, kernel, hostname, whether it is **root**, and a scan of which offensive-security tools (`nmap`, `metasploit`, `sqlmap`, `hashcat`, `hydra`, …) are actually installed — so it uses available tools instead of guessing, and installs what's missing.

### 🤖 5. Agentic Observe–Act Loop
The agent runs a goal → act → observe output → act again loop, signalling `task_complete` when the objective is done. A safety cap bounds runaway loops, and the robust JSON parser reliably decodes tool calls even when file payloads contain code, braces, or quotes.

### 🛡️ 6. Tiered Human-in-the-Loop Safety (`guardrails.py`)
Commands are classified into three tiers:
* **Blocked** — catastrophic commands never run (`rm -rf /` & home/system variants, `mkfs`, raw disk writes, fork bombs, firewall flushes, auth-file overwrites, …).
* **Confirm** — impactful-but-legitimate commands always require your approval (`rm`, `dd`, `kill`, service/firewall/user-management changes, mounts, package removal, recursive `chmod`/`chown`, …).
* **Auto** — safe/read-only commands. With **⚡ Auto-run safe commands** enabled, these execute automatically for true hands-off recon; everything risky still pauses for approval.

Plus a **🎯 Target Scope Guard** (restrict to authorized CIDRs/IPs/domains) and an **audit log** of every executed/blocked command at `~/.config/kali-ai/audit.log`.

### 💬 7. Natural Pair-Programming Co-Pilot
Talks first and aligns on a plan before executing, in Hindi / Hinglish / English. Interactive decision buttons let you pick targets/options directly in chat, and the input bar stays unlocked for mid-execution steering notes.

### 🧠 8. Self-Learning Memory & Session Persistence
Learns preferred tools and habits over time (`memory.py` → `~/.config/kali-ai/memory.json`), auto-saves every conversation (`sessions.py`), and keeps a bounded rolling context window so long sessions stay fast and don't re-send old screenshots.

### 🎛️ 9. Dynamic Model Switcher & Dual Providers
Auto-detects models from OpenAI/OpenRouter/AgentRouter and Google Gemini, with a one-click model switcher on the input bar.

---

## 📁 Repository Structure

```
kali-ai/
├── main.py            # Application launcher & entry point
├── gui.py             # PyQt6 GUI, chat, inventory, approval banners, dialogs
├── ai_engine.py       # Dual provider (Gemini + OpenAI/OpenRouter), prompt, robust JSON parsing
├── shell_session.py   # Persistent PTY bash session (state, sudo, streaming, interrupt, exit codes)
├── executor.py        # Execution engine (bash via shell_session, GUI actions, audit log)
├── tools.py           # Structured file tools (read_file / write_file / list_dir)
├── environment.py     # Live host + installed-tool awareness injected into the prompt
├── guardrails.py      # Tiered safety: blocked / confirm / auto + target-scope enforcement
├── memory.py          # Persistent self-learning user profile & habit memory
├── sessions.py        # Persistent disk storage for conversation sessions
├── config.py          # Config management (~/.config/kali-ai/config.json)
├── screenshot.py      # Multi-backend screenshot capture (mss / PIL / PyQt6)
├── requirements.txt   # Required Python packages
├── install.sh         # Self-contained single-file installer & uninstaller
├── run.sh             # Virtualenv auto-management launcher
├── build.sh           # Standalone binary compiler (PyInstaller)
├── builder.py         # Generates the self-extracting install.sh
└── README.md          # Project documentation
```

---

## 🚀 Installation & Usage

### Method 1: Single-File Installer (Recommended)
Download `install.sh` to your Kali machine and run:
```bash
bash install.sh
```
Extracts all source into `~/KaliAI/`, installs system + pip dependencies, and creates a desktop/app-menu shortcut. Uninstall anytime: `bash install.sh --uninstall`.

### Method 2: Direct Run
```bash
git clone https://github.com/ombuilds-ai/kali-ai-agent.git
cd kali-ai-agent
chmod +x run.sh
./run.sh
```

### Method 3: Standalone Binary
```bash
chmod +x build.sh
./build.sh      # output: dist/KaliAI-Agent
```

> **Note:** The persistent PTY terminal engine is Linux-only. On non-Linux hosts the app runs with a degraded per-command fallback (no state persistence) for UI testing.

---

## ⚙️ Configuration & API Setup

Dual AI provider backends:

1. **Google Gemini** — free key from [Google AI Studio](https://aistudio.google.com/). Models: `gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-1.5-pro`, …
2. **OpenAI / OpenRouter / Custom** — works with OpenRouter, AgentRouter, Ollama, vLLM, LM Studio, or OpenAI. Default Base URL `https://openrouter.ai/api/v1`.

Config is stored with `0600` permissions at `~/.config/kali-ai/config.json`.

---

## 🛡️ Security & Responsible Use

> [!IMPORTANT]
> This tool executes real commands on your system, including with root privileges. Use it only on systems and networks you are explicitly authorized to test.

* **Tiered guardrails** — catastrophic commands are blocked; impactful ones require approval; safe ones can auto-run (opt-in).
* **Target Scope Guard** — rejects commands aimed at IPs/domains outside your authorized scope.
* **Audit log** — every executed and blocked command is recorded at `~/.config/kali-ai/audit.log`.
* **Sudo password** — held in memory for the session only, never persisted.

---

## 📄 License

MIT License — see the `LICENSE` file.

---

<p align="center">
  <b>Developed for Ethical Hackers, Security Analysts, and Penetration Testers.</b><br>
  <i>Use responsibly and only on networks/systems you have explicit authorization to audit.</i>
</p>
