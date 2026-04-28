from __future__ import annotations

import json
from typing import Any

from app.router.intent_schema import Intent, RouteDecision
from app.router.router import IntentRouter
from app.services.answer_composer import AnswerComposer
from app.services.llm_service import LLMService
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
        self.policy_service = PolicyService()
        self.web_search_service = WebSearchService()
        self.intent_router = IntentRouter()
        self.answer_composer = AnswerComposer()

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
        parsed = parse_question_filters(question, metadata)
        parsed_filters = dict(parsed.get("filters") or {})
        filters = {
            "period": explicit_filters.get("period") or parsed_filters.get("period"),
            "bank": explicit_filters.get("bank") or parsed_filters.get("bank"),
            "filial": explicit_filters.get("filial") or parsed_filters.get("filial"),
            "account_number": explicit_filters.get("account_number") or parsed_filters.get("account_number"),
        }
        if parsed_filters.get("periods") and not filters.get("period"):
            filters["periods"] = parsed_filters.get("periods")

        route = self.intent_router.route(question, metadata=metadata, parsed_filters=parsed)
        route.filters.update({key: value for key, value in filters.items() if value})
        route.entities.update({key: value for key, value in filters.items() if value})

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

        return self._answer_with_llm(
            question=question,
            user=user,
            filters=filters,
            metadata=metadata,
            parsed=parsed,
            route=route,
            use_web=use_web,
            conversation_id=conversation_id,
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
        )
        return {
            "question": question,
            "conversation_id": conversation_id,
            "filters": filters,
            "filter_resolution": parsed.get("filter_resolution") or {},
            "route": route.intent.value,
            "intent": route.intent.value,
            "confidence": route.confidence,
            "used_llm": False,
            "model_used": None,
            "used_fallback": False,
            "web_used": False,
            "web_allowed": False,
            "web_query": None,
            "answer": answer,
            "context": {
                "evidence": evidence,
                "metadata": metadata,
                "parsed": parsed,
                "route": route.to_dict(),
                "tools_used": tools_used,
            },
        }

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
        }

        user_prompt = f"""
Pregunta del usuario:
{question}

Intenciones detectadas:
{_json_block(intents)}

Ruta del router:
{_json_block(route.to_dict())}

Filtros efectivos:
{_json_block(filters)}

Resumen interno:
{_json_block(summary)}

Incidencias agregadas:
{_json_block(incident_summary[:8])}

Incidencias foco:
{_json_block(focus_incidents)}

Archivos foco:
{_json_block(focus_files)}

Movimientos recientes:
{_json_block(compact_recent_movements[:8])}

Movimientos de mayor importe:
{_json_block(compact_largest_movements[:8])}

Top cuentas por incidencias:
{_json_block(top_accounts[:6])}

Top cuentas por movimientos:
{_json_block(top_entities[:6])}

Reglas relevantes:
{_json_block(rules[:5])}

Conocimiento indexado:
{_json_block(compact_knowledge[:5])}

Responsable sugerido:
{_json_block(owner)}

Consulta web de apoyo:
{_json_block({'enabled': web_allowed, 'used': web_used, 'query': web_query, 'results': compact_web_results})}

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
            answer = self.llm_service.generate(SYSTEM_PROMPT, user_prompt)
            if not answer:
                answer = _fallback_answer(question, filters, context, web_allowed=web_allowed, web_used=web_used)
                used_fallback = True
        except Exception as exc:
            answer = _fallback_answer(question, filters, context, web_allowed=web_allowed, web_used=web_used)
            used_fallback = True
            llm_error = str(exc)

        self.query_service.write_audit(question, filters, used_fallback, answer, route=route.to_dict(), model_used="configured_default_llm")
        return {
            "question": question,
            "conversation_id": conversation_id,
            "filters": filters,
            "filter_resolution": parsed.get("filter_resolution") or {},
            "route": route.intent.value,
            "intent": route.intent.value,
            "confidence": route.confidence,
            "used_llm": not used_fallback,
            "model_used": "configured_default_llm" if not used_fallback else None,
            "used_fallback": used_fallback,
            "web_used": web_used,
            "web_allowed": web_allowed,
            "web_query": web_query,
            "answer": answer,
            "context": context,
            "llm_error": llm_error,
        }
