"""Open WebUI Pipe for llm_corp Block 3.

Install this file as a Function/Pipe in Open WebUI. It keeps the Pipe thin:
- extracts the last user message,
- forwards a stable conversation_id to the FastAPI /chat endpoint,
- sends only minimal metadata/options,
- leaves routing, SQL, context and follow-up resolution to the backend.
"""

from __future__ import annotations

from typing import Any

import requests
from pydantic import BaseModel, Field


class Pipe:
    class Valves(BaseModel):
        API_BASE_URL: str = Field(default="http://api:8000", description="Base URL for llm_corp FastAPI inside docker compose")
        API_USERNAME: str = Field(default="admin", description="llm_corp username")
        API_PASSWORD: str = Field(default="Admin123!", description="llm_corp password")
        REQUEST_TIMEOUT_SECONDS: int = Field(default=180, ge=5, le=600)
        DEBUG_CONTEXT: bool = Field(default=False, description="Send options.debug=true only for diagnostics")
        MAX_ROWS: int = Field(default=10, ge=1, le=100)

    def __init__(self) -> None:
        self.type = "pipe"
        self.id = "corp_llm_bloque3"
        self.name = "CORP / Mosent Group"
        self.valves = self.Valves()
        self._token: str | None = None

    def _login(self) -> str:
        response = requests.post(
            f"{self.valves.API_BASE_URL.rstrip('/')}/auth/login",
            json={"username": self.valves.API_USERNAME, "password": self.valves.API_PASSWORD},
            timeout=self.valves.REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        self._token = response.json()["access_token"]
        return self._token

    def _headers(self) -> dict[str, str]:
        token = self._token or self._login()
        return {"Authorization": f"Bearer {token}"}

    def _last_user_message(self, body: dict[str, Any]) -> str:
        messages = body.get("messages") or []
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            parts.append(str(item.get("text") or ""))
                    return "\n".join(part for part in parts if part).strip()
        return str(body.get("prompt") or "").strip()

    def _conversation_id(self, body: dict[str, Any]) -> str | None:
        metadata = body.get("metadata") or {}
        candidates = [
            body.get("conversation_id"),
            body.get("chat_id"),
            body.get("id"),
            metadata.get("conversation_id"),
            metadata.get("chat_id"),
            metadata.get("session_id"),
        ]
        for value in candidates:
            if value:
                return str(value)
        return None

    def pipe(self, body: dict[str, Any], __user__: dict[str, Any] | None = None) -> str:
        question = self._last_user_message(body)
        payload = {
            "question": question,
            "conversation_id": self._conversation_id(body),
            "use_web": False,
            "options": {
                "debug": bool(self.valves.DEBUG_CONTEXT),
                "max_rows": int(self.valves.MAX_ROWS),
            },
        }
        try:
            response = requests.post(
                f"{self.valves.API_BASE_URL.rstrip('/')}/chat",
                json=payload,
                headers=self._headers(),
                timeout=self.valves.REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code == 401:
                self._token = None
                response = requests.post(
                    f"{self.valves.API_BASE_URL.rstrip('/')}/chat",
                    json=payload,
                    headers=self._headers(),
                    timeout=self.valves.REQUEST_TIMEOUT_SECONDS,
                )
            response.raise_for_status()
            data = response.json()
            return str(data.get("answer") or data)
        except Exception as exc:
            return f"No pude consultar la API corporativa: {exc}"
