
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
import time
import math
import random
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from urllib.parse import quote_plus
import importlib
import threading

# ---------- Optional modules ----------
try:
    import keyboard  # global hotkeys
except Exception:
    keyboard = None
try:
    from voice.voice_daemon import VoiceDaemon
except Exception:
    VoiceDaemon = None
try:
    import pyautogui
    import pyperclip
except Exception:
    pyautogui = None
    pyperclip = None
try:
    import pygetwindow as gw
except Exception:
    gw = None
try:
    from lxml import etree as ET  # preferred
except Exception:
    import xml.etree.ElementTree as ET  # type: ignore

# ---------- Logger ----------
def _setup_logger() -> logging.Logger:
    log = logging.getLogger("usefulclicker")
    if not log.handlers:
        log.setLevel(logging.INFO)
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
        log.addHandler(h)
    return log

# ---------- Substitutions & helpers ----------
_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:\|([A-Za-z_][A-Za-z0-9_]*))?\}")

def _apply_filter(value: str, filt: Optional[str]) -> str:
    f = (filt or "").strip().lower()
    if f in ("url", "urlencode", "quote", "quote_plus"):
        return quote_plus(str(value))
    return str(value)

def _substitute_vars(value: Optional[str], variables: Dict[str, Any]) -> str:
    if value is None:
        return ""
    def repl(m):
        var = m.group(1)
        filt = m.group(2)
        raw = variables.get(var, "")
        return _apply_filter(raw, filt)
    return _VAR_PATTERN.sub(repl, value)

def _maybe_int(v: str):
    try: return int(v)
    except Exception: return v

def _maybe_float(v: str):
    try: return float(v)
    except Exception: return v

def _smart_cast(s: Any):
    if isinstance(s, (int, float, bool)):
        return s
    st = str(s).strip()
    if st.lower() in ("1","true","yes","on"): return True
    if st.lower() in ("0","false","no","off"): return False
    v = _maybe_int(st)
    if isinstance(v, str): v = _maybe_float(v)
    return v

_ALLOWED_MATH = {
    "pi": math.pi, "e": math.e, "tau": math.tau,
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "exp": math.exp,
    "abs": abs, "min": min, "max": max, "round": round,
    "True": True, "False": False,
    "randint": lambda a,b: random.randint(int(a), int(b)),
    "uniform": lambda a,b: random.uniform(float(a), float(b)),
    "urlquote": lambda s: quote_plus(str(s)),
}

def _safe_eval(expr: str, vars_: Dict[str, Any]) -> Any:
    expr = (expr or "").replace("&lt;","<").replace("&gt;",">")
    env = dict(_ALLOWED_MATH); env.update(vars_)
    return eval(expr, {"__builtins__": {}}, env)

# ---------- Low-level actions ----------
def _safe_point(x: int, y: int, margin: int = 5) -> tuple[int, int]:
    if not pyautogui:
        return x, y
    try:
        sw, sh = pyautogui.size()
    except Exception:
        sw, sh = 1920, 1080
    x = max(margin, min(int(x), sw - margin))
    y = max(margin, min(int(y), sh - margin))
    return x, y

def _move_then_click(x: int, y: int, button: str = "left", retries: int = 2, allow_corner: bool = False):
    if not pyautogui: return
    try:
        if not allow_corner:
            x, y = _safe_point(x, y, margin=5)
        pyautogui.moveTo(x, y, duration=0.02)
        pyautogui.click(x=x, y=y, button=button)
    except Exception as e:
        if isinstance(e, getattr(pyautogui, "FailSafeException", Exception)) or "FailSafe" in str(e):
            for _ in range(retries):
                try:
                    if not allow_corner:
                        sw, sh = pyautogui.size()
                        pyautogui.moveTo(sw//2, sh//2, duration=0.05)
                        x2, y2 = _safe_point(x, y, margin=8)
                        pyautogui.moveTo(x2, y2, duration=0.03)
                        pyautogui.click(x=x2, y=y2, button=button); return
                    else:
                        pyautogui.click(x=x, y=y, button=button); return
                except Exception:
                    time.sleep(0.05)
        raise

def _hotkey(combo: str, delay_ms: Optional[int] = None):
    sent = False
    try:
        if keyboard:
            keyboard.send('+'.join([p.strip() for p in combo.split('+') if p.strip()]))
            sent = True
    except Exception:
        sent = False
    if not sent and pyautogui:
        keys = [p.strip().lower() for p in combo.split('+') if p.strip()]
        if keys: pyautogui.hotkey(*keys)
    if delay_ms: time.sleep(delay_ms/1000.0)

def _keysequence(seq: str, delay_ms: Optional[int] = None):
    if not pyautogui: return
    if delay_ms:
        for ch in seq: pyautogui.write(ch); time.sleep(delay_ms/1000.0)
    else:
        pyautogui.write(seq)

def _type_text(text: str, mode: str = "type"):
    if not pyautogui: return
    s = str(text)
    if mode.lower() != "copy_paste" or not pyperclip:
        pyautogui.write(s); return
    ok = False
    for attempt in range(5):
        try: pyperclip.copy(s)
        except Exception: time.sleep(0.1); continue
        time.sleep(0.15 + 0.05*attempt)
        try: cur = pyperclip.paste()
        except Exception: cur = None
        if cur == s:
            ok = True; break
    if ok: pyautogui.hotkey("ctrl","v")
    else:  pyautogui.write(s)

# ---------- LLM fallbacks ----------
_NUMBER_PREFIX = re.compile(r"""^\s*(?:\d+[\)\.\-:]|[\-\•\*])\s*""", re.X)

def _cleanup_list_item(s: str) -> str:
    s = s.strip(); s = _NUMBER_PREFIX.sub("", s)
    return s.strip(" \t\"'“”‘’")

def _llm_generate_list(prompt: str, separator: str = "\n", logger: logging.Logger = _setup_logger()) -> List[str]:
    try:
        from llm.openai_client import LLMClient
        client = LLMClient()
        raw_items = client.generate_list(prompt, separator=separator)
    except Exception as e:
        logger.info(f"Exception: {e}")
        raw_items = [prompt]
    out: List[str] = []
    for it in raw_items or []:
        s = str(it or "")
        parts = s.split(separator) if ("\n" in s and len(raw_items)==1) else [s]
        for p in parts:
            p = _cleanup_list_item(p)
            if p: out.append(p)
    return out

def _llm_generate_text(prompt: str, logger) -> str:
    try:
        from llm.openai_client import LLMClient
        client = LLMClient()
        return client.generate_text(prompt)
    except Exception as e:
        logger.info(f"Exception: {e}")
        return "\n".join(_llm_generate_list(prompt, logger=logger))

# ---------- Engine ----------
class XMLProgram:
    def __init__(self, xml_path: Path, debug: bool=False, log_path: Optional[Path]=None):
        self.xml_path = Path(xml_path)
        self.debug = debug
        self.logger = _setup_logger()
        self.variables: Dict[str, Any] = {}
        self.functions: Dict[str, ET.Element] = {}
        self.xml_text: str = ""
        self.tree = None

        # State
        self.skip_wait = False
        self.paused = False
        self._hotkeys_started = False
        self._last_ctrlspace = False

        # Ext caches
        self._extnode_cache = {}
        self._extmodule_cache = {}

        # Voice
        self.voice = None

        # Screen defaults
        try:
            if pyautogui:
                sw, sh = pyautogui.size()
                self.variables["SCREEN_W"] = int(sw)
                self.variables["SCREEN_H"] = int(sh)
        except Exception:
            pass
        self.variables.setdefault("SCREEN_W", 1920)
        self.variables.setdefault("SCREEN_H", 1080)

        self._load_xml()
        self._start_pause_listener()

    # ---------- Hotkeys ----------
    def _start_pause_listener(self):
        if self._hotkeys_started:
            return
        def _worker():
            if keyboard is None:
                self.logger.info("Hotkeys: 'keyboard' module unavailable; using inline polling fallback.")
                return
            try:
                keyboard.add_hotkey("ctrl+space", self._toggle_pause)
                keyboard.add_hotkey("ctrl+n", self._skip_wait_now)
                self.logger.info("PAUSE: press <ctrl+Space> to toggle pause/resume.")
                self.logger.info("NEXT:  press <ctrl+N> to skip current wait/step.")
                self._hotkeys_started = True
                keyboard.wait()
            except Exception as e:
                self.logger.info(f"Hotkeys listener error: {e}")
        threading.Thread(target=_worker, daemon=True).start()

    def _toggle_pause(self):
        self.paused = not self.paused
        self.logger.info(f"PAUSE {'ON' if self.paused else 'OFF'}")

    def _skip_wait_now(self):
        self.skip_wait = True
        self.logger.info("WAIT skip requested (Ctrl+N)")

    def _poll_hotkeys_inline(self):
        if keyboard is None: return
        try:
            if keyboard.is_pressed("ctrl") and keyboard.is_pressed("n"):
                self.skip_wait = True
            pressed = keyboard.is_pressed("ctrl") and keyboard.is_pressed("space")
            if pressed and not self._last_ctrlspace:
                self._toggle_pause(); self._last_ctrlspace = True
            if not pressed and self._last_ctrlspace:
                self._last_ctrlspace = False
        except Exception:
            pass

    def _pause_gate(self):
        while self.paused:
            self._poll_hotkeys_inline()
            time.sleep(0.05)
            try:
                from voice.voice_daemon import PAUSE_TOGGLE_EVENT
                if PAUSE_TOGGLE_EVENT.is_set():
                    PAUSE_TOGGLE_EVENT.clear()
                    self.paused = not self.paused
                    self.logger.info(f"PAUSE {'ON' if self.paused else 'OFF'} (hotkey bridge)")
            except Exception:
                pass


    def _sleep_ms_interruptible(self, total_ms: int):
        if total_ms <= 0: return
        end_ts = time.time() + total_ms/1000.0
        step = 0.05
        while True:
            self._poll_hotkeys_inline()
            
            # в _sleep_ms_interruptible(...) перед/после проверки self.skip_wait
            try:
                from voice.voice_daemon import SKIP_EVENT
                if SKIP_EVENT.is_set():
                    SKIP_EVENT.clear()
                    self.logger.info("WAIT interrupted (hotkey bridge)")
                    return
            except Exception:
                pass

            if self.skip_wait:
                self.skip_wait = False
                self.logger.info("WAIT interrupted")
                return
            if self.paused:
                time.sleep(step); continue
            now = time.time()
            if now >= end_ts: return
            time.sleep(step if (end_ts-now)>step else (end_ts-now))

    # ---------- XML Loading & <include> ----------
    def _load_xml(self):
        raw = self.xml_path.read_text(encoding="utf-8")
        root_dir = self.xml_path.parent

        def _strip_prolog(s: str) -> str:
            return re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", s, flags=re.I)

        def _inner_program(s: str) -> str:
            s2 = _strip_prolog(s)
            try:
                t = ET.fromstring(s2.encode("utf-8"))
                if isinstance(getattr(t, "tag", None), str) and t.tag.lower() == "program":
                    parts = [ET.tostring(ch, encoding="unicode") for ch in list(t)]
                    return "\n".join(parts)
            except Exception:
                pass
            return s2

        def repl_include(m):
            rel = (m.group(1) or "").strip()
            inc_path = (root_dir / rel).resolve()
            if not inc_path.exists():
                self.logger.info(f"Include not found: {inc_path}")
                return ""
            return _inner_program(inc_path.read_text(encoding="utf-8"))

        text = re.sub(r"<include>\s*(.*?)\s*</include>", repl_include, raw, flags=re.I|re.S)
        self.xml_text = text
        self.tree = ET.fromstring(self.xml_text.encode("utf-8"))

        for func in self.tree.findall(".//func"):
            name = func.get("name")
            if name:
                self.functions[name] = func

    # ---------- Delays ----------
    def _delays(self, node: ET.Element):
        df = node.get("delay_fixed")
        dm = node.get("delay_ms")
        if df:
            try: self._sleep_ms_interruptible(int(df))
            except Exception: pass
        if dm:
            try:
                jitter = random.uniform(0, int(dm)/1000.0)
                self._sleep_ms_interruptible(int(jitter*1000))
            except Exception:
                pass

    # ---------- Voice ----------
    def _ensure_voice(self):
        if self.voice is not None: return
        flag_xml = str(self.variables.get("VOICE_ENABLED", "0")).strip().lower() in ("1","true","yes")
        flag_env = str(os.getenv("USEFULCLICKER_VOICE","0")).strip().lower() in ("1","true","yes")
        if not (flag_xml or flag_env): return
        if VoiceDaemon is None:
            self.logger.info("VOICE: VoiceDaemon not available (import failed)."); return
        dev = self.variables.get("VOICE_DEVICE")
        try: dev = int(dev) if (dev is not None and str(dev).strip()!="") else None
        except Exception: dev = None
        try:
            self.voice = VoiceDaemon(model_name="base", device=dev, lang=None).start()
            self.logger.info("VOICE: background voice daemon started.")
        except Exception as e:
            self.logger.info(f"VOICE: failed to start ({e})"); self.voice = None

    # ---------- Handlers ----------
    def handle_set(self, node: ET.Element):
        for k,v in list(node.attrib.items()):
            if k in ("delay_fixed","delay_ms"): continue
            expr = _substitute_vars(v, self.variables)
            try: val = _safe_eval(expr, self.variables)
            except Exception: val = expr
            self.logger.info(f"SET {k} = {val}")
            self.variables[k] = val
        self._delays(node)

    def handle_if(self, node: ET.Element):
        cond_raw = node.get("cond","")
        try: cond_expanded = _substitute_vars(cond_raw, self.variables)
        except Exception: cond_expanded = cond_raw
        try:
            res = bool(eval(cond_expanded.strip() or "False", {"__builtins__": {}}, {}))
            self.logger.info(f"IF cond='{cond_expanded}' -> {res}")
        except Exception as e:
            self.logger.info(f"IF eval error: cond='{cond_expanded}' ({e}) -> False")
            res = False

        in_else = False
        for child in list(node):
            tag = getattr(child, "tag", None)
            if not isinstance(tag, str): continue
            if tag.lower()=="else":
                in_else = True; continue
            if (res and not in_else) or ((not res) and in_else):
                self._exec_node(child)

    def handle_check(self, node: ET.Element):
        tol = float(node.get("tol")) if node.get("tol") else None
        for k,v in list(node.attrib.items()):
            if k in ("delay_fixed","delay_ms","tol","comment"): continue
            expected_raw = _substitute_vars(v, self.variables)
            actual = self.variables.get(k)
            ok = False
            if tol is not None:
                try:
                    exp = float(_safe_eval(expected_raw, self.variables))
                    act = float(actual)
                    ok = abs(exp-act) <= tol
                except Exception:
                    ok = False
            else:
                ok = str(actual) == expected_raw
            self.logger.info(f"CHECK {k}: actual={actual} expected={expected_raw} tol={tol} -> {ok}")
            if not ok:
                raise AssertionError(f"Check failed for {k}: actual={actual}, expected={expected_raw}")
        self._delays(node)

    def handle_type(self, node: ET.Element):
        mode = node.get("mode","type")
        text = _substitute_vars(node.get("text",""), self.variables)
        self.logger.info(f"TYPE mode={mode} text='{text[:60]}'")
        _type_text(text, mode=mode)
        self._delays(node)

    def handle_click(self, node: ET.Element):
        button = node.get("button","left")
        allow_corner = str(node.get("allow_corner","0")).strip().lower() in ("1","true","yes")
        area = node.get("area")
        if area:
            area_eval = _substitute_vars(area, self.variables)
            parts = []
            for p in area_eval.split(","):
                p = p.strip()
                if not p: continue
                try: v = _safe_eval(p, self.variables)
                except Exception: v = p
                parts.append(int(float(v)))
            if len(parts) != 4:
                raise ValueError("area must be 'x1,y1,x2,y2' after substitution")
            self.logger.info(f"CLICK area={parts} button={button}")
            x1,y1,x2,y2 = parts
            rx = random.randint(min(x1,x2), max(x1,x2))
            ry = random.randint(min(y1,y2), max(y1,y2))
            _move_then_click(rx, ry, button=button, allow_corner=allow_corner)
        else:
            x_raw = _substitute_vars(node.get("x"), self.variables)
            y_raw = _substitute_vars(node.get("y"), self.variables)
            try:
                x = int(float(_safe_eval(x_raw, self.variables)))
                y = int(float(_safe_eval(y_raw, self.variables)))
            except Exception:
                x = int(float(x_raw)); y = int(float(y_raw))
            self.logger.info(f"CLICK x={x} y={y} button={button}")
            _move_then_click(x, y, button=button, allow_corner=allow_corner)
        self._delays(node)

    def handle_voice_event(self, node: ET.Element):
        self._ensure_voice()
        want = (node.get("type") or "any").lower()
        out = node.get("out") or "VOICE_TEXT"
        wait_ms = int(node.get("wait","0"))
        text, typ = "", ""

        if self.voice is None:
            self.variables[out] = text; self.variables[out+"_type"] = typ
            self._delays(node); return

        if hasattr(self.voice, "get_event"):
            deadline = time.time() + (wait_ms/1000.0) if wait_ms else None
            while True:
                self._pause_gate()
                if self.skip_wait:
                    self.skip_wait = False
                    self.logger.info("VOICE_EVENT interrupted by Ctrl+N")
                    break
                evt = self.voice.get_event(timeout_ms=200)
                if evt:
                    if want in ("any", getattr(evt, "type","")):
                        text = getattr(evt,"text","") or ""
                        typ  = getattr(evt,"type","") or ""
                        break
                if deadline and time.time()>deadline: break
        else:
            deadline = time.time() + (wait_ms/1000.0) if wait_ms else None
            while True:
                self._pause_gate()
                if self.skip_wait:
                    self.skip_wait = False
                    self.logger.info("VOICE_EVENT interrupted by Ctrl+N")
                    break
                evt = None
                if want in ("any","command"):
                    evt = self.voice.get_next_command(timeout_ms=0)
                    if evt and (want in ("any","command")):
                        text, typ = evt.text, "command"; break
                if want in ("any","query"):
                    evt = self.voice.get_next_query(timeout_ms=0)
                    if evt and (want in ("any","query")):
                        text, typ = evt.text, "query"; break
                if deadline and time.time()>deadline: break
                time.sleep(0.05)

        self.variables[out] = text
        self.variables[out+"_type"] = typ
        self.logger.info(f"VOICE_EVENT -> {out}='{text}' type='{typ}'")
        self._delays(node)

    def handle_hotkey(self, node: ET.Element):
        combo = node.get("hotkey"); seq = node.get("keysequence")
        d = node.get("delay_ms"); d_ms = int(d) if d else None
        if combo:
            self.logger.info(f"HOTKEY {combo}"); _hotkey(combo, delay_ms=d_ms)
        elif seq:
            self.logger.info(f"KEYSEQUENCE '{seq}'"); _keysequence(seq, delay_ms=d_ms)
        self._delays(node)

    def _decode_escapes(self, s: str) -> str:
        return s.encode("utf-8").decode("unicode_escape")

    def handle_shell(self, node: ET.Element):
        shell_type = (node.get("shell_type") or "cmd").lower()
        bg = str(node.get("bg","0")).strip().lower() in ("1","true","yes")
        show_console = str(node.get("showConsole","0")).strip().lower() in ("1","true","yes")
        sep_raw = node.get("separator") or "\n"
        separator = self._decode_escapes(sep_raw)
        out_var = node.get("output_var")
        out_fmt = (node.get("output_format") or "text").lower()
        cmd_raw = node.get("cmd") or (node.text or "")
        cmd_expanded = _substitute_vars(cmd_raw, self.variables)
        self.logger.info(f"SHELL type={shell_type} bg={bg} cmd={cmd_expanded}")

        if shell_type in ("cmd","cmd.exe","windows","win"):
            exe="cmd"; args=[exe,"/c",cmd_expanded]; creationflags=0 if show_console else 0x08000000
        elif shell_type in ("powershell","pwsh"):
            exe="powershell"; args=[exe,"-NoProfile","-Command",cmd_expanded]; creationflags=0 if show_console else 0x08000000
        elif shell_type in ("bash","sh"):
            exe="bash"; args=[exe,"-lc",cmd_expanded]; creationflags=0
        else:
            exe = "cmd" if os.name=="nt" else "bash"
            args=[exe, "/c" if os.name=="nt" else "-lc", cmd_expanded]
            creationflags=0 if show_console or os.name!="nt" else 0x08000000

        try:
            if bg and not out_var:
                subprocess.Popen(args, creationflags=creationflags)
            else:
                cp = subprocess.run(args, capture_output=True, text=True, creationflags=creationflags, check=False)
                stdout = (cp.stdout or "").strip(); stderr = (cp.stderr or "").strip()
                if stderr: self.logger.info(f"SHELL stderr: {stderr}")
                if out_var is not None:
                    if out_fmt=="list":
                        self.variables[out_var] = [s for s in stdout.split(separator) if s.strip()]
                    else:
                        self.variables[out_var] = stdout
        except Exception as e:
            self.logger.info(f"SHELL error: {e}")
        self._delays(node)

    def handle_focus(self, node: ET.Element):
        title = node.get("title") or node.get("title_contains") or ""
        retries = int(node.get("retries","20")); interval_ms=int(node.get("interval_ms","200"))
        if not gw:
            self.logger.info("FOCUS skipped: pygetwindow not available"); self._delays(node); return
        ok=False
        for _ in range(retries):
            try:
                for w in gw.getAllWindows():
                    if title.lower() in (w.title or "").lower():
                        try: w.minimize(); w.restore()
                        except Exception: pass
                        try: w.activate(); ok=True; break
                        except Exception:
                            try: w.maximize(); w.restore(); w.activate(); ok=True; break
                            except Exception: pass
                if ok: break
                time.sleep(interval_ms/1000.0)
            except Exception:
                time.sleep(interval_ms/1000.0)
        self.logger.info(f"FOCUS title~='{title}' -> {ok}")
        self._delays(node)

    def handle_llmcall(self, node: ET.Element):
        out_var = node.get("output_var")
        if not out_var: return
        out_fmt = (node.get("output_format") or "text").lower()
        sep = node.get("separator") or "\n"
        sep = sep.encode("utf-8").decode("unicode_escape")
        prompt = node.get("prompt") or (node.text or "")
        prompt = _substitute_vars(prompt, self.variables)
        if out_fmt=="list":
            items = _llm_generate_list(prompt, separator=sep, logger=self.logger)
            clean = [_cleanup_list_item(str(s)) for s in items if _cleanup_list_item(str(s))]
            self.variables[out_var] = clean
        else:
            text = _llm_generate_text(prompt, self.logger)
            self.variables[out_var] = text
        self.logger.info(f"LLMCALL -> {out_var} (format={out_fmt})")
        self._delays(node)

    def handle_foreach(self, node: ET.Element):
        list_attr = node.get("list") or ""
        func_name = node.get("do") or ""
        var_name = node.get("var") or "item"
        if not func_name: return
        if list_attr in self.variables: data = self.variables[list_attr]
        else:
            raw = _substitute_vars(list_attr, self.variables)
            data = [s for s in re.split(r"[\r\n]+", raw) if s.strip()]
        if isinstance(data, str):
            items = [s for s in re.split(r"[\r\n]+", data) if s.strip()]
        else:
            items = list(data)
        shuffle = node.attrib.get("random_shuffle","0")
        if shuffle in ("1","true","yes"): random.shuffle(items)
        if func_name not in self.functions:
            raise ValueError(f"Unknown function in foreach: {func_name}")
        for idx, val in enumerate(items):
            self._pause_gate()
            self.variables[var_name] = val
            self.variables["index"] = idx
            self.variables["arg0"] = val
            func = self.functions[func_name]
            for child in list(func):
                self._pause_gate()
                self._exec_node(child)
        self._delays(node)

    def handle_repeat(self, node: ET.Element):
        expr = node.get("times") or node.get("count") or "0"
        try: n = int(_safe_eval(_substitute_vars(expr, self.variables), self.variables))
        except Exception: n = 0
        n = max(0, n)
        self.logger.info(f"REPEAT times={n}")
        for _ in range(n):
            for child in list(node):
                self._pause_gate()
                self._exec_node(child)
        self._delays(node)

    def handle_call(self, node: ET.Element):
        name = node.get("name")
        if not name or name not in self.functions:
            raise ValueError(f"Unknown function: {name}")
        for k,v in node.attrib.items():
            if k.startswith("arg"):
                self.variables[k] = _substitute_vars(v, self.variables)
        self.logger.info(f"CALL {name}")
        func = self.functions[name]
        for child in list(func):
            self._exec_node(child)
        self._delays(node)

    def handle_func(self, node: ET.Element):
        pass

    def handle_wait(self, node: ET.Element):
        ms = int(node.get("ms","0"))
        self.logger.info(f"WAIT {ms}ms (pause=Ctrl+Space, skip=Ctrl+N)")
        self._sleep_ms_interruptible(ms)

    def handle_voice_poll(self, node: ET.Element):
        self._ensure_voice()
        out_cmd = node.get("out_cmd") or "VOICE_CMD"
        out_query = node.get("out_query") or "VOICE_QUERY"
        cmd, query = "", ""
        if self.voice:
            evt_cmd = self.voice.get_next_command(timeout_ms=0)
            if evt_cmd:
                cmd = evt_cmd.text
                if getattr(evt_cmd, "payload", None) and "seconds" in evt_cmd.payload:
                    self.variables[out_cmd+"_seconds"] = evt_cmd.payload["seconds"]
            evt_query = self.voice.get_next_query(timeout_ms=0)
            if evt_query: query = evt_query.text
        self.variables[out_cmd] = cmd
        self.variables[out_query] = query
        self.logger.info(f"VOICE_POLL -> {out_cmd}='{cmd}' {out_query}='{query}'")
        self._delays(node)

    def handle_extnode(self, node: ET.Element):
        mod_name = node.get("module"); cls_name = node.get("class"); method = node.get("method")
        out_var = node.get("output_var")
        if not mod_name or not method: raise RuntimeError("<extnode> requires module and method")
        mod = self._extmodule_cache.get(mod_name)
        if mod is None:
            mod = importlib.import_module(mod_name); self._extmodule_cache[mod_name] = mod
        if cls_name:
            key = (mod_name, cls_name)
            inst = self._extnode_cache.get(key)
            if inst is None:
                cls = getattr(mod, cls_name); inst = cls(); self._extnode_cache[key] = inst
            call_target = getattr(inst, method)
        else:
            call_target = getattr(mod, method)
        kw: Dict[str, Any] = {}
        for k,v in node.attrib.items():
            if k in {"module","class","method","output_var","delay_fixed","delay_ms","func","output_format","separator"}: continue
            vv = _substitute_vars(v, self.variables)
            if k in ("disciplines","subtopics") or k.lower().endswith("_list"):
                kw[k] = [p.strip() for p in vv.split(",") if p.strip()]
            else:
                kw[k] = _smart_cast(vv)
        res = call_target(**kw) if kw else call_target()
        if out_var:
            self.variables[out_var] = "" if res is None else res
        self._delays(node)

    # ---------- Dispatcher ----------
    def _exec_node(self, node: ET.Element):
        self._pause_gate()
        tag = node.tag if isinstance(getattr(node, "tag", None), str) else ""
        tagl = tag.lower()
        if tagl == "set": self.handle_set(node)
        elif tagl == "if": self.handle_if(node); return
        elif tagl == "voice_poll": self.handle_voice_poll(node)
        elif tagl == "check": self.handle_check(node)
        elif tagl == "type": self.handle_type(node)
        elif tagl == "click": self.handle_click(node)
        elif tagl == "hotkey": self.handle_hotkey(node)
        elif tagl == "shell": self.handle_shell(node)
        elif tagl == "focus": self.handle_focus(node)
        elif tagl == "llmcall": self.handle_llmcall(node)
        elif tagl == "foreach": self.handle_foreach(node)
        elif tagl == "func": self.handle_func(node)
        elif tagl == "call": self.handle_call(node)
        elif tagl == "repeat": self.handle_repeat(node)
        elif tagl == "wait": self.handle_wait(node)
        elif tagl == "extnode": self.handle_extnode(node)
        elif tagl == "voice_event": self.handle_voice_event(node)
        else: pass

    # ---------- Run ----------
    def run(self):
        for node in list(self.tree):
            tag = node.tag if isinstance(getattr(node, "tag", None), str) else ""
            if tag.lower()=="func": continue
            if tag=="": continue
            self._exec_node(node)

# If executed directly
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("xml_path")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--log", default=None)
    args = ap.parse_args()
    prog = XMLProgram(Path(args.xml_path), debug=args.debug, log_path=args.log)
    prog.run()
