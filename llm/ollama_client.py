"""
ollama_client.py

Client for Ollama LLM via HTTP API (/api/generate).
"""
import os
import logging
try:
    import httpx
except ImportError:
    httpx = None

log = logging.getLogger("usefulclicker.llm")

class OllamaClient:
    """
    LLM client that calls Ollama HTTP API for text and list outputs.
    """
    def __init__(self):
        # Default model for Ollama
        self.model = os.getenv("USEFULCLICKER_OLLAMA_MODEL", "llama3.2:latest")
        log.info(f"Ollama client ready (model={self.model}).")

    def generate_text(self, prompt: str, model: str | None = None, temperature: float | None = None) -> str:
        """
        Generate text using Ollama HTTP API at /api/generate.
        """
        if httpx is None:
            raise RuntimeError("httpx is required for Ollama HTTP client")
        use_model = model or self.model
        log.info(f"Ollama generate_text: using model={use_model} temperature={temperature}")
        api_url = os.getenv("USEFULCLICKER_OLLAMA_API_URL", "http://localhost:11434/api/generate")
        # construct request payload for Ollama HTTP API
        payload: dict[str, any] = {
            "model": use_model,
            "prompt": prompt,
            "stream": False
        }
        if temperature is not None:
            payload["temperature"] = temperature
        try:
            resp = httpx.post(api_url, json=payload, timeout=60)
            # Debug: raw HTTP response body from Ollama
            log.info(f"Ollama RAW response: {resp.text}")
            resp.raise_for_status()
            data = resp.json()
            # Extract text: support 'completion' or 'text' or OpenAI-like 'choices'
            if isinstance(data, dict):
                # Ollama HTTP API returns 'response' field
                if "response" in data:
                    text = data["response"]
                elif "completion" in data:
                    text = data["completion"]
                elif "text" in data:
                    text = data["text"]
                elif "choices" in data and isinstance(data["choices"], list) and data["choices"]:
                    ch = data["choices"][0]
                    text = ch.get("text") or ch.get("message", {}).get("content", "")
                else:
                    # Fallback to raw response
                    text = str(data)
            else:
                text = str(data)
            text = text.strip()
            log.info(f"Ollama OK ({len(text)} chars).")
            return text
        except Exception as e:
            log.info(f"Ollama HTTP error: {e}")
            raise

    def generate_list(
        self,
        prompt: str,
        separator: str = "\n",
        model: str | None = None,
        temperature: float | None = None,
    ) -> list[str]:
        """
        Generate a list by splitting the generated text on the separator.
        """
        text = self.generate_text(prompt, model=model, temperature=temperature)
        items = [s.strip() for s in text.split(separator) if s.strip()]
        log.info(f"Ollama split -> {len(items)} items")
        return items