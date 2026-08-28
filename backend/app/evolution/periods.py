"""时间片 YYYYQn 的解析与排序。跨时间比较必须在同一本体版本内进行。"""

from __future__ import annotations

from datetime import date

from app.domain.models import SkillObservation


def parse_period(period: str) -> tuple[int, int]:
    year_s, q_s = period.split("Q", 1)
    return int(year_s), int(q_s)


def period_sort_key(period: str) -> tuple[int, int]:
    return parse_period(period)


def period_to_date(period: str) -> date:
    """时间片起点：Qn 对应该年第 1/4/7/10 月 1 日。occurred_on 用业务发生时间。"""
    year, q = parse_period(period)
    return date(year, 1 + (q - 1) * 3, 1)


def sorted_obs(series: list[SkillObservation]) -> list[SkillObservation]:
    return sorted(series, key=lambda o: parse_period(o.period))


def consecutive_quarters(start: str, n: int) -> list[str]:
    year, q = parse_period(start)
    out: list[str] = []
    for _ in range(n):
        out.append(f"{year}Q{q}")
        q += 1
        if q > 4:
            q = 1
            year += 1
    return out
