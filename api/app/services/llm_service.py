from __future__ import annotations

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

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        timeout_seconds: int | None = None,
        temperature: float | None = None,
        num_predict: int | None = None,
        format_schema: dict[str, Any] | str | None = None,
    ) -> str | None:
        if not self.settings.llm_enabled:
            return None
        options: dict[str, Any] = {
            "temperature": self.settings.llm_temperature if temperature is None else temperature,
            "num_predict": self.settings.llm_max_tokens if num_predict is None else num_predict,
        }
        if not self.settings.llm_allow_thinking:
            # Ollama ignora opciones desconocidas en modelos que no las soportan.
            options["think"] = False

        payload: dict[str, Any] = {
            "model": model or self.settings.ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": options,
        }
        if format_schema:
            payload["format"] = format_schema

        response = requests.post(
            f"{self.settings.ollama_base_url}/api/chat",
            json=payload,
            timeout=timeout_seconds or self.settings.ollama_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        message = data.get("message") or {}
        content = message.get("content")
        return content.strip() if isinstance(content, str) and content.strip() else None
