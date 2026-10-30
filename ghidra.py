"""
Ghidra integration for Kali-AI Agent.

Lets the agent drive Ghidra for reverse engineering WITHOUT the GUI, using Ghidra's
official Headless Analyzer (`analyzeHeadless`). One-click "connect" locates the Ghidra
install; after that the agent can import a binary, auto-analyze it, list functions and
strings, decompile functions to C, and run arbitrary Ghidra (Jython) scripts — all by
talking to the user.

Nothing here needs the Ghidra GUI. Analysis results come back as text the agent reasons on.
If Ghidra isn't installed, connect() returns a clear message instead of failing hard.
"""

import glob
import os
import subprocess
import tempfile
from typing import Optional, Tuple

IS_WIN = os.name == "nt"

_HEADLESS_NAME = "analyzeHeadless.bat" if IS_WIN else "analyzeHeadless"

_STATE_DIR = os.path.join(os.path.expanduser("~"), ".config", "kali-ai")
_PROJECT_DIR = os.path.join(_STATE_DIR, "ghidra_projects")
_SCRIPTS_DIR = os.path.join(_STATE_DIR, "ghidra_scripts")
_PROJECT_NAME = "kaliai"

_BEGIN = "===KALIAI_BEGIN==="
_END = "===KALIAI_END==="


def find_headless() -> Optional[str]:
    """Locate Ghidra's analyzeHeadless launcher."""
    import shutil
    direct = shutil.which(_HEADLESS_NAME) or shutil.which("analyzeHeadless")
    if direct:
        return direct

    roots = []
    env_home = os.environ.get("GHIDRA_HOME") or os.environ.get("GHIDRA_INSTALL_DIR")
    if env_home:
        roots.append(env_home)
    roots += [
        "/opt/ghidra", "/usr/share/ghidra", "/usr/local/ghidra",
        os.path.expanduser("~/ghidra"),
        "C:\\ghidra", "C:\\Program Files\\ghidra",
    ]
    # Also glob versioned install dirs (ghidra_11.0.3_PUBLIC, etc.)
    patterns = [
        "/opt/ghidra*", "/usr/share/ghidra*", "/usr/local/ghidra*",
        os.path.expanduser("~/ghidra*"), os.path.expanduser("~/tools/ghidra*"),
        "C:\\ghidra*", "C:\\Program Files\\ghidra*",
    ]
    for pat in patterns:
        roots += glob.glob(pat)

    seen = set()
    for root in roots:
        if not root or root in seen:
            continue
        seen.add(root)
        cand = os.path.join(root, "support", _HEADLESS_NAME)
        if os.path.exists(cand):
            return cand
    return None


# ── Built-in Ghidra (Jython) scripts ───────────────────────────────────────────
_SCRIPT_FUNCTIONS = f'''# @category KaliAI
print("{_BEGIN}")
fm = currentProgram.getFunctionManager()
count = 0
for f in fm.getFunctions(True):
    print("%s\\t%s\\t%d" % (f.getEntryPoint(), f.getName(), f.getBody().getNumAddresses()))
    count += 1
print("TOTAL_FUNCTIONS=%d" % count)
print("{_END}")
'''

_SCRIPT_STRINGS = f'''# @category KaliAI
from ghidra.program.util import DefinedDataIterator
print("{_BEGIN}")
count = 0
for d in DefinedDataIterator.definedStrings(currentProgram):
    try:
        val = d.getValue()
    except:
        val = None
    if val is not None:
        print("%s\\t%s" % (d.getAddress(), str(val)))
        count += 1
    if count >= 2000:
        break
print("TOTAL_STRINGS=%d" % count)
print("{_END}")
'''

_SCRIPT_DECOMPILE = f'''# @category KaliAI
import os
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
target = os.environ.get("KALIAI_FUNC", "").strip()
di = DecompInterface()
di.openProgram(currentProgram)
monitor = ConsoleTaskMonitor()
fm = currentProgram.getFunctionManager()
print("{_BEGIN}")
printed = 0
for f in fm.getFunctions(True):
    name = f.getName()
    entry = f.getEntryPoint()
    match = (not target) or (name == target) or (("0x" + entry.toString().lstrip("0") ) == target) or (entry.toString() == target)
    if match:
        res = di.decompileFunction(f, 60, monitor)
        if res is not None and res.getDecompiledFunction() is not None:
            print("// ==== %s @ %s ====" % (name, entry))
            print(res.getDecompiledFunction().getC())
            printed += 1
        if target:
            break
if printed == 0:
    print("No matching function decompiled (target=%r)." % target)
print("{_END}")
'''


class GhidraController:
    def __init__(self):
        self.headless: Optional[str] = None
        self.current_program: Optional[str] = None

    @property
    def connected(self) -> bool:
        return self.headless is not None

    def _ensure_dirs(self):
        os.makedirs(_PROJECT_DIR, exist_ok=True)
        os.makedirs(_SCRIPTS_DIR, exist_ok=True)

    def connect(self) -> Tuple[bool, str]:
        hl = find_headless()
        if not hl:
            return False, (
                "Ghidra not found. Install Ghidra and/or set GHIDRA_HOME, e.g.:\n"
                "  export GHIDRA_HOME=/opt/ghidra\n"
                "Searched PATH, $GHIDRA_HOME, /opt, /usr/share, /usr/local, and ~."
            )
        self._ensure_dirs()
        self.headless = hl
        return True, f"✅ Ghidra connected via headless analyzer:\n{hl}\nProject: {_PROJECT_DIR}/{_PROJECT_NAME}"

    def _run(self, args: list, timeout: int, env_extra: Optional[dict] = None) -> Tuple[bool, str]:
        if not self.connected:
            ok, msg = self.connect()
            if not ok:
                return False, msg
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)
        try:
            proc = subprocess.run(
                [self.headless] + args,
                capture_output=True, text=True, timeout=timeout, env=env,
                stdin=subprocess.DEVNULL,
            )
            return True, (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired:
            return False, f"Ghidra operation timed out after {timeout}s."
        except Exception as exc:
            return False, f"Ghidra execution error: {exc}"

    @staticmethod
    def _extract(output: str) -> str:
        """Pull the script's marked output out of Ghidra's verbose headless log."""
        if _BEGIN in output and _END in output:
            try:
                return output.split(_BEGIN, 1)[1].split(_END, 1)[0].strip()
            except Exception:
                pass
        # Fall back to the tail of the raw log.
        lines = output.splitlines()
        return "\n".join(lines[-60:]).strip()

    def analyze(self, file_path: str) -> Tuple[bool, str]:
        path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(path):
            return False, f"File not found: {path}"
        self._ensure_dirs()
        ok, out = self._run(
            [_PROJECT_DIR, _PROJECT_NAME, "-import", path, "-overwrite"],
            timeout=1800,  # auto-analysis can be slow for large binaries
        )
        if not ok:
            return False, out
        self.current_program = os.path.basename(path)
        tail = "\n".join(out.splitlines()[-25:])
        return True, f"Imported & analyzed '{self.current_program}'.\n{tail}"

    def _run_script(self, script_code: str, env_extra=None, timeout=600) -> Tuple[bool, str]:
        if not self.current_program:
            return False, "No program loaded. Run ghidra 'analyze' on a file first."
        self._ensure_dirs()
        script_path = os.path.join(_SCRIPTS_DIR, "kaliai_run.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_code)
        ok, out = self._run(
            [_PROJECT_DIR, _PROJECT_NAME, "-process", self.current_program,
             "-noanalysis", "-scriptPath", _SCRIPTS_DIR, "-postScript", "kaliai_run.py"],
            timeout=timeout, env_extra=env_extra,
        )
        if not ok:
            return False, out
        return True, self._extract(out)

    def list_functions(self) -> Tuple[bool, str]:
        return self._run_script(_SCRIPT_FUNCTIONS)

    def list_strings(self) -> Tuple[bool, str]:
        return self._run_script(_SCRIPT_STRINGS)

    def decompile(self, function: str) -> Tuple[bool, str]:
        return self._run_script(_SCRIPT_DECOMPILE, env_extra={"KALIAI_FUNC": function or ""})

    def run_custom_script(self, code: str) -> Tuple[bool, str]:
        # Wrap the agent's code so its output is cleanly extractable.
        wrapped = f'# @category KaliAI\nprint("{_BEGIN}")\n{code}\nprint("{_END}")\n'
        return self._run_script(wrapped, timeout=900)

    def status(self) -> str:
        if not self.connected:
            return "Ghidra: not connected."
        prog = self.current_program or "(none loaded)"
        return f"Ghidra: connected ({self.headless}); current program: {prog}"


_CONTROLLER: Optional[GhidraController] = None


def get_ghidra() -> GhidraController:
    global _CONTROLLER
    if _CONTROLLER is None:
        _CONTROLLER = GhidraController()
    return _CONTROLLER
