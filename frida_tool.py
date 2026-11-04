"""
Frida integration for Kali-AI Agent — dynamic memory analysis & game cheat making.

This is the "live" counterpart to the static Ghidra integration. It drives Frida to
attach to a running process (local Linux process, or an Android/iOS app via
frida-server) and gives the agent Cheat-Engine-style powers:

  • value scanning (exact value) + iterative refinement (scan_next)
  • Array-of-Bytes (AoB) pattern scanning with ?? wildcards
  • typed memory read / write
  • value "freeze" (rewrite an address on an interval) — classic trainer cheat
  • function hooking / interception (log args & return, or force a return value)
  • module / export enumeration & symbol resolution

The heavy lifting runs inside an injected Frida JavaScript agent (rpc.exports); this
module is the thin Python controller the GUI/agent calls. If Frida isn't installed or
no device/process is attached, every method returns a clear (ok, message) instead of
throwing, so the agent can reason about the error and recover.

Typical mobile-game workflow (agent-driven):
  1. frida connect   (device="usb" → Android with frida-server running)
  2. frida processes (find the game)
  3. frida attach    (target = package/process name or pid)
  4. frida scan      (scan_type="int32", scan_value=100  → e.g. current HP/coins)
  5. (user plays — value changes) frida scan_next (scan_value=95) … until 1-3 addrs
  6. frida write / freeze  (lock HP/coins), or frida hook a method to force results
"""

import struct
import threading
from typing import List, Optional, Tuple

try:
    import frida  # type: ignore
    _FRIDA_AVAILABLE = True
    _FRIDA_IMPORT_ERR = ""
except Exception as _exc:  # pragma: no cover - import guard
    frida = None  # type: ignore
    _FRIDA_AVAILABLE = False
    _FRIDA_IMPORT_ERR = str(_exc)


# Injected Frida agent (JS). Kept as a plain string (no f-string) so braces are literal.
_AGENT_JS = r"""
'use strict';

var FREEZES = {};   // addr -> {type, value, timer}

function readTyped(addr, type) {
    var p = ptr(addr);
    switch (type) {
        case 'int8':   return p.readS8();
        case 'uint8':  return p.readU8();
        case 'int16':  return p.readS16();
        case 'uint16': return p.readU16();
        case 'int32':  return p.readS32();
        case 'uint32': return p.readU32();
        case 'int64':  return p.readS64().toString();
        case 'uint64': return p.readU64().toString();
        case 'float':  return p.readFloat();
        case 'double': return p.readDouble();
        case 'string': return p.readUtf8String();
        default:       return p.readS32();
    }
}

function writeTyped(addr, type, v) {
    var p = ptr(addr);
    switch (type) {
        case 'int8':   p.writeS8(parseInt(v)); break;
        case 'uint8':  p.writeU8(parseInt(v)); break;
        case 'int16':  p.writeS16(parseInt(v)); break;
        case 'uint16': p.writeU16(parseInt(v)); break;
        case 'int32':  p.writeS32(parseInt(v)); break;
        case 'uint32': p.writeU32(parseInt(v)); break;
        case 'int64':  p.writeS64(int64(String(v))); break;
        case 'uint64': p.writeU64(uint64(String(v))); break;
        case 'float':  p.writeFloat(parseFloat(v)); break;
        case 'double': p.writeDouble(parseFloat(v)); break;
        case 'string': p.writeUtf8String(String(v)); break;
        default:       p.writeS32(parseInt(v));
    }
}

rpc.exports = {
    listModules: function () {
        return Process.enumerateModules().map(function (m) {
            return { name: m.name, base: m.base.toString(), size: m.size, path: m.path };
        });
    },

    listExports: function (moduleName) {
        try {
            return Module.enumerateExports(moduleName).map(function (e) {
                return { name: e.name, address: e.address.toString(), type: e.type };
            });
        } catch (e) { return { error: e.message }; }
    },

    resolveSymbol: function (moduleName, name) {
        try {
            var a = Module.getExportByName(moduleName === '' ? null : moduleName, name);
            return a ? a.toString() : null;
        } catch (e) { return { error: e.message }; }
    },

    // Exact-value scan. `pattern` is a space-separated hex byte string built in Python.
    scanValue: function (pattern, prot, cap) {
        var out = [];
        var ranges = Process.enumerateRanges(prot || 'rw-');
        for (var i = 0; i < ranges.length; i++) {
            var r = ranges[i];
            try {
                var hits = Memory.scanSync(r.base, r.size, pattern);
                for (var j = 0; j < hits.length; j++) {
                    out.push(hits[j].address.toString());
                    if (out.length >= cap) return out;
                }
            } catch (e) { /* skip unreadable range */ }
        }
        return out;
    },

    // AoB pattern scan (supports ?? wildcards) over a protection class.
    scanAob: function (pattern, prot, cap) {
        var out = [];
        var ranges = Process.enumerateRanges(prot || 'r-x');
        for (var i = 0; i < ranges.length; i++) {
            var r = ranges[i];
            try {
                var hits = Memory.scanSync(r.base, r.size, pattern);
                for (var j = 0; j < hits.length; j++) {
                    out.push(hits[j].address.toString());
                    if (out.length >= cap) return out;
                }
            } catch (e) {}
        }
        return out;
    },

    // Keep only the addresses whose current bytes still match `pattern`.
    refine: function (addrs, pattern) {
        var bytesLen = pattern.trim().split(/\s+/).length;
        var want = [];
        var toks = pattern.trim().split(/\s+/);
        for (var k = 0; k < toks.length; k++) want.push(toks[k].toLowerCase());
        var kept = [];
        for (var i = 0; i < addrs.length; i++) {
            try {
                var p = ptr(addrs[i]);
                var buf = new Uint8Array(p.readByteArray(bytesLen));
                var ok = true;
                for (var b = 0; b < bytesLen; b++) {
                    if (want[b] === '??') continue;
                    var hv = ('0' + buf[b].toString(16)).slice(-2);
                    if (hv !== want[b]) { ok = false; break; }
                }
                if (ok) kept.push(addrs[i]);
            } catch (e) {}
        }
        return kept;
    },

    readValue: function (addr, type) {
        try { return { value: readTyped(addr, type) }; }
        catch (e) { return { error: e.message }; }
    },

    writeValue: function (addr, type, v) {
        try { writeTyped(addr, type, v); return { ok: true }; }
        catch (e) { return { error: e.message }; }
    },

    freeze: function (addr, type, v) {
        try {
            if (FREEZES[addr] && FREEZES[addr].timer) clearInterval(FREEZES[addr].timer);
            var t = setInterval(function () {
                try { writeTyped(addr, type, v); } catch (e) {}
            }, 100);
            FREEZES[addr] = { type: type, value: v, timer: t };
            return { ok: true };
        } catch (e) { return { error: e.message }; }
    },

    unfreeze: function (addr) {
        if (FREEZES[addr]) { clearInterval(FREEZES[addr].timer); delete FREEZES[addr]; }
        return { ok: true };
    },

    unfreezeAll: function () {
        for (var a in FREEZES) { clearInterval(FREEZES[a].timer); }
        FREEZES = {};
        return { ok: true };
    },

    listFreezes: function () {
        var out = [];
        for (var a in FREEZES) out.push({ address: a, type: FREEZES[a].type, value: FREEZES[a].value });
        return out;
    },

    hook: function (addr, onEnterSrc, onLeaveSrc) {
        try {
            var cfg = {};
            if (onEnterSrc) cfg.onEnter = new Function('args', onEnterSrc);
            if (onLeaveSrc) cfg.onLeave = new Function('retval', onLeaveSrc);
            if (!cfg.onEnter && !cfg.onLeave) {
                cfg.onEnter = function (args) { send({ hook: addr, event: 'enter' }); };
                cfg.onLeave = function (retval) { send({ hook: addr, event: 'leave', retval: retval.toString() }); };
            }
            Interceptor.attach(ptr(addr), cfg);
            return { ok: true };
        } catch (e) { return { error: e.message }; }
    },

    // Force a function to always return a fixed value (replace its implementation).
    forceReturn: function (addr, retval) {
        try {
            Interceptor.replace(ptr(addr), new NativeCallback(function () {
                return ptr(retval);
            }, 'pointer', []));
            return { ok: true };
        } catch (e) { return { error: e.message }; }
    },

    unhookAll: function () {
        try { Interceptor.detachAll(); Interceptor.revert; return { ok: true }; }
        catch (e) { return { error: e.message }; }
    }
};
"""


def _value_to_pattern(scan_type: str, value) -> Tuple[Optional[str], str]:
    """Convert a typed value to a space-separated little-endian hex byte pattern."""
    t = (scan_type or "int32").lower()
    try:
        if t == "string":
            data = str(value).encode("utf-8")
        else:
            fmt = {
                "int8": "<b", "uint8": "<B",
                "int16": "<h", "uint16": "<H",
                "int32": "<i", "uint32": "<I",
                "int64": "<q", "uint64": "<Q",
                "float": "<f", "double": "<d",
            }.get(t)
            if not fmt:
                return None, f"Unsupported scan_type '{scan_type}'."
            if t in ("float", "double"):
                data = struct.pack(fmt, float(value))
            else:
                data = struct.pack(fmt, int(value))
        return " ".join("%02x" % b for b in data), ""
    except Exception as exc:
        return None, f"Could not encode value {value!r} as {scan_type}: {exc}"


class FridaController:
    def __init__(self):
        self.device_type: str = "usb"      # "usb" (Android/iOS), "local", or "remote:host:port"
        self.device = None
        self.session = None
        self.script = None
        self.attached_label: Optional[str] = None
        self._scan_results: List[str] = []   # full address list from the last scan (kept server-side)
        self._scan_type: str = "int32"
        self._hook_log: List[str] = []
        self._lock = threading.Lock()

    # ── status helpers ────────────────────────────────────────────────────────
    @property
    def available(self) -> bool:
        return _FRIDA_AVAILABLE

    @property
    def attached(self) -> bool:
        return self.session is not None and self.script is not None

    def _need_script(self) -> Optional[str]:
        if not _FRIDA_AVAILABLE:
            return (f"Frida is not installed ({_FRIDA_IMPORT_ERR}).\n"
                    "Install on Kali:  pip install frida frida-tools\n"
                    "For Android:      push & run frida-server on the device, then `frida connect` (device=usb).")
        if not self.attached:
            return "Not attached. Run `frida attach` on a process first (after `frida connect`)."
        return None

    def _rpc_call(self, name: str, *args):
        """Call an rpc.export on the injected agent."""
        fn = getattr(self.script.exports_sync, name, None) if hasattr(self.script, "exports_sync") else None
        if fn is None:
            fn = getattr(self.script.exports, name)  # older frida
        return fn(*args)

    def _on_message(self, message, data):
        try:
            if message.get("type") == "send":
                self._hook_log.append(str(message.get("payload")))
            elif message.get("type") == "error":
                self._hook_log.append("[script error] " + str(message.get("stack") or message.get("description")))
        except Exception:
            pass

    # ── connection ────────────────────────────────────────────────────────────
    def connect(self, device: str = "") -> Tuple[bool, str]:
        if not _FRIDA_AVAILABLE:
            return False, (f"Frida not installed ({_FRIDA_IMPORT_ERR}).\n"
                           "Run:  pip install frida frida-tools")
        dt = (device or self.device_type or "usb").strip().lower()
        self.device_type = dt
        try:
            if dt == "local":
                self.device = frida.get_local_device()
            elif dt.startswith("remote"):
                # "remote" or "remote:host:port"
                parts = device.split(":", 1)
                if len(parts) == 2 and parts[1]:
                    self.device = frida.get_device_manager().add_remote_device(parts[1])
                else:
                    self.device = frida.get_remote_device()
            else:  # usb (Android / iOS via frida-server)
                self.device = frida.get_usb_device(timeout=10)
            name = getattr(self.device, "name", dt)
            return True, f"✅ Frida connected to device: {name} ({dt})."
        except Exception as exc:
            return False, (f"Frida connect failed ({dt}): {exc}\n"
                           "For Android: ensure the device is plugged in / emulator running AND frida-server "
                           "is running on it (adb push frida-server; adb shell su -c '/data/local/tmp/frida-server &').")

    def list_processes(self, filter_text: str = "") -> Tuple[bool, str]:
        if not _FRIDA_AVAILABLE:
            return False, f"Frida not installed ({_FRIDA_IMPORT_ERR})."
        if self.device is None:
            ok, msg = self.connect(self.device_type)
            if not ok:
                return False, msg
        try:
            procs = self.device.enumerate_processes()
            ft = (filter_text or "").lower()
            rows = []
            for p in procs:
                if ft and ft not in p.name.lower() and ft != str(p.pid):
                    continue
                rows.append(f"{p.pid}\t{p.name}")
            if not rows:
                return True, "No matching processes." if ft else "No processes found."
            return True, "PID\tNAME\n" + "\n".join(rows[:400])
        except Exception as exc:
            return False, f"enumerate_processes failed: {exc}"

    def attach(self, target: str) -> Tuple[bool, str]:
        if not _FRIDA_AVAILABLE:
            return False, f"Frida not installed ({_FRIDA_IMPORT_ERR})."
        if not target:
            return False, "attach requires a target (process name or PID)."
        if self.device is None:
            ok, msg = self.connect(self.device_type)
            if not ok:
                return False, msg
        try:
            self._detach_quiet()
            tgt = int(target) if str(target).isdigit() else target
            self.session = self.device.attach(tgt)
            self.script = self.session.create_script(_AGENT_JS)
            self.script.on("message", self._on_message)
            self.script.load()
            self.attached_label = str(target)
            self._scan_results = []
            return True, f"✅ Attached to '{target}' and injected agent. Ready to scan/hook."
        except Exception as exc:
            self.session = None
            self.script = None
            return False, f"attach failed for '{target}': {exc}"

    def spawn(self, identifier: str) -> Tuple[bool, str]:
        """Spawn an app suspended (Android package id or path), inject, then resume."""
        if not _FRIDA_AVAILABLE:
            return False, f"Frida not installed ({_FRIDA_IMPORT_ERR})."
        if not identifier:
            return False, "spawn requires an app identifier / package name."
        if self.device is None:
            ok, msg = self.connect(self.device_type)
            if not ok:
                return False, msg
        try:
            self._detach_quiet()
            pid = self.device.spawn([identifier])
            self.session = self.device.attach(pid)
            self.script = self.session.create_script(_AGENT_JS)
            self.script.on("message", self._on_message)
            self.script.load()
            self.device.resume(pid)
            self.attached_label = f"{identifier} (pid {pid})"
            self._scan_results = []
            return True, f"✅ Spawned & attached '{identifier}' (pid {pid}); agent injected and resumed."
        except Exception as exc:
            self.session = None
            self.script = None
            return False, f"spawn failed for '{identifier}': {exc}"

    def _detach_quiet(self):
        try:
            if self.script:
                self.script.unload()
        except Exception:
            pass
        try:
            if self.session:
                self.session.detach()
        except Exception:
            pass
        self.script = None
        self.session = None

    def detach(self) -> Tuple[bool, str]:
        self._detach_quiet()
        self.attached_label = None
        self._scan_results = []
        return True, "Detached from target."

    # ── scanning ────────────────────────────────────────────────────────────
    def scan(self, scan_type: str, value, prot: str = "rw-", cap: int = 20000) -> Tuple[bool, str]:
        err = self._need_script()
        if err:
            return False, err
        pattern, perr = _value_to_pattern(scan_type, value)
        if pattern is None:
            return False, perr
        try:
            res = self._rpc_call("scanValue", pattern, prot or "rw-", int(cap))
            self._scan_results = list(res or [])
            self._scan_type = (scan_type or "int32").lower()
            return True, self._scan_summary(f"Initial scan {scan_type}={value}")
        except Exception as exc:
            return False, f"scan failed: {exc}"

    def scan_next(self, value) -> Tuple[bool, str]:
        err = self._need_script()
        if err:
            return False, err
        if not self._scan_results:
            return False, "No previous scan to refine. Run `frida scan` first."
        pattern, perr = _value_to_pattern(self._scan_type, value)
        if pattern is None:
            return False, perr
        try:
            res = self._rpc_call("refine", self._scan_results, pattern)
            self._scan_results = list(res or [])
            return True, self._scan_summary(f"Refined to {self._scan_type}={value}")
        except Exception as exc:
            return False, f"scan_next failed: {exc}"

    def scan_aob(self, pattern: str, prot: str = "r-x", cap: int = 2000) -> Tuple[bool, str]:
        err = self._need_script()
        if err:
            return False, err
        if not pattern:
            return False, "aob scan requires a pattern (e.g. '89 47 44 ?? ?? 5B')."
        try:
            res = self._rpc_call("scanAob", pattern, prot or "r-x", int(cap))
            addrs = list(res or [])
            head = "\n".join(addrs[:60])
            return True, f"AoB '{pattern}' → {len(addrs)} match(es):\n{head}"
        except Exception as exc:
            return False, f"aob scan failed: {exc}"

    def _scan_summary(self, title: str) -> str:
        n = len(self._scan_results)
        head = "\n".join(self._scan_results[:40])
        tip = ""
        if n > 3:
            tip = ("\nTip: change the value in-game (take damage / spend coins), then `frida scan_next` "
                   "with the new value to narrow down.")
        elif 1 <= n <= 3:
            tip = "\nNarrowed enough — use `frida write` or `frida freeze` on these address(es)."
        return f"{title}: {n} address(es)." + (f"\n{head}" if head else "") + tip

    # ── read / write / freeze ─────────────────────────────────────────────────
    def read(self, address: str, scan_type: str = "") -> Tuple[bool, str]:
        err = self._need_script()
        if err:
            return False, err
        t = (scan_type or self._scan_type or "int32").lower()
        try:
            r = self._rpc_call("readValue", address, t)
            if isinstance(r, dict) and r.get("error"):
                return False, f"read failed @ {address}: {r['error']}"
            return True, f"[{address}] ({t}) = {r.get('value') if isinstance(r, dict) else r}"
        except Exception as exc:
            return False, f"read failed: {exc}"

    def write(self, address: str, scan_type: str, value) -> Tuple[bool, str]:
        err = self._need_script()
        if err:
            return False, err
        t = (scan_type or self._scan_type or "int32").lower()
        try:
            r = self._rpc_call("writeValue", address, t, value)
            if isinstance(r, dict) and r.get("error"):
                return False, f"write failed @ {address}: {r['error']}"
            return True, f"Wrote {value} ({t}) → {address}."
        except Exception as exc:
            return False, f"write failed: {exc}"

    def freeze(self, address: str, scan_type: str, value) -> Tuple[bool, str]:
        err = self._need_script()
        if err:
            return False, err
        t = (scan_type or self._scan_type or "int32").lower()
        try:
            r = self._rpc_call("freeze", address, t, value)
            if isinstance(r, dict) and r.get("error"):
                return False, f"freeze failed @ {address}: {r['error']}"
            return True, f"❄️ Frozen {address} = {value} ({t}) — rewritten every 100ms."
        except Exception as exc:
            return False, f"freeze failed: {exc}"

    def unfreeze(self, address: str = "") -> Tuple[bool, str]:
        err = self._need_script()
        if err:
            return False, err
        try:
            if address:
                self._rpc_call("unfreeze", address)
                return True, f"Unfroze {address}."
            self._rpc_call("unfreezeAll")
            return True, "Unfroze all addresses."
        except Exception as exc:
            return False, f"unfreeze failed: {exc}"

    # ── modules / exports ─────────────────────────────────────────────────────
    def list_modules(self, filter_text: str = "") -> Tuple[bool, str]:
        err = self._need_script()
        if err:
            return False, err
        try:
            mods = self._rpc_call("listModules")
            ft = (filter_text or "").lower()
            rows = []
            for m in mods or []:
                if ft and ft not in m.get("name", "").lower():
                    continue
                rows.append(f"{m.get('base')}\t{m.get('name')}")
            return True, "BASE\tNAME\n" + "\n".join(rows[:300])
        except Exception as exc:
            return False, f"list_modules failed: {exc}"

    def list_exports(self, module_name: str) -> Tuple[bool, str]:
        err = self._need_script()
        if err:
            return False, err
        if not module_name:
            return False, "exports requires a module name (see `frida modules`)."
        try:
            exps = self._rpc_call("listExports", module_name)
            if isinstance(exps, dict) and exps.get("error"):
                return False, exps["error"]
            rows = [f"{e.get('address')}\t{e.get('type')}\t{e.get('name')}" for e in (exps or [])]
            return True, f"{len(rows)} export(s) in {module_name}:\n" + "\n".join(rows[:300])
        except Exception as exc:
            return False, f"list_exports failed: {exc}"

    # ── hooking ───────────────────────────────────────────────────────────────
    def _resolve_target(self, target: str) -> Tuple[Optional[str], str]:
        """Resolve 'module!export', a bare export, or a raw address to an address string."""
        t = (target or "").strip()
        if not t:
            return None, "hook target is empty."
        if t.startswith("0x") or t.isdigit():
            return t, ""
        if "!" in t:
            mod, name = t.split("!", 1)
        else:
            mod, name = "", t
        try:
            addr = self._rpc_call("resolveSymbol", mod, name)
            if isinstance(addr, dict) and addr.get("error"):
                return None, addr["error"]
            if not addr:
                return None, f"Could not resolve symbol '{target}'."
            return addr, ""
        except Exception as exc:
            return None, f"resolveSymbol failed: {exc}"

    def hook(self, target: str, on_enter: str = "", on_leave: str = "") -> Tuple[bool, str]:
        err = self._need_script()
        if err:
            return False, err
        addr, rerr = self._resolve_target(target)
        if addr is None:
            return False, rerr
        try:
            r = self._rpc_call("hook", addr, on_enter or "", on_leave or "")
            if isinstance(r, dict) and r.get("error"):
                return False, f"hook failed: {r['error']}"
            return True, f"🪝 Hooked {target} @ {addr}. Use `frida hook_log` to read captured calls."
        except Exception as exc:
            return False, f"hook failed: {exc}"

    def force_return(self, target: str, retval) -> Tuple[bool, str]:
        err = self._need_script()
        if err:
            return False, err
        addr, rerr = self._resolve_target(target)
        if addr is None:
            return False, rerr
        try:
            r = self._rpc_call("forceReturn", addr, str(retval))
            if isinstance(r, dict) and r.get("error"):
                return False, f"forceReturn failed: {r['error']}"
            return True, f"Forced {target} @ {addr} to always return {retval}."
        except Exception as exc:
            return False, f"forceReturn failed: {exc}"

    def hook_log(self) -> Tuple[bool, str]:
        with self._lock:
            logs = self._hook_log[-200:]
            self._hook_log = []
        if not logs:
            return True, "(no hook events captured yet)"
        return True, "\n".join(logs)

    def unhook(self) -> Tuple[bool, str]:
        err = self._need_script()
        if err:
            return False, err
        try:
            self._rpc_call("unhookAll")
            return True, "Removed all hooks."
        except Exception as exc:
            return False, f"unhook failed: {exc}"

    def status(self) -> str:
        if not _FRIDA_AVAILABLE:
            return f"Frida: NOT installed ({_FRIDA_IMPORT_ERR}). pip install frida frida-tools"
        dev = getattr(self.device, "name", None) if self.device else None
        where = f"device={dev}" if dev else f"device-type={self.device_type} (not connected)"
        tgt = self.attached_label or "(not attached)"
        return f"Frida: available; {where}; target={tgt}; last-scan={len(self._scan_results)} addr(s)."


_CONTROLLER: Optional[FridaController] = None


def get_frida() -> FridaController:
    global _CONTROLLER
    if _CONTROLLER is None:
        _CONTROLLER = FridaController()
    return _CONTROLLER
