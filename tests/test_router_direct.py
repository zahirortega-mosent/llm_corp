from app.router.intent_schema import Intent
from app.router.router import IntentRouter
from app.utils.filters import parse_question_filters


def test_count_question_uses_direct_sql_without_memory():
    metadata = {"periods": ["2026-01-01", "2026-02-01"], "banks": [], "filiales": [], "accounts_sample": []}
    question = "cuantos movimientos hubo en enero 2026"
    parsed = parse_question_filters(question, metadata)
    route = IntentRouter().route(question, metadata=metadata, parsed_filters=parsed)

    assert route.intent == Intent.MOVEMENT_COUNT
    assert route.requires_sql is True
    assert route.requires_memory is False
    assert route.requires_llm_answer is False


def test_process_question_activates_institutional_memory():
    metadata = {"periods": ["2026-01-01"], "banks": [], "filiales": [], "accounts_sample": []}
    question = "cual es el proceso para escalar una incidencia de conciliacion"
    route = IntentRouter().route(question, metadata=metadata)

    assert route.intent == Intent.INSTITUTIONAL_KNOWLEDGE
    assert route.requires_memory is True
    assert route.requires_sql is False
