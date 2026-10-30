"""
Persistent interactive shell session for Kali-AI Agent.

The old executor ran every command with a brand-new `subprocess.run(..., shell=True)`
which meant NO state survived between commands:  `cd`, `export`, `source`, venv
activation, interactive tools and sudo all broke.  This module replaces that with a
single long-lived bash attached to a PTY so the agent behaves like a real terminal user:

  • State persists  — cwd, environment variables, shell functions stay between commands.
  • Real TTY        — sudo / apt / ssh / interactive tools work (they need a terminal).
  • Streaming       — output is delivered live via an on_output callback.
  • Sudo handling   — a cached sudo password is auto-typed when sudo prompts for it.
  • Interrupt       — Ctrl-C stops the current foreground command WITHOUT killing the shell.
  • Exit codes      — each command's real exit status is captured via a sentinel marker.

On non-POSIX platforms (Windows dev machines) a degraded fallback runs each command with
a fresh subprocess so the app still imports and the UI can be tested.
"""

import codecs
import errno
import os
import re
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

IS_POSIX = os.name == "posix"

if IS_POSIX:
    import fcntl
    import pty
    import select
    import signal
    import struct
    import termios


# Unique sentinel echoed after every command so we can detect completion, exit
# code, and the current working directory (so `cd` state is visible to UI + AI).
_MARKER = "__KALI_AI_CMD_DONE_a7f3b921__"
_MARKER_RE = re.compile(re.escape(_MARKER) + r"(-?\d+):::([^\n]*)\n")
_SUDO_PROMPT_RE = re.compile(r"\[sudo\] password for .*?:", re.IGNORECASE)
_GENERIC_PW_RE = re.compile(r"(?:^|\n)[^\n]*pass(?:word|phrase)[^\n]*:\s*$", re.IGNORECASE)

# Max bytes of a single command's output we retain in memory.
_MAX_OUTPUT = 200_000


class CommandResult:
    """Result of running one command inside the persistent shell."""

    def __init__(self, output: str = "", exit_code: Optional[int] = None,
                 timed_out: bool = False, interrupted: bool = False,
                 awaiting_input: bool = False, cwd: str = "", error: str = ""):
        self.output = output
        self.exit_code = exit_code
        self.timed_out = timed_out
        self.interrupted = interrupted
        self.awaiting_input = awaiting_input  # command paused at an interactive prompt
        self.cwd = cwd                        # shell's working directory after the command
        self.error = error

    @property
    def success(self) -> bool:
        if self.error:
            return False
        if self.timed_out or self.awaiting_input:
            # 124 is the conventional timeout code; we treat a graceful interrupt-on-timeout
            # as non-fatal so the agent can still read whatever output was captured.
            return False
        return self.exit_code == 0


class _PendingRead:
    """Mutable read-state for a command that may pause at an interactive prompt."""

    def __init__(self, timeout: Optional[float], on_output):
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.acc = ""
        self.emitted = 0
        self.exit_code: Optional[int] = None
        self.timed_out = False
        self.interrupt_sent = False
        self.sudo_sent = False
        self.timeout = timeout
        self.on_output = on_output
        self.start = time.time()
        self.last_data = time.time()
        self.deadline: Optional[float] = None


class PersistentShell:
    """A single bash process living behind a PTY, reused for every command."""

    def __init__(self):
        self._marker = _MARKER
        self.master_fd: Optional[int] = None
        self.proc: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()
        self._sudo_password: Optional[str] = None
        self._busy = False
        self._cancel = False
        self._pending: Optional[_PendingRead] = None  # set while a command awaits input
        self._last_cwd = ""                           # most recent working directory

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self) -> None:
        """Spawn the bash process attached to a fresh PTY."""
        if not IS_POSIX:
            return
        with self._lock:
            if self.is_alive():
                return

            self.master_fd, slave_fd = pty.openpty()
            self._set_winsize(self.master_fd, 40, 160)

            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["PS1"] = ""
            env["PS2"] = ""
            # Keep Debian/Kali apt non-interactive-friendly without forcing -y everywhere.
            env.setdefault("DEBIAN_FRONTEND", "readline")

            self.proc = subprocess.Popen(
                ["/bin/bash", "--norc", "--noprofile", "-i"],
                preexec_fn=os.setsid,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                close_fds=True,
            )
            os.close(slave_fd)

            # Non-blocking master so our reader never wedges.
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            # Quiet, predictable shell: no echo, no job-control chatter, empty prompts.
            self._raw_write("stty -echo 2>/dev/null; set +m; export PS1=''; export PS2=''\n")
            time.sleep(0.3)
            self._drain(0.4)

    def is_alive(self) -> bool:
        return (
            IS_POSIX
            and self.proc is not None
            and self.proc.poll() is None
            and self.master_fd is not None
        )

    def close(self) -> None:
        with self._lock:
            if not IS_POSIX:
                return
            try:
                if self.proc and self.proc.poll() is None:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except Exception:
                pass
            try:
                if self.master_fd is not None:
                    os.close(self.master_fd)
            except Exception:
                pass
            self.master_fd = None
            self.proc = None

    def restart(self) -> None:
        self.close()
        self.start()

    # ── sudo ─────────────────────────────────────────────────────────────────
    def set_sudo_password(self, password: Optional[str]) -> None:
        self._sudo_password = password or None

    @property
    def has_sudo_password(self) -> bool:
        return bool(self._sudo_password)

    # ── interrupt / cancel ─────────────────────────────────────────────────────
    def interrupt(self) -> None:
        """Send Ctrl-C to the foreground command without killing the shell."""
        self._cancel = True
        if IS_POSIX and self.master_fd is not None:
            try:
                os.write(self.master_fd, b"\x03")
            except Exception:
                pass

    def send_input(self, text: str, newline: bool = True) -> None:
        """Feed text to a running interactive command (e.g. answer a prompt)."""
        if newline and not text.endswith("\n"):
            text += "\n"
        self._raw_write(text)

    # ── core execution ─────────────────────────────────────────────────────────
    def run(
        self,
        command: str,
        timeout: Optional[float] = 60.0,
        on_output: Optional[Callable[[str], None]] = None,
        interactive: bool = True,
    ) -> CommandResult:
        """Run a command in the persistent shell, streaming output via on_output.

        If `interactive` is True and the command pauses at a prompt (and no cached
        sudo password applies), the call returns early with `awaiting_input=True`.
        Continue it later with `resume(input_text)`.
        """
        if not IS_POSIX:
            return self._run_fallback(command, timeout, on_output)

        with self._lock:
            if not self.is_alive():
                self.start()
            if not self.is_alive():
                return CommandResult(error="Failed to start persistent shell.")

            # Abandon any previous half-finished interactive command.
            self._pending = None
            self._cancel = False
            self._busy = True
            try:
                self._drain(0)  # discard anything left from a previous command
                payload = f"{command}\nprintf '\\n{self._marker}%d:::%s\\n' \"$?\" \"$PWD\"\n"
                self._raw_write(payload)
                pending = _PendingRead(timeout, on_output)
                return self._pump(pending, interactive)
            finally:
                self._busy = False

    def resume(
        self,
        input_text: Optional[str],
        timeout: Optional[float] = 60.0,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> CommandResult:
        """Send input to a command paused at a prompt and keep reading its output."""
        if not IS_POSIX:
            return CommandResult(error="Interactive input is only supported on Linux.")

        with self._lock:
            pending = self._pending
            if pending is None:
                return CommandResult(error="No command is currently awaiting input.")
            if on_output is not None:
                pending.on_output = on_output
            if timeout is not None:
                pending.timeout = timeout
            pending.start = time.time()
            pending.deadline = None
            pending.interrupt_sent = False
            pending.timed_out = False
            self._cancel = False
            self._busy = True
            try:
                if input_text is not None:
                    self._raw_write(input_text if input_text.endswith("\n") else input_text + "\n")
                pending.last_data = time.time()
                return self._pump(pending, interactive=True)
            finally:
                self._busy = False

    def _pump(self, p: _PendingRead, interactive: bool) -> CommandResult:
        """Read from the PTY until the command finishes, times out, or awaits input."""
        idle_threshold = 3.0

        while True:
            now = time.time()
            if p.timeout and not p.interrupt_sent and (now - p.start) > p.timeout:
                # Graceful interrupt first; the trailing printf still runs (code 130).
                self.interrupt()
                p.interrupt_sent = True
                p.timed_out = True
                p.deadline = now + 5
            if p.interrupt_sent and p.deadline and time.time() > p.deadline:
                break
            if self._cancel and not p.interrupt_sent:
                self.interrupt()
                p.interrupt_sent = True
                p.deadline = time.time() + 5

            try:
                r, _, _ = select.select([self.master_fd], [], [], 0.2)
            except (OSError, ValueError):
                break

            if not r:
                # No data right now — maybe the command is waiting for interactive input.
                if (interactive and not p.interrupt_sent
                        and (time.time() - p.last_data) > idle_threshold
                        and self._looks_like_prompt(p.acc)):
                    if p.on_output and len(p.acc) > p.emitted:
                        p.on_output(p.acc[p.emitted:])
                        p.emitted = len(p.acc)
                    self._pending = p  # keep state so resume() can continue
                    return CommandResult(
                        output=self._strip_marker(p.acc),
                        awaiting_input=True,
                        cwd=self._last_cwd,
                    )
                continue

            try:
                data = os.read(self.master_fd, 65536)
            except OSError as exc:
                if exc.errno == errno.EAGAIN:
                    continue
                break  # EIO => slave closed / shell died
            if not data:
                break

            p.last_data = time.time()
            p.acc += p.decoder.decode(data)

            # Auto-answer sudo (and other) password prompts if we have a cached secret.
            if not p.sudo_sent and self._sudo_password:
                tail = p.acc[-240:]
                if _SUDO_PROMPT_RE.search(tail) or _GENERIC_PW_RE.search(tail):
                    self._raw_write(self._sudo_password + "\n")
                    p.sudo_sent = True

            m = _MARKER_RE.search(p.acc)
            if m:
                pre = p.acc[:m.start()]
                if p.on_output and len(pre) > p.emitted:
                    p.on_output(pre[p.emitted:])
                p.emitted = len(pre)
                try:
                    p.exit_code = int(m.group(1))
                except ValueError:
                    p.exit_code = None
                cwd = m.group(2).strip()
                if cwd:
                    self._last_cwd = cwd
                self._pending = None
                return CommandResult(
                    output=pre.rstrip("\n"),
                    exit_code=p.exit_code,
                    cwd=self._last_cwd,
                    timed_out=False,
                    interrupted=self._cancel,
                )

            # Stream output but NEVER emit a (possibly partial) marker line.
            mpos = p.acc.find(self._marker)
            if mpos != -1:
                # Marker has begun but its line isn't complete yet; emit only up to it.
                if mpos > p.emitted and p.on_output:
                    p.on_output(p.acc[p.emitted:mpos])
                    p.emitted = mpos
            else:
                # Hold back the last marker-length chars in case a marker is forming.
                safe = len(p.acc) - len(self._marker)
                if safe > p.emitted:
                    if p.on_output:
                        p.on_output(p.acc[p.emitted:safe])
                    p.emitted = safe

            if len(p.acc) > _MAX_OUTPUT:
                p.acc = p.acc[: _MAX_OUTPUT // 2] + p.acc[-(_MAX_OUTPUT // 2):]
                p.emitted = min(p.emitted, len(p.acc))

        # Loop exited without a marker: timeout or shell/EOF.
        self._pending = None
        output = self._strip_marker(p.acc)
        exit_code = p.exit_code
        if p.timed_out and exit_code is None:
            exit_code = 124
        return CommandResult(
            output=output,
            exit_code=exit_code,
            cwd=self._last_cwd,
            timed_out=p.timed_out,
            interrupted=self._cancel,
        )

    @staticmethod
    def _looks_like_prompt(text: str) -> bool:
        """Heuristic: does the tail of the output look like it's waiting for input?"""
        if not text:
            return False
        clean = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)  # strip ANSI
        lines = [ln for ln in clean.splitlines() if ln.strip()]
        if not lines:
            return False
        last = lines[-1].rstrip()
        low = last.lower()
        if any(tok in low for tok in ("[y/n]", "(yes/no)", "[y/n/", "password", "passphrase")):
            return True
        return last.endswith((":", "?", ">", "#", "$")) and len(last) < 200

    def _strip_marker(self, text: str) -> str:
        idx = text.find(self._marker)
        if idx != -1:
            text = text[:idx]
        return text.rstrip("\n")

    def get_cwd(self) -> str:
        return self._last_cwd

    # ── low-level helpers ──────────────────────────────────────────────────────
    def _raw_write(self, text: str) -> None:
        if not IS_POSIX or self.master_fd is None:
            return
        try:
            os.write(self.master_fd, text.encode("utf-8", "replace"))
        except Exception:
            pass

    def _drain(self, wait: float) -> None:
        """Discard any pending bytes on the master fd."""
        if not IS_POSIX or self.master_fd is None:
            return
        end = time.time() + wait
        while True:
            try:
                r, _, _ = select.select([self.master_fd], [], [], 0.05)
            except (OSError, ValueError):
                return
            if r:
                try:
                    if not os.read(self.master_fd, 65536):
                        return
                except OSError:
                    return
            elif time.time() >= end:
                return

    @staticmethod
    def _set_winsize(fd: int, rows: int, cols: int) -> None:
        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

    # ── Windows / non-POSIX fallback (no persistence) ──────────────────────────
    def _run_fallback(
        self,
        command: str,
        timeout: Optional[float],
        on_output: Optional[Callable[[str], None]],
    ) -> CommandResult:
        import shutil

        shell_exe = shutil.which("bash") or shutil.which("cmd") or "cmd"
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                executable=shell_exe if shutil.which("bash") else None,
                stdin=subprocess.DEVNULL,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            if on_output and out:
                on_output(out)
            return CommandResult(output=out.strip(), exit_code=proc.returncode)
        except subprocess.TimeoutExpired as exc:
            partial = ""
            if exc.stdout:
                partial += exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", "replace")
            if exc.stderr:
                partial += exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", "replace")
            if on_output and partial:
                on_output(partial)
            return CommandResult(output=partial.strip(), timed_out=True, exit_code=124)
        except Exception as exc:
            return CommandResult(error=str(exc))


# Process-wide singleton — the whole app shares ONE shell so state persists.
_SHELL: Optional[PersistentShell] = None
_SHELL_LOCK = threading.Lock()


def get_shell() -> PersistentShell:
    global _SHELL
    with _SHELL_LOCK:
        if _SHELL is None:
            _SHELL = PersistentShell()
            _SHELL.start()
        return _SHELL
