"""
Structured file & directory tools for Kali-AI Agent.

These give the agent reliable, structured primitives instead of fragile bash
heredocs / cat pipelines for reading and writing files:

  • read_file   — read a text file (size-capped) and return its contents.
  • write_file  — create/overwrite or append to a file (parent dirs auto-created).
  • list_dir    — list a directory.

Note: these run as the current user.  For root-owned paths the agent should use
`sudo` via a bash command instead.
"""

import os
from typing import Tuple

_MAX_READ = 200_000  # 200 KB cap for a single read


def _expand(path: str) -> str:
    return os.path.abspath(os.path.expanduser(os.path.expandvars(path)))


def read_file(path: str, max_bytes: int = _MAX_READ) -> Tuple[bool, str]:
    """Return (ok, content_or_error)."""
    try:
        full = _expand(path)
        if not os.path.exists(full):
            return False, f"File not found: {full}"
        if os.path.isdir(full):
            return False, f"Path is a directory, not a file: {full}"
        size = os.path.getsize(full)
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            data = f.read(max_bytes)
        note = ""
        if size > max_bytes:
            note = f"\n\n[... truncated, showing {max_bytes} of {size} bytes ...]"
        return True, f"[File: {full} ({size} bytes)]\n{data}{note}"
    except PermissionError:
        return False, f"Permission denied reading {path}. For root-owned files use: sudo cat {path}"
    except Exception as exc:
        return False, f"Error reading {path}: {exc}"


def write_file(path: str, content: str, append: bool = False) -> Tuple[bool, str]:
    """Create/overwrite (or append to) a file. Returns (ok, message)."""
    try:
        full = _expand(path)
        parent = os.path.dirname(full)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        mode = "a" if append else "w"
        with open(full, mode, encoding="utf-8") as f:
            f.write(content)
        verb = "Appended to" if append else "Wrote"
        return True, f"{verb} {full} ({len(content)} bytes)."
    except PermissionError:
        return False, (
            f"Permission denied writing {path}. For root-owned locations, write via a "
            f"bash command using sudo (e.g. `echo ... | sudo tee {path}`)."
        )
    except Exception as exc:
        return False, f"Error writing {path}: {exc}"


def list_dir(path: str = ".") -> Tuple[bool, str]:
    """List a directory's entries. Returns (ok, listing_or_error)."""
    try:
        full = _expand(path)
        if not os.path.isdir(full):
            return False, f"Not a directory: {full}"
        entries = sorted(os.listdir(full))
        lines = [f"[Directory: {full}] ({len(entries)} entries)"]
        for name in entries:
            p = os.path.join(full, name)
            suffix = "/" if os.path.isdir(p) else ""
            try:
                sz = os.path.getsize(p)
            except OSError:
                sz = 0
            lines.append(f"  {name}{suffix}\t{sz}")
        return True, "\n".join(lines)
    except Exception as exc:
        return False, f"Error listing {path}: {exc}"
