from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict

try:
    from unidecode import unidecode
except Exception:
    def unidecode(value: str) -> str:
        return value


BANK_ALIASES = {
    "SANTANDER": ["santander"],
    "BANAMEX": ["banamex", "citibanamex", "citi"],
    "BANBAJIO": ["banbajio", "ban bajio", "bajio"],
    "BANORTE": ["banorte"],
    "BANREGIO": ["banregio"],
    "BBVA": ["bbva", "bancomer"],
    "SCOTIABANK": ["scotia", "scotiabank"],
    "SCOTIABANK INVERT": ["scotiabank invert", "scotia invert"],
}

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

SPANISH_MONTH_BY_NUMBER = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", unidecode(value).lower()).strip()


def month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def normalize_period(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}", cleaned):
        return f"{cleaned}-01"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        return cleaned[:7] + "-01"
    return None


def _available_periods(metadata: Dict[str, Any]) -> list[str]:
    raw_periods = metadata.get("periods", []) or []
    normalized: list[str] = []
    for item in raw_periods:
        period = normalize_period(str(item))
        if period:
            normalized.append(period)
    return sorted(set(normalized))


def _period_exists(period: str | None, periods: list[str]) -> bool:
    if not period:
        return False
    return normalize_period(period) in set(periods)


def _periods_for_month(month: int, periods: list[str]) -> list[str]:
    month_part = f"-{month:02d}-"
    return [period for period in periods if month_part in period]


def _parse_explicit_numeric_period(question_norm: str) -> str | None:
    numeric = re.search(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])\b", question_norm)
    if numeric:
        return f"{int(numeric.group(1)):04d}-{int(numeric.group(2)):02d}-01"
    return None


def _parse_month_year_period(question_norm: str) -> tuple[str | None, dict[str, Any]]:
    for month_name, month_num in MONTHS.items():
        # enero 2026, enero de 2026, en enero del 2026
        pattern = "\\b" + re.escape(month_name) + "\\b(?:\\s+(?:de|del))?\\s+(20\\d{2})\\b"
        match = re.search(pattern, question_norm)
        if match:
            year = int(match.group(1))
            return f"{year:04d}-{month_num:02d}-01", {
                "period_source": "explicit_user_text",
                "period_confidence": 1.0,
                "month_name": month_name,
                "month_number": month_num,
                "year": year,
                "ambiguous": False,
            }
    return None, {}


def _parse_single_month_without_year(question_norm: str, periods: list[str]) -> tuple[str | None, dict[str, Any]]:
    for month_name, month_num in MONTHS.items():
        if re.search("\\b" + re.escape(month_name) + "\\b", question_norm):
            candidates = _periods_for_month(month_num, periods)
            if len(candidates) == 1:
                return candidates[0], {
                    "period_source": "month_inferred_from_single_available_year",
                    "period_confidence": 0.8,
                    "month_name": month_name,
                    "month_number": month_num,
                    "ambiguous": False,
                    "inferred_from_available_periods": True,
                }
            if len(candidates) > 1:
                return None, {
                    "period_source": "month_without_year",
                    "period_confidence": 0.4,
                    "month_name": month_name,
                    "month_number": month_num,
                    "ambiguous": True,
                    "candidate_periods": candidates,
                    "clarification_needed": True,
                }
            return None, {
                "period_source": "month_without_available_period",
                "period_confidence": 0.5,
                "month_name": month_name,
                "month_number": month_num,
                "ambiguous": False,
                "available_period_not_found": True,
            }
    return None, {}


def _parse_periods_list(question_norm: str, periods: list[str]) -> list[str]:
    # Caso acotado de Bloque 1: "enero y febrero 2026".
    year_match = re.search(r"\b(20\d{2})\b", question_norm)
    if not year_match:
        return []
    year = int(year_match.group(1))
    month_hits = [month_num for month_name, month_num in MONTHS.items() if re.search("\\b" + re.escape(month_name) + "\\b", question_norm)]
    if len(month_hits) < 2:
        return []
    result = [f"{year:04d}-{month_num:02d}-01" for month_num in sorted(set(month_hits))]
    return result


def _parse_quarter_periods(question_norm: str) -> list[str]:
    match = re.search(r"\bq([1-4])\s*(20\d{2})\b|\b(20\d{2})\s*q([1-4])\b", question_norm)
    if not match:
        return []
    quarter = int(match.group(1) or match.group(4))
    year = int(match.group(2) or match.group(3))
    start_month = ((quarter - 1) * 3) + 1
    return [f"{year:04d}-{month:02d}-01" for month in range(start_month, start_month + 3)]


def parse_question_filters(question: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    question_norm = normalize_text(question)
    periods = _available_periods(metadata)
    available_period_labels = [period[:7] for period in periods]

    detected_period: str | None = None
    resolution: dict[str, Any] = {
        "period_source": None,
        "period_confidence": 0.0,
        "ambiguous": False,
        "available_periods_considered": available_period_labels,
        "period_available": None,
        "clarification_needed": False,
    }

    period_list = _parse_quarter_periods(question_norm) or _parse_periods_list(question_norm, periods)

    numeric_period = _parse_explicit_numeric_period(question_norm)
    if numeric_period:
        detected_period = numeric_period
        resolution.update({
            "period_source": "explicit_user_text",
            "period_confidence": 1.0,
            "ambiguous": False,
        })
    else:
        month_year_period, month_year_resolution = _parse_month_year_period(question_norm)
        if month_year_period:
            detected_period = month_year_period
            resolution.update(month_year_resolution)
        else:
            month_period, month_resolution = _parse_single_month_without_year(question_norm, periods)
            if month_resolution:
                detected_period = month_period
                resolution.update(month_resolution)

    if "este mes" in question_norm and periods:
        detected_period = periods[-1]
        resolution.update({
            "period_source": "relative_latest_available_period",
            "period_confidence": 0.75,
            "ambiguous": False,
            "relative_expression": "este mes",
        })

    if detected_period:
        detected_period = normalize_period(detected_period)
        resolution["period_available"] = _period_exists(detected_period, periods)
    elif period_list:
        resolution.update({
            "period_source": "explicit_period_list",
            "period_confidence": 1.0,
            "ambiguous": False,
            "period_available": all(_period_exists(period, periods) for period in period_list) if periods else None,
        })

    detected_bank = None
    for canonical, aliases in BANK_ALIASES.items():
        if any(alias in question_norm for alias in aliases):
            detected_bank = canonical
            break

    detected_filial = None
    for filial in metadata.get("filiales", []) or []:
        filial_norm = normalize_text(filial)
        if filial_norm and filial_norm in question_norm:
            detected_filial = filial
            break

    account_match = re.search(r"\b(\d{6,18})\b", question)
    detected_account = account_match.group(1) if account_match else None

    intents = set()
    if any(term in question_norm for term in ["incidencia", "incidencias", "revision", "revisar", "error", "anomalo", "anomal", "no cuadra", "cuadrar", "descuadre"]):
        intents.add("incidents")
    if any(term in question_norm for term in ["archivo", "origen", "hash", "nextcloud"]):
        intents.add("files")
    if any(term in question_norm for term in ["saldo", "saldos", "deposito", "depositos", "retiro", "retiros", "monto", "movimiento", "movimientos"]):
        intents.add("movements")
    if any(term in question_norm for term in ["regla", "reglas", "contable", "niif", "nif", "ifrs", "ias"]):
        intents.add("rules")
    if any(term in question_norm for term in ["conciliador", "consolidador", "segun el sistema", "segun conciliador", "cotejar", "comparar", "segun codigo"]):
        intents.add("knowledge")
    if any(term in question_norm for term in ["primero", "primer", "primera", "prioridad", "urgente", "detallame", "detalle", "desglosa", "desglose", "top", "ranking"]):
        intents.add("priority")
    if not intents:
        intents.add("summary")

    filters = {
        "period": detected_period,
        "bank": detected_bank,
        "filial": detected_filial,
        "account_number": detected_account,
    }
    if period_list:
        filters["periods"] = period_list

    return {
        "period": detected_period,
        "periods": period_list,
        "bank": detected_bank,
        "filial": detected_filial,
        "account_number": detected_account,
        "filters": filters,
        "filter_resolution": resolution,
        "intents": sorted(intents),
        "question_normalized": question_norm,
    }
