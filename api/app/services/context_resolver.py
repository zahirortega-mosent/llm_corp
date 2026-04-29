from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.router.intent_schema import Intent, RouteDecision
from app.utils.filters import MONTHS, normalize_period, normalize_text, parse_question_filters, period_label


GROUP_BY_WORDS = {
    "bank": ("por banco", "por bancos", "banco", "bancos"),
    "filial": ("por filial", "por filiales", "filial", "filiales"),
    "account_number": ("por cuenta", "por cuentas", "cuenta", "cuentas"),
    "period": ("por periodo", "por periodos", "por mes", "por meses"),
    "rule_code": ("por regla", "por reglas"),
    "severity": ("por severidad", "por gravedad"),
}

REFERENCE_TERMS = (
    "revisa la primera",
    "revisar la primera",
    "la primera",
    "el primero",
    "primer caso",
    "primera cuenta",
    "ese",
    "esa",
    "ese caso",
    "esa cuenta",
    "dame mas detalle",
    "mas detalle",
    "detalle",
)

FOLLOWUP_PREFIXES = ("y ", "tambien ", "ahora ", "entonces ")


@dataclass(slots=True)
class ResolvedContext:
    original_question: str
    effective_question: str
    inherited_previous_context: bool = False
    filters: dict[str, Any] = field(default_factory=dict)
    entities: dict[str, Any] = field(default_factory=dict)
    route_override: RouteDecision | None = None
    result_ref: dict[str, Any] | None = None
    reason: str = "no_previous_context"

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_question": self.original_question,
            "effective_question": self.effective_question,
            "inherited_previous_context": self.inherited_previous_context,
            "filters": self.filters,
            "entities": self.entities,
            "route_override": self.route_override.to_dict() if self.route_override else None,
            "result_ref": self.result_ref,
            "reason": self.reason,
        }


class ContextResolver:
    """Resolve follow-ups with persisted structured state before final routing."""

    def resolve(
        self,
        question: str,
        conversation_state: dict[str, Any] | None,
        metadata: dict[str, Any] | None = None,
        parsed_filters: dict[str, Any] | None = None,
    ) -> ResolvedContext:
        metadata = metadata or {}
        parsed = parsed_filters or parse_question_filters(question, metadata)
        question_norm = parsed.get("question_normalized") or normalize_text(question)
        state = conversation_state or {}
        if not state:
            return ResolvedContext(question, question, reason="no_previous_context")

        last_filters = dict(state.get("last_filters") or {})
        last_route = dict(state.get("last_route") or {})
        last_intent = str(state.get("last_intent") or last_route.get("intent") or "")
        last_refs = list(state.get("last_result_refs") or [])

        reference = self._resolve_reference(question, question_norm, last_filters, last_refs, last_route)
        if reference:
            return reference

        group_by = self._detect_group_by(question_norm)
        if group_by and self._looks_like_short_followup(question_norm):
            return self._resolve_group_by_followup(question, group_by, last_filters, last_intent, last_route, parsed)

        period_followup = self._resolve_period_followup(question, question_norm, last_filters, last_intent, last_route, metadata, parsed)
        if period_followup:
            return period_followup

        inherited_filters = self._inherit_missing_filters(parsed.get("filters") or {}, last_filters)
        if inherited_filters != (parsed.get("filters") or {}) and self._looks_like_short_followup(question_norm):
            return ResolvedContext(
                original_question=question,
                effective_question=question,
                inherited_previous_context=True,
                filters=inherited_filters,
                entities={k: v for k, v in inherited_filters.items() if v},
                reason="inherited_missing_filters",
            )

        return ResolvedContext(question, question, reason="no_resolvable_followup")

    def _looks_like_short_followup(self, question_norm: str) -> bool:
        words = question_norm.split()
        if len(words) <= 5:
            return True
        return any(question_norm.startswith(prefix) for prefix in FOLLOWUP_PREFIXES)

    def _detect_group_by(self, question_norm: str) -> str | None:
        for group_by, aliases in GROUP_BY_WORDS.items():
            if any(alias in question_norm for alias in aliases):
                return group_by
        return None

    def _resolve_reference(
        self,
        question: str,
        question_norm: str,
        last_filters: dict[str, Any],
        last_refs: list[dict[str, Any]],
        last_route: dict[str, Any],
    ) -> ResolvedContext | None:
        if not any(term in question_norm for term in REFERENCE_TERMS):
            return None

        ref = last_refs[0] if last_refs else None
        filters = dict(last_filters)
        if ref:
            for key in ["period", "bank", "filial", "account_number"]:
                if ref.get(key):
                    filters[key] = ref[key]
        if not filters.get("account_number"):
            return None

        route = RouteDecision(
            intent=Intent.ACCOUNT_PROFILE,
            confidence=0.90,
            requires_sql=True,
            metric="account_profile",
            filters=filters,
            entities={k: v for k, v in filters.items() if v},
            reason="context_reference_followup",
        )
        return ResolvedContext(
            original_question=question,
            effective_question="perfil de cuenta con detalle",
            inherited_previous_context=True,
            filters=filters,
            entities={k: v for k, v in filters.items() if v},
            route_override=route,
            result_ref=ref,
            reason="reference_to_previous_result",
        )

    def _resolve_group_by_followup(
        self,
        question: str,
        group_by: str,
        last_filters: dict[str, Any],
        last_intent: str,
        last_route: dict[str, Any],
        parsed: dict[str, Any],
    ) -> ResolvedContext:
        filters = self._inherit_missing_filters(parsed.get("filters") or {}, last_filters)
        metric = str(last_route.get("metric") or "")
        is_incident_context = "incident" in last_intent or metric == "incidents"
        intent = Intent.INCIDENT_BREAKDOWN if is_incident_context else Intent.MOVEMENT_BREAKDOWN
        route = RouteDecision(
            intent=intent,
            confidence=0.88,
            requires_sql=True,
            group_by=group_by,
            metric="incidents" if is_incident_context else "movements",
            filters=filters,
            entities={k: v for k, v in filters.items() if v},
            reason="context_group_by_followup",
        )
        noun = "incidencias" if is_incident_context else "movimientos"
        effective_question = f"{noun} por {self._group_label(group_by)}"
        if filters.get("period"):
            effective_question += f" en {period_label(filters.get('period')) or str(filters.get('period'))[:7]}"
        return ResolvedContext(
            original_question=question,
            effective_question=effective_question,
            inherited_previous_context=True,
            filters=filters,
            entities={k: v for k, v in filters.items() if v},
            route_override=route,
            reason="group_by_followup",
        )

    def _resolve_period_followup(
        self,
        question: str,
        question_norm: str,
        last_filters: dict[str, Any],
        last_intent: str,
        last_route: dict[str, Any],
        metadata: dict[str, Any],
        parsed: dict[str, Any],
    ) -> ResolvedContext | None:
        last_period = normalize_period(last_filters.get("period"))
        if not last_period:
            return None
        month_num = None
        for month_name, value in MONTHS.items():
            if month_name in question_norm:
                month_num = value
                break
        if not month_num:
            return None
        explicit_year_present = any(str(year) in question_norm for year in range(2020, 2031))
        parsed_period = normalize_period((parsed.get("filters") or {}).get("period"))
        target_period = parsed_period
        if not explicit_year_present:
            target_period = f"{last_period[:4]}-{month_num:02d}-01"
        if not target_period:
            return None
        available = {normalize_period(str(item)) for item in metadata.get("periods", []) or []}
        if available and target_period not in available:
            return None

        filters = dict(last_filters)
        filters.update({k: v for k, v in (parsed.get("filters") or {}).items() if v})
        filters["period"] = target_period
        route = self._route_from_previous(last_intent, last_route, filters)
        return ResolvedContext(
            original_question=question,
            effective_question=question,
            inherited_previous_context=True,
            filters=filters,
            entities={k: v for k, v in filters.items() if v},
            route_override=route,
            reason="period_followup_same_context",
        )

    def _route_from_previous(self, last_intent: str, last_route: dict[str, Any], filters: dict[str, Any]) -> RouteDecision:
        try:
            intent = Intent(last_intent)
        except Exception:
            intent = Intent.SUMMARY
        direct_intents = {
            Intent.MOVEMENT_COUNT,
            Intent.MOVEMENT_LIST,
            Intent.MOVEMENT_BREAKDOWN,
            Intent.MOVEMENT_SEARCH,
            Intent.INCIDENT_COUNT,
            Intent.INCIDENT_BREAKDOWN,
            Intent.REVIEW_CANDIDATES,
            Intent.ACCOUNT_PROFILE,
            Intent.BANK_RANKING,
            Intent.FILIAL_RANKING,
        }
        if intent not in direct_intents:
            intent = Intent.MOVEMENT_COUNT if str(last_route.get("metric")) == "movements" else Intent.SUMMARY
        return RouteDecision(
            intent=intent,
            confidence=0.86,
            requires_sql=intent != Intent.SUMMARY,
            requires_llm_answer=intent == Intent.SUMMARY,
            group_by=last_route.get("group_by"),
            metric=last_route.get("metric"),
            filters=filters,
            entities={k: v for k, v in filters.items() if v},
            reason="context_period_followup",
        )

    def _inherit_missing_filters(self, current_filters: dict[str, Any], last_filters: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current_filters or {})
        for key in ["period", "periods", "bank", "filial", "account_number"]:
            if not merged.get(key) and last_filters.get(key):
                merged[key] = last_filters[key]
        return merged

    def _group_label(self, group_by: str) -> str:
        return {
            "bank": "banco",
            "filial": "filial",
            "account_number": "cuenta",
            "period": "periodo",
            "rule_code": "regla",
            "severity": "severidad",
        }.get(group_by, group_by)
