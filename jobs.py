"""
Background Job Manager for Kali-AI Agent.

Long-running tasks (full nmap sweeps, gobuster/ffuf, hashcat/john cracking, large
downloads) shouldn't block the interactive shell or the agent loop. This module runs
them as detached background processes, each writing to its own log file, and lets the
agent start / list / tail / stop them while continuing other work.

Notes:
- Jobs run as separate processes (their own process group), so they do NOT share the
  persistent shell's cwd/env. Pass self-contained commands (absolute paths if needed).
- Jobs run as the current user. Commands needing root should already run as root or
  use passwordless sudo, since a detached job cannot answer an interactive prompt.
- Destructive commands are still screened by guardrails before a job starts.
"""

import datetime
import os
import shutil
import signal
import subprocess
import threading
from typing import Dict, Optional, Tuple

from guardrails import is_command_blocked

_JOBS_DIR = os.path.join(os.path.expanduser("~"), ".config", "kali-ai", "jobs")
IS_POSIX = os.name == "posix"


class Job:
    def __init__(self, job_id: int, command: str, logfile: str, proc: subprocess.Popen):
        self.id = job_id
        self.command = command
        self.logfile = logfile
        self.proc = proc
        self.start_ts = datetime.datetime.now()

    def status(self) -> str:
        code = self.proc.poll()
        if code is None:
            return "running"
        return f"exited({code})"


class JobManager:
    def __init__(self):
        self._jobs: Dict[int, Job] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def _shell(self) -> str:
        return shutil.which("bash") or shutil.which("sh") or "/bin/sh"

    def start(self, command: str) -> Tuple[bool, str, Optional[int]]:
        blocked, reason = is_command_blocked(command)
        if blocked:
            return False, reason, None

        try:
            os.makedirs(_JOBS_DIR, exist_ok=True)
            with self._lock:
                self._counter += 1
                job_id = self._counter
            logfile = os.path.join(_JOBS_DIR, f"job_{job_id}.log")

            log_fh = open(logfile, "wb")
            popen_kwargs = dict(
                shell=True,
                stdin=subprocess.DEVNULL,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
            )
            if IS_POSIX:
                popen_kwargs["executable"] = self._shell()
                popen_kwargs["start_new_session"] = True  # own process group → killable

            proc = subprocess.Popen(command, **popen_kwargs)
            self._jobs[job_id] = Job(job_id, command, logfile, proc)
            return True, f"Started background job #{job_id} (log: {logfile})", job_id
        except Exception as exc:
            return False, f"Failed to start job: {exc}", None

    def list_jobs(self) -> str:
        if not self._jobs:
            return "No background jobs."
        lines = ["[Background jobs]:"]
        for jid in sorted(self._jobs):
            job = self._jobs[jid]
            dur = (datetime.datetime.now() - job.start_ts)
            dur_s = int(dur.total_seconds())
            lines.append(f"  #{jid} [{job.status()}] ({dur_s}s)  {job.command[:80]}")
        return "\n".join(lines)

    def snapshot(self) -> list:
        """Structured view of all jobs for the UI."""
        import datetime as _dt
        out = []
        for jid in sorted(self._jobs):
            job = self._jobs[jid]
            dur = int((_dt.datetime.now() - job.start_ts).total_seconds())
            out.append({
                "id": jid,
                "command": job.command,
                "status": job.status(),
                "duration": dur,
            })
        return out

    def running_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.proc.poll() is None)

    def output(self, job_id: int, tail_lines: int = 200) -> str:
        job = self._jobs.get(job_id)
        if not job:
            return f"No such job #{job_id}."
        try:
            with open(job.logfile, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
        except FileNotFoundError:
            return f"Job #{job_id}: no output yet."
        lines = data.splitlines()
        tail = lines[-tail_lines:]
        note = "" if len(lines) <= tail_lines else f"[... {len(lines) - tail_lines} earlier lines ...]\n"
        return f"[Job #{job_id} status={job.status()}]\n{note}" + "\n".join(tail)

    def stop(self, job_id: int) -> Tuple[bool, str]:
        job = self._jobs.get(job_id)
        if not job:
            return False, f"No such job #{job_id}."
        if job.proc.poll() is not None:
            return True, f"Job #{job_id} already finished ({job.status()})."
        try:
            if IS_POSIX:
                os.killpg(os.getpgid(job.proc.pid), signal.SIGTERM)
            else:
                job.proc.terminate()
            return True, f"Stopped job #{job_id}."
        except Exception as exc:
            return False, f"Could not stop job #{job_id}: {exc}"

    def stop_all(self) -> None:
        for jid in list(self._jobs):
            try:
                self.stop(jid)
            except Exception:
                pass


# Process-wide singleton.
_MANAGER: Optional[JobManager] = None


def get_job_manager() -> JobManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = JobManager()
    return _MANAGER
