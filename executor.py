"""
Execution Engine for Kali-AI Agent.
Handles bash command execution and GUI automation via pyautogui.
"""

import shutil
import subprocess
import sys
import time
from typing import Optional

import pyautogui

from guardrails import is_command_blocked


class ExecutionResult:
    """Result of a command or GUI action execution."""

    def __init__(self, success: bool, stdout: str = "", stderr: str = "",
                 blocked: bool = False, reason: str = ""):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.blocked = blocked
        self.reason = reason

    def combined_output(self) -> str:
        """Combine stdout and stderr into a single string."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(f"[STDERR]\n{self.stderr}")
        return "\n".join(parts).strip()


def _get_shell() -> str:
    """Get the system shell executable path."""
    if sys.platform == "win32":
        return shutil.which("bash") or shutil.which("cmd") or "cmd"
    else:
        # Try bash first, then sh as fallback
        return shutil.which("bash") or shutil.which("sh") or "/bin/sh"


def run_bash(command: str, timeout: int = 45) -> ExecutionResult:
    """
    Execute a bash command safely without freezing.
    Returns an ExecutionResult with stdout/stderr.
    """
    # Safety check first
    blocked, reason = is_command_blocked(command)
    if blocked:
        return ExecutionResult(success=False, blocked=True, reason=reason)

    shell_executable = _get_shell()
    
    # Auto-protect infinite/interactive streaming tools from hanging forever
    cmd_trimmed = command.strip()
    cmd_lower = cmd_trimmed.lower()
    infinite_tools = ["airodump-ng", "tcpdump", "tshark", "top", "htop", "monit"]
    if any(tool in cmd_lower for tool in infinite_tools) and "timeout" not in cmd_lower:
        command = f"timeout 15 {cmd_trimmed}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            executable=shell_executable,
            stdin=subprocess.DEVNULL,  # Prevents interactive tools from hanging on stdin input
            env=None,  # Inherit current environment
        )

        # Truncate very long output to prevent memory issues
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        max_output = 50000  # 50KB limit

        if len(stdout) > max_output:
            stdout = stdout[:max_output] + f"\n\n[... output truncated, {len(result.stdout)} total chars ...]"
        if len(stderr) > max_output:
            stderr = stderr[:max_output] + f"\n\n[... stderr truncated, {len(result.stderr)} total chars ...]"

        return ExecutionResult(
            success=(result.returncode == 0 or result.returncode == 124), # 124 is standard timeout exit code
            stdout=stdout,
            stderr=stderr,
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            success=False,
            stderr=f"⏰ Command execution timed out after {timeout}s to prevent freeze.\n"
                   f"Output captured prior to timeout.",
        )
    except FileNotFoundError:
        return ExecutionResult(
            success=False,
            stderr=f"Shell not found: {shell_executable}. "
                   f"Ensure bash or sh is installed.",
        )
    except Exception as exc:
        return ExecutionResult(success=False, stderr=f"Execution error: {str(exc)}")


def run_gui_action(gui_action: dict) -> ExecutionResult:
    """
    Execute a GUI action (click or type) using pyautogui.
    Optimized for ultra-fast, smooth execution.
    """
    pyautogui.PAUSE = 0.02
    action_type = gui_action.get("type", "").lower()
    x = gui_action.get("x", 0)
    y = gui_action.get("y", 0)
    text = gui_action.get("text", "")

    try:
        if action_type == "click":
            pyautogui.moveTo(x, y, duration=0.08)
            pyautogui.click()
            return ExecutionResult(success=True, stdout=f"Clicked at ({x}, {y})")

        elif action_type == "doubleclick":
            pyautogui.moveTo(x, y, duration=0.08)
            pyautogui.doubleClick()
            return ExecutionResult(success=True, stdout=f"Double-clicked at ({x}, {y})")

        elif action_type == "rightclick":
            pyautogui.moveTo(x, y, duration=0.08)
            pyautogui.rightClick()
            return ExecutionResult(success=True, stdout=f"Right-clicked at ({x}, {y})")

        elif action_type == "type":
            if x and y:
                pyautogui.moveTo(x, y, duration=0.08)
                pyautogui.click()
                time.sleep(0.05)
            pyautogui.typewrite(text, interval=0.005)
            return ExecutionResult(success=True, stdout=f"Typed: {text!r}")

        elif action_type == "hotkey":
            keys = text.split("+") if text else []
            if keys:
                pyautogui.hotkey(*[k.strip() for k in keys])
                return ExecutionResult(success=True, stdout=f"Hotkey: {text}")
            return ExecutionResult(success=False, stderr="No keys specified for hotkey action")

        elif action_type == "scroll":
            scroll_amount = gui_action.get("amount", -3)
            if x and y:
                pyautogui.moveTo(x, y, duration=0.05)
            pyautogui.scroll(scroll_amount)
            return ExecutionResult(success=True, stdout=f"Scrolled {scroll_amount} at ({x}, {y})")

        else:
            return ExecutionResult(
                success=False,
                stderr=f"Unknown GUI action type: {action_type!r}. "
                       f"Supported: click, doubleclick, rightclick, type, hotkey, scroll",
            )
    except Exception as exc:
        return ExecutionResult(success=False, stderr=f"GUI action error: {str(exc)}")
