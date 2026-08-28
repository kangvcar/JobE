"""领域规则：职位标题归一化与时间片计算。

放在 domain 而不是各模块内部，因为它们定义了"两个职位何时算同一个"和"一条职位属于
哪个时间片"——这是跨模块必须完全一致的判定。采集层与仓储层各留一份副本会静默漂移，
一旦漂移去重就失效，而且不会报错。

纯函数，无外部依赖。
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

_SPACE_RE = re.compile(r"[\s\u3000]+")
_PUNCT_RE = re.compile(r"[()（）\[\]【】\-—_/\\]+")

# 出现在标题末尾、不改变岗位身份的后缀
_SUFFIXES = ("工程师", "工程師", "专员", "專員", "岗位", "職位", "职位")


def normalize_title(title: str) -> str:
    """把 `Java开发工程师` / `JAVA 开发` / `java研发工程师` 归一到同一个键。

    只做确定性的字符层归一。语义相近但字面不同的标题（如"算法工程师"与"机器学习
    工程师"）不在这里合并，那是图谱层的事。
    """
    text = unicodedata.normalize("NFKC", title).casefold()
    text = _SPACE_RE.sub("", text)
    text = _PUNCT_RE.sub("", text)
    text = text.replace("研发", "开发").replace("研發", "开发")
    for suffix in _SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    if text.endswith("岗"):
        text = text[:-1]
    return text


def period_from_date(value: date | None) -> str | None:
    """时间片格式固定为 YYYYQn，全项目统一。"""
    if value is None:
        return None
    return f"{value.year}Q{(value.month - 1) // 3 + 1}"
