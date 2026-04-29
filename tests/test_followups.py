from app.services.context_resolver import ContextResolver


def test_followup_inherits_period_and_changes_group_by():
    state = {
        "last_filters": {"period": "2026-01-01"},
        "last_intent": "movement_breakdown",
        "last_route": {"intent": "movement_breakdown", "metric": "movements", "group_by": "bank"},
        "last_result_refs": [],
    }
    metadata = {"periods": ["2026-01-01", "2026-02-01"]}
    resolved = ContextResolver().resolve("y por filial?", state, metadata=metadata)
    assert resolved.inherited_previous_context is True
    assert resolved.filters["period"] == "2026-01-01"
    assert resolved.route_override.group_by == "filial"
