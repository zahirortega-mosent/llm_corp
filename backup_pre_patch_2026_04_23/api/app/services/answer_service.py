import json
from typing import Any

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
- Luego agrega solo lo necesario para sustentarla.
- Evita encabezados rigidos, lenguaje burocratico y frases como:
  'Hechos internos confirmados', 'Comparacion controlada', 'Nivel de confianza',
  'respuesta de contingencia', 'fallback', 'nota tecnica'.
- No expongas detalles tecnicos salvo que el usuario los pida.
- Si hay riesgos o pendientes, mencionalos como recomendaciones concretas.
- Si faltan datos, dilo de forma breve y clara.
- Meta de estilo: sonar como un analista util, no como una plantilla.
- Si hay referencia web, intégrala en 1 o 2 frases máximo.
- Preséntala como contexto o benchmark, no como verdad principal.
- Nunca abras una sección titulada “fuente externa”, “comparación controlada” o similar.
- Responde como un analista financiero, o la especialización que  se solicite en la pregunta,  que resume hallazgos y siguiente acción.
"""


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


def _compact_rows(rows: list[dict[str, Any]], max_items: int, text_fields: list[str] | None = None, text_limit: int = 220) -> list[dict[str, Any]]:
    text_fields = text_fields or []
    compact = []
    for row in rows[:max_items]:
        item = dict(row)
        for field in text_fields:
            if field in item:
                item[field] = _clip_text(item[field], text_limit)
        compact.append(item)
    return compact


def _fallback_answer(question: str, filters: dict[str, Any], context: dict[str, Any], web_allowed: bool, web_used: bool) -> str:
    summary = context.get("summary") or {}
    incidents = context.get("incident_summary") or []
    owner = context.get("owner")

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
            scope.append(f"en {period[:7]}")
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
        priorities.append(
            f"{item.get('rule_code')}: {int(item.get('total', 0))} caso(s)"
        )

    answer = " ".join(intro_parts)

    if details:
        answer += "\n\n" + " ".join(details)

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

    def answer(self, question: str, user: dict[str, Any], explicit_filters: dict[str, Any] | None = None, use_web: bool = False) -> dict[str, Any]:
        explicit_filters = explicit_filters or {}
        metadata = self.query_service.get_metadata(user)
        parsed = parse_question_filters(question, metadata)
        filters = {
            "period": explicit_filters.get("period") or parsed.get("period"),
            "bank": explicit_filters.get("bank") or parsed.get("bank"),
            "filial": explicit_filters.get("filial") or parsed.get("filial"),
            "account_number": explicit_filters.get("account_number") or parsed.get("account_number"),
        }
        summary = self.query_service.get_summary(user, filters)
        movements = self.query_service.get_movements(user, filters, limit=5)
        incident_summary = self.query_service.get_incidents(user, filters, limit=4, aggregated=True)
        incident_details = self.query_service.get_incidents(user, filters, limit=4, aggregated=False)
        files = self.query_service.get_files(user, filters, limit=3)
        top_accounts = self.query_service.get_top_accounts_by_incidents(user, filters, limit=3)
        top_entities = self.query_service.get_top_movement_entities(user, filters, limit=3)
        related_rule_codes = [item["rule_code"] for item in incident_summary]
        rules = self.query_service.get_relevant_rules(user, question, related_rule_codes=related_rule_codes, limit=3)
        knowledge = self.query_service.search_knowledge(user, question, limit=3)

        owner = None
        if filters.get("bank") and filters.get("filial") and filters.get("account_number") and user.get("table_access", {}).get("assignments"):
            owner = self.query_service.get_assignment_for(
                user,
                bank=filters["bank"],
                filial=filters["filial"],
                account_number=filters["account_number"],
            )

        compact_movements = _compact_rows(movements, 5, ["description", "concept", "reference", "folio", "source_filename"], 120)
        compact_incident_details = _compact_rows(incident_details, 4, ["description", "source_filename"], 140)
        compact_files = _compact_rows(files, 3, ["source_filename"], 120)
        compact_knowledge = _compact_rows(knowledge, 3, ["title", "content", "source_name", "source_path"], 220)

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

        context = {
            "summary": summary,
            "movements": compact_movements,
            "incident_summary": incident_summary,
            "incident_details": compact_incident_details,
            "files": compact_files,
            "top_accounts": top_accounts,
            "top_entities": top_entities,
            "rules": rules,
            "knowledge": compact_knowledge,
            "owner": owner,
            "parsed": parsed,
            "metadata": metadata,
            "web_results": web_results,
            "web_query": web_query,
        }

        user_prompt = f"""
Pregunta del usuario: {question}

Filtros:
- periodo: {filters.get('period')}
- banco: {filters.get('bank')}
- filial: {filters.get('filial')}
- cuenta: {filters.get('account_number')}

Resumen interno:
- movimientos: {summary.get('movements', 0)}
- depositos: {_money(summary.get('total_deposits', 0))}
- retiros: {_money(summary.get('total_withdrawals', 0))}
- incidencias: {summary.get('incidents', 0)}
- movimientos no conciliados: {summary.get('unreconciled_movements', 0)}
- incidencias criticas: {summary.get('critical_incidents', 0)}
- descuadres de saldo: {summary.get('statement_balance_mismatch', 0)}

Top incidencias:
{chr(10).join([f"- {i.get('rule_code')}: {i.get('total')} caso(s)" for i in incident_summary[:3]]) or "- Sin incidencias relevantes"}

Movimientos ejemplo:
{chr(10).join([f"- {m.get('movement_date')} | {m.get('movement_type')} | {m.get('amount')} | {m.get('concept') or m.get('description')}" for m in compact_movements[:3]]) or "- Sin ejemplos"}

Instruccion:
Responde en tono natural y directo. Primero da la conclusion. Luego explica lo importante en pocas lineas.
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

        self.query_service.write_audit(question, filters, used_fallback, answer)
        return {
            "question": question,
            "filters": filters,
            "used_fallback": used_fallback,
            "web_used": web_used,
            "web_allowed": web_allowed,
            "web_query": web_query,
            "answer": answer,
            "context": context,
            "llm_error": llm_error,
        }
