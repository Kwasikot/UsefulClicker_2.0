# -*- coding: utf-8 -*-
from __future__ import annotations
import sys, os, re, time, math, random, logging, subprocess, importlib, threading, platform
from pathlib import Path
from typing import Dict, Any, Optional, List
from urllib.parse import quote_plus

# -------- Logger --------
def _setup_logger() -> logging.Logger:
    log = logging.getLogger("usefulclicker")
    if not log.handlers:
        log.setLevel(logging.INFO)
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
        log.addHandler(h)
    return log

logger = _setup_logger()

# Exception used to signal requested restart (distinct from exit)
class RestartRequested(Exception):
    pass

# -------- Hotkey bridge (WinAPI) --------
SKIP_EVENT = None
PAUSE_TOGGLE_EVENT = None
EXIT_EVENT = None
try:
    if platform.system().lower() == "windows":
        sys.path.insert(0, os.path.dirname(__file__))
        from hotkeys_win_safe import start_hotkeys, SKIP_EVENT as _SE, PAUSE_TOGGLE_EVENT as _PE, EXIT_EVENT as _EE
        start_hotkeys()
        SKIP_EVENT = _SE
        PAUSE_TOGGLE_EVENT = _PE
        EXIT_EVENT = _EE
        print("[xml_engine_full_voice] hotkeys_win_safe started", file=sys.stderr)
except Exception as e:
    print(f"[xml_engine_full_voice] hotkeys bridge unavailable: {e}", file=sys.stderr)

# -------- Optional modules --------
try:
    import keyboard
except Exception:
    keyboard = None

try:
    import pyautogui, pyperclip
except Exception:
    pyautogui = None; pyperclip = None

try:
    import pygetwindow as gw
except Exception:
    gw = None

try:
    from lxml import etree as ET
except Exception:
    import xml.etree.ElementTree as ET  # type: ignore

# Voice (optional)
# перед import VoiceDaemon:
try:
    from voice.voice_daemon import VoiceDaemon
except Exception:
    # Fallback: подцепить файл по относительному пути, если нет пакета voice
    import importlib.util, os
    p = os.path.join(os.path.dirname(__file__), "voice_daemon.py")
    if os.path.exists(p):
        spec = importlib.util.spec_from_file_location("voice_daemon", p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        VoiceDaemon = getattr(m, "VoiceDaemon", None)
    else:
        VoiceDaemon = None


# -------- Substitution & eval --------
_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:\|([A-Za-z_][A-Za-z0-9_]*))?\}")

def _apply_filter(value: str, filt: Optional[str]) -> str:
    f = (filt or "").strip().lower()
    if f in ("url","urlencode","quote","quote_plus"):
        return quote_plus(str(value))
    return str(value)

def _substitute_vars(value: Optional[str], variables: Dict[str, Any]) -> str:
    if value is None: return ""
    def repl(m):
        var, filt = m.group(1), m.group(2)
        raw = variables.get(var, "")
        return _apply_filter(raw, filt)
    return _VAR_PATTERN.sub(repl, value)

_ALLOWED = {
    "pi": math.pi, "e": math.e, "tau": math.tau,
    "abs": abs, "min": min, "max": max, "round": round,
    "int": int, "float": float,
    "randint": lambda a,b: random.randint(int(a), int(b)),
}

def _safe_eval(expr: str, env: Dict[str, Any]) -> Any:
    expr = (expr or "").replace("&lt;","<").replace("&gt;",">")
    return eval(expr, {"__builtins__": {}}, {**_ALLOWED, **env})

def _smart_cast(s: Any):
    if isinstance(s, (int,float,bool)): return s
    st = str(s).strip().lower()
    if st in ("1","true","yes","on"): return True
    if st in ("0","false","no","off"): return False
    try:
        if "." in st: return float(st)
        return int(st)
    except Exception:
        return s

# -------- Low-level actions --------
def _hotkey(combo: str):
    sent=False
    try:
        if keyboard: keyboard.send('+'.join([p.strip() for p in combo.split('+') if p.strip()])); sent=True
    except Exception: sent=False
    if not sent and pyautogui:
        keys=[p.strip().lower() for p in combo.split('+') if p.strip()]
        if keys: pyautogui.hotkey(*keys)

def _type_text(text: str, mode: str = "type"):
    if not pyautogui: return
    s = str(text)
    if mode.lower() != "copy_paste" or not pyperclip:
        pyautogui.write(s); return
    ok=False
    for attempt in range(5):
        try: pyperclip.copy(s)
        except Exception: time.sleep(0.05); continue
        time.sleep(0.1 + 0.05*attempt)
        try: cur = pyperclip.paste()
        except Exception: cur=None
        if cur == s: ok=True; break
    if ok: pyautogui.hotkey("ctrl","v")
    else:  pyautogui.write(s)

def _click_xy(x: int, y: int, button: str="left"):
    if pyautogui:
        try:
            pyautogui.moveTo(int(x), int(y), duration=0.02)
            pyautogui.click(x=int(x), y=int(y), button=button)
        except Exception as e:
            logger.info(f"click error: {e}")

# -------- Engine --------
class XMLProgram:
    def __init__(self, xml_path: Path, debug: bool=False, log_path: Optional[Path]=None):
        self.xml_path = Path(xml_path)
        self.logger = logger
        self.variables: Dict[str, Any] = {}
        self.functions: Dict[str, ET.Element] = {}
        # Start the engine in paused mode so UI/runner can inspect before resuming
        self.paused = False
        self.skip_wait = False
        self._last_ctrlspace = False
        self._hotkeys_started = False
        self._extmodule_cache = {}
        self._extclass_cache = {}
        self.voice = None  # VoiceDaemon instance
        # Flag to signal program restart (requested from external UI)
        self.restart_requested = False
        # Flag to signal program exit via hotkey
        self.exit_flag = False
        # timestamp until which hotkey handling (external) should be suppressed
        self._suppress_hotkeys_until = 0.0

    def _suppress_hotkeys_for(self, seconds: float):
        try:
            self._suppress_hotkeys_until = time.monotonic() + float(seconds)
        except Exception:
            self._suppress_hotkeys_until = time.monotonic() + 0.5

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

        #self._load_xml()
        # ensure UI shows initial paused state
        try:
            self.logger.info("PAUSE ON (initial)")
        except Exception:
            pass
        self._start_fallback_hotkeys()

    # ---- hotkeys fallback ----
    def _start_fallback_hotkeys(self):
        if self._hotkeys_started: return
        def worker():
            # Fallback hotkey registration using 'keyboard' library
            if keyboard is None:
                return
            try:
                # Pause and skip controls
                keyboard.add_hotkey("ctrl+space", self._toggle_pause)
                keyboard.add_hotkey("ctrl+n", self._skip_now)
                # Exit controls: Escape or Ctrl+Q -> set exit_flag
                def _exit_cb():
                    self.exit_flag = True
                    try:
                        self.logger.info("Exit requested via hotkey (flag set)")
                    except Exception:
                        pass
                keyboard.add_hotkey("esc", _exit_cb)
                keyboard.add_hotkey("ctrl+q", _exit_cb)
                self._hotkeys_started = True
                self.logger.info("Hotkeys armed (fallback): pause=Ctrl+Space, skip=Ctrl+N, exit=Esc/Ctrl+Q")
                # Block this thread to keep hotkeys active
                keyboard.wait()
            except Exception as e:
                self.logger.info(f"keyboard hotkeys error: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def request_restart(self):
        """Request a restart of the running program. The engine will raise
        RestartRequested at the next safe checkpoint (before next node or inside waits).
        """
        self.logger.info("Restart requested (flag set)")
        self.restart_requested = True

    def _toggle_pause(self):
        # ignore toggle requests if we suppressed hotkeys recently
        try:
            if time.monotonic() < getattr(self, '_suppress_hotkeys_until', 0):
                self.logger.info('PAUSE toggle suppressed (recent automated action)')
                return
        except Exception:
            pass
        self.paused = not self.paused
        self.logger.info(f"PAUSE {'ON' if self.paused else 'OFF'}")

    def _skip_now(self):
        self.skip_wait = True
        self.logger.info("WAIT skip requested")

    def _poll_hotkeys_inline(self):
        global SKIP_EVENT, PAUSE_TOGGLE_EVENT, EXIT_EVENT
        try:
            if SKIP_EVENT is not None and SKIP_EVENT.is_set():
                SKIP_EVENT.clear()
                self.skip_wait = True
            if PAUSE_TOGGLE_EVENT is not None and PAUSE_TOGGLE_EVENT.is_set():
                PAUSE_TOGGLE_EVENT.clear()
                self._toggle_pause()
            if EXIT_EVENT is not None and EXIT_EVENT.is_set():
                EXIT_EVENT.clear()
                self.exit_flag = True
                self.logger.info("Exit requested via hotkey (inline)")
        except Exception:
            pass
        if keyboard is None: return
        try:
            # If fallback hotkeys (keyboard.add_hotkey) have been started in a
            # separate thread, avoid inline polling toggles to prevent double
            # toggles caused by both mechanisms. Use inline polling only if no
            # fallback hotkeys are active.
            if not self._hotkeys_started:
                if keyboard.is_pressed("ctrl") and keyboard.is_pressed("n"):
                    self.skip_wait = True
                pressed = keyboard.is_pressed("ctrl") and keyboard.is_pressed("space")
                if pressed and not self._last_ctrlspace:
                    self._toggle_pause(); self._last_ctrlspace=True
                if not pressed and self._last_ctrlspace:
                    self._last_ctrlspace=False
        except Exception:
            pass

    def _pause_gate(self):
        while self.paused:
            # check for exit request
            if self.exit_flag:
                raise SystemExit
            if self.restart_requested:
                raise RestartRequested()
            self._poll_hotkeys_inline()
            time.sleep(0.05)

    def _sleep_ms_interruptible(self, ms:int):
        if ms<=0: return
        end = time.monotonic() + ms/1000.0
        tick = 0.03
        while True:
            # check for exit request
            if self.exit_flag:
                raise SystemExit
            if self.restart_requested:
                raise RestartRequested()
            self._poll_hotkeys_inline()
            if self.skip_wait:
                self.skip_wait = False
                self.logger.info("WAIT interrupted")
                return
            if self.paused:
                time.sleep(tick)
                continue
            now = time.monotonic()
            if now >= end:
                return
            time.sleep(min(tick, end-now))

    # ---- Voice ----
    def _ensure_voice(self):
        if self.voice is not None: return
        # check flags
        flag_xml = str(self.variables.get("VOICE_ENABLED","0")).strip().lower() in ("1","true","yes")
        flag_env = str(os.getenv("USEFULCLICKER_VOICE","0")).strip().lower() in ("1","true","yes")
        if not (flag_xml or flag_env):
            return
        if VoiceDaemon is None:
            self.logger.info("VOICE: VoiceDaemon not available (import failed)."); return
        dev = self.variables.get("VOICE_DEVICE")
        try: dev = int(dev) if (dev is not None and str(dev).strip()!="") else None
        except Exception: dev = None
        try:
            self.voice = VoiceDaemon(model_name="base", device=dev, lang=None).start()
            self.logger.info("VOICE: background voice daemon started.")
        except Exception as e:
            self.logger.info(f"VOICE: failed to start ({e})"); self.voice=None

    def handle_voice_event(self, node: ET.Element):
        self._ensure_voice()
        want = (node.get("type") or "any").lower()
        out = node.get("out") or "VOICE_TEXT"
        wait_ms = int(node.get("wait","0"))
        text, typ = "", ""
        if self.voice is None:
            self.variables[out] = text; self.variables[out+"_type"] = typ
            self._sleep_ms_interruptible(wait_ms)
            self.logger.info(f"VOICE_EVENT -> {out}='{text}' type='{typ}'")
            return

        deadline = time.time() + (wait_ms/1000.0) if wait_ms else None
        # Prefer generic get_event(timeout_ms) if VoiceDaemon exposes it
        if hasattr(self.voice, "get_event"):
            while True:
                self._pause_gate()
                if self.skip_wait:
                    self.skip_wait=False
                    self.logger.info("VOICE_EVENT interrupted by Ctrl+N")
                    break
                evt = self.voice.get_event(timeout_ms=200)
                if evt:
                    et = getattr(evt, "type", "") or ""
                    if want in ("any", et):
                        text = getattr(evt, "text","") or ""
                        typ = et
                        break
                if deadline and time.time()>deadline: break
        else:
            while True:
                self._pause_gate()
                if self.skip_wait:
                    self.skip_wait=False
                    self.logger.info("VOICE_EVENT interrupted by Ctrl+N")
                    break
                evt = None
                if want in ("any","command") and hasattr(self.voice, "get_next_command"):
                    evt = self.voice.get_next_command(timeout_ms=0)
                    if evt: text, typ = evt.text, "command"; break
                if want in ("any","query") and hasattr(self.voice, "get_next_query"):
                    evt = self.voice.get_next_query(timeout_ms=0)
                    if evt: text, typ = evt.text, "query"; break
                if deadline and time.time()>deadline: break
                time.sleep(0.05)

        self.variables[out] = text
        self.variables[out+"_type"] = typ
        self.logger.info(f"VOICE_EVENT -> {out}='{text}' type='{typ}'")

    def handle_voice_poll(self, node: ET.Element):
        self._ensure_voice()
        out_cmd = node.get("out_cmd") or "VOICE_CMD"
        out_query = node.get("out_query") or "VOICE_QUERY"
        cmd, query = "", ""
        if self.voice:
            if hasattr(self.voice, "get_next_command"):
                evt_cmd = self.voice.get_next_command(timeout_ms=0)
                if evt_cmd:
                    cmd = evt_cmd.text
                    if getattr(evt_cmd, "payload", None) and "seconds" in evt_cmd.payload:
                        self.variables[out_cmd+"_seconds"] = evt_cmd.payload["seconds"]
            if hasattr(self.voice, "get_next_query"):
                evt_query = self.voice.get_next_query(timeout_ms=0)
                if evt_query: query = evt_query.text
        self.variables[out_cmd] = cmd
        self.variables[out_query] = query
        self.logger.info(f"VOICE_POLL -> {out_cmd}='{cmd}' {out_query}='{query}'")

    # ---- XML ----
    def _load_xml(self):
        txt = self.xml_path.read_text(encoding="utf-8")
        self.tree = ET.fromstring(txt.encode("utf-8"))
        for f in self.tree.findall(".//func"):
            name = f.get("name")
            if name: self.functions[name]=f
        self.logger.info("XML loaded OK")

    # ---- handlers ----
    def handle_set(self, node: ET.Element):
        for k,v in node.attrib.items():
            if k in ("delay_fixed","delay_ms"): continue
            s = _substitute_vars(v, self.variables)
            try: val = _safe_eval(s, self.variables)
            except Exception: val = s
            self.variables[k]=val
            self.logger.info(f"SET {k} = {val}")

    def handle_wait(self, node: ET.Element):
        ms = int(float(node.get("ms","0")))
        self.logger.info(f"WAIT {ms}ms (pause=Ctrl+Space, skip=Ctrl+N)")
        self._sleep_ms_interruptible(ms)

    def handle_shell(self, node: ET.Element):
        # For safety: disallow execution of arbitrary shell commands from XML.
        # This node is retained for compatibility but will not execute.
        try:
            cmd = node.get("cmd","")
            self.logger.info(f"SHELL node blocked for safety; command suppressed: {cmd}")
        except Exception:
            self.logger.info("SHELL node blocked for safety; command suppressed")

    def handle_hotkey(self, node: ET.Element):
        hk = _substitute_vars(node.get("hotkey",""), self.variables)
        self.logger.info(f"HOTKEY {hk}")
        _hotkey(hk)

    def handle_type(self, node: ET.Element):
        mode = node.get("mode","type")
        text = _substitute_vars(node.get("text",""), self.variables)
        self.logger.info(f"TYPE mode={mode} text='{text[:30]}'")
        # suppress hotkeys briefly to avoid synthetic key events triggering hotkey handlers
        #try: self._suppress_hotkeys_for(0.6)
        #except Exception: pass
        _type_text(text, mode=mode)

    def handle_click(self, node: ET.Element):
        btn = node.get("button","left")
        area = node.get("area")
        if area:
            expr = _substitute_vars(area, self.variables)
            parts = [p.strip() for p in expr.split(",")]
            if len(parts)!=4:
                self.logger.info("click area must be 'x1,y1,x2,y2'"); return
            try:
                vals = [int(float(_safe_eval(p, self.variables))) for p in parts]
            except Exception:
                vals = [int(float(p)) for p in parts]
            x1,y1,x2,y2 = vals
            rx = random.randint(min(x1,x2), max(x1,x2))
            ry = random.randint(min(y1,y2), max(y1,y2))
            self.logger.info(f"CLICK area={vals} -> ({rx},{ry})")
            #try: self._suppress_hotkeys_for(0.6)
            #except Exception: pass
            _click_xy(rx, ry, button=btn)
        else:
            xs = _substitute_vars(node.get("x","0"), self.variables)
            ys = _substitute_vars(node.get("y","0"), self.variables)
            try:
                x = int(float(_safe_eval(xs, self.variables)))
                y = int(float(_safe_eval(ys, self.variables)))
            except Exception:
                x = int(float(xs)); y = int(float(ys))
            self.logger.info(f"CLICK ({x},{y})")
            #try: self._suppress_hotkeys_for(0.6)
            #except Exception: pass
            _click_xy(x,y,button=btn)

    def handle_focus(self, node: ET.Element):
        title = node.get("title") or node.get("title_contains") or ""
        retries = int(node.get("retries","20")); interval_ms=int(node.get("interval_ms","200"))
        if not gw:
            self.logger.info("FOCUS skipped: pygetwindow not available"); return
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

    def handle_if(self, node: ET.Element):
        cond_raw = node.get("cond","")
        cond = _substitute_vars(cond_raw, self.variables)
        try: res = bool(eval(cond or "False", {"__builtins__": {}}, {}))
        except Exception as e:
            self.logger.info(f"IF eval error: {e}"); res=False
        children=list(node)
        if res:
            for sub in children:
                if isinstance(getattr(sub, "tag", None), str) and sub.tag.lower()=="else": break
                self._exec_node(sub)
        else:
            hit=False
            for sub in children:
                if isinstance(getattr(sub, "tag", None), str) and sub.tag.lower()=="else":
                    hit=True; continue
                if hit: self._exec_node(sub)

    def handle_repeat(self, node: ET.Element):
        expr = node.get("times","0")
        try: times = int(float(_safe_eval(_substitute_vars(expr, self.variables), self.variables)))
        except Exception: times = 0
        self.logger.info(f"REPEAT times={times}")
        for _ in range(times):
            for ch in list(node): self._exec_node(ch)

    def handle_list(self, node: ET.Element):
        """Handle <list> node: create a list or text variable from inline text.

        Attributes supported:
        - output_var (required): variable name to store result
        - output_format: 'list' or 'text' (default 'list')
        - separator: separator string for list (default '\n')
        - text: inline text block (can contain newlines)
        """
        out_var = node.get("output_var")
        if not out_var:
            self.logger.info("<list> missing output_var"); return
        out_fmt = (node.get("output_format") or "list").lower()
        separator = (node.get("separator") or "\n").encode("utf-8").decode("unicode_escape")
        # collect text: prefer element body (preserves newlines) else attribute 'text'
        raw_attr = node.get("text")
        try:
            # use itertext() to preserve internal newlines and avoid HTML-escaping
            body = ''.join(t for t in node.itertext()) if hasattr(node, 'itertext') else None
        except Exception:
            body = None
        if body and body.strip():
            raw = body
        else:
            raw = raw_attr or (node.text or "")
        raw = _substitute_vars(raw, self.variables)
        if out_fmt == "list":
            items = [s for s in re.split(r"[\r\n]+", raw) if s.strip()]
            # if separator explicitly provided, split by it instead
            if separator and separator != "\n":
                items = [s for s in raw.split(separator) if s.strip()]
            self.variables[out_var] = items
            self.logger.info(f"LIST -> {out_var} size={len(items)}")
        else:
            self.variables[out_var] = raw
            self.logger.info(f"LIST -> {out_var} text_len={len(raw)}")

    def handle_func(self, node: ET.Element): pass

    def handle_call(self, node: ET.Element):
        name = node.get("name","")
        f = self.functions.get(name)
        if not f:
            self.logger.info(f"CALL missing func {name}"); return
        for k,v in node.attrib.items():
            if k.startswith("arg"): self.variables[k]=_substitute_vars(v, self.variables)
        self.logger.info(f"CALL {name}")
        for ch in list(f): self._exec_node(ch)

    def handle_foreach(self, node: ET.Element):
        list_name = node.get("list","")
        func_name = node.get("do","")
        if func_name not in self.functions:
            self.logger.info(f"FOREACH unknown func: {func_name}"); return
        data = self.variables.get(list_name, [])
        if isinstance(data, str):
            items = [s for s in re.split(r"[\r\n]+", data) if s.strip()]
        else:
            items = list(data)
        if str(node.get("random_shuffle","0")).lower() in ("1","true","yes"):
            random.shuffle(items)
        for idx, item in enumerate(items):
            self.variables["item"] = item
            self.variables["index"] = idx
            self.variables["arg0"] = item
            f = self.functions[func_name]
            for ch in list(f): self._exec_node(ch)
        self.variables.pop("item", None)
        self.variables.pop("index", None)
        self.variables.pop("arg0", None)

    def handle_llmcall(self, node: ET.Element):
        # параметры
        # For safety: do NOT perform variable substitution inside LLM prompt
        # declared in XML. Use the raw prompt text as authored by the user.
        # This prevents leaking internal variables into prompts.
        prompt = node.get("prompt","")
        out_var = node.get("output_var")
        out_fmt = (node.get("output_format") or "text").lower()
        separator = (node.get("separator") or "\n").encode("utf-8").decode("unicode_escape")
        # allow model/temperature to be specified on the XML node
        model = node.get("model")
        temp_raw = node.get("temperature")
        temperature = None
        if temp_raw is not None:
            try:
                temperature = float(_substitute_vars(temp_raw, self.variables))
            except Exception:
                try:
                    temperature = float(temp_raw)
                except Exception:
                    temperature = None
        # log LLM call parameters
        self.logger.info(f"LLMCALL params: model={model}, temperature={temperature}")

        # select LLM client based on provider: 'openai', 'ollama', or auto
        provider = node.get("provider")
        llm_client = None
        self.logger.info(f"LLM: creating client for provider={provider or '<auto>'}...")
        if provider:
            prov = provider.strip().lower()
            if prov == "ollama":
                try:
                    from llm.ollama_client import OllamaClient as _LLM
                    llm_client = _LLM()
                    self.logger.info("LLM: client ready (ollama).")
                except Exception as e:
                    self.logger.info(f"LLM: ollama client unavailable: {e}")
            elif prov == "openai":
                try:
                    from llm.openai_client_compat import LLMClientCompat as _LLM
                    llm_client = _LLM()
                    self.logger.info("LLM: client ready (compat).")
                except Exception:
                    try:
                        from llm.openai_client import LLMClient as _LLM
                        llm_client = _LLM()
                        self.logger.info("LLM: client ready (native).")
                    except Exception as e:
                        self.logger.info(f"LLM: openai client unavailable: {e}")
            else:
                self.logger.info(f"LLM: unknown provider '{provider}', skipping client setup")
        else:
            # auto-detect: try OpenAI compat, then native, then Ollama
            try:
                from llm.openai_client_compat import LLMClientCompat as _LLM
                llm_client = _LLM()
                self.logger.info("LLM: client ready (compat).")
            except Exception as e1:
                try:
                    from llm.openai_client import LLMClient as _LLM
                    llm_client = _LLM()
                    self.logger.info("LLM: client ready (native).")
                except Exception as e2:
                    try:
                        from llm.ollama_client import OllamaClient as _LLM
                        llm_client = _LLM()
                        self.logger.info("LLM: client ready (ollama).")
                    except Exception as e3:
                        self.logger.info(f"LLM: client unavailable ({e1} / {e2} / {e3})")

        text = ""
        used = "none"
        if llm_client is None:
            self.logger.info("LLM: skipped (no client).")
        else:
            t0 = time.time()
            try:
                if out_fmt == "list" and hasattr(llm_client, "generate_list"):
                    # прямой список с разделителем
                    # try to pass model/temperature if supported
                    try:
                        value = llm_client.generate_list(prompt, separator=separator, model=model, temperature=temperature)
                    except TypeError:
                        try:
                            value = llm_client.generate_list(prompt, separator=separator, model=model)
                        except TypeError:
                            value = llm_client.generate_list(prompt, separator=separator)
                    dt = (time.time() - t0) * 1000.0
                    self.logger.info(f"LLM: prompt done in {dt:.1f} ms; used=generate_list")
                    self.variables[out_var] = value
                    if not value:
                        self.logger.info(f"LLM warning: {out_var} is empty list")
                    else:
                        self.logger.info(f"LLM output[{out_var}] size={len(value)}")
                    return  # уже всё сохранили → выходим
                elif hasattr(llm_client, "generate_text"):
                    # try to pass model/temperature if supported
                    try:
                        text = llm_client.generate_text(prompt, model=model, temperature=temperature)
                    except TypeError:
                        try:
                            text = llm_client.generate_text(prompt, model=model)
                        except TypeError:
                            text = llm_client.generate_text(prompt)
                    used = "generate_text"
                else:
                    # попытка на случай других реализаций
                    for meth in ("complete", "generate", "chat", "__call__"):
                        fn = getattr(llm_client, meth, None)
                        if not fn: continue
                        try:
                            text = fn(prompt)  # или fn(prompt=prompt) если нужно
                        except TypeError:
                            text = fn(prompt=prompt)
                        used = meth
                        break
            except Exception as e:
                self.logger.info(f"LLM: call failed: {e}")
            dt = (time.time() - t0) * 1000.0
            self.logger.info(f"LLM: prompt done in {dt:.1f} ms; used={used}")

        # сохранение строки (если пришли сюда из generate_text/иных)
        if out_var:
            if out_fmt == "list":
                value = [s for s in (text or "").split(separator) if s.strip()]
                self.variables[out_var] = value
                if not value:
                    self.logger.info(f"LLM warning: {out_var} is empty list")
                else:
                    self.logger.info(f"LLM output[{out_var}] size={len(value)}")
            else:
                self.variables[out_var] = text or ""
                if not (text or "").strip():
                    self.logger.info(f"LLM warning: {out_var} is empty string")
                else:
                    self.logger.info(f"LLM output[{out_var}] len={len(text)}")



    def handle_extnode(self, node: ET.Element):
        mod_name = node.get("module"); cls_name = node.get("class"); method = node.get("method")
        out_var = node.get("output_var")
        if not mod_name:
            self.logger.info("<extnode> requires module"); return
        # optional output formatting
        separator = (node.get("separator") or "").encode("utf-8").decode("unicode_escape")
        out_fmt = (node.get("output_format") or "text").lower()
        # extract and log LLM parameters from XML node
        model = node.get("model")
        temp_raw = node.get("temperature")
        temperature = None
        if temp_raw is not None:
            try:
                temperature = float(_substitute_vars(temp_raw, self.variables))
            except Exception:
                temperature = None
        if model is not None:
            model = _substitute_vars(model, self.variables)
        provider = node.get("provider")  # 'openai' or 'ollama'
        self.logger.info(f"EXTNODE LLM params: model={model}, temperature={temperature}, provider={provider}")

        # Collect kwargs from XML (with substitutions and simple casts)
        kw: Dict[str, Any] = {}
        for k,v in node.attrib.items():
            if k in {"module","class","method","func","output_var","output_format","separator"}: 
                continue
            vv = _substitute_vars(v, self.variables)
            if k.endswith("_list") or k in {"disciplines","subtopics"}:
                kw[k] = [p.strip() for p in vv.split(",") if p.strip()]
            else:
                kw[k] = _smart_cast(vv)

        # select LLM client based on provider: 'openai', 'ollama', or auto
        llm_client = None
        self.logger.info(f"LLM: creating client for provider={provider or '<auto>'}...")
        if provider:
            prov = provider.strip().lower()
            if prov == "ollama":
                try:
                    from llm.ollama_client import OllamaClient as _LLM
                    llm_client = _LLM()
                    self.logger.info("LLM: client ready (ollama).")
                except Exception as e:
                    self.logger.info(f"LLM: ollama client unavailable: {e}")
            elif prov == "openai":
                try:
                    from llm.openai_client_compat import LLMClientCompat as _LLM
                    llm_client = _LLM()
                    self.logger.info("LLM: client ready (compat).")
                except Exception:
                    try:
                        from llm.openai_client import LLMClient as _LLM
                        llm_client = _LLM()
                        self.logger.info("LLM: client ready (native).")
                    except Exception as e:
                        self.logger.info(f"LLM: openai client unavailable: {e}")
            else:
                self.logger.info(f"LLM: unknown provider '{provider}', skipping client setup")
        else:
            # auto-detect: try OpenAI compat, then native, then Ollama
            try:
                from llm.openai_client_compat import LLMClientCompat as _LLM
                llm_client = _LLM()
                self.logger.info("LLM: client ready (compat).")
            except Exception as e1:
                try:
                    from llm.openai_client import LLMClient as _LLM
                    llm_client = _LLM()
                    self.logger.info("LLM: client ready (native).")
                except Exception as e2:
                    try:
                        from llm.ollama_client import OllamaClient as _LLM
                        llm_client = _LLM()
                        self.logger.info("LLM: client ready (ollama).")
                    except Exception as e3:
                        self.logger.info(f"LLM: client unavailable ({e1} / {e2} / {e3})")

        # Import target module
        try:
            mod = self._extmodule_cache.get(mod_name) or importlib.import_module(mod_name)
            self._extmodule_cache[mod_name] = mod
        except Exception as e:
            self.logger.info(f"EXTNODE import error for module '{mod_name}': {e}")
            return

        # Resolve call target
        func_name = node.get("func")
        result = None
        try:
            if func_name:
                # module-level function
                call_target = getattr(mod, func_name)
                # Try with llm first, then without
                try:
                    result = call_target(**{**kw, "llm": llm_client})
                except TypeError:
                    result = call_target(**kw) if kw else call_target()
            elif cls_name:
                # class + method (default 'run')
                method_name = method or "run"
                key=(mod_name, cls_name)
                inst = self._extclass_cache.get(key)
                if inst is None:
                    cls = getattr(mod, cls_name)
                    # try constructor(llm=...)
                    try:
                        inst = cls(llm=llm_client)
                    except TypeError:
                        inst = cls()
                    self._extclass_cache[key]=inst
                meth = getattr(inst, method_name)
                try:
                    result = meth(**{**kw, "llm": llm_client})
                except TypeError:
                    result = meth(**kw) if kw else meth()
            else:
                # Fall back to common entrypoints
                if hasattr(mod, "run_node"):
                    try:
                        result = getattr(mod, "run_node")(**{**kw, "llm": llm_client})
                    except TypeError:
                        result = getattr(mod, "run_node")(**kw) if kw else getattr(mod, "run_node")()
                elif hasattr(mod, "run"):
                    try:
                        result = getattr(mod, "run")(**{**kw, "llm": llm_client})
                    except TypeError:
                        result = getattr(mod, "run")(**kw) if kw else getattr(mod, "run")()
                else:
                    raise AttributeError("No entrypoint: expected 'func', or 'class'+'method', or module.run_node/run")
        except Exception as e:
            try:
                import traceback; tb = traceback.format_exc()
                self.logger.info(f"EXTNODE runtime error: {e}{tb}")
            except Exception:
                self.logger.info(f"EXTNODE runtime error: {e}")
            return

        # Save output if requested
        if out_var:
            if out_fmt == "list":
                if result is None:
                    value = []
                elif isinstance(result, (list, tuple)):
                    value = [str(x) for x in result]
                elif isinstance(result, str):
                    value = [s for s in result.split(separator) if s.strip()]
                elif isinstance(result, dict) and "list" in result:
                    value = [str(x) for x in result["list"]]
                else:
                    value = [str(result)]
                self.variables[out_var] = value
                # --- добавь это ---
                if not value:
                    self.logger.info(f"EXTNODE warning: {out_var} is empty list")

            else:
                if result is None:
                    text = ""
                elif isinstance(result, str):
                    text = result
                elif isinstance(result, (list, tuple)):
                    text = separator.join(str(x) for x in result)
                elif isinstance(result, dict) and "text" in result:
                    text = str(result["text"])
                else:
                    text = str(result)
                self.variables[out_var] = text
                if not (text or "").strip():
                    self.logger.info(f"EXTNODE warning: {out_var} is empty string")  # ### NEW

        self.logger.info(f"EXTNODE {mod_name}.{(cls_name+'.' if cls_name else '')}{func_name or method or 'run'} -> {out_var}")

    # ---- dispatcher ----
    def _exec_node(self, node):
        # Exit immediately if exit_flag is set
        if self.exit_flag:
            raise SystemExit
        if self.restart_requested:
            raise RestartRequested()
        tag = getattr(node, "tag", None)
        if not isinstance(tag, str):
            return  # skip comments/PI
        # expose current node info for UIs
        try:
            self.variables["_CURRENT_NODE_TAG"] = tag.lower()
        except Exception:
            pass
        self._pause_gate()
        tagl = tag.lower()
        if   tagl=="set": self.handle_set(node)
        elif tagl=="wait": self.handle_wait(node)
        elif tagl=="shell": self.handle_shell(node)
        elif tagl=="hotkey": self.handle_hotkey(node)
        elif tagl=="type": self.handle_type(node)
        elif tagl=="click": self.handle_click(node)
        elif tagl=="focus": self.handle_focus(node)
        elif tagl=="if": self.handle_if(node)
        elif tagl=="repeat": self.handle_repeat(node)
        elif tagl=="list": self.handle_list(node)
        elif tagl=="func": self.handle_func(node)
        elif tagl=="call": self.handle_call(node)
        elif tagl == "llmcall": self.handle_llmcall(node)
        elif tagl=="foreach": self.handle_foreach(node)
        elif tagl=="extnode": self.handle_extnode(node)
        elif tagl=="voice_event": self.handle_voice_event(node)
        elif tagl=="voice_poll": self.handle_voice_poll(node)
        else:
            for ch in list(node): self._exec_node(ch)

    def run(self):
        # Load XML and initialize screen defaults and hotkeys
        self._load_xml()
        try:
            self._suppress_hotkeys_for(0)
        except Exception:
            pass
        self.logger.info("RUN start")
        try:
            for node in list(self.tree):
                # stop if exit requested
                if self.exit_flag:
                    self.logger.info("RUN aborted by exit flag")
                    break
                if not isinstance(getattr(node, "tag", None), str):
                    continue
                if node.tag.lower() == "func":
                    continue
                self._exec_node(node)
        except SystemExit:
            self.logger.info("RUN aborted via SystemExit")
            return
        self.logger.info("RUN end")

# Entrypoint
if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("xml_path")
    args=ap.parse_args()
    XMLProgram(Path(args.xml_path)).run()
