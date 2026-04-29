from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.router.intent_schema import Intent, RouteDecision
from app.router.router import IntentRouter
from app.router.llm_classifier import LLMClassifier
from app.services.answer_composer import AnswerComposer
from app.services.context_builder import ContextBuilder
from app.services.context_resolver import ContextResolver, ResolvedContext
from app.services.conversation_service import ConversationService
from app.services.llm_service import LLMService
from app.services.knowledge_service import KnowledgeService
from app.services.model_selector import ModelSelector
from app.services.policy_service import PolicyService
from app.services.query_service import QueryService
from app.services.web_search_service import WebSearchService
from app.utils.filters import parse_question_filters


SYSTEM_PROMPT = """Eres un analista corporativo de conciliacion bancaria.
Responde en espanol natural, directo y profesional.

Reglas:
- La verdad para cifras, saldos, movimientos, periodos e incidencias viene solo de datos internos.
- Usa internet solo como referencia publica general, nunca para sustituir datos internos.
- Responde primero con una conclusion breve y clara.
- Luego explica solo lo necesario para sustentarla.
- Si el usuario pide el primer caso, el caso critico o el detalle de una incidencia, identifica el registro mas relevante del contexto y describe banco, filial, cuenta, archivo, periodo y evidencia disponible.
- Si no hay evidencia suficiente para afirmar una causa raiz, dilo claramente y no inventes.
- Evita encabezados rigidos, lenguaje burocratico y frases como:
  'Hechos internos confirmados', 'Comparacion controlada', 'Nivel de confianza',
  'respuesta de contingencia', 'fallback', 'nota tecnica'.
- No expongas detalles tecnicos salvo que el usuario los pida.
- Si hay riesgos o pendientes, menciónalos como recomendaciones concretas.
- Si faltan datos, dilo de forma breve y clara.
- Meta de estilo: sonar como un analista util, no como una plantilla.
- Si hay referencia web, intégrala en 1 o 2 frases maximo.
- Preséntala como contexto o benchmark, no como verdad principal.
- Nunca abras una seccion titulada “fuente externa”, “comparacion controlada” o similar.
- Responde como un analista financiero, o la especialización que se solicite en la pregunta, que resume hallazgos y siguiente acción.
"""


CRITICAL_RULE_CODES = {
    "STATEMENT_BALANCE_MISMATCH",
    "HEADER_WITHOUT_MOVEMENTS",
    "DUPLICATE_HEURISTIC",
    "UNRECONCILED_MOVEMENT",
}


FOCUS_KEYWORDS = {
    "STATEMENT_BALANCE_MISMATCH": ["descuadre", "descuadres", "saldo", "saldos", "mismatch", "balance mismatch", "saldo final"],
    "HEADER_WITHOUT_MOVEMENTS": ["header", "cabecera", "sin movimientos", "sin detalle", "header_without_movements"],
    "DUPLICATE_HEURISTIC": ["duplicado", "duplicados", "repetido", "repetidos"],
    "UNRECONCILED_MOVEMENT": ["no conciliado", "no conciliados", "pendiente", "pendientes", "unreconciled"],
}


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "$0.00"


def _clip_text(value: Any, max_len: int = 250) -> Any:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= max_len else text[:max_len] + "... [truncado]"


def _compact_rows(
    rows: list[dict[str, Any]],
    max_items: int,
    text_fields: list[str] | None = None,
    text_limit: int = 220,
) -> list[dict[str, Any]]:
    text_fields = text_fields or []
    compact = []
    for row in rows[:max_items]:
        item = dict(row)
        for field in text_fields:
            if field in item:
                item[field] = _clip_text(item[field], text_limit)
        compact.append(item)
    return compact


def _json_block(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "si", "sí", "on", "debug"}


def _debug_enabled(options: dict[str, Any] | None) -> bool:
    options = options or {}
    return _truthy(options.get("debug"))


def _short_periods(periods: list[Any] | tuple[Any, ...] | None) -> list[str]:
    return [str(item)[:7] for item in (periods or []) if item is not None]


def _clean_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in (filters or {}).items() if value not in (None, "", [], {})}



def _merge_filter_resolution(parsed: dict[str, Any], resolved_context: ResolvedContext | None) -> dict[str, Any]:
    resolution = dict((parsed or {}).get("filter_resolution") or {})
    if not resolved_context:
        return resolution
    resolution.update({
        "inherits_previous_context": bool(resolved_context.inherited_previous_context),
        "context_resolution_reason": resolved_context.reason,
    })
    if resolved_context.result_ref:
        resolution["referenced_previous_result_index"] = resolved_context.result_ref.get("index")
    return resolution


def _apply_resolved_filters(parsed: dict[str, Any], resolved_context: ResolvedContext | None) -> dict[str, Any]:
    if not resolved_context or not resolved_context.filters:
        return parsed
    merged = dict(parsed or {})
    filters = dict(merged.get("filters") or {})
    for key, value in resolved_context.filters.items():
        if value not in (None, "", [], {}):
            filters[key] = value
            if key in {"period", "periods", "bank", "filial", "account_number"}:
                merged[key] = value
    merged["filters"] = filters
    merged["filter_resolution"] = _merge_filter_resolution(merged, resolved_context)
    return merged


def _row_reference(row: dict[str, Any], index: int) -> dict[str, Any]:
    keys = [
        "bank",
        "filial",
        "account_number",
        "period",
        "movement_uid",
        "incident_uid",
        "statement_uid",
        "source_filename",
        "rule_code",
        "severity",
        "movements",
        "incidents",
        "critical_incidents",
        "high_incidents",
        "review_score",
    ]
    ref = {"index": index}
    for key in keys:
        value = row.get(key)
        if value not in (None, "", [], {}):
            ref[key] = value
    label_parts = []
    for key in ["bank", "filial", "account_number", "rule_code"]:
        if ref.get(key):
            label_parts.append(str(ref[key]))
    if label_parts:
        ref["label"] = " / ".join(label_parts)
    return ref


def _extract_result_refs(evidence: dict[str, Any] | None, limit: int = 10) -> list[dict[str, Any]]:
    evidence = evidence or {}
    rows: list[dict[str, Any]] = []
    if isinstance(evidence.get("rows"), list):
        rows.extend([item for item in evidence["rows"] if isinstance(item, dict)])
    if isinstance(evidence.get("recent_movements"), list):
        rows.extend([item for item in evidence["recent_movements"] if isinstance(item, dict)])
    profile = evidence.get("profile")
    if isinstance(profile, dict):
        rows.insert(0, profile)
    refs: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        ref = _row_reference(row, len(refs) + 1)
        identity = (
            ref.get("account_number"),
            ref.get("movement_uid"),
            ref.get("incident_uid"),
            ref.get("statement_uid"),
            ref.get("bank"),
            ref.get("filial"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        refs.append(ref)
        if len(refs) >= limit:
            break
    return refs


def _public_metadata(
    filters: dict[str, Any],
    parsed: dict[str, Any],
    route: RouteDecision,
    metadata: dict[str, Any],
    evidence: dict[str, Any] | None,
    tools_used: list[str] | None,
) -> dict[str, Any]:
    """Metadata estable y pequena para Open WebUI.

    No publica evidencia completa, muestras de cuentas ni contexto interno.
    El contexto grande se entrega solo con options.debug=true.
    """
    evidence = evidence or {}
    available_periods = _short_periods(metadata.get("periods"))
    filter_resolution = parsed.get("filter_resolution") or route.filter_resolution or {}
    row_count = None
    if isinstance(evidence.get("rows"), list):
        row_count = len(evidence["rows"])
    elif isinstance(evidence.get("summary"), dict):
        row_count = 1

    public: dict[str, Any] = {
        "filters": _clean_filters(filters),
        "filter_resolution": filter_resolution,
        "available_periods": available_periods,
        "tools_used": tools_used or [],
        "row_count": row_count,
    }
    if route.group_by:
        public["group_by"] = route.group_by
    if route.metric:
        public["metric"] = route.metric
    return public


def _build_chat_response(
    *,
    question: str,
    conversation_id: str | None,
    filters: dict[str, Any],
    parsed: dict[str, Any],
    route: RouteDecision,
    answer: str,
    metadata: dict[str, Any],
    evidence: dict[str, Any] | None,
    tools_used: list[str] | None,
    used_llm: bool,
    model_used: str | None,
    used_fallback: bool,
    web_used: bool,
    web_allowed: bool,
    web_query: str | None,
    debug: bool,
    context: dict[str, Any] | None = None,
    llm_error: str | None = None,
    used_memory: bool | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "question": question,
        "conversation_id": conversation_id,
        "filters": filters,
        "filter_resolution": parsed.get("filter_resolution") or {},
        "route": route.intent.value,
        "intent": route.intent.value,
        "confidence": route.confidence,
        "used_llm": used_llm,
        "model_used": model_used,
        "used_memory": bool(route.requires_memory) if used_memory is None else bool(used_memory),
        "used_fallback": used_fallback,
        "web_used": web_used,
        "web_allowed": web_allowed,
        "web_query": web_query,
        "answer": answer,
        "metadata": _public_metadata(
            filters=filters,
            parsed=parsed,
            route=route,
            metadata=metadata,
            evidence=evidence,
            tools_used=tools_used,
        ),
    }
    if debug:
        response["context"] = context or {}
        if llm_error:
            response["llm_error"] = llm_error
    return response


def _normalized_question(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _pick_focus_rule_codes(question: str) -> list[str]:
    question_norm = _normalized_question(question)
    selected: list[str] = []
    for rule_code, keywords in FOCUS_KEYWORDS.items():
        if any(keyword in question_norm for keyword in keywords):
            selected.append(rule_code)
    return selected


def _select_focus_incidents(question: str, incident_details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not incident_details:
        return []

    focus_rule_codes = _pick_focus_rule_codes(question)
    if focus_rule_codes:
        focused = [item for item in incident_details if item.get("rule_code") in focus_rule_codes]
        if focused:
            return focused[:5]

    critical = [item for item in incident_details if item.get("rule_code") in CRITICAL_RULE_CODES or item.get("severity") == "critica"]
    if critical:
        return critical[:5]

    return incident_details[:5]


def _select_focus_files(focus_incidents: list[dict[str, Any]], files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not files:
        return []
    incident_filenames = {
        str(item.get("source_filename") or "").strip()
        for item in focus_incidents
        if item.get("source_filename")
    }
    if not incident_filenames:
        return files[:5]
    matching = [item for item in files if str(item.get("source_filename") or "").strip() in incident_filenames]
    return (matching or files)[:5]


def _fallback_answer(
    question: str,
    filters: dict[str, Any],
    context: dict[str, Any],
    web_allowed: bool,
    web_used: bool,
) -> str:
    summary = context.get("summary") or {}
    incidents = context.get("incident_summary") or []
    owner = context.get("owner")
    focus_incidents = context.get("focus_incidents") or []

    movements = int(summary.get("movements", 0) or 0)
    deposits = _money(summary.get("total_deposits", 0))
    withdrawals = _money(summary.get("total_withdrawals", 0))
    incident_count = int(summary.get("incidents", 0) or 0)
    mismatch = int(summary.get("statement_balance_mismatch", 0) or 0)
    unreconciled = int(summary.get("unreconciled_movements", 0) or 0)
    critical = int(summary.get("critical_incidents", 0) or 0)

    bank = filters.get("bank")
    period = filters.get("period")
    owner_text = owner.get("owner_name") if isinstance(owner, dict) and owner.get("owner_name") else None

    intro_parts = []
    if movements > 0:
        scope = []
        if bank:
            scope.append(f"de {bank}")
        if period:
            scope.append(f"en {str(period)[:7]}")
        scope_text = f" {' '.join(scope)}" if scope else ""
        intro_parts.append(
            f"Sí, encontré {movements:,} movimientos{scope_text}. "
            f"En total suman {deposits} en depósitos y {withdrawals} en retiros."
        )
    else:
        intro_parts.append("No encontré movimientos con los filtros actuales.")

    details = []
    if incident_count:
        details.append(f"También aparecen {incident_count:,} incidencias asociadas al conjunto filtrado.")
    if mismatch:
        details.append(f"Hay {mismatch} estado(s) de cuenta con posible descuadre de saldo.")
    if unreconciled:
        details.append(f"Quedan {unreconciled:,} movimientos no conciliados.")
    if critical:
        details.append(f"Detecté {critical} incidencia(s) crítica(s).")
    if owner_text:
        details.append(f"El responsable sugerido es {owner_text}.")

    priorities = []
    for item in incidents[:3]:
        priorities.append(f"{item.get('rule_code')}: {int(item.get('total', 0))} caso(s)")

    answer = " ".join(intro_parts)
    if details:
        answer += "\n\n" + " ".join(details)

    if focus_incidents:
        first = focus_incidents[0]
        answer += (
            "\n\nEl primer caso que revisaría es "
            f"{first.get('rule_code')} en banco {first.get('bank')}, filial {first.get('filial')}, "
            f"cuenta {first.get('account_number')} y archivo {first.get('source_filename')}."
        )

    if priorities:
        answer += "\n\nLo primero que revisaría es: " + "; ".join(priorities) + "."

    if web_used:
        answer += "\n\nUsé referencia pública solo como apoyo conceptual, sin cambiar los datos internos."

    return answer.strip()


class AnswerService:
    def __init__(self) -> None:
        self.query_service = QueryService()
        self.llm_service = LLMService()
        self.knowledge_service = KnowledgeService()
        self.policy_service = PolicyService()
        self.web_search_service = WebSearchService()
        self.intent_router = IntentRouter()
        self.answer_composer = AnswerComposer()
        self.model_selector = ModelSelector()
        self.context_builder = ContextBuilder()
        self.conversation_service = ConversationService()
        self.context_resolver = ContextResolver()
        self.llm_classifier = LLMClassifier(self.llm_service, self.model_selector)
        self.settings = get_settings()

    def answer(
        self,
        question: str,
        user: dict[str, Any],
        explicit_filters: dict[str, Any] | None = None,
        use_web: bool = False,
        conversation_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        explicit_filters = explicit_filters or {}
        options = options or {}
        metadata = self.query_service.get_metadata(user)
        original_parsed = parse_question_filters(question, metadata)
        conversation_state = None
        resolved_context: ResolvedContext | None = None
        if self.settings.enable_context_resolver and conversation_id:
            conversation_state = self.conversation_service.get_state(str(user.get("username") or ""), conversation_id)
            resolved_context = self.context_resolver.resolve(
                question,
                conversation_state=conversation_state,
                metadata=metadata,
                parsed_filters=original_parsed,
            )
        else:
            resolved_context = ResolvedContext(question, question, reason="context_resolver_disabled")

        effective_question = resolved_context.effective_question or question
        parsed = original_parsed if effective_question == question else parse_question_filters(effective_question, metadata)
        parsed = _apply_resolved_filters(parsed, resolved_context)
        parsed_filters = dict(parsed.get("filters") or {})
        filters = {
            "period": explicit_filters.get("period") or parsed_filters.get("period"),
            "bank": explicit_filters.get("bank") or parsed_filters.get("bank"),
            "filial": explicit_filters.get("filial") or parsed_filters.get("filial"),
            "account_number": explicit_filters.get("account_number") or parsed_filters.get("account_number"),
        }
        if parsed_filters.get("periods") and not filters.get("period"):
            filters["periods"] = parsed_filters.get("periods")

        route = resolved_context.route_override or self.intent_router.route(effective_question, metadata=metadata, parsed_filters=parsed)
        if route.requires_llm_classifier and self.settings.enable_llm_classifier:
            classified_route = self.llm_classifier.classify(effective_question, metadata=metadata, conversation_state=conversation_state)
            if classified_route and classified_route.confidence >= route.confidence:
                route = classified_route

        route.filters.update({key: value for key, value in filters.items() if value})
        route.entities.update({key: value for key, value in filters.items() if value})

        filter_resolution = parsed.get("filter_resolution") or {}
        if filter_resolution.get("clarification_needed"):
            clarification_route = RouteDecision(
                intent=Intent.CLARIFICATION,
                confidence=1.0,
                filters=filters,
                filter_resolution=filter_resolution,
                reason="period_clarification_needed",
                clarification_needed=True,
            )
            answer = self.answer_composer.clarification_needed(filters, metadata, filter_resolution)
            return _build_chat_response(
                question=question,
                conversation_id=conversation_id,
                filters=filters,
                parsed=parsed,
                route=clarification_route,
                answer=answer,
                metadata=metadata,
                evidence={},
                tools_used=[],
                used_llm=False,
                model_used=None,
                used_fallback=False,
                web_used=False,
                web_allowed=False,
                web_query=None,
                debug=_debug_enabled(options),
                context={"parsed": parsed, "metadata": metadata, "route": clarification_route.to_dict()},
            )

        if filter_resolution.get("available_period_not_found") and not filters.get("period") and not filters.get("periods") and route.is_direct_sql:
            metric = "incidencias" if route.intent in {Intent.INCIDENT_COUNT, Intent.INCIDENT_BREAKDOWN} else "movimientos"
            unavailable_route = RouteDecision(
                intent=route.intent,
                confidence=route.confidence,
                requires_sql=False,
                metric=route.metric,
                group_by=route.group_by,
                filters=filters,
                filter_resolution=filter_resolution,
                reason="month_not_available_without_year",
            )
            answer = self.answer_composer.unavailable_month(filters, metadata, filter_resolution, metric=metric)
            return _build_chat_response(
                question=question,
                conversation_id=conversation_id,
                filters=filters,
                parsed=parsed,
                route=unavailable_route,
                answer=answer,
                metadata=metadata,
                evidence={},
                tools_used=[],
                used_llm=False,
                model_used=None,
                used_fallback=False,
                web_used=False,
                web_allowed=False,
                web_query=None,
                debug=_debug_enabled(options),
                context={"parsed": parsed, "metadata": metadata, "route": unavailable_route.to_dict()},
            )

        if route.is_direct_sql:
            return self._answer_direct_sql(
                question=question,
                user=user,
                filters=filters,
                metadata=metadata,
                parsed=parsed,
                route=route,
                conversation_id=conversation_id,
                options=options,
            )

        if route.requires_memory:
            return self._answer_institutional(
                question=question,
                user=user,
                filters=filters,
                metadata=metadata,
                parsed=parsed,
                route=route,
                conversation_id=conversation_id,
                options=options,
            )

        return self._answer_with_llm(
            question=question,
            user=user,
            filters=filters,
            metadata=metadata,
            parsed=parsed,
            route=route,
            use_web=use_web,
            conversation_id=conversation_id,
            options=options,
        )

    def _save_conversation_state(
        self,
        *,
        conversation_id: str | None,
        user: dict[str, Any],
        question: str,
        route: RouteDecision,
        filters: dict[str, Any],
        evidence: dict[str, Any] | None,
        answer: str,
    ) -> None:
        if not self.settings.enable_context_resolver or not conversation_id:
            return
        self.conversation_service.save_state(
            username=str(user.get("username") or ""),
            conversation_id=conversation_id,
            last_question=question,
            last_intent=route.intent.value,
            last_filters=_clean_filters(filters),
            last_entities=route.entities,
            last_route=route.to_dict(),
            last_result_refs=_extract_result_refs(evidence),
            last_answer_summary=answer,
        )

    def _answer_direct_sql(
        self,
        question: str,
        user: dict[str, Any],
        filters: dict[str, Any],
        metadata: dict[str, Any],
        parsed: dict[str, Any],
        route: RouteDecision,
        conversation_id: str | None,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        max_rows = int(options.get("max_rows") or 10)
        evidence: dict[str, Any] = {}
        tools_used: list[str] = []

        if route.intent == Intent.AVAILABLE_PERIODS:
            evidence = self.query_service.get_available_periods_summary(user)
            tools_used.append("get_available_periods_summary")
        elif route.intent in {Intent.MOVEMENT_COUNT, Intent.INCIDENT_COUNT}:
            evidence = {"summary": self.query_service.get_summary(user, filters)}
            tools_used.append("get_summary")
        elif route.intent in {Intent.MOVEMENT_BREAKDOWN, Intent.BANK_RANKING, Intent.FILIAL_RANKING}:
            group_by = route.group_by or "bank"
            evidence = {"rows": self.query_service.get_movements_breakdown(user, filters, group_by=group_by, limit=max_rows)}
            tools_used.append("get_movements_breakdown")
        elif route.intent == Intent.INCIDENT_BREAKDOWN:
            group_by = route.group_by or "rule_code"
            evidence = {"rows": self.query_service.get_incidents_breakdown(user, filters, group_by=group_by, limit=max_rows)}
            tools_used.append("get_incidents_breakdown")
        elif route.intent == Intent.MOVEMENT_LIST:
            evidence = {"rows": self.query_service.get_movements(user, filters, limit=max_rows, offset=0, sort_mode="recent")}
            tools_used.append("get_movements")
        elif route.intent == Intent.MOVEMENT_SEARCH:
            search_text = route.entities.get("search_text") or question
            evidence = {"rows": self.query_service.search_movements_text(user, filters, query=search_text, limit=max_rows)}
            tools_used.append("search_movements_text")
        elif route.intent == Intent.REVIEW_CANDIDATES:
            evidence = {"rows": self.query_service.get_review_candidates(user, filters, limit=max_rows)}
            tools_used.append("get_review_candidates")
        elif route.intent == Intent.ACCOUNT_PROFILE:
            evidence = self.query_service.get_account_profile(user, filters, limit=max_rows)
            tools_used.append("get_account_profile")
        else:
            evidence = {"summary": self.query_service.get_summary(user, filters)}
            tools_used.append("get_summary")

        answer = self.answer_composer.compose_direct(
            question=question,
            route=route,
            filters=filters,
            evidence=evidence,
            metadata=metadata,
        )
        self.query_service.write_audit(
            question,
            filters,
            used_fallback=False,
            response=answer,
            route=route.to_dict(),
            tools_used=tools_used,
            model_used=None,
            username=str(user.get("username") or ""),
            conversation_id=conversation_id,
        )
        self._save_conversation_state(
            conversation_id=conversation_id,
            user=user,
            question=question,
            route=route,
            filters=filters,
            evidence=evidence,
            answer=answer,
        )
        debug = _debug_enabled(options)
        context = {
            "evidence": evidence,
            "metadata": metadata,
            "parsed": parsed,
            "route": route.to_dict(),
            "tools_used": tools_used,
        }
        return _build_chat_response(
            question=question,
            conversation_id=conversation_id,
            filters=filters,
            parsed=parsed,
            route=route,
            answer=answer,
            metadata=metadata,
            evidence=evidence,
            tools_used=tools_used,
            used_llm=False,
            model_used=None,
            used_fallback=False,
            web_used=False,
            web_allowed=False,
            web_query=None,
            debug=debug,
            context=context,
        )

    def _answer_institutional(
        self,
        question: str,
        user: dict[str, Any],
        filters: dict[str, Any],
        metadata: dict[str, Any],
        parsed: dict[str, Any],
        route: RouteDecision,
        conversation_id: str | None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = options or {}
        memory_enabled = bool(self.settings.enable_institutional_memory)
        max_chunks = int(options.get("memory_top_k") or self.settings.institutional_memory_top_k)
        tools_used: list[str] = []
        evidence: list[dict[str, Any]] = []
        if memory_enabled:
            evidence = self.knowledge_service.search(
                question,
                user=user,
                limit=max_chunks,
                require_approved=self.settings.institutional_memory_require_approved,
            )
            tools_used.append("knowledge_service.search")

        model_decision = self.model_selector.select(route, {"institutional_evidence": evidence})
        compact_context = self.context_builder.build_context_for_prompt(
            {
                "institutional_evidence": evidence,
                "parsed": parsed,
                "metadata": metadata,
                "route": route.to_dict(),
                "tools_used": tools_used,
            },
            max_context_tokens=model_decision.max_context_tokens or min(self.settings.llm_default_context, 4096),
        )

        generated_answer: str | None = None
        used_fallback = False
        llm_error = None
        if evidence and model_decision.use_llm:
            try:
                prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "institutional_answer.md"
                system_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else SYSTEM_PROMPT
                user_prompt = f"""
Pregunta institucional:
{question}

Evidencia institucional aprobada y compactada:
{_json_block(compact_context)}

Instruccion final:
Responde solo con la evidencia anterior. Si falta evidencia para algun dato, dilo claramente.
"""
                generated_answer = self.llm_service.generate(
                    system_prompt,
                    user_prompt,
                    model=model_decision.model,
                    timeout_seconds=model_decision.timeout_seconds,
                    temperature=model_decision.temperature,
                )
                if not generated_answer:
                    used_fallback = True
            except Exception as exc:
                used_fallback = True
                llm_error = str(exc)

        answer = self.answer_composer.institutional_answer(
            question,
            evidence,
            generated_answer=generated_answer,
            memory_enabled=memory_enabled,
        )
        audit_route = route.to_dict()
        audit_route["memory_chunks_used"] = [
            {"chunk_id": item.get("chunk_id"), "document_id": item.get("document_id"), "title": item.get("title")}
            for item in evidence
        ]
        self.query_service.write_audit(
            question,
            filters,
            used_fallback=used_fallback,
            response=answer,
            route=audit_route,
            tools_used=tools_used,
            model_used=model_decision.model if generated_answer else None,
            username=str(user.get("username") or ""),
            conversation_id=conversation_id,
        )
        evidence_bundle = {"institutional_chunks": evidence, "rows": evidence}
        self._save_conversation_state(
            conversation_id=conversation_id,
            user=user,
            question=question,
            route=route,
            filters=filters,
            evidence=evidence_bundle,
            answer=answer,
        )
        debug = _debug_enabled(options)
        return _build_chat_response(
            question=question,
            conversation_id=conversation_id,
            filters=filters,
            parsed=parsed,
            route=route,
            answer=answer,
            metadata=metadata,
            evidence=evidence_bundle,
            tools_used=tools_used,
            used_llm=bool(generated_answer),
            model_used=model_decision.model if generated_answer else None,
            used_fallback=used_fallback,
            web_used=False,
            web_allowed=False,
            web_query=None,
            debug=debug,
            context={"institutional_evidence": evidence, "compact_context": compact_context, "route": route.to_dict()},
            llm_error=llm_error,
            used_memory=bool(evidence),
        )

    def _answer_with_llm(
        self,
        question: str,
        user: dict[str, Any],
        filters: dict[str, Any],
        metadata: dict[str, Any],
        parsed: dict[str, Any],
        route: RouteDecision,
        use_web: bool,
        conversation_id: str | None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        intents = parsed.get("intents") or ["summary"]
        wants_incidents = any(intent in intents for intent in ["incidents", "priority", "summary"])
        wants_movements = any(intent in intents for intent in ["movements", "summary"])
        wants_rules = any(intent in intents for intent in ["rules", "summary"])
        wants_knowledge = any(intent in intents for intent in ["knowledge", "summary"])
        wants_files = any(intent in intents for intent in ["files", "incidents", "priority", "summary"])

        summary = self.query_service.get_summary(user, filters)
        recent_movements = self.query_service.get_movements(user, filters, limit=12, offset=0, sort_mode="recent") if wants_movements else []
        largest_movements = self.query_service.get_movements(user, filters, limit=12, offset=0, sort_mode="amount") if wants_movements else []
        incident_summary = self.query_service.get_incidents(user, filters, limit=8, aggregated=True) if wants_incidents else []
        incident_details = self.query_service.get_incidents(user, filters, limit=12, aggregated=False) if wants_incidents else []
        files = self.query_service.get_files(user, filters, limit=8) if wants_files else []
        top_accounts = self.query_service.get_top_accounts_by_incidents(user, filters, limit=6) if wants_incidents else []
        top_entities = self.query_service.get_top_movement_entities(user, filters, limit=6) if wants_movements else []

        related_rule_codes = [item["rule_code"] for item in incident_summary if item.get("rule_code")]
        rules = self.query_service.get_relevant_rules(user, question, related_rule_codes=related_rule_codes, limit=5) if wants_rules else []
        knowledge = self.query_service.search_knowledge(user, question, limit=5) if wants_knowledge else []

        owner = None
        if (
            filters.get("bank")
            and filters.get("filial")
            and filters.get("account_number")
            and user.get("table_access", {}).get("assignments")
        ):
            owner = self.query_service.get_assignment_for(
                user,
                bank=filters["bank"],
                filial=filters["filial"],
                account_number=filters["account_number"],
            )

        compact_recent_movements = _compact_rows(
            recent_movements,
            10,
            ["description", "concept", "reference", "folio", "source_filename"],
            160,
        )
        compact_largest_movements = _compact_rows(
            largest_movements,
            10,
            ["description", "concept", "reference", "folio", "source_filename"],
            160,
        )
        compact_incident_details = _compact_rows(
            incident_details,
            10,
            ["description", "source_filename"],
            220,
        )
        compact_files = _compact_rows(files, 8, ["source_filename"], 180)
        compact_knowledge = _compact_rows(
            knowledge,
            5,
            ["title", "content", "source_name", "source_path"],
            260,
        )
        focus_incidents = _compact_rows(_select_focus_incidents(question, compact_incident_details), 5, ["description", "source_filename"], 220)
        focus_files = _compact_rows(_select_focus_files(focus_incidents, compact_files), 5, ["source_filename"], 180)

        web_allowed = bool(use_web and self.policy_service.is_user_allowed_web(user))
        web_used = False
        web_query = None
        web_results: list[dict[str, Any]] = []
        if web_allowed:
            try:
                web_query, web_results = self.web_search_service.search_concepts(question, username=user["username"])
                web_used = bool(web_results)
            except Exception:
                web_used = False
                web_results = []

        compact_web_results = _compact_rows(web_results, 4, ["title", "snippet", "url"], 220)

        tools_used = ["get_summary"]
        if wants_movements:
            tools_used.extend(["get_movements_recent", "get_movements_amount", "get_top_movement_entities"])
        if wants_incidents:
            tools_used.extend(["get_incidents_summary", "get_incidents_details", "get_top_accounts_by_incidents"])
        if wants_rules:
            tools_used.append("get_relevant_rules")
        if wants_knowledge:
            tools_used.append("search_knowledge")
        if wants_files:
            tools_used.append("get_files")
        if web_used:
            tools_used.append("web_search_service.search_concepts")

        context = {
            "summary": summary,
            "recent_movements": compact_recent_movements,
            "largest_movements": compact_largest_movements,
            "movements": compact_recent_movements,
            "incident_summary": incident_summary,
            "incident_details": compact_incident_details,
            "focus_incidents": focus_incidents,
            "files": compact_files,
            "focus_files": focus_files,
            "top_accounts": top_accounts,
            "top_entities": top_entities,
            "rules": rules,
            "knowledge": compact_knowledge,
            "owner": owner,
            "parsed": parsed,
            "metadata": metadata,
            "route": route.to_dict(),
            "web_results": compact_web_results,
            "web_query": web_query,
            "tools_used": tools_used,
        }

        model_decision = self.model_selector.select(route, context)
        context["model_decision"] = {
            "model": model_decision.model,
            "use_llm": model_decision.use_llm,
            "reason": model_decision.reason,
            "max_context_tokens": model_decision.max_context_tokens,
            "timeout_seconds": model_decision.timeout_seconds,
        }
        compact_context = self.context_builder.build_context_for_prompt(
            context,
            max_context_tokens=model_decision.max_context_tokens,
        )

        user_prompt = f"""
Pregunta del usuario:
{question}

Evidencia interna compactada:
{_json_block(compact_context)}

Instrucción final:
1. Contesta en tono natural y directo.
2. Abre con la conclusión en 1 o 2 frases.
3. Si el usuario pidió el primer caso o un caso crítico, identifica explícitamente el registro que estás tomando como referencia.
4. Si existe evidencia estructurada, úsala tal cual; si no existe, dilo claramente.
5. Cuando hables de montos, periodos, cuentas, banco o archivo, apóyate solo en los datos internos mostrados arriba.
6. Si la web se usó, intégrala solo como benchmark general en no más de 2 frases.
7. Cierra con la siguiente acción más útil.
"""

        used_fallback = False
        llm_error = None
        try:
            answer = self.llm_service.generate(
                SYSTEM_PROMPT,
                user_prompt,
                model=model_decision.model,
                timeout_seconds=model_decision.timeout_seconds,
                temperature=model_decision.temperature,
            )
            if not answer:
                answer = _fallback_answer(question, filters, context, web_allowed=web_allowed, web_used=web_used)
                used_fallback = True
        except Exception as exc:
            answer = _fallback_answer(question, filters, context, web_allowed=web_allowed, web_used=web_used)
            used_fallback = True
            llm_error = str(exc)

        self.query_service.write_audit(
            question,
            filters,
            used_fallback,
            answer,
            route=route.to_dict(),
            tools_used=tools_used,
            model_used=model_decision.model,
            username=str(user.get("username") or ""),
            conversation_id=conversation_id,
        )
        debug = _debug_enabled(options)
        evidence = {
            "summary": summary,
            "rows": top_accounts or top_entities or compact_recent_movements or incident_summary or compact_knowledge or [],
        }
        self._save_conversation_state(
            conversation_id=conversation_id,
            user=user,
            question=question,
            route=route,
            filters=filters,
            evidence=evidence,
            answer=answer,
        )
        return _build_chat_response(
            question=question,
            conversation_id=conversation_id,
            filters=filters,
            parsed=parsed,
            route=route,
            answer=answer,
            metadata=metadata,
            evidence=evidence,
            tools_used=tools_used,
            used_llm=not used_fallback,
            model_used=model_decision.model if not used_fallback else None,
            used_fallback=used_fallback,
            web_used=web_used,
            web_allowed=web_allowed,
            web_query=web_query,
            debug=debug,
            context=context,
            llm_error=llm_error,
        )
