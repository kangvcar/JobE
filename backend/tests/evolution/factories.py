"""构造合成观测值。测试不许联网、连库、调大模型。"""

from __future__ import annotations

from app.domain.models import SkillObservation
from app.evolution.periods import consecutive_quarters


def make_obs(
    skill_id: str,
    period: str,
    posting_count: int,
    total_postings: int,
    *,
    role_id: str | None = None,
    ontology_version: str = "v0",
    weight: float | None = None,
) -> SkillObservation:
    if total_postings <= 0:
        w = 0.0
    else:
        w = weight if weight is not None else posting_count / total_postings
    return SkillObservation(
        role_id=role_id,
        skill_id=skill_id,
        period=period,
        weight=w,
        posting_count=posting_count,
        total_postings=total_postings,
        ontology_version=ontology_version,
    )


def series_from_counts(
    skill_id: str,
    counts: list[int],
    totals: list[int] | int,
    *,
    start: str = "2020Q1",
    role_id: str | None = None,
    ontology_version: str = "v0",
) -> list[SkillObservation]:
    periods = consecutive_quarters(start, len(counts))
    if isinstance(totals, int):
        totals_list = [totals] * len(counts)
    else:
        totals_list = totals
    return [
        make_obs(
            skill_id,
            period,
            c,
            t,
            role_id=role_id,
            ontology_version=ontology_version,
        )
        for period, c, t in zip(periods, counts, totals_list, strict=True)
    ]
