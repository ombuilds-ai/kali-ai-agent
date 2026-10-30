"""
Live system environment awareness for Kali-AI Agent.

Gives the AI real, grounded facts about the machine it is driving (distro, kernel,
whether it is root, hostname, shell) so it stops guessing — e.g. it knows NOT to use
sudo when already root, and which package manager/distro it is on.

Uses only the Python standard library so it is safe and cheap on any platform.
"""

import getpass
import os
import platform
import shutil
import socket

_cache = None
_tools_cache = None

# Curated toolset an offensive-security agent commonly reaches for. We report which
# are actually installed so the AI picks available tools instead of guessing.
_KNOWN_TOOLS = [
    "nmap", "masscan", "rustscan", "nikto", "gobuster", "ffuf", "dirb", "feroxbuster",
    "hydra", "medusa", "john", "hashcat", "sqlmap", "msfconsole", "msfvenom",
    "searchsploit", "aircrack-ng", "airmon-ng", "airodump-ng", "reaver", "wifite",
    "tshark", "tcpdump", "nc", "ncat", "socat", "curl", "wget", "git", "python3",
    "pip3", "gcc", "make", "enum4linux", "enum4linux-ng", "smbclient", "smbmap",
    "crackmapexec", "nxc", "responder", "wpscan", "whatweb", "dnsenum", "dnsrecon",
    "fierce", "theharvester", "recon-ng", "openssl", "ssh", "sshpass", "nuclei",
    "amass", "subfinder", "httpx", "wfuzz", "evil-winrm", "impacket-smbserver",
    "setoolkit", "bettercap", "ettercap", "proxychains", "sudo",
]


def _read_distro() -> str:
    try:
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release", "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return ""


def is_root() -> bool:
    if hasattr(os, "geteuid"):
        try:
            return os.geteuid() == 0
        except Exception:
            return False
    return False


def get_tool_availability_summary(force: bool = False) -> str:
    """Scan PATH for known offensive-security tools and summarize what's installed."""
    global _tools_cache
    if _tools_cache is not None and not force:
        return _tools_cache

    installed = [t for t in _KNOWN_TOOLS if shutil.which(t)]
    notable_missing = [
        t for t in ("nmap", "msfconsole", "sqlmap", "hydra", "hashcat", "john",
                    "gobuster", "nikto", "aircrack-ng", "nuclei")
        if t not in installed
    ]

    lines = ["[Installed Security Tools (detected on PATH)]:"]
    if installed:
        lines.append("- Available: " + ", ".join(installed))
    else:
        lines.append("- (none of the common tools were detected — this may not be a Kali host)")
    if notable_missing:
        lines.append("- NOT installed (install with apt before using): " + ", ".join(notable_missing))
    lines.append("- If a tool is missing, install it (e.g. `sudo apt install -y <pkg>`) before relying on it.")

    _tools_cache = "\n".join(lines)
    return _tools_cache


def get_environment_summary(force: bool = False) -> str:
    """Return a cached, prompt-ready summary of the host environment."""
    global _cache
    if _cache is not None and not force:
        return _cache

    try:
        user = getpass.getuser()
    except Exception:
        user = "unknown"
    try:
        host = socket.gethostname()
    except Exception:
        host = "unknown"
    try:
        cwd = os.getcwd()
    except Exception:
        cwd = "unknown"

    root = is_root()
    distro = _read_distro()
    shell = os.environ.get("SHELL", "unknown")

    lines = ["[Live System Environment]:"]
    lines.append(f"- OS / Kernel: {platform.platform()}")
    if distro:
        lines.append(f"- Distribution: {distro}")
    lines.append(f"- User: {user}  (root privileges: {'YES' if root else 'NO'})")
    lines.append(f"- Hostname: {host}")
    lines.append(f"- Default shell: {shell}")
    lines.append(f"- Initial working directory: {cwd}")
    if root:
        lines.append("- You are ALREADY root — do NOT prefix commands with sudo.")
    else:
        lines.append("- You are a non-root user — prefix privileged commands with sudo "
                     "(the password is supplied automatically when prompted).")

    _cache = "\n".join(lines)
    return _cache
