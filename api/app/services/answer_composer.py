from __future__ import annotations

from typing import Any

from app.router.intent_schema import Intent, RouteDecision

SPANISH_MONTHS = {
    "01": "enero",
    "02": "febrero",
    "03": "marzo",
    "04": "abril",
    "05": "mayo",
    "06": "junio",
    "07": "julio",
    "08": "agosto",
    "09": "septiembre",
    "10": "octubre",
    "11": "noviembre",
    "12": "diciembre",
}

GROUP_LABELS = {
    "bank": "banco",
    "filial": "filial",
    "account_number": "cuenta",
    "period": "periodo",
    "rule_code": "regla",
    "severity": "severidad",
}


def money(value: Any) -> str:
    try:
        return f"${float(value or 0):,.2f}"
    except Exception:
        return "$0.00"


def integer(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def period_label(period: str | None) -> str:
    if not period:
        return "el periodo solicitado"
    value = str(period)
    if len(value) >= 7 and value[4] == "-":
        month = SPANISH_MONTHS.get(value[5:7], value[5:7])
        return f"{month} {value[:4]}"
    return value


def available_periods_text(metadata: dict[str, Any] | None) -> str:
    metadata = metadata or {}
    periods = metadata.get("periods") or metadata.get("available_periods") or []
    labels = []
    for item in periods:
        value = str(item)
        labels.append(value[:7] if len(value) >= 7 else value)
    labels = sorted(set(labels))
    if not labels:
        return "no hay periodos disponibles registrados"
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " y " + labels[-1]


def _top_lines(rows: list[dict[str, Any]], value_key: str, group_by: str | None, limit: int = 8) -> list[str]:
    if not rows:
        return []
    label = GROUP_LABELS.get(group_by or "", group_by or "grupo")
    lines = []
    for idx, row in enumerate(rows[:limit], start=1):
        name = row.get(group_by or "") or row.get("group_value") or "sin dato"
        total = integer(row.get(value_key))
        extra = []
        if row.get("total_deposits") is not None:
            extra.append(f"depositos {money(row.get('total_deposits'))}")
        if row.get("total_withdrawals") is not None:
            extra.append(f"retiros {money(row.get('total_withdrawals'))}")
        suffix = f" ({'; '.join(extra)})" if extra else ""
        lines.append(f"{idx}. {label} {name}: {total:,}{suffix}")
    return lines


class AnswerComposer:
    """Convierte evidencia autorizada en respuestas de Bloque 1.

    No consulta la base, no decide permisos y no llama al LLM. Solo formatea
    evidencia que ya fue recuperada por QueryService.
    """

    def compose_direct(
        self,
        question: str,
        route: RouteDecision,
        filters: dict[str, Any],
        evidence: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        intent = route.intent
        if intent == Intent.AVAILABLE_PERIODS:
            return self.available_periods(evidence, metadata)
        if intent == Intent.MOVEMENT_COUNT:
            return self.movement_count(filters, evidence, metadata)
        if intent == Intent.INCIDENT_COUNT:
            return self.incident_count(filters, evidence, metadata)
        if intent in {Intent.MOVEMENT_BREAKDOWN, Intent.BANK_RANKING, Intent.FILIAL_RANKING}:
            return self.movement_breakdown(filters, evidence, metadata, route.group_by)
        if intent == Intent.INCIDENT_BREAKDOWN:
            return self.incident_breakdown(filters, evidence, metadata, route.group_by)
        if intent == Intent.MOVEMENT_LIST:
            return self.movement_list(filters, evidence, metadata)
        if intent == Intent.MOVEMENT_SEARCH:
            return self.movement_search(filters, evidence, metadata, route.entities.get("search_text"))
        if intent == Intent.REVIEW_CANDIDATES:
            return self.review_candidates(filters, evidence, metadata)
        if intent == Intent.ACCOUNT_PROFILE:
            return self.account_profile(filters, evidence, metadata)
        return self.summary(filters, evidence, metadata)

    def available_periods(self, evidence: dict[str, Any], metadata: dict[str, Any] | None) -> str:
        periods = evidence.get("periods") or (metadata or {}).get("periods") or []
        text = available_periods_text({"periods": periods})
        return f"Los periodos disponibles actualmente son {text}."

    def _period_unavailable_suffix(self, filters: dict[str, Any], metadata: dict[str, Any] | None) -> str:
        period = filters.get("period")
        if not period:
            return ""
        available = {str(item)[:7] for item in (metadata or {}).get("periods", [])}
        if str(period)[:7] not in available:
            return f" Los periodos disponibles actualmente son {available_periods_text(metadata)}."
        return ""

    def movement_count(self, filters: dict[str, Any], evidence: dict[str, Any], metadata: dict[str, Any] | None) -> str:
        summary = evidence.get("summary") or evidence
        count = integer(summary.get("movements"))
        period = period_label(filters.get("period"))
        suffix = self._period_unavailable_suffix(filters, metadata)
        return f"En {period} hay {count:,} movimientos registrados en los datos cargados.{suffix}"

    def incident_count(self, filters: dict[str, Any], evidence: dict[str, Any], metadata: dict[str, Any] | None) -> str:
        summary = evidence.get("summary") or evidence
        count = integer(summary.get("incidents"))
        period = period_label(filters.get("period"))
        suffix = self._period_unavailable_suffix(filters, metadata)
        return f"En {period} hay {count:,} incidencias registradas en los datos cargados.{suffix}"

    def movement_breakdown(self, filters: dict[str, Any], evidence: dict[str, Any], metadata: dict[str, Any] | None, group_by: str | None) -> str:
        rows = evidence.get("rows") or []
        label = GROUP_LABELS.get(group_by or "", group_by or "dimension")
        period = period_label(filters.get("period"))
        if not rows:
            return f"No encontre movimientos para desglosar por {label} en {period}.{self._period_unavailable_suffix(filters, metadata)}"
        lines = _top_lines(rows, "movements", group_by)
        return f"Movimientos por {label} en {period}:\n" + "\n".join(lines)

    def incident_breakdown(self, filters: dict[str, Any], evidence: dict[str, Any], metadata: dict[str, Any] | None, group_by: str | None) -> str:
        rows = evidence.get("rows") or []
        label = GROUP_LABELS.get(group_by or "", group_by or "dimension")
        period = period_label(filters.get("period"))
        if not rows:
            return f"No encontre incidencias para desglosar por {label} en {period}.{self._period_unavailable_suffix(filters, metadata)}"
        lines = _top_lines(rows, "incidents", group_by)
        return f"Incidencias por {label} en {period}:\n" + "\n".join(lines)

    def movement_list(self, filters: dict[str, Any], evidence: dict[str, Any], metadata: dict[str, Any] | None) -> str:
        rows = evidence.get("rows") or []
        period = period_label(filters.get("period"))
        if not rows:
            return f"No encontre movimientos para listar en {period}.{self._period_unavailable_suffix(filters, metadata)}"
        lines = []
        for idx, row in enumerate(rows[:10], start=1):
            amount = row.get("amount")
            if amount is None:
                amount = float(row.get("deposit") or 0) - float(row.get("withdrawal") or 0)
            lines.append(
                f"{idx}. {row.get('movement_date') or 'sin fecha'} | {row.get('bank') or 'sin banco'} | "
                f"{row.get('filial') or 'sin filial'} | cuenta {row.get('account_number') or 'sin cuenta'} | "
                f"{money(amount)} | {row.get('description') or row.get('concept') or 'sin descripcion'}"
            )
        return f"Movimientos encontrados en {period}:\n" + "\n".join(lines)

    def movement_search(self, filters: dict[str, Any], evidence: dict[str, Any], metadata: dict[str, Any] | None, search_text: str | None) -> str:
        rows = evidence.get("rows") or []
        period = period_label(filters.get("period"))
        term = f" con texto '{search_text}'" if search_text else ""
        if not rows:
            return f"No encontre movimientos{term} en {period}.{self._period_unavailable_suffix(filters, metadata)}"
        return self.movement_list(filters, evidence, metadata)

    def review_candidates(self, filters: dict[str, Any], evidence: dict[str, Any], metadata: dict[str, Any] | None) -> str:
        rows = evidence.get("rows") or []
        period = period_label(filters.get("period"))
        if not rows:
            return f"No encontre cuentas candidatas para revisar en {period}.{self._period_unavailable_suffix(filters, metadata)}"
        lines = []
        for idx, row in enumerate(rows[:10], start=1):
            lines.append(
                f"{idx}. Cuenta {row.get('account_number') or 'sin cuenta'} | {row.get('bank') or 'sin banco'} | "
                f"{row.get('filial') or 'sin filial'} | score {integer(row.get('review_score')):,} | "
                f"incidencias {integer(row.get('incidents')):,} (criticas {integer(row.get('critical_incidents')):,}, altas {integer(row.get('high_incidents')):,}) | "
                f"movimientos no conciliados {integer(row.get('unreconciled_movements')):,} | monto en riesgo {money(row.get('amount_at_risk'))}"
            )
        return f"Cuentas sugeridas a revisar en {period}, calculadas por score deterministico:\n" + "\n".join(lines)

    def account_profile(self, filters: dict[str, Any], evidence: dict[str, Any], metadata: dict[str, Any] | None) -> str:
        profile = evidence.get("profile") or {}
        movements = evidence.get("recent_movements") or []
        incidents = evidence.get("incidents") or []
        account = filters.get("account_number") or profile.get("account_number") or "la cuenta solicitada"
        if not profile:
            return f"No encontre perfil para {account}.{self._period_unavailable_suffix(filters, metadata)}"
        lines = [
            f"Perfil de cuenta {account}:",
            f"Banco: {profile.get('bank') or 'sin dato'}; filial: {profile.get('filial') or 'sin dato'}.",
            f"Periodos con datos: {profile.get('periods') or 'sin dato'}.",
            f"Movimientos: {integer(profile.get('movements')):,}; incidencias: {integer(profile.get('incidents')):,}.",
            f"Depositos: {money(profile.get('total_deposits'))}; retiros: {money(profile.get('total_withdrawals'))}; monto en riesgo: {money(profile.get('amount_at_risk'))}.",
        ]
        if incidents:
            top = "; ".join(f"{item.get('rule_code')}: {integer(item.get('total'))}" for item in incidents[:5])
            lines.append(f"Incidencias principales: {top}.")
        if movements:
            lines.append(f"Movimiento reciente destacado: {movements[0].get('movement_date')} | {money(movements[0].get('amount'))} | {movements[0].get('description') or movements[0].get('concept') or 'sin descripcion'}.")
        return "\n".join(lines)

    def summary(self, filters: dict[str, Any], evidence: dict[str, Any], metadata: dict[str, Any] | None) -> str:
        summary = evidence.get("summary") or evidence
        period = period_label(filters.get("period"))
        return (
            f"Resumen de {period}: {integer(summary.get('movements')):,} movimientos, "
            f"{integer(summary.get('incidents')):,} incidencias, "
            f"depositos {money(summary.get('total_deposits'))} y retiros {money(summary.get('total_withdrawals'))}."
        )
