from __future__ import annotations

from datetime import date

import pytest

from app.graph.periods import parse_period, period_end


def test_parse_period() -> None:
    assert parse_period("2026Q1") == (2026, 1)
    assert parse_period("2025Q4") == (2025, 4)


def test_parse_period_rejects_bad() -> None:
    with pytest.raises(ValueError, match="YYYYQn"):
        parse_period("2026-Q1")
    with pytest.raises(ValueError, match="YYYYQn"):
        parse_period("2026Q5")


def test_period_end() -> None:
    assert period_end("2026Q1") == date(2026, 3, 31)
    assert period_end("2026Q2") == date(2026, 6, 30)
    assert period_end("2026Q4") == date(2026, 12, 31)
