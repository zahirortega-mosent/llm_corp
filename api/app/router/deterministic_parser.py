from __future__ import annotations

import re
from typing import Any

from app.router.intent_schema import Intent, RouteDecision
from app.utils.filters import normalize_text, parse_question_filters


COUNT_TERMS = ("cuanto", "cuantos", "cuantas", "total", "numero", "cantidad", "conteo", "count")
MOVEMENT_TERMS = ("movimiento", "movimientos", "deposito", "depositos", "retiro", "retiros")
INCIDENT_TERMS = ("incidencia", "incidencias", "hallazgo", "hallazgos", "error", "errores", "descuadre", "descuadres")
LIST_TERMS = ("lista", "listar", "muestra", "mostrar", "dame", "ver", "ultimos", "recientes", "detalle")
SEARCH_TERMS = ("busca", "buscar", "contenga", "contienen", "texto", "descripcion", "concepto", "referencia")
REVIEW_TERMS = ("revisar", "revision", "prioridad", "prioridades", "sugerida", "sugeridas", "recomendadas", "criticas", "criticos")
AVAILABLE_PERIOD_TERMS = ("periodos disponibles", "meses disponibles", "periodos cargados", "que periodos", "cuales periodos", "catalogo de periodos")
INSTITUTIONAL_TERMS = (
    "proceso", "flujo", "responsable", "autoriza", "politica", "procedimiento", "regla interna",
    "area", "escalamiento", "manual", "como se hace", "que significa", "sla", "matriz de aprobacion",
)

GROUP_BY_ALIASES = {
    # Solo aliases que implican agrupacion. Evita tomar "banco BANBAJIO"
    # como desglose por banco cuando realmente es filtro de banco.
    "bank": ("por banco", "por bancos", "agrupado por banco", "desglose por banco", "ranking de bancos", "top bancos"),
    "filial": ("por filial", "por filiales", "agrupado por filial", "desglose por filial", "ranking de filiales", "top filiales"),
    "account_number": ("por cuenta", "por cuentas", "agrupado por cuenta", "desglose por cuenta", "ranking de cuentas", "top cuentas"),
    "period": ("por periodo", "por periodos", "por mes", "por meses", "agrupado por periodo", "desglose por periodo"),
    "rule_code": ("por regla", "por reglas", "por rule_code", "desglose por regla"),
    "severity": ("por severidad", "por gravedad", "desglose por severidad", "desglose por gravedad"),
}


def _contains_any(question_norm: str, terms: tuple[str, ...]) -> bool:
    return any(term in question_norm for term in terms)


def _detect_group_by(question_norm: str) -> str | None:
    for group_by, aliases in GROUP_BY_ALIASES.items():
        if any(alias in question_norm for alias in aliases):
            return group_by
    return None


def _extract_search_text(question: str, question_norm: str) -> str | None:
    quoted = re.search(r"['\"]([^'\"]{3,80})['\"]", question)
    if quoted:
        return quoted.group(1).strip()
    for pattern in [r"(?:busca|buscar|contenga|contienen)\s+(.{3,80})", r"(?:descripcion|concepto|referencia)\s+(.{3,80})"]:
        match = re.search(pattern, question_norm)
        if match:
            value = match.group(1).strip(" .,:;?¿!")
            # Evita pasar toda la pregunta si no hay texto claro.
            value = re.sub(r"\b(en|de|del|por)\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\b.*$", "", value).strip()
            return value or None
    return None


class DeterministicParser:
    """Router deterministico acotado para rutas exactas de Bloque 1.

    Este parser no intenta entender todo. Solo toma rutas de alta confianza que
    pueden resolverse con SQL y plantillas. Lo ambiguo queda marcado para el
    router/LLM classifier de fases posteriores.
    """

    def parse(self, question: str, metadata: dict[str, Any] | None = None, parsed_filters: dict[str, Any] | None = None) -> RouteDecision:
        metadata = metadata or {}
        parsed = parsed_filters or parse_question_filters(question, metadata)
        question_norm = parsed.get("question_normalized") or normalize_text(question)
        filters = dict(parsed.get("filters") or {})
        entities = {
            "period": filters.get("period"),
            "periods": filters.get("periods") or parsed.get("periods") or [],
            "bank": filters.get("bank"),
            "filial": filters.get("filial"),
            "account_number": filters.get("account_number"),
        }
        filter_resolution = parsed.get("filter_resolution") or {}

        if _contains_any(question_norm, AVAILABLE_PERIOD_TERMS):
            return RouteDecision(
                intent=Intent.AVAILABLE_PERIODS,
                confidence=0.98,
                requires_sql=True,
                metric="periods",
                entities=entities,
                filters=filters,
                filter_resolution=filter_resolution,
            )

        has_count = _contains_any(question_norm, COUNT_TERMS)
        has_movements = _contains_any(question_norm, MOVEMENT_TERMS)
        has_incidents = _contains_any(question_norm, INCIDENT_TERMS)
        has_review = _contains_any(question_norm, REVIEW_TERMS) or ("top" in question_norm and "cuenta" in question_norm)
        group_by = _detect_group_by(question_norm)
        search_text = _extract_search_text(question, question_norm)
        if search_text:
            entities["search_text"] = search_text

        if has_incidents and group_by:
            return RouteDecision(
                intent=Intent.INCIDENT_BREAKDOWN,
                confidence=0.93,
                requires_sql=True,
                group_by=group_by,
                metric="incidents",
                entities=entities,
                filters=filters,
                filter_resolution=filter_resolution,
            )

        if has_movements and group_by:
            intent = Intent.MOVEMENT_BREAKDOWN
            if group_by == "bank":
                intent = Intent.BANK_RANKING if "top" in question_norm or "ranking" in question_norm else Intent.MOVEMENT_BREAKDOWN
            if group_by == "filial":
                intent = Intent.FILIAL_RANKING if "top" in question_norm or "ranking" in question_norm else Intent.MOVEMENT_BREAKDOWN
            return RouteDecision(
                intent=intent,
                confidence=0.93,
                requires_sql=True,
                group_by=group_by,
                metric="movements",
                entities=entities,
                filters=filters,
                filter_resolution=filter_resolution,
            )

        if has_review and ("cuenta" in question_norm or "cuentas" in question_norm or has_incidents):
            return RouteDecision(
                intent=Intent.REVIEW_CANDIDATES,
                confidence=0.90,
                requires_sql=True,
                metric="review_score",
                entities=entities,
                filters=filters,
                filter_resolution=filter_resolution,
            )

        if entities.get("account_number") and any(term in question_norm for term in ("perfil", "detalle", "detallame", "cuenta", "revisa")):
            return RouteDecision(
                intent=Intent.ACCOUNT_PROFILE,
                confidence=0.91,
                requires_sql=True,
                metric="account_profile",
                entities=entities,
                filters=filters,
                filter_resolution=filter_resolution,
            )

        if has_movements and search_text and _contains_any(question_norm, SEARCH_TERMS):
            return RouteDecision(
                intent=Intent.MOVEMENT_SEARCH,
                confidence=0.90,
                requires_sql=True,
                metric="movements",
                entities=entities,
                filters=filters,
                filter_resolution=filter_resolution,
            )

        if has_movements and _contains_any(question_norm, LIST_TERMS):
            return RouteDecision(
                intent=Intent.MOVEMENT_LIST,
                confidence=0.90,
                requires_sql=True,
                metric="movements",
                entities=entities,
                filters=filters,
                filter_resolution=filter_resolution,
            )

        if has_count and has_incidents:
            return RouteDecision(
                intent=Intent.INCIDENT_COUNT,
                confidence=0.94,
                requires_sql=True,
                metric="incidents",
                entities=entities,
                filters=filters,
                filter_resolution=filter_resolution,
            )

        if has_count and has_movements:
            return RouteDecision(
                intent=Intent.MOVEMENT_COUNT,
                confidence=0.94,
                requires_sql=True,
                metric="movements",
                entities=entities,
                filters=filters,
                filter_resolution=filter_resolution,
            )

        if _contains_any(question_norm, INSTITUTIONAL_TERMS):
            return RouteDecision(
                intent=Intent.INSTITUTIONAL_KNOWLEDGE,
                confidence=0.82,
                requires_sql=False,
                requires_memory=True,
                requires_llm_answer=True,
                task="institutional_synthesis",
                entities=entities,
                filters=filters,
                filter_resolution=filter_resolution,
                reason="institutional_keywords",
            )

        return RouteDecision(
            intent=Intent.SUMMARY,
            confidence=0.62,
            requires_sql=True,
            requires_llm_classifier=True,
            requires_llm_answer=True,
            metric="summary",
            entities=entities,
            filters=filters,
            filter_resolution=filter_resolution,
            task="analytic_answer",
            reason="no_high_confidence_direct_route",
        )
