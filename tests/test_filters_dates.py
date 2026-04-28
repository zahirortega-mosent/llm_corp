from app.utils.filters import parse_question_filters


METADATA = {"periods": ["2026-01-01", "2026-02-01"]}


def test_explicit_month_year_respects_year_2025():
    parsed = parse_question_filters("cuantos movimientos hubo en enero 2025", METADATA)
    assert parsed["filters"]["period"] == "2025-01-01"
    assert parsed["filter_resolution"]["period_source"] == "explicit_user_text"
    assert parsed["filter_resolution"]["period_available"] is False


def test_explicit_month_year_respects_year_2026():
    parsed = parse_question_filters("cuantos movimientos hubo en enero 2026", METADATA)
    assert parsed["filters"]["period"] == "2026-01-01"
    assert parsed["filter_resolution"]["period_available"] is True


def test_explicit_october_2025():
    parsed = parse_question_filters("cuantos movimientos hubo en octubre 2025", METADATA)
    assert parsed["filters"]["period"] == "2025-10-01"
    assert parsed["filter_resolution"]["period_source"] == "explicit_user_text"


def test_month_without_year_infers_only_candidate():
    parsed = parse_question_filters("cuantos movimientos hubo en enero", METADATA)
    assert parsed["filters"]["period"] == "2026-01-01"
    assert parsed["filter_resolution"]["period_source"] == "month_inferred_from_single_available_year"


def test_month_without_year_requires_clarification_when_ambiguous():
    metadata = {"periods": ["2025-01-01", "2026-01-01"]}
    parsed = parse_question_filters("cuantos movimientos hubo en enero", metadata)
    assert parsed["filters"]["period"] is None
    assert parsed["filter_resolution"]["clarification_needed"] is True
    assert parsed["filter_resolution"]["candidate_period_labels"] == ["2025-01", "2026-01"]


def test_month_without_available_period_does_not_infer_current_year():
    parsed = parse_question_filters("cuantos movimientos hubo en octubre", METADATA)
    assert parsed["filters"]["period"] is None
    assert parsed["filter_resolution"]["available_period_not_found"] is True


def test_month_list_same_year():
    parsed = parse_question_filters("movimientos de enero y febrero 2026", METADATA)
    assert parsed["filters"].get("period") is None
    assert parsed["filters"]["periods"] == ["2026-01-01", "2026-02-01"]
    assert parsed["filter_resolution"]["period_source"] == "explicit_period_list"


def test_q1_2026_period_list():
    parsed = parse_question_filters("movimientos Q1 2026", METADATA)
    assert parsed["filters"]["periods"] == ["2026-01-01", "2026-02-01", "2026-03-01"]
