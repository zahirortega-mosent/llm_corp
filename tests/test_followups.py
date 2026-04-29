from app.router.intent_schema import Intent
from app.services.context_resolver import ContextResolver
from app.utils.filters import parse_question_filters


METADATA = {"periods": ["2026-01-01", "2026-02-01"], "filiales": []}


def resolve(question: str, state: dict):
    parsed = parse_question_filters(question, METADATA)
    return ContextResolver().resolve(question, conversation_state=state, metadata=METADATA, parsed_filters=parsed)


def test_group_by_followup_inherits_period_and_changes_dimension():
    state = {
        "last_intent": "movement_breakdown",
        "last_filters": {"period": "2026-01-01"},
        "last_route": {"intent": "movement_breakdown", "metric": "movements", "group_by": "bank"},
        "last_result_refs": [],
    }
    resolved = resolve("y por filial?", state)
    assert resolved.inherited_previous_context is True
    assert resolved.filters["period"] == "2026-01-01"
    assert resolved.route_override.intent == Intent.MOVEMENT_BREAKDOWN
    assert resolved.route_override.group_by == "filial"
    assert resolved.route_override.requires_sql is True


def test_reference_followup_uses_first_previous_account():
    state = {
        "last_intent": "review_candidates",
        "last_filters": {"period": "2026-01-01"},
        "last_route": {"intent": "review_candidates", "metric": "review_score"},
        "last_result_refs": [
            {
                "index": 1,
                "bank": "BANBAJIO",
                "filial": "MOSENT NORTE",
                "account_number": "1234567890",
                "period": "2026-01-01",
            }
        ],
    }
    resolved = resolve("revisa la primera", state)
    assert resolved.route_override.intent == Intent.ACCOUNT_PROFILE
    assert resolved.filters["account_number"] == "1234567890"
    assert resolved.filters["bank"] == "BANBAJIO"
    assert resolved.filters["filial"] == "MOSENT NORTE"
    assert resolved.result_ref["index"] == 1


def test_month_followup_keeps_previous_route_and_uses_same_year():
    state = {
        "last_intent": "movement_count",
        "last_filters": {"period": "2026-01-01"},
        "last_route": {"intent": "movement_count", "metric": "movements"},
        "last_result_refs": [],
    }
    resolved = resolve("y febrero?", state)
    assert resolved.route_override.intent == Intent.MOVEMENT_COUNT
    assert resolved.filters["period"] == "2026-02-01"
    assert resolved.inherited_previous_context is True
