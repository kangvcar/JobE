"""Kleinberg 突增检测与 Mann-Kendall。"""

from __future__ import annotations

from app.evolution.burst import KleinbergBurstDetector, classify_skill, trend_test
from app.evolution.periods import consecutive_quarters
from tests.evolution.factories import series_from_counts


def test_kleinberg_detects_burst_in_periods_8_to_11() -> None:
    """第 8–11 期占比从 5% 抬到 40%，应检出覆盖该区间的突增。"""
    counts = [25] * 8 + [200] * 4 + [25] * 8
    series = series_from_counts("pytorch", counts, totals=500)
    bursts = KleinbergBurstDetector(source_id="boss").detect(series)
    periods = consecutive_quarters("2020Q1", 20)
    target = set(periods[8:12])
    assert bursts, "应检出至少一段突增"
    covered: set[str] = set()
    for burst in bursts:
        span = consecutive_quarters(burst.start_period, 40)
        for p in span:
            covered.add(p)
            if p == burst.end_period:
                break
        assert burst.level == 1
        assert burst.weight > 0
        assert burst.skill_id == "pytorch"
        assert burst.source_id == "boss"
    assert len(target & covered) >= 3


def test_constant_share_with_doubling_volume_is_not_a_burst() -> None:
    """伪突增：总量逐期翻倍但占比恒定，不得报突增。"""
    totals = [100 * (2**i) for i in range(12)]
    counts = [int(0.1 * t) for t in totals]
    series = series_from_counts("java", counts, totals)
    bursts = KleinbergBurstDetector().detect(series)
    assert bursts == []


def test_empty_and_zero_series_yield_no_burst() -> None:
    assert KleinbergBurstDetector().detect([]) == []
    series = series_from_counts("x", [0] * 8, totals=100)
    assert KleinbergBurstDetector().detect(series) == []
    assert KleinbergBurstDetector().detect(series_from_counts("x", [10], totals=100)) == []


def test_mixed_skills_are_detected_separately() -> None:
    a = series_from_counts("a", [10] * 6 + [80] * 4, totals=200)
    b = series_from_counts("b", [20] * 10, totals=200)
    bursts = KleinbergBurstDetector().detect(a + b)
    assert {x.skill_id for x in bursts} == {"a"}


def test_mann_kendall_increasing_on_monotone_share() -> None:
    counts = [10 + 8 * i for i in range(16)]
    series = series_from_counts("k8s", counts, totals=200)
    result = trend_test(series)
    assert result.trend == "increasing"
    assert result.p_value < 0.05
    assert result.slope > 0


def test_classify_hype_vs_growth() -> None:
    hype_counts = [20] * 8 + [120] * 4 + [20] * 8
    hype = series_from_counts("web3", hype_counts, totals=400)
    hype_cls = classify_skill(hype)
    assert hype_cls.bursts
    assert hype_cls.label == "hype"

    growth_counts = [10 + 6 * i for i in range(16)]
    growth = series_from_counts("rust", growth_counts, totals=200)
    assert classify_skill(growth).label == "growth"


def test_short_series_has_no_trend() -> None:
    series = series_from_counts("x", [1, 2, 3], totals=10)
    assert trend_test(series).trend == "no trend"


def test_already_saturated_share_has_no_burst_state() -> None:
    """p0·s ≥ 1 时突增态不定义，应空结果。"""
    series = series_from_counts("everywhere", [100] * 10, totals=100)
    assert KleinbergBurstDetector().detect(series) == []


def test_stable_and_decline_labels() -> None:
    stable = series_from_counts("sql", [40] * 12, totals=200)
    assert classify_skill(stable).label == "stable"
    decline = series_from_counts("flash", [80 - 5 * i for i in range(12)], totals=200)
    assert classify_skill(decline).label == "decline"
