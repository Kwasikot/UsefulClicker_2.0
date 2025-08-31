# llm/openai_client.py
import os, logging
import httpx
from openai import OpenAI

log = logging.getLogger("usefulclicker.llm")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] LLM: %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

class LLMClient:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            log.info("OPENAI_API_KEY is not set -> using MOCK.")
            raise RuntimeError("OPENAI_API_KEY missing")

        # Явно собираем httpx.Client, чтобы OpenAI SDK НЕ создавал свой
        # и не подсовывал 'proxies' из своего кода.
        proxy = os.getenv("USEFULCLICKER_OPENAI_PROXY")  # опционально
        if proxy:
            http_client = httpx.Client(proxies=proxy, timeout=30, trust_env=False)
            proxy_state = "explicit"
        else:
            # без прокси и без автоподхвата системных переменных (HTTP(S)_PROXY)
            http_client = httpx.Client(timeout=30, trust_env=False)
            proxy_state = "off"

        self.client = OpenAI(api_key=api_key, http_client=http_client)
        self.model = os.getenv("USEFULCLICKER_OPENAI_MODEL", "gpt-5")
        #log.info(f"Client ready (model={self.model}, proxy={proxy_state}).")

    def generate_text(self, prompt: str, model: str | None = None, temperature: float | None = None) -> str:
        log.info("generate_text()")
        use_model = model or self.model
        use_temp = 1 if temperature is None else float(temperature)
        resp = self.client.chat.completions.create(
            model=use_model,
            messages=[{"role":"user","content":prompt}],
            temperature=use_temp,
        )
        txt = (resp.choices[0].message.content or "").strip()
        log.info(f"OK ({len(txt)} chars).")
        return txt

    def generate_list(self, prompt: str, separator: str = "\n", model: str | None = None, temperature: float | None = None):
        txt = self.generate_text(prompt, model=model, temperature=temperature)
        items = [s.strip() for s in txt.split(separator) if s.strip()]
        log.info(f"split -> {len(items)} items")
        return items
