"""联系人字段图谱用不上，写入快照前丢弃，payload 里不得残留。"""

from __future__ import annotations

from typing import Any

# aae004/aae005：人社部联系人姓名与电话。其余为 Moka / BOSS 招聘接口可能返回的负责人字段。
PII_KEYS = frozenset(
    {
        "aae004",
        "aae005",
        "jobManager",
        "jobHrAssistant",
        "jobHiringManager",
        "jobInterviewer",
        "bossName",
        "bossInfo",
    }
)


def drop_pii(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: drop_pii(v) for k, v in obj.items() if k not in PII_KEYS}
    if isinstance(obj, list):
        return [drop_pii(v) for v in obj]
    return obj
