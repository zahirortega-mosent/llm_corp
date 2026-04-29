from app.router.intent_schema import Intent
from app.router.router import IntentRouter


def test_breakdown_by_bank_is_direct_sql():
    metadata = {"periods": ["2026-01-01"], "banks": [], "filiales": [], "accounts_sample": []}
    route = IntentRouter().route("movimientos por banco en enero 2026", metadata=metadata)
    assert route.intent in {Intent.MOVEMENT_BREAKDOWN, Intent.BANK_RANKING}
    assert route.group_by == "bank"
    assert route.requires_sql is True
    assert route.requires_memory is False
