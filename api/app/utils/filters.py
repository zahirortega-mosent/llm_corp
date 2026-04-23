import re
from datetime import date
from typing import Any, Dict

from unidecode import unidecode


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


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", unidecode(value).lower()).strip()


def month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def normalize_period(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}", cleaned):
        return f"{cleaned}-01"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        return cleaned[:7] + "-01"
    return None


def parse_question_filters(question: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    question_norm = normalize_text(question)
    periods = metadata.get("periods", [])
    default_year = None
    if periods:
        years = sorted({int(p[:4]) for p in periods if len(p) >= 7})
        if len(years) == 1:
            default_year = years[0]
        elif years:
            default_year = years[-1]

    detected_period = None

    explicit_period = re.search(r"(20\d{2})[-/](\d{2})", question_norm)
    if explicit_period:
        detected_period = f"{explicit_period.group(1)}-{explicit_period.group(2)}-01"
    else:
        for month_name, month_num in MONTHS.items():
            if month_name in question_norm:
                year_match = re.search(rf"{month_name}\s+de\s+(20\d{{2}})", question_norm)
                year = int(year_match.group(1)) if year_match else default_year
                if year:
                    detected_period = f"{year:04d}-{month_num:02d}-01"
                break

    if "este mes" in question_norm and periods:
        detected_period = sorted(periods)[-1]

    detected_bank = None
    for canonical, aliases in BANK_ALIASES.items():
        if any(alias in question_norm for alias in aliases):
            detected_bank = canonical
            break

    detected_filial = None
    for filial in metadata.get("filiales", []):
        if normalize_text(filial) and normalize_text(filial) in question_norm:
            detected_filial = filial
            break

    account_match = re.search(r"\b(\d{6,18})\b", question)
    detected_account = account_match.group(1) if account_match else None

    intents = set()
    if any(term in question_norm for term in ["incidencia", "incidencias", "revision", "revisar", "error", "anomalo", "anomal", "no cuadra", "cuadrar", "descuadre"]):
        intents.add("incidents")
    if any(term in question_norm for term in ["archivo", "origen", "hash", "nextcloud"]):
        intents.add("files")
    if any(term in question_norm for term in ["saldo", "saldos", "deposito", "retiro", "monto", "movimiento", "movimientos"]):
        intents.add("movements")
    if any(term in question_norm for term in ["regla", "reglas", "contable", "niif", "nif", "ifrs", "ias"]):
        intents.add("rules")
    if any(term in question_norm for term in ["conciliador", "consolidador", "segun el sistema", "segun conciliador", "cotejar", "comparar", "segun codigo"]):
        intents.add("knowledge")
    if any(term in question_norm for term in ["primero", "prioridad", "urgente"]):
        intents.add("priority")
    if not intents:
        intents.add("summary")

    return {
        "period": detected_period,
        "bank": detected_bank,
        "filial": detected_filial,
        "account_number": detected_account,
        "intents": sorted(intents),
        "question_normalized": question_norm,
    }
