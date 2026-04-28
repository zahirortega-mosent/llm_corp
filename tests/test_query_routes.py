from app.router.intent_schema import Intent, RouteDecision
from app.services.answer_composer import AnswerComposer
from app.services.query_service import QueryService


def test_query_service_exposes_block_1_methods_without_instantiating_db():
    required = [
        "get_available_periods_summary",
        "get_movements_breakdown",
        "get_incidents_breakdown",
        "get_review_candidates",
        "get_account_profile",
        "search_movements_text",
    ]
    for name in required:
        assert hasattr(QueryService, name), name


def test_composer_zero_for_unavailable_period_includes_available_periods():
    route = RouteDecision(intent=Intent.MOVEMENT_COUNT, confidence=0.94, requires_sql=True)
    answer = AnswerComposer().compose_direct(
        question="cuantos movimientos hubo en enero 2025",
        route=route,
        filters={"period": "2025-01-01"},
        evidence={"summary": {"movements": 0}},
        metadata={"periods": ["2026-01-01", "2026-02-01"]},
    )
    assert "0 movimientos" in answer
    assert "2026-01" in answer
    assert "2026-02" in answer
