"""
Enhanced Self-Learning & User-Preference Memory Engine for Kali-AI Agent.

Two kinds of learning are combined:

1. AUTOMATIC (observed) — every executed command updates per-tool success/failure
   statistics, usage counts, discovered targets, and lightweight habit keywords.

2. AI-DRIVEN (reflective) — the model records durable lessons it reasons out:
     • learned_corrections   — fixes discovered from failures ("nmap -sS needs sudo")
     • learned_preferences   — user habits it infers ("prefers rockyou.txt wordlist")
     • successful_workflows  — reusable summaries of goals that worked

All state persists to ~/.config/kali-ai/memory.json and is injected into every
system prompt so the agent gets measurably smarter the more it is used.
"""

import datetime
import json
import os
import re

_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "kali-ai")
MEMORY_FILE = os.path.join(_CONFIG_DIR, "memory.json")

DEFAULT_MEMORY = {
    "user_preferences": [
        "Prefers step-by-step strategic execution plan before running commands",
        "Prefers concise, expert-level technical explanations",
    ],
    "favorite_tools": [],            # back-compat: ordered list of tool names
    "tool_stats": {},                # {tool: {"success": int, "fail": int, "last_used": iso}}
    "learned_corrections": [],       # AI-recorded fixes from failures
    "learned_preferences": [],       # AI-inferred user habits
    "successful_workflows": [],      # [{"goal":..., "summary":..., "ts":...}]
    "engagement_findings": [],       # AI-recorded findings (hosts/ports/creds/vulns)
    "target_history": [],            # IPs / domains seen in commands
    "total_commands": 0,
    "total_tasks_completed": 0,
}

# Caps so the file and the prompt section stay bounded.
_MAX_CORRECTIONS = 25
_MAX_PREFERENCES = 15
_MAX_WORKFLOWS = 15
_MAX_TARGETS = 30
_MAX_FAV_TOOLS = 20
_MAX_FINDINGS = 40


def _ensure_dir():
    if not os.path.exists(_CONFIG_DIR):
        os.makedirs(_CONFIG_DIR, mode=0o700, exist_ok=True)


def load_memory() -> dict:
    """Load persistent memory, filling any missing keys with defaults."""
    _ensure_dir()
    memory = json.loads(json.dumps(DEFAULT_MEMORY))  # deep copy of defaults
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                memory.update(data)
        except Exception:
            pass
    # Guarantee structural keys exist even if an older file is loaded.
    for key, default in DEFAULT_MEMORY.items():
        memory.setdefault(key, json.loads(json.dumps(default)))
    return memory


def save_memory(memory: dict) -> None:
    _ensure_dir()
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ── helpers ──────────────────────────────────────────────────────────────────────
def _extract_tool(command: str) -> str:
    """Best-effort: the meaningful program name in a command (skips sudo/env/VAR=)."""
    tokens = command.strip().split()
    for tok in tokens:
        if not tok or tok in ("sudo", "env", "time", "nohup", "exec"):
            continue
        if tok.startswith("-") or "=" in tok:
            continue
        # strip path, keep the binary name
        return os.path.basename(tok)
    return ""


_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_DOMAIN_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.IGNORECASE)


def _extract_targets(command: str) -> list:
    targets = set()
    for ip in _IP_RE.findall(command):
        if ip not in ("127.0.0.1", "0.0.0.0"):
            targets.add(ip)
    # Only treat domains inside URLs or obvious host args as targets, keep it light.
    for dom in _DOMAIN_RE.findall(command):
        if not dom.endswith((".sh", ".py", ".txt", ".conf", ".log", ".json", ".xml")):
            targets.add(dom.lower())
    return list(targets)


def _dedupe_cap(items: list, cap: int) -> list:
    """De-duplicate (case-insensitive for strings) keeping the latest, capped to `cap`."""
    seen, out = set(), []
    # Walk newest-first so the most recent phrasing of a repeated item wins, then restore order.
    for it in reversed(items):
        key = json.dumps(it, sort_keys=True) if isinstance(it, dict) else " ".join(str(it).lower().split())
        if key not in seen:
            seen.add(key)
            out.append(it)
    out.reverse()
    return out[-cap:]


# ── automatic (observed) learning ─────────────────────────────────────────────────
def record_command(user_input: str, command_executed: str = "", was_successful: bool = True):
    """Update tool stats, usage, targets, and habit keywords from one command."""
    memory = load_memory()
    memory["total_commands"] = memory.get("total_commands", 0) + 1

    tool = _extract_tool(command_executed)
    if tool and len(tool) > 1:
        stats = memory.setdefault("tool_stats", {})
        entry = stats.setdefault(tool, {"success": 0, "fail": 0, "last_used": ""})
        entry["success" if was_successful else "fail"] += 1
        entry["last_used"] = datetime.datetime.now().isoformat(timespec="seconds")

        # favorite_tools = most-used tools, ranked by total invocations.
        ranked = sorted(
            stats.items(),
            key=lambda kv: kv[1].get("success", 0) + kv[1].get("fail", 0),
            reverse=True,
        )
        memory["favorite_tools"] = [name for name, _ in ranked[:_MAX_FAV_TOOLS]]

    targets = memory.get("target_history", [])
    for t in _extract_targets(command_executed):
        targets.append(t)
    memory["target_history"] = _dedupe_cap(targets, _MAX_TARGETS)

    # Lightweight habit keywords from the user's phrasing.
    prefs = memory.get("user_preferences", [])
    habit_map = {
        "fast": "Prefers fast scans & execution",
        "quick": "Prefers fast scans & execution",
        "quiet": "Prefers stealthy/quiet scans",
        "stealth": "Prefers stealthy/quiet scans",
        "aggressive": "Comfortable with aggressive scanning",
        "verbose": "Prefers verbose output",
        "detail": "Prefers detailed explanations",
    }
    low = (user_input or "").lower()
    for kw, pref in habit_map.items():
        if kw in low and pref not in prefs:
            prefs.append(pref)
    memory["user_preferences"] = prefs[-12:]

    save_memory(memory)


# Back-compat alias (callers may still use the old name).
def learn_from_interaction(user_input: str, command_executed: str = "", was_successful: bool = True):
    record_command(user_input, command_executed, was_successful)


# ── AI-driven (reflective) learning ───────────────────────────────────────────────
def add_learned_correction(correction: str):
    """Register a durable fix the AI reasoned out from a failure."""
    correction = (correction or "").strip()
    if not correction:
        return
    memory = load_memory()
    corrections = memory.get("learned_corrections", [])
    corrections.append(correction)
    memory["learned_corrections"] = _dedupe_cap(corrections, _MAX_CORRECTIONS)
    save_memory(memory)


def add_learned_preference(preference: str):
    """Register a user habit/preference the AI inferred."""
    preference = (preference or "").strip()
    if not preference:
        return
    memory = load_memory()
    prefs = memory.get("learned_preferences", [])
    prefs.append(preference)
    memory["learned_preferences"] = _dedupe_cap(prefs, _MAX_PREFERENCES)
    save_memory(memory)


def record_workflow(goal: str, summary: str):
    """Store a reusable summary of a workflow that achieved its goal."""
    summary = (summary or "").strip()
    if not summary:
        return
    memory = load_memory()
    wf = memory.get("successful_workflows", [])
    wf.append({
        "goal": (goal or "").strip()[:200],
        "summary": summary[:600],
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
    })
    memory["successful_workflows"] = wf[-_MAX_WORKFLOWS:]
    save_memory(memory)


def record_finding(finding: str):
    """Persist a concise engagement finding (host/port/service/cred/vuln/foothold)."""
    finding = (finding or "").strip()
    if not finding:
        return
    memory = load_memory()
    findings = memory.get("engagement_findings", [])
    findings.append(finding)
    memory["engagement_findings"] = _dedupe_cap(findings, _MAX_FINDINGS)
    save_memory(memory)


def increment_task_completed():
    memory = load_memory()
    memory["total_tasks_completed"] = memory.get("total_tasks_completed", 0) + 1
    save_memory(memory)


def reset_memory():
    """Wipe learned memory back to defaults."""
    save_memory(json.loads(json.dumps(DEFAULT_MEMORY)))


# ── prompt injection ───────────────────────────────────────────────────────────────
def get_memory_summary_for_ai() -> str:
    """Format persistent memory into a rich system-prompt section."""
    memory = load_memory()
    tasks = memory.get("total_tasks_completed", 0)
    cmds = memory.get("total_commands", 0)

    lines = [f"\n[Persistent Self-Learning Memory (tasks completed: {tasks}, commands run: {cmds})]:"]

    prefs = memory.get("user_preferences", [])
    if prefs:
        lines.append("• User preferences: " + "; ".join(prefs))

    learned_prefs = memory.get("learned_preferences", [])
    if learned_prefs:
        lines.append("• Learned user habits: " + "; ".join(learned_prefs))

    # Top tools with success rates so the AI favours what reliably works here.
    stats = memory.get("tool_stats", {})
    if stats:
        ranked = sorted(
            stats.items(),
            key=lambda kv: kv[1].get("success", 0) + kv[1].get("fail", 0),
            reverse=True,
        )[:10]
        parts = []
        for name, s in ranked:
            total = s.get("success", 0) + s.get("fail", 0)
            rate = int(100 * s.get("success", 0) / total) if total else 0
            parts.append(f"{name}({s.get('success',0)}/{total}, {rate}% ok)")
        lines.append("• Frequently used tools: " + ", ".join(parts))

    corrections = memory.get("learned_corrections", [])
    if corrections:
        lines.append("• Learned corrections (apply these to avoid past mistakes):")
        for c in corrections[-8:]:
            lines.append(f"   - {c}")

    findings = memory.get("engagement_findings", [])
    if findings:
        lines.append("• Engagement findings so far (build on these, don't re-discover):")
        for fnd in findings[-15:]:
            lines.append(f"   - {fnd}")

    workflows = memory.get("successful_workflows", [])
    if workflows:
        lines.append("• Recent successful workflows:")
        for wf in workflows[-4:]:
            goal = wf.get("goal", "")
            summ = wf.get("summary", "")
            lines.append(f"   - [{goal}] {summ}")

    targets = memory.get("target_history", [])
    if targets:
        lines.append("• Recently seen targets: " + ", ".join(targets[-10:]))

    return "\n".join(lines)
