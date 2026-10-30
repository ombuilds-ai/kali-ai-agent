"""Security guardrails — destructive command filter & target scope enforcement for Kali-AI Agent.

Prevents execution of catastrophic/destructive commands that could
damage the host system irreversibly and enforces Target Scope boundaries.
"""

import ipaddress
import re
from typing import Optional, List

# Target Scope Boundary Storage
_ALLOWED_TARGET_SCOPES: List[str] = []

def set_allowed_target_scopes(scopes: List[str]):
    """Set authorized target IP ranges/domains (e.g. ['192.168.1.0/24', '10.0.0.5', 'example.com'])."""
    global _ALLOWED_TARGET_SCOPES
    _ALLOWED_TARGET_SCOPES = [s.strip() for s in scopes if s.strip()]

def get_allowed_target_scopes() -> List[str]:
    """Get active authorized target scopes."""
    return _ALLOWED_TARGET_SCOPES

# Patterns that match catastrophic / destructive commands.
_BLOCKED_PATTERNS: list[tuple[re.Pattern, str]] = [
    # rm -rf / variants
    (re.compile(r"\brm\s+.*-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/\s*$", re.I),
     "Recursive forced deletion of root filesystem"),
    (re.compile(r"\brm\s+.*-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*\s+/\s*$", re.I),
     "Recursive forced deletion of root filesystem"),
    (re.compile(r"\brm\s+.*-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/\*", re.I),
     "Recursive forced deletion of root contents"),
    (re.compile(r"\brm\s+.*-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*\s+/\*", re.I),
     "Recursive forced deletion of root contents"),
    (re.compile(r"\brm\s+-r\s+-f\s+/", re.I),
     "Recursive forced deletion of root (split flags)"),
    (re.compile(r"\brm\s+-f\s+-r\s+/", re.I),
     "Recursive forced deletion of root (split flags)"),
    (re.compile(r"\brm\s+--no-preserve-root", re.I),
     "rm with --no-preserve-root flag"),

    # Filesystem destruction
    (re.compile(r"\bmkfs\b", re.I),
     "Filesystem format command"),
    (re.compile(r"\bparted\s+.*\bmklabel\b", re.I),
     "Partition table destruction"),

    # Fork bomb
    (re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;", re.I),
     "Fork bomb"),
    (re.compile(r"\bfork\s*bomb\b", re.I),
     "Fork bomb reference"),

    # Disk wipe
    (re.compile(r"\bdd\s+.*of=/dev/[sh]d", re.I),
     "Direct disk write with dd"),
    (re.compile(r">\s*/dev/[sh]d", re.I),
     "Redirect output to raw disk"),
    (re.compile(r"\bshred\s+.*(/dev/[sh]d|/boot|/etc|/usr|/var)", re.I),
     "Shredding critical system paths"),

    # Permission destruction
    (re.compile(r"\bchmod\s+(-R\s+)?0?0?0\s+/\s*$", re.I),
     "Removing all permissions from root"),
    (re.compile(r"\bchmod\s+(-R\s+)?0?0?0\s+/(etc|usr|var|boot|bin|sbin|lib)\b", re.I),
     "Removing all permissions from critical directories"),
    (re.compile(r"\bchown\s+(-R\s+)?.*\s+/\s*$", re.I),
     "Recursive ownership change on root"),

    # Pipe to shell
    (re.compile(r"\b(wget|curl)\s+.*\|\s*(ba)?sh\b", re.I),
     "Piping downloaded content directly to shell"),
    (re.compile(r"\b(wget|curl)\s+.*\|\s*python", re.I),
     "Piping downloaded content directly to python"),

    # System shutdown/halt
    (re.compile(r"\b(halt|poweroff|shutdown|init\s+0)\b", re.I),
     "System shutdown/halt command"),
    (re.compile(r"\bsystemctl\s+(poweroff|halt|reboot)\b", re.I),
     "Systemctl shutdown command"),

    # Critical file deletion
    (re.compile(r"\brm\s+.*/(etc/passwd|etc/shadow|etc/sudoers)\b", re.I),
     "Deletion of critical authentication files"),
    (re.compile(r"\brm\s+.*/(boot/vmlinuz|boot/initrd|boot/grub)\b", re.I),
     "Deletion of boot files"),

    # Firewall flush
    (re.compile(r"\biptables\s+(-F|--flush)\b", re.I),
     "Flushing all firewall rules"),
    (re.compile(r"\bnft\s+flush\s+ruleset\b", re.I),
     "Flushing nftables ruleset"),

    # Dangerous eval patterns
    (re.compile(r"\beval\s+.*\$\(.*base64\s+-d", re.I),
     "Eval with base64 decoded content"),

    # Recursive deletion of home / critical system directories (beyond bare root)
    (re.compile(r"\brm\s+(?:-\S+\s+)*-?\S*r\S*f\S*\s+(?:~|\$HOME)(?:/|\s|$)", re.I),
     "Recursive forced deletion of the home directory"),
    (re.compile(r"\brm\s+(?:-\S+\s+)*-?\S*[rf]\S*[rf]\S*\s+/(?:etc|var|usr|bin|sbin|lib|lib64|boot|root|home|opt)(?:/\s|/?$|\s)", re.I),
     "Recursive forced deletion of a critical system directory"),

    # Mass deletion via find
    (re.compile(r"\bfind\s+/(?:etc|var|usr|bin|sbin|lib|boot|root|home)?\S*\s+.*-delete\b", re.I),
     "Mass deletion via find -delete on system paths"),
    (re.compile(r"\bfind\s+/\S*\s+.*-exec\s+rm\b", re.I),
     "Mass deletion via find -exec rm"),

    # Disk writes to any block device (extends sd/hd to nvme/vd/mmc)
    (re.compile(r"\bdd\s+.*of=/dev/(?:sd|hd|nvme|vd|mmcblk|loop)", re.I),
     "Direct disk write with dd"),
    (re.compile(r">\s*/dev/(?:sd|hd|nvme|vd|mmcblk)", re.I),
     "Redirect output to a raw disk device"),

    # Moving/overwriting critical system paths
    (re.compile(r"\bmv\s+.*\s+/(?:etc|boot|bin|sbin|lib|lib64|usr)(?:/\s*$|\s*$)", re.I),
     "Moving over a critical system directory"),
    (re.compile(r">\s*/(?:etc/(?:passwd|shadow|sudoers|fstab|hosts)|boot/\S+)\b", re.I),
     "Overwriting a critical system/auth file"),

    # Recursive permission/ownership changes on system trees
    (re.compile(r"\bchmod\s+-R\s+\S+\s+/(?:etc|usr|var|boot|bin|sbin|lib|lib64|root)\b", re.I),
     "Recursive permission change on a system directory"),
    (re.compile(r"\bchown\s+-R\s+\S+\s+/(?:etc|usr|var|boot|bin|sbin|lib|lib64|root)\b", re.I),
     "Recursive ownership change on a system directory"),

    # Wipe all cron jobs
    (re.compile(r"\bcrontab\s+-r\b", re.I),
     "Removing all cron jobs"),

    # Overwrite the whole disk with zeros/random
    (re.compile(r"\b(?:cat|dd)\s+.*/dev/(?:zero|u?random)\s*.*of=/dev/", re.I),
     "Overwriting a disk with zero/random data"),
]


def check_scope_compliance(command: str) -> tuple[bool, str]:
    """Check if command IP matches specified authorized target scope."""
    if not _ALLOWED_TARGET_SCOPES:
        return True, ""
        
    # Extract IP addresses from command string
    found_ips = re.findall(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", command)
    for ip in found_ips:
        if ip in ["127.0.0.1", "0.0.0.0"]:
            continue
        try:
            target_obj = ipaddress.ip_address(ip)
            in_scope = False
            for scope in _ALLOWED_TARGET_SCOPES:
                try:
                    net = ipaddress.ip_network(scope, strict=False)
                    if target_obj in net:
                        in_scope = True
                        break
                except ValueError:
                    if scope.lower() in command.lower() or ip == scope:
                        in_scope = True
                        break
            if not in_scope:
                return False, f"🎯 Out-of-Scope Protection: IP {ip} is not in authorized target scopes ({', '.join(_ALLOWED_TARGET_SCOPES)})"
        except ValueError:
            pass
            
    return True, ""


def is_command_blocked(command: str) -> tuple[bool, str]:
    """Return (True, reason) if the command matches a destructive pattern or violates target scope."""
    stripped = command.strip()
    
    # 1. Destructive pattern check
    for pat, description in _BLOCKED_PATTERNS:
        if pat.search(stripped):
            return True, f"⛔ Blocked: {description}"
            
    # 2. Scope compliance check
    allowed, scope_reason = check_scope_compliance(stripped)
    if not allowed:
        return True, scope_reason
        
    return False, ""


# Commands that are legitimate but impactful enough to always need a human OK,
# even when "auto-run safe commands" mode is enabled. (Blocked commands never run.)
_CONFIRM_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(rm|rmdir|shred|unlink)\b", re.I), "Deletes files"),
    (re.compile(r"\bdd\b", re.I), "Raw disk/file write (dd)"),
    (re.compile(r"\b(mkfs\w*|mke2fs|fdisk|sfdisk|parted|gparted|wipefs|mkswap)\b", re.I), "Disk/partition operation"),
    (re.compile(r"\b(kill|pkill|killall)\b", re.I), "Terminates processes"),
    (re.compile(r"\bsystemctl\s+(stop|disable|mask|restart|reload)\b", re.I), "Changes a system service"),
    (re.compile(r"\bservice\s+\S+\s+(stop|restart|reload)\b", re.I), "Changes a system service"),
    (re.compile(r"\b(ip6?tables)\b.*\s-(A|I|D|F|X|P|N)\b", re.I), "Modifies firewall rules"),
    (re.compile(r"\bufw\s+(enable|disable|allow|deny|reset|delete)\b", re.I), "Modifies firewall (ufw)"),
    (re.compile(r"\bnft\b.*\b(add|delete|flush)\b", re.I), "Modifies nftables"),
    (re.compile(r"\b(useradd|userdel|usermod|groupadd|groupdel|chpasswd|adduser|deluser)\b", re.I), "User/group/credential change"),
    (re.compile(r"(?<![\w/.\-])passwd\b", re.I), "Changes a password"),
    (re.compile(r"\bchmod\s+-R\b", re.I), "Recursive permission change"),
    (re.compile(r"\bchown\s+-R\b", re.I), "Recursive ownership change"),
    (re.compile(r"\b(mount|umount)\b", re.I), "Mounts/unmounts a filesystem"),
    (re.compile(r"\bapt(-get)?\s+(remove|purge|autoremove)\b", re.I), "Removes system packages"),
    (re.compile(r"\bdpkg\s+(-r|--remove|-P|--purge)\b", re.I), "Removes system packages"),
    (re.compile(r"\bcrontab\s+-e\b", re.I), "Edits scheduled jobs"),
    (re.compile(r"\btruncate\b", re.I), "Truncates a file"),
    (re.compile(r"\b(insmod|rmmod)\b|\bmodprobe\s+-r\b", re.I), "Kernel module change"),
]


def requires_confirmation(command: str) -> tuple[bool, str]:
    """Return (True, reason) for impactful-but-legit commands that still need approval."""
    stripped = command.strip()
    for pat, description in _CONFIRM_PATTERNS:
        if pat.search(stripped):
            return True, description
    return False, ""


def classify_command(command: str) -> tuple[str, str]:
    """Classify a command: 'blocked' | 'confirm' | 'auto', with a reason."""
    blocked, reason = is_command_blocked(command)
    if blocked:
        return "blocked", reason
    needs, reason = requires_confirmation(command)
    if needs:
        return "confirm", reason
    return "auto", ""
