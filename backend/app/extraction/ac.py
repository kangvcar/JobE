"""Aho-Corasick 多模式匹配。不引入第三方库。"""

from __future__ import annotations

from collections import deque


class AhoCorasick:
    """模式串 → 原文精确 offset。通道 A 靠它拿到天然带位置的命中。"""

    def __init__(self) -> None:
        self._goto: list[dict[str, int]] = [{}]
        self._fail: list[int] = [0]
        self._out: list[list[int]] = [[]]
        self.patterns: list[str] = []

    def add(self, pattern: str) -> int:
        if not pattern:
            raise ValueError("模式串不能为空")
        node = 0
        for ch in pattern:
            nxt = self._goto[node].get(ch)
            if nxt is None:
                nxt = len(self._goto)
                self._goto[node][ch] = nxt
                self._goto.append({})
                self._fail.append(0)
                self._out.append([])
            node = nxt
        pid = len(self.patterns)
        self.patterns.append(pattern)
        self._out[node].append(pid)
        return pid

    def build(self) -> None:
        q: deque[int] = deque()
        for _ch, nxt in self._goto[0].items():
            q.append(nxt)
            self._fail[nxt] = 0
        while q:
            node = q.popleft()
            for ch, nxt in self._goto[node].items():
                q.append(nxt)
                f = self._fail[node]
                while f and ch not in self._goto[f]:
                    f = self._fail[f]
                self._fail[nxt] = self._goto[f].get(ch, 0)
                self._out[nxt].extend(self._out[self._fail[nxt]])

    def finditer(self, text: str) -> list[tuple[int, int, int]]:
        """返回 (start, end, pattern_index)，end 为开区间。"""
        hits: list[tuple[int, int, int]] = []
        node = 0
        for i, ch in enumerate(text):
            while node and ch not in self._goto[node]:
                node = self._fail[node]
            node = self._goto[node].get(ch, 0)
            for pid in self._out[node]:
                plen = len(self.patterns[pid])
                hits.append((i + 1 - plen, i + 1, pid))
        return hits


def prefer_longest(hits: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """重叠命中保留更长的。同起点时长的优先。"""
    if not hits:
        return []
    ordered = sorted(hits, key=lambda h: (h[0], -(h[1] - h[0])))
    kept: list[tuple[int, int, int]] = []
    last_end = -1
    for start, end, pid in ordered:
        if start < last_end:
            continue
        kept.append((start, end, pid))
        last_end = end
    return kept


def latin_word_boundary(text: str, start: int, end: int) -> bool:
    """拉丁片段要求词边界，避免 Go 命中 Going、C 命中 CSS。

    邻接判断只用 ASCII 字母数字：中文邻接（精通 Go 语言）视为边界。
    """

    def _ok(idx: int) -> bool:
        if idx < 0 or idx >= len(text):
            return True
        return not _latin_ident(text[idx])

    return _ok(start - 1) and _ok(end)


def _latin_ident(ch: str) -> bool:
    o = ord(ch)
    return 48 <= o <= 57 or 65 <= o <= 90 or 97 <= o <= 122 or ch == "_"
