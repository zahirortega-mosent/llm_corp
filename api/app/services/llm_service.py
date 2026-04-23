from typing import Any

import requests

from app.config import get_settings


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def available(self) -> bool:
        if not self.settings.llm_enabled:
            return False
        try:
            response = requests.get(f"{self.settings.ollama_base_url}/api/tags", timeout=10)
            response.raise_for_status()
            return True
        except Exception:
            return False

    def generate(self, system_prompt: str, user_prompt: str) -> str | None:
        if not self.settings.llm_enabled:
            return None
        payload: dict[str, Any] = {
            "model": self.settings.ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": self.settings.llm_temperature,
                "num_predict": self.settings.llm_max_tokens,
            },
        }
        response = requests.post(
            f"{self.settings.ollama_base_url}/api/chat",
            json=payload,
            timeout=self.settings.ollama_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        message = data.get("message") or {}
        content = message.get("content")
        return content.strip() if isinstance(content, str) and content.strip() else None
