from __future__ import annotations

from typing import Any


class ContextBuilder:
    """Compacta evidencia para no enviar contexto gigante al LLM.

    Aproximacion conservadora: 1 token ~= 4 caracteres. El objetivo no es
    contar exacto sino cortar temprano evidencia no esencial antes de llamar
    al modelo.
    """

    def __init__(self, chars_per_token: int = 4) -> None:
        self.chars_per_token = chars_per_token

    def estimate_tokens(self, value: Any) -> int:
        return max(1, len(str(value)) // self.chars_per_token)

    def trim_text(self, value: Any, max_chars: int) -> Any:
        if value is None:
            return None
        text = str(value)
        if len(text) <= max_chars:
            return value
        return text[: max(0, max_chars - 20)] + "... [truncado]"

    def compact_rows(self, rows: list[dict[str, Any]], row_limit: int = 10, text_limit: int = 220) -> list[dict[str, Any]]:
        compact: list[dict[str, Any]] = []
        for row in rows[:row_limit]:
            item: dict[str, Any] = {}
            for key, value in row.items():
                if isinstance(value, str):
                    item[key] = self.trim_text(value, text_limit)
                else:
                    item[key] = value
            compact.append(item)
        return compact

    def build_context_for_prompt(self, context: dict[str, Any], max_context_tokens: int) -> dict[str, Any]:
        budget_chars = max(1000, max_context_tokens * self.chars_per_token)
        result: dict[str, Any] = {}
        priority_keys = [
            "route",
            "parsed",
            "metadata",
            "summary",
            "incident_summary",
            "focus_incidents",
            "focus_files",
            "recent_movements",
            "largest_movements",
            "top_accounts",
            "top_entities",
            "rules",
            "knowledge",
            "owner",
            "web_query",
            "web_results",
        ]
        used_chars = 0
        for key in priority_keys:
            if key not in context:
                continue
            value = context[key]
            if isinstance(value, list) and value and isinstance(value[0], dict):
                value = self.compact_rows(value)
            if isinstance(value, str):
                value = self.trim_text(value, 800)
            value_chars = len(str(value))
            if used_chars + value_chars > budget_chars:
                remaining = max(0, budget_chars - used_chars)
                if remaining > 200:
                    result[key] = self.trim_text(value, remaining)
                break
            result[key] = value
            used_chars += value_chars
        result["context_tokens_estimated"] = self.estimate_tokens(result)
        result["context_budget_tokens"] = max_context_tokens
        return result
