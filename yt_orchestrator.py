# yt_orchestrator.py
from typing import List
import time
try:
    from llm.openai_client import LLMClient
except Exception:
    LLMClient = None

class _Core:
    def __init__(self, max_list_size=20, min_step_interval_ms=400):
        self.max_list_size = int(max_list_size)
        self.min_step_interval_ms = int(min_step_interval_ms)
        self.epoch = 0
        self.query_list: List[str] = []
        self.q_index = 0
        self._cmd_queue: List[str] = []
        self._last_step_ts = 0.0
        self._llm = None  # ленивое создание

    @property
    def llm(self):
        if self._llm is None and LLMClient is not None:
            self._llm = LLMClient()
        return self._llm

    def on_voice(self, text: str = "", vtype: str = "") -> None:
        text = (text or "").strip()
        vtype = (vtype or "").strip().lower()
        if not text:
            return
        if vtype == "command":
            known = {"next","pause","resume","seek_fwd","seek_back","scroll_down","scroll_up","fullscreen","click_first"}
            if text in known:
                self._cmd_queue.append(text)
            return
        # query / пустой тип => начать новую эпоху
        self.epoch += 1
        self.query_list = self._build_list(text)
        self.q_index = 0
        self._last_step_ts = 0.0

    def next_cmd(self) -> str:
        return self._cmd_queue.pop(0) if self._cmd_queue else ""

    def next_query(self) -> str:
        now = time.time()
        if (now - self._last_step_ts) * 1000.0 < self.min_step_interval_ms:
            return ""
        if 0 <= self.q_index < len(self.query_list):
            q = self.query_list[self.q_index]
            print(f"[YTDBG] next_query -> {q}")
            self.q_index += 1
            self._last_step_ts = now
            return q or ""
        return ""

    def _build_list(self, phrase: str) -> List[str]:
        phrase = (phrase or "").strip()
        if not phrase:
            return []
        if self.llm is not None:
            prompt = (
                "Ты — оператор научного поиска на YouTube.\n"
                "Сделай 12 точных запросов по теме. "
                "Синонимы, смежные темы, имена авторов/каналов, форматы (lecture, tutorial, interview, conference). "
                "Только строки-запросы, без нумерации и пояснений.\n\n"
                f"Фраза: «{phrase}»"
            )
            try:
                text = self.llm.generate_text(prompt)
                lines = [ln.strip(" \t\r\n-•") for ln in text.splitlines()] if isinstance(text, str) else []
                lines = [ln for ln in lines if ln]
                if lines:
                    return lines[: self.max_list_size]
            except Exception:
                pass
        return [phrase]

# Глобальный синглтон
_CORE = _Core()

# Модульные функции, чтобы не создавать классы в <extnode>


def next_cmd() -> str:
    return _CORE.next_cmd()


def on_voice(text: str = "", vtype: str = "") -> str:
    _CORE.on_voice(text=text, vtype=vtype)
    try:
        print(f"[YTDBG] on_voice vtype={vtype!r} text={text!r} "
              f"-> size={len(_CORE.query_list)} epoch={_CORE.epoch}")
        if _CORE.query_list[:3]:
            print(f"[YTDBG] preview: {_CORE.query_list[:3]}")
    except Exception:
        pass
    return ""

def next_query() -> str:
    q = _CORE.next_query()
    try:
        print(f"[YTDBG] next_query -> {q!r} "
              f"(idx={_CORE.q_index}/{len(_CORE.query_list)})")
    except Exception:
        pass
    return q
