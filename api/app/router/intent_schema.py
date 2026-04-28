from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Intent(str, Enum):
    MOVEMENT_COUNT = "movement_count"
    MOVEMENT_LIST = "movement_list"
    MOVEMENT_BREAKDOWN = "movement_breakdown"
    MOVEMENT_SEARCH = "movement_search"
    INCIDENT_COUNT = "incident_count"
    INCIDENT_BREAKDOWN = "incident_breakdown"
    REVIEW_CANDIDATES = "review_candidates"
    ACCOUNT_PROFILE = "account_profile"
    AVAILABLE_PERIODS = "available_periods"
    BANK_RANKING = "bank_ranking"
    FILIAL_RANKING = "filial_ranking"
    SUMMARY = "summary"
    ANALYTIC_RECOMMENDATION = "analytic_recommendation"
    INSTITUTIONAL_KNOWLEDGE = "institutional_knowledge"
    POLICY_OR_PROCESS = "policy_or_process"
    PERSON_OR_RESPONSIBLE = "person_or_responsible"
    WEB_SEARCH = "web_search"
    FOLLOWUP = "followup"
    CLARIFICATION = "clarification"


DIRECT_SQL_INTENTS = {
    Intent.MOVEMENT_COUNT,
    Intent.MOVEMENT_LIST,
    Intent.MOVEMENT_BREAKDOWN,
    Intent.MOVEMENT_SEARCH,
    Intent.INCIDENT_COUNT,
    Intent.INCIDENT_BREAKDOWN,
    Intent.REVIEW_CANDIDATES,
    Intent.ACCOUNT_PROFILE,
    Intent.AVAILABLE_PERIODS,
    Intent.BANK_RANKING,
    Intent.FILIAL_RANKING,
}


@dataclass(slots=True)
class RouteDecision:
    intent: Intent
    confidence: float
    requires_sql: bool = False
    requires_memory: bool = False
    requires_web: bool = False
    requires_llm_classifier: bool = False
    requires_llm_answer: bool = False
    group_by: str | None = None
    metric: str | None = None
    entities: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)
    filter_resolution: dict[str, Any] = field(default_factory=dict)
    task: str = "direct"
    reason: str = "deterministic_parser"
    clarification_needed: bool = False

    @property
    def is_direct_sql(self) -> bool:
        return self.intent in DIRECT_SQL_INTENTS and self.requires_sql and not self.requires_llm_answer

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "requires_sql": self.requires_sql,
            "requires_memory": self.requires_memory,
            "requires_web": self.requires_web,
            "requires_llm_classifier": self.requires_llm_classifier,
            "requires_llm_answer": self.requires_llm_answer,
            "group_by": self.group_by,
            "metric": self.metric,
            "entities": self.entities,
            "filters": self.filters,
            "filter_resolution": self.filter_resolution,
            "task": self.task,
            "reason": self.reason,
            "clarification_needed": self.clarification_needed,
        }
