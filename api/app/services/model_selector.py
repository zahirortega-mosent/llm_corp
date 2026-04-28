from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.router.intent_schema import RouteDecision


@dataclass(slots=True)
class ModelDecision:
    model: str | None
    use_llm: bool
    reason: str
    max_context_tokens: int
    timeout_seconds: int
    temperature: float
    structured_output_schema: dict[str, Any] | None = None


class ModelSelector:
    """Selecciona modelo segun ruta y evidencia.

    Regla de negocio: rutas SQL directas no usan LLM; clasificacion ambigua usa
    modelo chico con JSON schema; analisis financiero usa el modelo analista.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def select(self, route: RouteDecision, evidence: dict[str, Any] | None = None) -> ModelDecision:
        evidence = evidence or {}
        if not route.requires_llm_answer and route.task != "classification":
            return ModelDecision(
                model=None,
                use_llm=False,
                reason="direct_sql_or_template",
                max_context_tokens=0,
                timeout_seconds=0,
                temperature=0.0,
            )

        if route.task == "classification" or route.requires_llm_classifier:
            return ModelDecision(
                model=self.settings.llm_classifier_model,
                use_llm=True,
                reason="ambiguous_route_classification",
                max_context_tokens=min(self.settings.llm_default_context, 2048),
                timeout_seconds=self.settings.llm_classifier_timeout_seconds,
                temperature=0.0,
                structured_output_schema=classification_schema(),
            )

        if route.task == "institutional_synthesis" or route.requires_memory:
            return ModelDecision(
                model=self.settings.llm_fast_model,
                use_llm=True,
                reason="institutional_or_short_synthesis",
                max_context_tokens=min(self.settings.llm_default_context, 4096),
                timeout_seconds=self.settings.llm_classifier_timeout_seconds,
                temperature=0.1,
            )

        return ModelDecision(
            model=self.settings.llm_analyst_model,
            use_llm=True,
            reason="analytic_answer_with_compact_evidence",
            max_context_tokens=self.settings.llm_default_context,
            timeout_seconds=self.settings.llm_analyst_timeout_seconds,
            temperature=self.settings.llm_temperature,
        )


def classification_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "intent": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "inherits_previous_context": {"type": "boolean"},
            "group_by": {"type": ["string", "null"]},
            "requires_sql": {"type": "boolean"},
            "requires_llm_answer": {"type": "boolean"},
            "requires_memory": {"type": "boolean"},
            "clarification_needed": {"type": "boolean"},
            "entities": {"type": "object"},
        },
        "required": [
            "intent",
            "confidence",
            "inherits_previous_context",
            "group_by",
            "requires_sql",
            "requires_llm_answer",
            "requires_memory",
            "clarification_needed",
            "entities",
        ],
    }
