from __future__ import annotations

import json
from typing import Any

from app.router.intent_schema import Intent, RouteDecision
from app.services.llm_service import LLMService
from app.services.model_selector import ModelSelector, classification_schema
from app.utils.filters import parse_question_filters


SYSTEM_PROMPT = """Clasifica preguntas para un sistema de conciliacion bancaria.
Devuelve solo JSON valido conforme al schema. No consultes datos. No respondas al usuario.
Usa SQL directo para conteos, listados, busquedas, desgloses y rankings exactos.
Pide aclaracion si falta periodo y no puede inferirse de metadata disponible.
"""


class LLMClassifier:
    def __init__(self, llm_service: LLMService | None = None, model_selector: ModelSelector | None = None) -> None:
        self.llm_service = llm_service or LLMService()
        self.model_selector = model_selector or ModelSelector()

    def classify(
        self,
        question: str,
        metadata: dict[str, Any] | None = None,
        conversation_state: dict[str, Any] | None = None,
    ) -> RouteDecision | None:
        metadata = metadata or {}
        conversation_state = conversation_state or {}
        parsed = parse_question_filters(question, metadata)
        selector_route = RouteDecision(
            intent=Intent.SUMMARY,
            confidence=0.0,
            requires_llm_classifier=True,
            task="classification",
            filters=parsed.get("filters") or {},
            filter_resolution=parsed.get("filter_resolution") or {},
        )
        decision = self.model_selector.select(selector_route)
        prompt = json.dumps(
            {
                "current_question": question,
                "parsed_filters": parsed,
                "conversation_state": conversation_state,
                "available_periods": [str(item)[:7] for item in metadata.get("periods", [])],
            },
            ensure_ascii=False,
            default=str,
        )
        raw = self.llm_service.generate(
            SYSTEM_PROMPT,
            prompt,
            model=decision.model,
            timeout_seconds=decision.timeout_seconds,
            temperature=decision.temperature,
            format_schema=classification_schema(),
        )
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start < 0 or end <= start:
                return None
            payload = json.loads(raw[start : end + 1])
        try:
            intent = Intent(str(payload.get("intent")))
        except Exception:
            intent = Intent.SUMMARY
        return RouteDecision(
            intent=intent,
            confidence=float(payload.get("confidence") or 0.0),
            requires_sql=bool(payload.get("requires_sql", True)),
            requires_memory=bool(payload.get("requires_memory", False)),
            requires_llm_classifier=False,
            requires_llm_answer=bool(payload.get("requires_llm_answer", False)),
            group_by=payload.get("group_by"),
            entities=payload.get("entities") or {},
            filters=parsed.get("filters") or {},
            filter_resolution=parsed.get("filter_resolution") or {},
            task="direct" if not payload.get("requires_llm_answer") else "analytic_answer",
            reason="llm_classifier",
            clarification_needed=bool(payload.get("clarification_needed", False)),
        )
