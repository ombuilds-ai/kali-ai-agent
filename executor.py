"""
Execution Engine for Kali-AI Agent.

Bash commands now run inside ONE persistent PTY-backed shell (see shell_session.py),
so working directory, environment, sudo and interactive tools all behave like a real
terminal.  Output is streamed live via an optional callback.  GUI automation via
pyautogui is unchanged.
"""

import datetime
import os
import re
import time
from typing import Callable, Optional

import pyautogui

from guardrails import is_command_blocked
from shell_session import get_shell

_AUDIT_LOG = os.path.join(os.path.expanduser("~"), ".config", "kali-ai", "audit.log")

# Redact common secret-bearing arguments before writing to the audit log.
_SECRET_PATTERNS = [
    re.compile(r"(--password[=\s]+)(\S+)", re.I),
    re.compile(r"(--pass[=\s]+)(\S+)", re.I),
    re.compile(r"(--token[=\s]+)(\S+)", re.I),
    re.compile(r"(\bsshpass\s+-p\s*)(\S+)", re.I),
    re.compile(r"(\bmysql\b[^\n]*\s-p)(\S+)", re.I),
]


def _redact(command: str) -> str:
    out = command
    for pat in _SECRET_PATTERNS:
        out = pat.sub(lambda m: m.group(1) + "******", out)
    return out


def _audit(command: str, status: str) -> None:
    """Append an executed/blocked command to the on-disk audit trail (secrets redacted)."""
    try:
        os.makedirs(os.path.dirname(_AUDIT_LOG), exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(_AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(f"{stamp} [{status}] {_redact(command)}\n")
    except Exception:
        pass


class ExecutionResult:
    """Result of a command or GUI action execution."""

    def __init__(self, success: bool, stdout: str = "", stderr: str = "",
                 blocked: bool = False, reason: str = "",
                 exit_code: Optional[int] = None, timed_out: bool = False,
                 interrupted: bool = False, awaiting_input: bool = False,
                 cwd: str = ""):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.blocked = blocked
        self.reason = reason
        self.exit_code = exit_code
        self.timed_out = timed_out
        self.interrupted = interrupted
        self.awaiting_input = awaiting_input
        self.cwd = cwd

    def combined_output(self) -> str:
        """Combine stdout and stderr into a single string."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(f"[STDERR]\n{self.stderr}")
        return "\n".join(parts).strip()

    def output_for_ai(self) -> str:
        """Command output annotated with status, so the model can reason about it."""
        body = self.combined_output() or "(no output)"
        status_bits = []
        if self.awaiting_input:
            status_bits.append("AWAITING INPUT (command paused at an interactive prompt — "
                               "respond with action_type 'send_input')")
        if self.exit_code is not None:
            status_bits.append(f"exit_code={self.exit_code}")
        if self.timed_out:
            status_bits.append("TIMED OUT (interrupted)")
        if self.interrupted and not self.timed_out:
            status_bits.append("INTERRUPTED by user")
        if self.cwd:
            status_bits.append(f"cwd={self.cwd}")
        header = f"[Execution status: {', '.join(status_bits)}]" if status_bits else ""
        return f"{header}\n{body}".strip()


# Tools that stream forever; if the model forgets to bound them we cap the default
# timeout so the UI never waits indefinitely (the user can still allow long runs).
_STREAMING_TOOLS = ("airodump-ng", "tcpdump", "tshark", "top", "htop", "iftop", "nload")


def _default_timeout(command: str, timeout: Optional[int]) -> Optional[float]:
    if timeout is not None:
        return float(timeout)
    low = command.lower()
    if any(tool in low for tool in _STREAMING_TOOLS):
        return 20.0
    return 300.0  # generous default; long scans/installs get room to finish


def run_bash(
    command: str,
    timeout: Optional[int] = None,
    on_output: Optional[Callable[[str], None]] = None,
) -> ExecutionResult:
    """
    Execute a command inside the persistent shell.

    `on_output(chunk)` is called with output chunks as they arrive (live streaming).
    `timeout=None` picks a sensible per-command default; pass 0 for no limit.
    """
    blocked, reason = is_command_blocked(command)
    if blocked:
        _audit(command, f"BLOCKED: {reason}")
        return ExecutionResult(success=False, blocked=True, reason=reason)

    effective_timeout = _default_timeout(command, timeout)
    if timeout == 0:
        effective_timeout = None

    try:
        result = get_shell().run(command, timeout=effective_timeout, on_output=on_output)
    except Exception as exc:
        _audit(command, f"ERROR: {exc}")
        return ExecutionResult(success=False, stderr=f"Execution error: {exc}")

    if result.awaiting_input:
        status = "AWAITING_INPUT"
    elif result.timed_out:
        status = "TIMEOUT"
    elif result.error:
        status = f"ERROR: {result.error}"
    else:
        status = f"exit={result.exit_code}"
    _audit(command, status)

    return _to_execution_result(result)


def resume_bash(
    input_text: Optional[str],
    timeout: Optional[int] = None,
    on_output: Optional[Callable[[str], None]] = None,
) -> ExecutionResult:
    """Send input to a command paused at an interactive prompt and keep reading."""
    effective_timeout = 300.0 if timeout is None else (None if timeout == 0 else float(timeout))
    try:
        result = get_shell().resume(input_text, timeout=effective_timeout, on_output=on_output)
    except Exception as exc:
        return ExecutionResult(success=False, stderr=f"Execution error: {exc}")
    return _to_execution_result(result)


def _to_execution_result(result) -> ExecutionResult:
    if result.error:
        return ExecutionResult(success=False, stderr=result.error)

    stdout = result.output or ""
    max_output = 50000
    if len(stdout) > max_output:
        stdout = stdout[:max_output] + f"\n\n[... output truncated, {len(result.output)} total chars ...]"

    return ExecutionResult(
        success=result.success,
        stdout=stdout,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
        interrupted=result.interrupted,
        awaiting_input=result.awaiting_input,
        cwd=getattr(result, "cwd", ""),
    )


def get_screen_size() -> tuple:
    """Return (width, height) of the primary screen in pyautogui's coordinate space."""
    try:
        size = pyautogui.size()
        return int(size.width), int(size.height)
    except Exception:
        return 0, 0


def run_gui_action(gui_action: dict) -> ExecutionResult:
    """Execute a GUI action (click or type) using pyautogui."""
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
