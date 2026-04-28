from app.router.intent_schema import Intent, RouteDecision
from app.services.answer_service import _build_chat_response


ROUTE = RouteDecision(
    intent=Intent.MOVEMENT_COUNT,
    confidence=0.94,
    requires_sql=True,
    metric="movements",
)
PARSED = {
    "filter_resolution": {
        "period_source": "explicit_user_text",
        "period_confidence": 1.0,
        "ambiguous": False,
    }
}
METADATA = {
    "periods": ["2026-01-01", "2026-02-01"],
    "accounts_sample": ["SHOULD_NOT_BE_PUBLIC"],
}


def build(debug: bool):
    return _build_chat_response(
        question="cuantos movimientos hubo en enero 2026",
        conversation_id="test-cleanup",
        filters={"period": "2026-01-01", "bank": None},
        parsed=PARSED,
        route=ROUTE,
        answer="En enero 2026 hay 40,546 movimientos registrados.",
        metadata=METADATA,
        evidence={"summary": {"movements": 40546}},
        tools_used=["get_summary"],
        used_llm=False,
        model_used=None,
        used_fallback=False,
        web_used=False,
        web_allowed=False,
        web_query=None,
        debug=debug,
        context={"metadata": METADATA, "evidence": {"summary": {"movements": 40546}}},
    )


def test_context_hidden_by_default_and_metadata_is_small():
    payload = build(debug=False)
    assert "context" not in payload
    assert payload["metadata"]["available_periods"] == ["2026-01", "2026-02"]
    assert payload["metadata"]["tools_used"] == ["get_summary"]
    assert "accounts_sample" not in payload["metadata"]
    assert "SHOULD_NOT_BE_PUBLIC" not in str(payload["metadata"])


def test_context_is_available_only_with_debug_true():
    payload = build(debug=True)
    assert "context" in payload
    assert payload["context"]["metadata"]["accounts_sample"] == ["SHOULD_NOT_BE_PUBLIC"]
