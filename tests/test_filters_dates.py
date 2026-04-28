from app.utils.filters import parse_question_filters


METADATA = {
    "periods": ["2026-01-01", "2026-02-01"],
    "banks": [],
    "filiales": [],
}


def test_explicit_enero_2025_is_not_overwritten_by_available_year():
    parsed = parse_question_filters("cuantos movimientos hubo en enero 2025", METADATA)
    assert parsed["period"] == "2025-01-01"
    assert parsed["filter_resolution"]["period_source"] == "explicit_user_text"
    assert parsed["filter_resolution"]["period_available"] is False


def test_explicit_enero_2026():
    parsed = parse_question_filters("cuantos movimientos hubo en enero 2026", METADATA)
    assert parsed["period"] == "2026-01-01"
    assert parsed["filter_resolution"]["period_available"] is True


def test_explicit_octubre_2025():
    parsed = parse_question_filters("cuantos movimientos hubo en octubre 2025", METADATA)
    assert parsed["period"] == "2025-10-01"
    assert parsed["filter_resolution"]["period_source"] == "explicit_user_text"


def test_month_without_year_uses_single_available_month():
    parsed = parse_question_filters("cuantos movimientos hubo en febrero", METADATA)
    assert parsed["period"] == "2026-02-01"
    assert parsed["filter_resolution"]["period_source"] == "month_inferred_from_single_available_year"


def test_month_without_year_ambiguous_when_multiple_years_available():
    metadata = {"periods": ["2025-01-01", "2026-01-01"], "banks": [], "filiales": []}
    parsed = parse_question_filters("cuantos movimientos hubo en enero", metadata)
    assert parsed["period"] is None
    assert parsed["filter_resolution"]["ambiguous"] is True
    assert parsed["filter_resolution"]["clarification_needed"] is True


def test_enero_y_febrero_2026_period_list():
    parsed = parse_question_filters("movimientos enero y febrero 2026", METADATA)
    assert parsed["periods"] == ["2026-01-01", "2026-02-01"]
