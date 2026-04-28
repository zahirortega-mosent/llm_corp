from app.router.intent_schema import Intent
from app.router.router import IntentRouter
from app.utils.filters import parse_question_filters


METADATA = {"periods": ["2026-01-01", "2026-02-01"], "filiales": []}


def route(question: str):
    parsed = parse_question_filters(question, METADATA)
    return IntentRouter().route(question, metadata=METADATA, parsed_filters=parsed)


def test_movement_count_is_direct_sql():
    decision = route("cuantos movimientos hubo en enero 2026")
    assert decision.intent == Intent.MOVEMENT_COUNT
    assert decision.is_direct_sql
    assert decision.requires_llm_answer is False


def test_available_periods_is_direct_sql():
    decision = route("periodos disponibles")
    assert decision.intent == Intent.AVAILABLE_PERIODS
    assert decision.is_direct_sql


def test_movements_by_bank_is_breakdown():
    decision = route("movimientos por banco en enero 2026")
    assert decision.intent in {Intent.MOVEMENT_BREAKDOWN, Intent.BANK_RANKING}
    assert decision.group_by == "bank"
    assert decision.is_direct_sql


def test_review_candidates_is_direct_sql():
    decision = route("cuentas sugeridas a revisar en enero 2026")
    assert decision.intent == Intent.REVIEW_CANDIDATES
    assert decision.is_direct_sql


def test_bank_filter_word_does_not_force_group_by():
    decision = route("muestra movimientos del banco BANBAJIO en enero 2026")
    assert decision.intent == Intent.MOVEMENT_LIST
    assert decision.group_by is None
