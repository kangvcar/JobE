"""Kleinberg 两状态突增检测（KDD 2002）与 Mann-Kendall 趋势。

输入是每期「含该技能的职位数 / 同期总职位数」。分子分母同期，才能消掉
职位总量增长造成的伪突增。不要用 Prophet / STL：季度点太少、无日周季节性。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pymannkendall as mk
from numpy.typing import NDArray

from app.domain.models import Burst, SkillObservation
from app.evolution.periods import sorted_obs

# s：突增态事件率 = 基线率 × s。论文与 CiteSpace 常用 2，即占比至少翻倍才值得进突增态。
S_DEFAULT = 2.0
# γ：状态上迁代价系数，转移代价为 γ ln n。γ=1 是论文默认；20 个季度下
# ln(20)≈3，足以压掉单期噪声，4 期连续翻倍仍进得去。
GAMMA_DEFAULT = 1.0

MK_MIN_POINTS = 4  # 再少 Sen 斜率没有意义


@dataclass(frozen=True)
class TrendResult:
    trend: str  # increasing / decreasing / no trend
    p_value: float
    z: float
    slope: float


@dataclass(frozen=True)
class SkillClassification:
    """Kleinberg 答区间，MK 答整体方向。两者合起来区分炒作与持续增长。"""

    label: str  # hype / growth / stable / decline
    bursts: list[Burst]
    trend: TrendResult


class KleinbergBurstDetector:
    """两状态隐马尔可夫 + 维特比。实现 ports.BurstDetector。

    状态 q0 基线概率 p0 = Σr / Σd；q1 突增概率 p1 = p0 · s。
    发射代价是二项分布负对数似然（省略与状态无关的组合数）。
    上迁代价 τ(0,1)=γ ln n，下迁与自环为 0（论文 §2）。
    """

    def __init__(
        self,
        source_id: str = "aggregate",
        s: float = S_DEFAULT,
        gamma: float = GAMMA_DEFAULT,
    ) -> None:
        self.source_id = source_id
        self.s = s
        self.gamma = gamma

    def detect(self, series: list[SkillObservation]) -> list[Burst]:
        if not series:
            return []
        grouped: dict[tuple[str, str], list[SkillObservation]] = {}
        for obs in series:
            grouped.setdefault((obs.skill_id, obs.ontology_version), []).append(obs)
        bursts: list[Burst] = []
        for (skill_id, _version), obs_list in grouped.items():
            bursts.extend(self._detect_one(skill_id, obs_list))
        return bursts

    def _detect_one(self, skill_id: str, series: list[SkillObservation]) -> list[Burst]:
        ordered = sorted_obs(series)
        n = len(ordered)
        if n < 2:
            return []
        r = np.array([obs.posting_count for obs in ordered], dtype=float)
        d = np.array([obs.total_postings for obs in ordered], dtype=float)
        d = np.maximum(d, 1.0)
        r = np.minimum(r, d)
        total_r = float(r.sum())
        total_d = float(d.sum())
        if total_r <= 0 or total_d <= 0:
            return []
        p0 = total_r / total_d
        p1 = p0 * self.s
        # 论文：pi 不得超过 1，否则该状态不定义。两状态下 p1>1 即无法进入突增态。
        if p1 >= 1.0 - 1e-15:
            return []
        p0 = min(max(p0, 1e-15), 1.0 - 1e-15)

        emission = np.column_stack([_binomial_nll(r, d, p0), _binomial_nll(r, d, p1)])
        trans_up = self.gamma * np.log(n)
        states = _viterbi_two_state(emission, trans_up)
        return _states_to_bursts(skill_id, self.source_id, ordered, states, r, d, p0, p1)


def _binomial_nll(r: NDArray[np.float64], d: NDArray[np.float64], p: float) -> NDArray[np.float64]:
    """-ln(p^r (1-p)^{d-r})。组合数与状态无关，维特比与权重差都消掉。"""
    return -r * np.log(p) - (d - r) * np.log(1.0 - p)


def _viterbi_two_state(emission: NDArray[np.float64], trans_up: float) -> NDArray[np.int_]:
    """C0(0)=0, C1(0)=∞，然后按论文递推。"""
    n = emission.shape[0]
    inf = np.inf
    prev = np.array([0.0, inf])
    ptr = np.zeros((n, 2), dtype=np.int_)
    for t in range(n):
        cand0 = prev  # 下迁与自环代价 0
        cand1 = prev + np.array([trans_up, 0.0])
        ptr[t, 0] = int(np.argmin(cand0))
        ptr[t, 1] = int(np.argmin(cand1))
        nxt = np.array([cand0[ptr[t, 0]] + emission[t, 0], cand1[ptr[t, 1]] + emission[t, 1]])
        prev = nxt
    states = np.zeros(n, dtype=np.int_)
    states[n - 1] = int(np.argmin(prev))
    for t in range(n - 1, 0, -1):
        states[t - 1] = ptr[t, states[t]]
    return states


def _states_to_bursts(
    skill_id: str,
    source_id: str,
    ordered: list[SkillObservation],
    states: NDArray[np.int_],
    r: NDArray[np.float64],
    d: NDArray[np.float64],
    p0: float,
    p1: float,
) -> list[Burst]:
    bursts: list[Burst] = []
    t = 0
    n = len(states)
    while t < n:
        if states[t] == 0:
            t += 1
            continue
        start = t
        while t < n and states[t] == 1:
            t += 1
        end = t - 1
        # 权重 = Σ (σ0 − σ1)，即相对基线的代价改善（论文对 [t1,t2] 的 weight）
        weight = float(
            np.sum(_binomial_nll(r[start : end + 1], d[start : end + 1], p0))
            - np.sum(_binomial_nll(r[start : end + 1], d[start : end + 1], p1))
        )
        bursts.append(
            Burst(
                skill_id=skill_id,
                source_id=source_id,
                start_period=ordered[start].period,
                end_period=ordered[end].period,
                level=1,
                weight=weight,
            )
        )
    return bursts


def trend_test(series: list[SkillObservation]) -> TrendResult:
    """对占比序列做 MK。用占比而不是原始计数，理由与突增检测相同。"""
    ordered = sorted_obs(series)
    if len(ordered) < MK_MIN_POINTS:
        return TrendResult("no trend", 1.0, 0.0, 0.0)
    props = [
        obs.posting_count / obs.total_postings if obs.total_postings else 0.0 for obs in ordered
    ]
    result = mk.original_test(props)
    return TrendResult(
        trend=str(result.trend),
        p_value=float(result.p),
        z=float(result.z),
        slope=float(result.slope),
    )


def classify_skill(
    series: list[SkillObservation],
    detector: KleinbergBurstDetector | None = None,
) -> SkillClassification:
    bursts = (detector or KleinbergBurstDetector()).detect(series)
    trend = trend_test(series)
    if trend.trend == "increasing":
        label = "growth"
    elif trend.trend == "decreasing":
        label = "decline"
    elif bursts:
        label = "hype"
    else:
        label = "stable"
    return SkillClassification(label=label, bursts=bursts, trend=trend)
