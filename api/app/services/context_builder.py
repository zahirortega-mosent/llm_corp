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

    def compact_institutional_chunks(
        self,
        chunks: list[dict[str, Any]],
        *,
        max_context_tokens: int,
        per_chunk_chars: int = 900,
    ) -> list[dict[str, Any]]:
        """Incluye solo evidencia institucional relevante, no documentos completos."""
        budget_chars = max(1000, max_context_tokens * self.chars_per_token)
        compact: list[dict[str, Any]] = []
        used_chars = 0
        for chunk in chunks:
            item = {
                "chunk_id": chunk.get("chunk_id"),
                "document_id": chunk.get("document_id"),
                "chunk_index": chunk.get("chunk_index"),
                "title": chunk.get("title"),
                "content": self.trim_text(chunk.get("content"), per_chunk_chars),
                "source_type": chunk.get("source_type"),
                "source_path": chunk.get("source_path"),
                "owner_area": chunk.get("owner_area"),
                "status": chunk.get("status"),
                "version": chunk.get("version"),
                "valid_from": chunk.get("valid_from"),
                "valid_to": chunk.get("valid_to"),
                "rank": chunk.get("rank"),
                "search_mode": chunk.get("search_mode"),
            }
            size = len(str(item))
            if used_chars + size > budget_chars:
                break
            compact.append(item)
            used_chars += size
        return compact

    def build_context_for_prompt(self, context: dict[str, Any], max_context_tokens: int) -> dict[str, Any]:
        budget_chars = max(1000, max_context_tokens * self.chars_per_token)
        result: dict[str, Any] = {}
        priority_keys = [
            "route",
            "parsed",
            "metadata",
            "summary",
            "institutional_evidence",
            "institutional_sources",
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
            if key == "institutional_evidence" and isinstance(value, list):
                value = self.compact_institutional_chunks(value, max_context_tokens=max_context_tokens)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
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
