"""
Persistent Self-Learning & User Preference Memory Engine for Kali-AI Agent.
Saves learned user habits, preferred tool flags, workflow patterns, and self-corrections
to ~/.config/kali-ai/memory.json to continuously adapt and improve over time.
"""

import json
import os
import sys

_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "kali-ai")
MEMORY_FILE = os.path.join(_CONFIG_DIR, "memory.json")

DEFAULT_MEMORY = {
    "user_preferences": [
        "Prefers step-by-step strategic execution plan before running commands",
        "Prefers concise, expert-level technical explanations"
    ],
    "favorite_tools": [],
    "learned_corrections": [],
    "successful_workflows": [],
    "total_tasks_completed": 0
}


def _ensure_dir():
    if not os.path.exists(_CONFIG_DIR):
        os.makedirs(_CONFIG_DIR, mode=0o700, exist_ok=True)


def load_memory() -> dict:
    """Load persistent self-learning memory from disk."""
    _ensure_dir()
    memory = dict(DEFAULT_MEMORY)
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                memory.update(data)
        except Exception:
            pass
    return memory


def save_memory(memory: dict) -> None:
    """Save persistent self-learning memory to disk."""
    _ensure_dir()
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2)
    except Exception:
        pass


def learn_from_interaction(user_input: str, command_executed: str = "", was_successful: bool = True):
    """Automatically analyze interaction and update self-learning memory."""
    memory = load_memory()
    
    if was_successful:
        memory["total_tasks_completed"] = memory.get("total_tasks_completed", 0) + 1
        
    if command_executed:
        tool = command_executed.strip().split()[0]
        favs = memory.get("favorite_tools", [])
        if tool not in favs and len(tool) > 1 and not tool.startswith("-"):
            favs.append(tool)
            memory["favorite_tools"] = favs[:15] # keep top 15
            
    # Auto-learn user habits
    prefs = memory.get("user_preferences", [])
    if "fast" in user_input.lower() and "Prefers fast scan & execution" not in prefs:
        prefs.append("Prefers fast scan & execution")
    if "quiet" in user_input.lower() and "Prefers stealthy/quiet scans" not in prefs:
        prefs.append("Prefers stealthy/quiet scans")
        
    memory["user_preferences"] = prefs[:10]
    save_memory(memory)


def add_learned_correction(correction: str):
    """Register a self-correction learned from command failure."""
    memory = load_memory()
    corrections = memory.get("learned_corrections", [])
    if correction and correction not in corrections:
        corrections.append(correction)
        memory["learned_corrections"] = corrections[-10:] # Keep recent 10
        save_memory(memory)


def get_memory_summary_for_ai() -> str:
    """Format persistent memory into a system prompt section."""
    memory = load_memory()
    prefs = memory.get("user_preferences", [])
    favs = memory.get("favorite_tools", [])
    corrections = memory.get("learned_corrections", [])
    completed = memory.get("total_tasks_completed", 0)
    
    lines = [f"\n[Persistent Self-Learning Memory & User Profile (Tasks Completed: {completed})]:"]
    
    if prefs:
        lines.append("• User Preferences: " + "; ".join(prefs))
    if favs:
        lines.append("• Frequently Used Tools: " + ", ".join(favs))
    if corrections:
        lines.append("• Learned System Corrections: " + "; ".join(corrections))
        
    return "\n".join(lines)
