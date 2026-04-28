from app.router.intent_schema import Intent
from app.router.router import IntentRouter


METADATA = {
    "periods": ["2026-01-01", "2026-02-01"],
    "banks": ["BANBAJIO"],
    "filiales": ["MOSENT NORTE"],
}


def route(question: str):
    return IntentRouter().route(question, metadata=METADATA)


def test_movement_count_direct_sql_no_llm():
    decision = route("cuantos movimientos hubo en enero 2026")
    assert decision.intent == Intent.MOVEMENT_COUNT
    assert decision.requires_sql is True
    assert decision.requires_llm_answer is False
    assert decision.confidence >= 0.85


def test_available_periods_direct_sql():
    decision = route("que periodos disponibles hay")
    assert decision.intent == Intent.AVAILABLE_PERIODS
    assert decision.is_direct_sql


def test_movements_breakdown_by_bank():
    decision = route("movimientos por banco en enero 2026")
    assert decision.intent == Intent.MOVEMENT_BREAKDOWN
    assert decision.group_by == "bank"
    assert decision.is_direct_sql


def test_review_candidates_direct_sql():
    decision = route("cuentas sugeridas a revisar en enero 2026")
    assert decision.intent == Intent.REVIEW_CANDIDATES
    assert decision.is_direct_sql


def test_institutional_question_not_forced_to_sql_direct():
    decision = route("cual es el proceso de autorizacion de conciliacion")
    assert decision.intent == Intent.INSTITUTIONAL_KNOWLEDGE
    assert decision.requires_memory is True
    assert decision.requires_llm_answer is True
