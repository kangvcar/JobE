"""时间片格式 YYYYQn。跨模块只认这一种写法。"""

from __future__ import annotations

import calendar
import re
from datetime import date

PERIOD_RE = re.compile(r"^(\d{4})Q([1-4])$")


def parse_period(period: str) -> tuple[int, int]:
    """返回 (年, 季度)。格式不对就立刻失败，避免静默写进错误分片。"""
    matched = PERIOD_RE.match(period)
    if not matched:
        raise ValueError(f"时间片必须是 YYYYQn，收到：{period}")
    return int(matched.group(1)), int(matched.group(2))


def period_end(period: str) -> date:
    """该时间片的最后一天，用作计算出的能力变更的业务发生时间。"""
    year, quarter = parse_period(period)
    month = quarter * 3
    return date(year, month, calendar.monthrange(year, month)[1])
