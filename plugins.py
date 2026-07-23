"""
Modular Plugin & Extension System for Kali-AI Agent.
Allows custom Python scripts or shell tools placed in ~/KaliAI/plugins/
to be automatically loaded and made available to the AI Engine.
"""

import importlib.util
import os
import shutil
import sys
from typing import Callable, Dict

PLUGIN_DIR = os.path.join(os.path.expanduser("~"), "KaliAI", "plugins")

def ensure_plugin_dir() -> str:
    """Create plugins directory if it doesn't exist and add a sample plugin."""
    if not os.path.exists(PLUGIN_DIR):
        os.makedirs(PLUGIN_DIR, exist_ok=True)
        
        # Create a sample custom plugin
        sample_path = os.path.join(PLUGIN_DIR, "custom_port_scanner.py")
        if not os.path.exists(sample_path):
            with open(sample_path, "w", encoding="utf-8") as f:
                f.write('''"""
Sample Kali-AI Custom Plugin
"""
def plugin_info():
    return {
        "name": "Custom Port Checker",
        "description": "Quickly checks if port 80/443/22 are open on a target IP.",
        "command_keyword": "check_ports"
    }

def run_plugin(target_ip="127.0.0.1"):
    import socket
    results = []
    for port in [22, 80, 443]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        res = s.connect_ex((target_ip, port))
        s.close()
        status = "OPEN" if res == 0 else "CLOSED"
        results.append(f"Port {port}: {status}")
    return "\\n".join(results)
''')
    return PLUGIN_DIR


def load_installed_plugins() -> Dict[str, dict]:
    """Scan ~/KaliAI/plugins/ and load all valid Python plugins."""
    ensure_plugin_dir()
    plugins = {}
    
    if not os.path.exists(PLUGIN_DIR):
        return plugins

    for fname in os.listdir(PLUGIN_DIR):
        if fname.endswith(".py") and not fname.startswith("_"):
            fpath = os.path.join(PLUGIN_DIR, fname)
            mod_name = fname[:-3]
            try:
                spec = importlib.util.spec_from_file_location(mod_name, fpath)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    
                    if hasattr(mod, "plugin_info") and hasattr(mod, "run_plugin"):
                        info = mod.plugin_info()
                        info["filepath"] = fpath
                        info["module"] = mod
                        plugins[info.get("name", mod_name)] = info
            except Exception as e:
                print(f"[Plugin Warning] Could not load {fname}: {e}")
                
    return plugins


def import_plugin_file(source_path: str) -> tuple[bool, str]:
    """Copy a custom plugin .py file into ~/KaliAI/plugins/."""
    ensure_plugin_dir()
    if not os.path.exists(source_path):
        return False, "File does not exist."
        
    if not source_path.endswith(".py"):
        return False, "Only Python (.py) plugin files are supported."
        
    dest_name = os.path.basename(source_path)
    dest_path = os.path.join(PLUGIN_DIR, dest_name)
    
    try:
        shutil.copy2(source_path, dest_path)
        return True, f"Plugin imported successfully to {dest_path}"
    except Exception as e:
        return False, f"Failed to import plugin: {e}"


get_plugin_summary_for_ai = lambda: get_plugin_summary_text()

def get_plugin_summary_text() -> str:
    """Generate prompt string listing custom loaded plugins for AI awareness."""
    plugins = load_installed_plugins()
    if not plugins:
        return ""
        
    lines = ["\n[Custom User Plugins Loaded in ~/KaliAI/plugins/]:"]
    for name, info in plugins.items():
        kw = info.get("command_keyword", name)
        desc = info.get("description", "Custom user plugin script")
        lines.append(f"- Plugin '{name}' (keyword: '{kw}'): {desc}")
    return "\n".join(lines)
