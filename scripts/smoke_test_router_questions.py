#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

from app.router.intent_schema import Intent
from app.router.router import IntentRouter


METADATA = {
    "periods": ["2026-01-01", "2026-02-01"],
    "banks": ["SANTANDER", "BANBAJIO"],
    "filiales": ["Guadalajara", "Puebla"],
}

CASES = [
    ("cuantos movimientos hubo en enero 2026", Intent.MOVEMENT_COUNT, True),
    ("movimientos por banco en enero 2026", Intent.MOVEMENT_BREAKDOWN, True),
    ("periodos disponibles", Intent.AVAILABLE_PERIODS, True),
    ("cuentas sugeridas a revisar en enero 2026", Intent.REVIEW_CANDIDATES, True),
    ("banco", Intent.SUMMARY, False),
    ("por filial", Intent.SUMMARY, False),
    ("revisa esto", Intent.SUMMARY, False),
    ("cual es el proceso por banco para autorizar la conciliacion", Intent.INSTITUTIONAL_KNOWLEDGE, False),
    ("como se autoriza una cuenta bancaria en el proceso interno", Intent.INSTITUTIONAL_KNOWLEDGE, False),
]


def main() -> int:
    router = IntentRouter()
    failures = []
    rows = []
    for question, expected_intent, expected_direct in CASES:
        decision = router.route(question, metadata=METADATA)
        ok = decision.intent == expected_intent and decision.is_direct_sql is expected_direct
        rows.append(
            {
                "question": question,
                "intent": decision.intent.value,
                "expected_intent": expected_intent.value,
                "is_direct_sql": decision.is_direct_sql,
                "expected_direct_sql": expected_direct,
                "confidence": decision.confidence,
                "clarification_needed": decision.clarification_needed,
                "ok": ok,
            }
        )
        if not ok:
            failures.append(rows[-1])
    print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    if failures:
        print("ERROR: hay rutas inesperadas", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
