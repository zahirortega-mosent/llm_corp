from app.router.intent_schema import Intent
from app.router.router import IntentRouter


METADATA = {
    "periods": ["2026-01-01", "2026-02-01"],
    "banks": ["SANTANDER", "BANBAJIO"],
    "filiales": ["Guadalajara", "Puebla"],
}


def route(question: str):
    return IntentRouter().route(question, metadata=METADATA)


def test_word_banco_alone_does_not_force_breakdown():
    decision = route("banco")
    assert decision.intent == Intent.SUMMARY
    assert decision.clarification_needed is True
    assert not decision.is_direct_sql


def test_revisa_without_account_or_incidents_does_not_fetch_global_accounts():
    decision = route("revisa esto")
    assert decision.intent == Intent.SUMMARY
    assert decision.intent != Intent.REVIEW_CANDIDATES
    assert decision.clarification_needed is True


def test_process_question_with_bank_word_uses_institutional_route_not_sql_breakdown():
    decision = route("cual es el proceso por banco para autorizar la conciliacion")
    assert decision.intent == Intent.INSTITUTIONAL_KNOWLEDGE
    assert decision.requires_memory is True
    assert decision.requires_llm_answer is True
    assert not decision.is_direct_sql


def test_account_word_plus_authorization_is_not_account_profile_without_account_number():
    decision = route("como se autoriza una cuenta bancaria en el proceso interno")
    assert decision.intent == Intent.INSTITUTIONAL_KNOWLEDGE
    assert decision.intent != Intent.ACCOUNT_PROFILE
    assert not decision.is_direct_sql


def test_direct_sql_still_requires_metric_and_grouping_not_just_alias():
    decision = route("por filial")
    assert decision.intent == Intent.SUMMARY
    assert decision.clarification_needed is True
    assert not decision.is_direct_sql


def test_exact_movement_breakdown_stays_direct_sql():
    decision = route("movimientos por banco en enero 2026")
    assert decision.intent == Intent.MOVEMENT_BREAKDOWN
    assert decision.group_by == "bank"
    assert decision.is_direct_sql
