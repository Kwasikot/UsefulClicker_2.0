# voice/voice_daemon.py
import queue
import threading
import time
import re
from dataclasses import dataclass
from typing import Optional, Literal, Dict, Any

import numpy as np
import sounddevice as sd

# ---- optional deps ----
try:
    import webrtcvad
except Exception:
    webrtcvad = None

try:
    import whisper  # openai-whisper (local)
except Exception:
    whisper = None

# optional LLM (to condense free-form speech into a short YouTube query)
try:
    from llm.openai_client import LLMClient
except Exception:
    LLMClient = None




# === Global Hotkey Bridge (module-level) ===
# Other modules (e.g., xml_engine) can import these to react to hotkeys without duplicating listeners.
try:
    import keyboard as _kbd_bridge
except Exception:
    _kbd_bridge = None

SKIP_EVENT = __import__("threading").Event()       # set() => request to skip current wait/step
PAUSE_TOGGLE_EVENT = __import__("threading").Event()  # set() => toggle pause; the consumer should immediately clear()

_hotkeys_started = False

def start_hotkey_bridge():
    """Start a single global hotkey listener per process.
    - Ctrl+N sets SKIP_EVENT
    - Ctrl+Space sets PAUSE_TOGGLE_EVENT
    """
    global _hotkeys_started
    if _hotkeys_started:
        return
    if _kbd_bridge is None:
        return
    try:
        def _on_skip():
            SKIP_EVENT.set()
        def _on_pause():
            PAUSE_TOGGLE_EVENT.set()
        _kbd_bridge.add_hotkey("ctrl+n", _on_skip)
        _kbd_bridge.add_hotkey("ctrl+space", _on_pause)
        _hotkeys_started = True
    except Exception:
        # If keyboard hook fails (permissions), consumers can still poll these Events by other means.
        pass
EventType = Literal["command", "query"]

def list_microphones():
    print("=== Mics ===")
    devices = sd.query_devices()
    for idx, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            print(f"[{idx}] {dev['name']}")

@dataclass
class VoiceEvent:
    type: EventType
    text: str          # command name (for commands) OR query string (for queries)
    ts: float
    payload: Optional[Dict[str, Any]] = None  # e.g., {"seconds": 30} for seek


def rms_int16(frame_bytes: bytes) -> float:
    if not frame_bytes:
        return 0.0
    x = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(x * x)) + 1e-8)


class VoiceDaemon:
    """
    Background daemon: mic -> ASR (Whisper) -> intent -> queues.
      commands: next/prev/pause/resume/seek_fwd/seek_back/scroll_down/scroll_up/fullscreen
      queries : user free speech distilled into a search string
    Anti-noise:
      - webrtcvad (aggr=3) + RMS gate with auto-calibration
      - min phrase duration, hangover, cooldown
    """

    # numeric seconds (both langs)
    _RE_NUM = re.compile(r"(?P<num>\d{1,3})")

    # English & Russian command patterns
    # Order matters: more specific earlier.
    CMD_RULES = [
        # CLICK first result (en/ru, с вариациями)
        (r"^\s*(click|клик(ни)?|открой|выбери|select|open)(\s+(the\s*)?(first|перв(ый|ое)))?(\s+(video|видео))?\b", "click_first"),
        # NEXT
        (r"^\s*(next|skip|play next|go next|следующ(ий|ая)|дальш(е|ий))\b", "next"),
        # PREV
        (r"^\s*(prev(ious)?|back|go back|назад|предыдущ(ий|ая))\b", "prev"),
        # PAUSE / RESUME
        (r"\b(pause|стоп|пауза|останови(ть)?)\b", "pause"),
        (r"\b(resume|continue|play|продолж(ай|ить)|воспроизведи)\b", "resume"),
        # FULLSCREEN
        (r"\b(fullscreen|full screen|полноэкран|на весь экран|фуллскрин|f11)\b", "fullscreen"),
        # SCROLL
        (r"(scroll\s*down|scrol(l)? down|вниз|скролл вниз|листай вниз)", "scroll_down"),
        (r"(scroll\s*up|scrol(l)? up|вверх|скролл вверх|листай вверх)", "scroll_up"),
        # SEEK FORWARD / BACKWARD with optional number of seconds
        (r"(промот(ай|ать)|перемот(ай|ать)|перемотка|seek|skip).*(впер(е|ё)д|forward|\+\s*\d+|\b\+?\d+\b)", "seek_fwd"),
        (r"(промот(ай|ать)|перемот(ай|ать)|перемотка|seek|skip).*(назад|back|\-\s*\d+|\b\-?\d+\b)", "seek_back"),
        # Simple "forward 10 sec" / "назад 10 сек"
        (r"\b(forward|впер(е|ё)д)\b", "seek_fwd"),
        (r"\b(back|назад)\b", "seek_back"),
    ]

    def __init__(self,
                 model_name: str = "base",
                 sample_rate: int = 16000,
                 device: Optional[int] = None,
                 use_vad: bool = True,
                 lang: Optional[str] = None,         # "ru" / "en" / None (auto)
                 use_llm_for_queries: bool = True):
        self.sample_rate = sample_rate
        self.device = device
        self.use_vad = bool(use_vad and (webrtcvad is not None))
        self.lang = lang
        self.use_llm_for_queries = bool(use_llm_for_queries and (LLMClient is not None))

        self._audio_q: "queue.Queue[bytes]" = queue.Queue()
        self._stop = threading.Event()
        self._listen_thread: Optional[threading.Thread] = None
        self._proc_thread: Optional[threading.Thread] = None

        self.commands: "queue.Queue[VoiceEvent]" = queue.Queue()
        self.queries: "queue.Queue[VoiceEvent]" = queue.Queue()

        self._accum_frames: list[bytes] = []

        # --- VAD + RMS gate params ---
        self._vad = webrtcvad.Vad(3) if self.use_vad else None  # stricter
        self._noise_calibrated = False
        self._noise_rms_mean = 0.0
        self._noise_rms_std = 0.0
        self._rms_gate_k = 2.7      # 2.0–3.5: higher => stricter
        self._min_phrase_ms = 550   # ignore phrases shorter than this
        self._hangover_ms = 1000     # keep collecting after last speech
        self._cooldown_ms = 450     # min time between phrases
        self._last_flush_ts = 0.0

        # Whisper model
        self._model = whisper.load_model(model_name) if whisper is not None else None
        # LLM for query condensing
        self._llm = LLMClient() if self.use_llm_for_queries else None

        self._stream: Optional[sd.InputStream] = None
        
        list_microphones()

    # ----------------- public API -----------------
    def start(self):
        start_hotkey_bridge()
        self._stop.clear()
        self._start_stream()
        self._listen_thread = threading.Thread(target=self._listen_audio_loop, daemon=True)
        self._proc_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._listen_thread.start()
        self._proc_thread.start()
        return self

    def stop(self):
        self._stop.set()
        try:
            if self._stream:
                self._stream.stop(); self._stream.close()
        except Exception:
            pass

    def get_next_command(self, timeout_ms: int = 0) -> Optional[VoiceEvent]:
        try:
            return self.commands.get(timeout=timeout_ms/1000.0 if timeout_ms else 0)
        except queue.Empty:
            return None

    def get_next_query(self, timeout_ms: int = 0) -> Optional[VoiceEvent]:
        try:
            return self.queries.get(timeout=timeout_ms/1000.0 if timeout_ms else 0)
        except queue.Empty:
            return None

    # ----------------- audio -----------------
    def _start_stream(self):
        def _cb(indata, frames, time_info, status):
            if status:
                # optionally log status
                pass
            mono = indata[:, 0]
            pcm16 = (mono * 32767).astype(np.int16).tobytes()
            self._audio_q.put(pcm16)

        self._stream = sd.InputStream(samplerate=self.sample_rate, channels=1,
                                      dtype="float32", device=self.device, callback=_cb)
        self._stream.start()

    def _listen_audio_loop(self):
        block_ms = 20  # 10/20/30ms are valid for webrtcvad; 20ms works well
        bytes_per_ms = int(self.sample_rate * 2 / 1000)  # int16
        ring = bytearray()
        speaking = False
        last_voice_ts = time.time()

        # --- calibration of noise floor ---
        calib_ms = 1500
        calib_buf = []
        calib_collected = 0

        while not self._stop.is_set():

            # global pause toggle from hotkey bridge
            try:
                from voice.voice_daemon import PAUSE_TOGGLE_EVENT
                if PAUSE_TOGGLE_EVENT.is_set():
                    PAUSE_TOGGLE_EVENT.clear()
                    # simple local pause: wait until toggled again
                    paused = True
                    while paused and not self._stop.is_set():
                        time.sleep(0.05)
                        if PAUSE_TOGGLE_EVENT.is_set():
                            PAUSE_TOGGLE_EVENT.clear()
                            paused = False
            except Exception:
                pass
            try:
                chunk = self._audio_q.get(timeout=0.1)
            except queue.Empty:
                chunk = None

            # calibration phase: fill RMS stats and skip processing
            if not self._noise_calibrated:
                if chunk:
                    ring.extend(chunk)
                    while len(ring) >= bytes_per_ms * block_ms:
                        frame = ring[: bytes_per_ms * block_ms]
                        del ring[: bytes_per_ms * block_ms]
                        calib_buf.append(rms_int16(frame))
                        calib_collected += block_ms
                if calib_collected >= calib_ms:
                    arr = np.array(calib_buf, dtype=np.float32)
                    self._noise_rms_mean = float(arr.mean()) if arr.size else 0.0
                    self._noise_rms_std  = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
                    self._noise_calibrated = True
                    ring.clear()
                continue

            if chunk:
                ring.extend(chunk)
                while len(ring) >= bytes_per_ms * block_ms:
                    frame = ring[: bytes_per_ms * block_ms]
                    del ring[: bytes_per_ms * block_ms]

                    frame_rms = rms_int16(frame)
                    gate = self._noise_rms_mean + self._rms_gate_k * max(self._noise_rms_std, 1.0)

                    vad_ok = self._vad.is_speech(frame, self.sample_rate) if self._vad else True
                    rms_ok = (frame_rms > gate)
                    is_speech = vad_ok and rms_ok

                    now = time.time()
                    if is_speech:
                        speaking = True
                        last_voice_ts = now
                        self._accum_frames.append(frame)
                    else:
                        # silence; allow hangover before flushing
                        if speaking and (now - last_voice_ts) * 1000 > self._hangover_ms:
                            dur_ms = len(self._accum_frames) * block_ms
                            if dur_ms >= self._min_phrase_ms:
                                if (now - self._last_flush_ts) * 1000 >= self._cooldown_ms:
                                    audio_bytes = b"".join(self._accum_frames)
                                    self._accum_frames.clear()
                                    speaking = False
                                    self._last_flush_ts = now
                                    self._on_phrase(audio_bytes)
                                else:
                                    self._accum_frames.clear()
                                    speaking = False
                            else:
                                self._accum_frames.clear()
                                speaking = False
            else:
                # nothing new; if we were speaking and hangover passed, flush
                now = time.time()
                if speaking and (now - last_voice_ts) * 1000 > self._hangover_ms:
                    dur_ms = len(self._accum_frames) * block_ms
                    if dur_ms >= self._min_phrase_ms and (now - self._last_flush_ts) * 1000 >= self._cooldown_ms:
                        audio_bytes = b"".join(self._accum_frames)
                        self._accum_frames.clear()
                        speaking = False
                        self._last_flush_ts = now
                        self._on_phrase(audio_bytes)
                    else:
                        self._accum_frames.clear()
                        speaking = False

    def _process_loop(self):
        # reserved in case you want extra background processing later
        while not self._stop.is_set():
            time.sleep(0.05)

    # ----------------- ASR + intent -----------------
    def _extract_seconds(self, text: str, default_seconds: int = 10) -> int:
        m = self._RE_NUM.search(text)
        if m:
            try:
                n = int(m.group("num"))
                return max(1, min(n, 600))
            except Exception:
                pass
        return default_seconds

    def _on_phrase(self, audio_bytes: bytes):
        if self._model is None:
            return

        # whisper expects float32 PCM in [-1,1]
        pcm16 = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        try:
            kwargs = dict(fp16=False)
            if self.lang:
                kwargs["language"] = self.lang  # "ru" / "en"; if None -> auto
            result = self._model.transcribe(pcm16, **kwargs)
            text = (result.get("text") or "").strip()
        except Exception:
            text = ""

        # Drop ultra-short / non-alnum
        if not text or len(text) < 3 or not any(ch.isalnum() for ch in text):
            return

        evt = self._interpret(text)
        if not evt:
            return

        if evt.type == "command":
            self.commands.put(evt)
        else:
            self.queries.put(evt)

    def _interpret(self, text: str) -> Optional[VoiceEvent]:
        low = text.lower()

        # 1) commands (ru + en)
        for pat, name in self.CMD_RULES:
            if re.search(pat, low):
                payload = None
                if name in ("seek_fwd", "seek_back"):
                    seconds = self._extract_seconds(low, default_seconds=10)
                    payload = {"seconds": seconds}
                return VoiceEvent(type="command", text=name, ts=time.time(), payload=payload)

        # 2) otherwise: it's a search query → optionally condense with LLM
        query = text
        if self._llm is not None:
            try:
                resp = self._llm.generate_text(
                    "Сформулируй краткий поисковый запрос для YouTube по смыслу фразы: "
                    f"«{text}». Ответь одной строкой, без кавычек."
                )
                if isinstance(resp, str) and resp.strip():
                    query = resp.strip()
            except Exception:
                pass

        return VoiceEvent(type="query", text=query, ts=time.time())
