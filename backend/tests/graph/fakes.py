"""测试用假执行器。不放在 conftest，避免被当成仅夹具模块。"""

from __future__ import annotations

from typing import Any


class FakeExecutor:
    """记录 Cypher 与参数，按队列返回结果。"""

    def __init__(self, results: list[list[dict[str, Any]]] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any], bool]] = []
        self._results = list(results or [])

    def queue(self, rows: list[dict[str, Any]]) -> None:
        self._results.append(rows)

    def run(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        *,
        write: bool = False,
    ) -> list[dict[str, Any]]:
        self.calls.append((cypher, params or {}, write))
        if self._results:
            return self._results.pop(0)
        return []

    @property
    def last(self) -> tuple[str, dict[str, Any], bool]:
        return self.calls[-1]
