from __future__ import annotations

from typing import Any

from app.router.deterministic_parser import DeterministicParser
from app.router.intent_schema import RouteDecision
from app.utils.filters import parse_question_filters


class IntentRouter:
    def __init__(self) -> None:
        self.deterministic_parser = DeterministicParser()

    def route(self, question: str, metadata: dict[str, Any] | None = None, parsed_filters: dict[str, Any] | None = None) -> RouteDecision:
        metadata = metadata or {}
        parsed = parsed_filters or parse_question_filters(question, metadata)
        decision = self.deterministic_parser.parse(question, metadata=metadata, parsed_filters=parsed)

        # Umbrales de Bloque 1. El LLM classifier se deja marcado para bloques
        # posteriores, pero no se invoca aqui para no meter el modelo grande en
        # rutas exactas.
        if decision.confidence >= 0.85:
            decision.requires_llm_classifier = False
            return decision
        if 0.65 <= decision.confidence < 0.85:
            decision.requires_llm_classifier = True
            return decision
        decision.clarification_needed = True
        return decision
