"""技术信号相对招聘需求的领先滞后期。

用互相关峰值位置测滞后期，用 Granger 检验方向。不用 DTW：它会把
「领先 N 期」弹性掉。Stack Overflow 不得作为领先指标（ADR 0004）。
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray
from statsmodels.tsa.stattools import ccf, grangercausalitytests

from app.domain.models import LeadLag, SkillObservation
from app.evolution.periods import parse_period

# 季度序列约 20 点，默认窗口 8 期 = 两年。再长自由度不够。
MAX_LAG_DEFAULT = 8
MIN_OVERLAP = 8  # 少于 8 个对齐时间片，CCF 峰值不可信
SIGNIFICANCE_Z = 1.96  # 95% 界 ±1.96/√n

# 月发帖量自 2016 峰值跌约 98%，与招聘需求负相关；跨 2022 年会得出反向结论。
EXCLUDED_LEADING_SOURCES = frozenset({"stackoverflow", "stack_overflow", "stack-overflow", "so"})


class CcfLeadLagAnalyzer:
    """实现 ports.LeadLagAnalyzer。"""

    def __init__(
        self,
        leading_source_id: str = "leading",
        lagging_source_id: str = "lagging",
        max_lag: int = MAX_LAG_DEFAULT,
    ) -> None:
        self.leading_source_id = leading_source_id
        self.lagging_source_id = lagging_source_id
        self.max_lag = max_lag

    def analyze(
        self,
        leading: list[SkillObservation],
        lagging: list[SkillObservation],
    ) -> LeadLag | None:
        if _is_excluded(self.leading_source_id):
            return None
        aligned = _align_rates(leading, lagging)
        if aligned is None:
            return None
        skill_id, x, y = aligned
        max_lag = min(self.max_lag, len(x) - 2)
        if max_lag < 1:
            return None
        lags, values = two_way_ccf(x, y, max_lag)
        n = len(x)
        bound = SIGNIFICANCE_Z / math.sqrt(n)
        peak_idx = int(np.argmax(values))
        peak_corr = float(values[peak_idx])
        peak_lag_sm = int(lags[peak_idx])
        if peak_corr < bound:
            return None
        # statsmodels 正 lag 是 corr(x[t+k], y[t])；x 领先 y 共 L 期时峰值在 k=-L。
        # 对外约定：lag_periods>0 表示 leading 领先 lagging。
        lag_periods = -peak_lag_sm
        p_value = _granger_p(x, y, max(1, abs(lag_periods)), max_lag)
        return LeadLag(
            skill_id=skill_id,
            leading_source_id=self.leading_source_id,
            lagging_source_id=self.lagging_source_id,
            lag_periods=lag_periods,
            correlation=peak_corr,
            p_value=p_value,
        )


def two_way_ccf(
    x: NDArray[np.floating], y: NDArray[np.floating], max_lag: int
) -> tuple[NDArray[np.int_], NDArray[np.float64]]:
    """完整 ±lag 互相关。statsmodels.ccf 只给非负 lag，反转序列再拼接。"""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    # 不依赖 nlags 的返回长度（0.14 对「含不含 lag 0」有歧义），取满序列再切片。
    forwards = np.asarray(ccf(x, y, adjusted=False), dtype=float)[: max_lag + 1]
    backwards = np.asarray(ccf(x[::-1], y[::-1], adjusted=False), dtype=float)[: max_lag + 1][::-1]
    max_lag = min(max_lag, len(forwards) - 1, len(backwards) - 1)
    forwards = forwards[: max_lag + 1]
    backwards = backwards[-(max_lag + 1) :]
    full = np.concatenate([backwards[:-1], forwards])
    lags = np.arange(-max_lag, max_lag + 1)
    return lags.astype(int), np.asarray(full, dtype=float)


def _is_excluded(source_id: str) -> bool:
    return source_id.strip().lower().replace(" ", "_") in EXCLUDED_LEADING_SOURCES


def _align_rates(
    leading: list[SkillObservation], lagging: list[SkillObservation]
) -> tuple[str, NDArray[np.float64], NDArray[np.float64]] | None:
    """按时间片内连接，跨本体版本的点丢弃。"""
    lead_map: dict[tuple[str, str], SkillObservation] = {}
    for obs in leading:
        lead_map[(obs.period, obs.ontology_version)] = obs
    lag_map: dict[tuple[str, str], SkillObservation] = {}
    for obs in lagging:
        lag_map[(obs.period, obs.ontology_version)] = obs
    keys = sorted(set(lead_map) & set(lag_map), key=lambda k: parse_period(k[0]))
    if len(keys) < MIN_OVERLAP:
        return None
    versions = {k[1] for k in keys}
    if len(versions) != 1:
        version = keys[-1][1]
        keys = [k for k in keys if k[1] == version]
        if len(keys) < MIN_OVERLAP:
            return None
    skill_ids = {lead_map[k].skill_id for k in keys}
    if len(skill_ids) != 1:
        return None
    x, y = [], []
    for key in keys:
        a, b = lead_map[key], lag_map[key]
        if a.total_postings <= 0 or b.total_postings <= 0:
            continue
        x.append(a.posting_count / a.total_postings)
        y.append(b.posting_count / b.total_postings)
    if len(x) < MIN_OVERLAP:
        return None
    return next(iter(skill_ids)), np.asarray(x, dtype=float), np.asarray(y, dtype=float)


def _granger_p(
    leading: NDArray[np.float64],
    lagging: NDArray[np.float64],
    lag: int,
    max_lag: int,
) -> float:
    """原假设：第二列不 Granger 引起第一列。列序：[招聘, 技术信号]。"""
    k = max(1, min(lag, max_lag, len(leading) // 5 or 1))
    data = np.column_stack([lagging, leading])
    try:
        # statsmodels 0.15 已去掉 verbose；短序列或完美拟合会失败，此时只信 CCF。
        out = grangercausalitytests(data, maxlag=k)
    except Exception:
        return 1.0
    tests = out.get(k) or out.get(min(out))
    if not tests:
        return 1.0
    return float(tests[0][0][1])
