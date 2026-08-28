from app.evolution.periods import consecutive_quarters, parse_period, period_to_date


def test_period_helpers() -> None:
    assert parse_period("2026Q3") == (2026, 3)
    assert period_to_date("2026Q3").month == 7
    assert consecutive_quarters("2023Q4", 3) == ["2023Q4", "2024Q1", "2024Q2"]
