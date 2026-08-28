"""CCF ±lag 拼接与领先滞后期。"""

from __future__ import annotations

import numpy as np

from app.evolution.leadlag import CcfLeadLagAnalyzer, two_way_ccf
from app.evolution.periods import consecutive_quarters
from tests.evolution.factories import series_from_counts


def test_two_way_ccf_concatenates_negative_and_positive_lags() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=24)
    y = rng.normal(size=24)
    max_lag = 6
    lags, values = two_way_ccf(x, y, max_lag)
    assert list(lags) == list(range(-max_lag, max_lag + 1))
    assert len(values) == 2 * max_lag + 1
    # lag 0 应等于普通相关系数
    expected0 = float(np.corrcoef(x, y)[0, 1])
    assert abs(values[max_lag] - expected0) < 0.05


def test_ccf_recovers_known_lead_of_three_periods() -> None:
    n = 20
    x = np.zeros(n)
    x[4:8] = np.array([0.2, 0.8, 0.9, 0.3])
    y = np.zeros(n)
    y[7:11] = x[4:8]  # y 落后 x 三期
    lags, values = two_way_ccf(x, y, max_lag=6)
    peak_lag_sm = int(lags[int(np.argmax(values))])
    lag_periods = -peak_lag_sm
    assert lag_periods == 3


def test_analyzer_reports_lag_three_on_shifted_observations() -> None:
    n = 20
    lead_rates = np.zeros(n)
    lead_rates[4:8] = np.array([0.15, 0.55, 0.60, 0.20])
    lag_rates = np.zeros(n)
    lag_rates[7:11] = lead_rates[4:8]
    totals = 1000
    leading = series_from_counts("cuda", [int(r * totals) for r in lead_rates], totals)
    lagging = series_from_counts("cuda", [int(r * totals) for r in lag_rates], totals)
    result = CcfLeadLagAnalyzer("github", "boss").analyze(leading, lagging)
    assert result is not None
    assert result.lag_periods == 3
    assert result.skill_id == "cuda"
    assert result.leading_source_id == "github"
    assert result.correlation > 0.5
    assert 0.0 <= result.p_value <= 1.0


def test_stackoverflow_is_excluded_as_leading_source() -> None:
    periods = consecutive_quarters("2020Q1", 12)
    leading = series_from_counts("x", [10] * 12, 100)
    lagging = series_from_counts("x", [10] * 12, 100)
    assert len(periods) == 12
    result = CcfLeadLagAnalyzer("stackoverflow", "boss").analyze(leading, lagging)
    assert result is None


def test_too_short_overlap_returns_none() -> None:
    leading = series_from_counts("x", [10, 11, 12], 100)
    lagging = series_from_counts("x", [10, 11, 12], 100)
    assert CcfLeadLagAnalyzer().analyze(leading, lagging) is None


def test_mixed_ontology_versions_are_not_compared() -> None:
    leading = series_from_counts("x", [10] * 10, 100, ontology_version="v0")
    lagging = series_from_counts("x", [10] * 10, 100, ontology_version="v1")
    assert CcfLeadLagAnalyzer().analyze(leading, lagging) is None
