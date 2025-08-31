#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
usefulclicker_runner.py — direct-buffer runner + safety tap

Проблема: у тебя буфер пуст в раннере, хотя тест с TAP показывает текст.
Решение: в раннере тоже ставим TAP на VoiceDaemon._dump_text и
добавляем любые VOICE RAW/SEG прямо в ВНУТРЕННИЙ _text_buffer демона (под локом).
Так мы не зависим от того, вызывает ли сам демон _append_to_buffer.

Горячие клавиши:
  Ctrl+D — показать текущий буфер (без очистки)
  Ctrl+S — флаш: забрать и очистить буфер → LLM → YouTube
  Ctrl+B — добавить тестовую строку в буфер (диагностика)
  Esc    — выход
"""

import os, sys, time, threading, platform, ctypes, logging

def _setup_logger():
    log = logging.getLogger("usefulclicker")
    if not log.handlers:
        log.setLevel(logging.INFO)
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
        log.addHandler(h)
    return log

logger = _setup_logger()

# --- Optional deps ---
try:
    from voice.voice_daemon import VoiceDaemon
except Exception as e:
    logger.info(f"VOICE: import failed: {e}")
    VoiceDaemon = None

try:
    from llm.openai_client import LLMClient
except Exception:
    LLMClient = None

try:
    import yt_orchestrator
except Exception:
    yt_orchestrator = None

# --- Win hotkeys (fallback) ---
def win_hotkey_pressed(ctrl: bool, key_vk: int, debounce_ms: int, last_times: dict) -> bool:
    try:
        if platform.system().lower() != "windows":
            return False
        GetAsyncKeyState = ctypes.windll.user32.GetAsyncKeyState
        VK_CONTROL = 0x11
        ctrl_ok = (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0 if ctrl else True
        key_ok  = (GetAsyncKeyState(key_vk) & 0x8000) != 0
        if ctrl_ok and key_ok:
            now = time.monotonic()
            key_id = f"ctrl+{key_vk}" if ctrl else str(key_vk)
            last = last_times.get(key_id, 0.0)
            if (now - last) * 1000.0 >= debounce_ms:
                last_times[key_id] = now
                return True
    except Exception:
        return False
    return False

# --- LLM wrapper ---
class LLMWrapper:
    def __init__(self, prompt=None):
        self.client = None
        if LLMClient is not None:
            try:
                self.client = LLMClient()
                logger.info("LLM: client initialized")
            except Exception as e:
                logger.info(f"LLM: client init failed: {e}")
                self.client = None
        self.prompt = prompt or (
            "Ты помощник, который помогает искать музыку/видео на YouTube. "
            "Преобразуй пользовательский запрос в короткую точную строку для поиска на YouTube. "
            "Отвечай ТОЛЬКО этой строкой, без комментариев."
        )

    def run(self, user_text: str) -> str:
        t = (user_text or "").strip()
        if not t:
            return ""
        if self.client is None:
            logger.info("LLM: not available, using raw text")
            return t
        # пробуем разные сигнатуры
        try:
            resp = self.client.generate_text(system_prompt=self.prompt, user_text=t)
            out = (resp or "").strip().strip('"')
            logger.info(f"LLM: OK ({len(out)} chars).")
            return out or t
        except TypeError:
            pass
        try:
            resp = self.client.generate_text(self.prompt, t)
            out = (resp or "").strip().strip('"')
            logger.info(f"LLM: OK ({len(out)} chars).")
            return out or t
        except TypeError:
            pass
        try:
            resp = self.client.generate_text(f"{self.prompt}\n\nUSER:\n{t}")
            out = (resp or "").strip().strip('"')
            logger.info(f"LLM: OK ({len(out)} chars).")
            return out or t
        except Exception as e:
            logger.info(f"LLM: error: {e}; fallback to raw")
            return t

class YTWrapper:
    def __init__(self):
        self.mod = yt_orchestrator
    def search_step(self, query: str):
        q = (query or "").strip()
        if not q:
            logger.info("YT: empty query, skip")
            return None
        if self.mod is None:
            logger.info(f"YT: module not available -> echo")
            print(f"[YT QUERY] {q}")
            return None
        try:
            if hasattr(self.mod, "on_text"):
                self.mod.on_text(query=q)
            res = self.mod.search(query=q) if hasattr(self.mod, "search") else None
            logger.info("YT: search done")
            print(f"[YT RESULT] {res}")
            return res
        except Exception as e:
            logger.info(f"YT: error: {e}")
            return None

class UsefulClickerRunner:
    def __init__(self):
        self.voice_device = os.getenv("VOICE_DEVICE")
        try:
            if self.voice_device is not None and self.voice_device.strip() != "":
                self.voice_device = int(self.voice_device)
            else:
                self.voice_device = None
        except Exception:
            pass
        self.voice_lang  = os.getenv("VOICE_LANG", "ru") or None
        try:
            self.wait_seconds = float(os.getenv("VOICE_WAIT_SECONDS", "60"))
        except Exception:
            self.wait_seconds = 60.0

        self.debounce = {}
        self.voice = None
        self.llm = LLMWrapper()
        self.yt  = YTWrapper()
        self._stop = threading.Event()

    def _try_start_voice(self):
        if VoiceDaemon is None:
            logger.info("VOICE: VoiceDaemon not available (import failed).")
            return False
        argsets = [
            dict(model_name="tiny", device=self.voice_device, lang=self.voice_lang, wait_seconds=self.wait_seconds),
            dict(model_name="tiny", device=self.voice_device, lang=self.voice_lang),
            dict(model_name="tiny", device=self.voice_device),
            dict(model_name="tiny"),
            {}
        ]
        last_err = None
        for kwargs in argsets:
            try:
                vd = VoiceDaemon(**kwargs)
                try:
                    vd.start()
                except TypeError:
                    vd.start()
                self.voice = vd
                logger.info(f"VOICE: background voice daemon started. kwargs={list(kwargs.keys())}")
                # TAP
                self._attach_tap_into_daemon_buffer()
                has_buf = hasattr(vd, "_buf_lock") and hasattr(vd, "_text_buffer")
                logger.info(f"VOICE: daemon buffer present = {has_buf}")
                return True
            except TypeError as e:
                last_err = e; continue
            except Exception as e:
                last_err = e; continue
        logger.info(f"VOICE: failed to start ({last_err})")
        return False

    def _attach_tap_into_daemon_buffer(self):
        vd = self.voice
        if vd is None:
            return
        orig = getattr(vd, "_dump_text", None)
        if not callable(orig):
            logger.info("VOICE: _dump_text not found -> cannot tap")
            return
        if not hasattr(vd, "_buf_lock"):
            vd._buf_lock = threading.Lock()
        if not hasattr(vd, "_text_buffer"):
            vd._text_buffer = []
        def tapped(tag: str, text: str):
            try:
                ret = orig(tag, text)
            except Exception:
                ret = None
            try:
                if tag in ("VOICE RAW", "VOICE SEG"):
                    t = (text or "").strip()
                    if t and t != "(empty)":
                        with vd._buf_lock:
                            vd._text_buffer.append(t)
            except Exception:
                pass
            return ret
        setattr(vd, "_dump_text", tapped)
        logger.info("VOICE: tap attached (into daemon _text_buffer)")

    def start_voice(self):
        self._try_start_voice()

    def stop_voice(self):
        try:
            if self.voice:
                self.voice.stop()
                logger.info("VOICE: stopped")
        except Exception:
            pass

    def _read_buffer(self) -> str:
        if not self.voice or not hasattr(self.voice, "_buf_lock") or not hasattr(self.voice, "_text_buffer"):
            return ""
        with self.voice._buf_lock:
            parts = [p for p in self.voice._text_buffer if isinstance(p, str)]
        return "\n".join(parts).strip()

    def _flush_buffer(self) -> str:
        if not self.voice:
            return ""
        if hasattr(self.voice, "manual_flush") and callable(self.voice.manual_flush):
            try:
                t = self.voice.manual_flush(reason="Ctrl+S")  # type: ignore
                if t:
                    return t.strip()
            except Exception:
                pass
        if hasattr(self.voice, "_buf_lock") and hasattr(self.voice, "_text_buffer"):
            with self.voice._buf_lock:
                parts = [p for p in self.voice._text_buffer if isinstance(p, str)]
                self.voice._text_buffer.clear()
            return "\n".join(parts).strip()
        return ""

    def _action_show(self):
        text = self._read_buffer()
        if text:
            print("[BUFFER]\n" + text + "\n[/BUFFER]")
        else:
            print("[BUFFER] (empty)")

    def _action_flush(self):
        text = self._flush_buffer()
        if not text:
            logger.info("VOICE: nothing to flush")
            return
        print(f"[FLUSH TEXT]\n{text}\n[/FLUSH TEXT]")
        q = self.llm.run(text)
        print(f"[SEARCH QUERY] {q}")
        self.yt.search_step(q)

    def _action_append_test(self):
        if not self.voice or not hasattr(self.voice, "_buf_lock") or not hasattr(self.voice, "_text_buffer"):
            print("[TEST] daemon buffer not present")
            return
        with self.voice._buf_lock:
            self.voice._text_buffer.append("[TEST INSERT] hello from runner")
        print("[TEST] appended a test line to daemon buffer")

    def run(self):
        self.start_voice()
        last_log = time.monotonic()
        try:
            while not self._stop.is_set():
                if win_hotkey_pressed(True, 0x53, 300, self.debounce):  # Ctrl+S
                    self._action_flush()
                if win_hotkey_pressed(True, 0x44, 300, self.debounce):  # Ctrl+D
                    self._action_show()
                if win_hotkey_pressed(True, 0x42, 300, self.debounce):  # Ctrl+B
                    self._action_append_test()
                if win_hotkey_pressed(False, 0x1B, 300, self.debounce):  # ESC
                    self._stop.set(); break

                now = time.monotonic()
                if now - last_log > 5:
                    blen = 0
                    try:
                        if self.voice and hasattr(self.voice, "_buf_lock") and hasattr(self.voice, "_text_buffer"):
                            with self.voice._buf_lock:
                                blen = sum(len(s) for s in self.voice._text_buffer if isinstance(s, str))
                    except Exception:
                        pass
                    logger.info(f"Runner alive... buffer ~{blen} chars (Ctrl+S: flush, Ctrl+D: show, Ctrl+B: test, Esc: exit)")
                    last_log = now
                time.sleep(0.05)
        finally:
            self.stop_voice()
            logger.info("Runner stopped.")

if __name__ == "__main__":
    UsefulClickerRunner().run()
