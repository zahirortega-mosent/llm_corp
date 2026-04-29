from app.utils.filters import parse_question_filters


def test_explicit_year_is_respected():
    metadata = {"periods": ["2026-01-01", "2026-02-01"]}
    parsed = parse_question_filters("cuantos movimientos hubo en enero 2025", metadata)
    assert parsed["filters"]["period"] == "2025-01-01"
    assert parsed["filter_resolution"]["period_source"] == "explicit_user_text"


def test_month_without_year_uses_single_available_period():
    metadata = {"periods": ["2026-01-01", "2026-02-01"]}
    parsed = parse_question_filters("cuantos movimientos hubo en enero", metadata)
    assert parsed["filters"]["period"] == "2026-01-01"
    assert parsed["filter_resolution"]["inferred_from_available_periods"] is True
