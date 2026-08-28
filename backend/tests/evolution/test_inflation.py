"""技能通胀观测与固定效应分解。"""

from __future__ import annotations

from app.evolution.inflation import (
    FirmRolePeriod,
    PeriodSkillLoad,
    deflate_weights,
    observe_inflation,
)
from app.evolution.periods import consecutive_quarters
from tests.evolution.factories import series_from_counts


def test_density_rise_is_inflation_and_deflates_weights() -> None:
    periods = consecutive_quarters("2020Q1", 6)
    loads = [
        PeriodSkillLoad(
            period=p,
            n_postings=100,
            n_skill_mentions=400 + 80 * i,
            total_text_chars=20_000,
        )
        for i, p in enumerate(periods)
    ]
    report = observe_inflation(loads, ontology_version="v0")
    assert report.inflated
    assert report.density_trend == "increasing"
    assert report.points[0].adjustment == 1.0
    assert report.points[-1].adjustment < 1.0

    obs = series_from_counts("python", [50] * 6, 100, start="2020Q1")
    deflated = deflate_weights(obs, report)
    assert deflated[-1].weight < obs[-1].weight
    assert deflated[0].weight == obs[0].weight


def test_longer_postings_without_density_rise_is_not_inflation() -> None:
    """职位写长了、技能项随篇幅同比增加，C_t 不变，不算通胀。"""
    loads = [
        PeriodSkillLoad(
            period=f"202{i}Q1",
            n_postings=100,
            n_skill_mentions=400 + 80 * i,
            total_text_chars=20_000 + 4_000 * i,
        )
        for i in range(6)
    ]
    report = observe_inflation(loads, ontology_version="v0")
    assert report.inflated is False
    assert all(p.adjustment == 1.0 for p in report.points)


def test_firm_effects_separate_company_from_market() -> None:
    panel: list[FirmRolePeriod] = []
    for period, market in [("2023Q1", 8), ("2023Q2", 8), ("2023Q3", 9)]:
        panel.append(FirmRolePeriod("保守公司", "backend", period, market - 2, 1000))
        panel.append(FirmRolePeriod("膨胀公司", "backend", period, market + 4, 1000))
        panel.append(FirmRolePeriod("中位公司", "backend", period, market, 1000))
    report = observe_inflation(
        [
            PeriodSkillLoad(
                period="2023Q1", n_postings=3, n_skill_mentions=24, total_text_chars=3000
            ),
            PeriodSkillLoad(
                period="2023Q2", n_postings=3, n_skill_mentions=24, total_text_chars=3000
            ),
            PeriodSkillLoad(
                period="2023Q3", n_postings=3, n_skill_mentions=27, total_text_chars=3000
            ),
        ],
        ontology_version="v0",
        firm_panel=panel,
    )
    by_firm = {e.company: e.mean_deviation for e in report.firm_effects}
    assert by_firm["膨胀公司"] > 0
    assert by_firm["保守公司"] < 0


def test_empty_loads() -> None:
    report = observe_inflation([], ontology_version="v0")
    assert report.points == []
    assert report.inflated is False
