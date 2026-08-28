"""技能通胀观测。

文献里的学历通胀、简历通胀都搬不过来：我们观测的是职位文本里技能项密度
随时间的基线漂移。S_t = 技能项数/职位，C_t = 技能项数/文本长度。
C_t 上升才是「往同等篇幅里塞更多技能」；仅 S_t 上升可能只是职位写长了。
显著上升时，重要度乘以 C_0/C_t 扣除漂移。同企业同岗位的跨期偏离用来
拆开「企业自己在膨胀」和「市场真实需求变化」。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pymannkendall as mk

from app.domain.models import SkillObservation
from app.evolution.periods import period_sort_key

MK_ALPHA = 0.05
MK_MIN_POINTS = 4


@dataclass(frozen=True)
class PeriodSkillLoad:
    period: str
    n_postings: int
    n_skill_mentions: int
    total_text_chars: int


@dataclass(frozen=True)
class FirmRolePeriod:
    company: str
    role_id: str
    period: str
    n_skills: int
    text_chars: int


@dataclass(frozen=True)
class InflationPoint:
    period: str
    skills_per_posting: float
    skills_per_kchars: float
    n_postings: int
    adjustment: float


@dataclass(frozen=True)
class FirmEffect:
    company: str
    role_id: str
    mean_deviation: float  # 相对同期市场均值的平均偏离；>0 该企业要求更膨胀
    n_periods: int


@dataclass
class InflationReport:
    ontology_version: str
    points: list[InflationPoint]
    posting_trend: str
    posting_p_value: float
    density_trend: str
    density_p_value: float
    sen_slope_density: float
    inflated: bool
    firm_effects: list[FirmEffect] = field(default_factory=list)


def observe_inflation(
    loads: list[PeriodSkillLoad],
    *,
    ontology_version: str,
    firm_panel: list[FirmRolePeriod] | None = None,
) -> InflationReport:
    ordered = sorted(loads, key=lambda x: period_sort_key(x.period))
    if not ordered:
        return InflationReport(
            ontology_version=ontology_version,
            points=[],
            posting_trend="no trend",
            posting_p_value=1.0,
            density_trend="no trend",
            density_p_value=1.0,
            sen_slope_density=0.0,
            inflated=False,
        )
    s_series = [rec.n_skill_mentions / rec.n_postings if rec.n_postings else 0.0 for rec in ordered]
    c_series = [
        rec.n_skill_mentions / rec.total_text_chars if rec.total_text_chars else 0.0
        for rec in ordered
    ]
    s_mk = _mk(s_series)
    c_mk = _mk(c_series)
    # 用文本密度做通胀开关：职位变长不算通胀。
    inflated = c_mk[0] == "increasing" and c_mk[1] < MK_ALPHA
    baseline = next((c for c in c_series if c > 0), 0.0)
    points: list[InflationPoint] = []
    for rec, s, c in zip(ordered, s_series, c_series, strict=True):
        if inflated and c > 0 and baseline > 0:
            adjustment = baseline / c
        else:
            adjustment = 1.0
        points.append(
            InflationPoint(
                period=rec.period,
                skills_per_posting=s,
                skills_per_kchars=c * 1000.0,
                n_postings=rec.n_postings,
                adjustment=adjustment,
            )
        )
    return InflationReport(
        ontology_version=ontology_version,
        points=points,
        posting_trend=s_mk[0],
        posting_p_value=s_mk[1],
        density_trend=c_mk[0],
        density_p_value=c_mk[1],
        sen_slope_density=c_mk[2],
        inflated=inflated,
        firm_effects=_firm_effects(firm_panel or []),
    )


def deflate_weights(
    observations: list[SkillObservation], report: InflationReport
) -> list[SkillObservation]:
    """重要度扣除基线漂移。无显著通胀时 adjustment=1，原样返回新对象。"""
    by_period = {p.period: p.adjustment for p in report.points}
    out: list[SkillObservation] = []
    for obs in observations:
        factor = by_period.get(obs.period, 1.0)
        out.append(obs.model_copy(update={"weight": obs.weight * factor}))
    return out


def _mk(values: list[float]) -> tuple[str, float, float]:
    if len(values) < MK_MIN_POINTS or all(v == values[0] for v in values):
        return "no trend", 1.0, 0.0
    result = mk.original_test(values)
    return str(result.trend), float(result.p), float(result.slope)


def _firm_effects(panel: list[FirmRolePeriod]) -> list[FirmEffect]:
    """固定效应思路：每期市场均值 ᾱ_t，企业偏离 s_{f,t} − ᾱ_t。"""
    if not panel:
        return []
    by_period: dict[str, list[float]] = {}
    for rec in panel:
        by_period.setdefault(rec.period, []).append(float(rec.n_skills))
    market = {p: sum(xs) / len(xs) for p, xs in by_period.items()}
    grouped: dict[tuple[str, str], list[float]] = {}
    for rec in panel:
        grouped.setdefault((rec.company, rec.role_id), []).append(rec.n_skills - market[rec.period])
    effects = [
        FirmEffect(
            company=company,
            role_id=role_id,
            mean_deviation=sum(devs) / len(devs),
            n_periods=len(devs),
        )
        for (company, role_id), devs in grouped.items()
    ]
    effects.sort(key=lambda e: e.mean_deviation, reverse=True)
    return effects
