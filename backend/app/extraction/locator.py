"""把 LLM 给出的原文片段定位成字符区间与版面坐标。

大模型不得输出位置。本模块做确定性匹配：精确命中，其次 NFKC/去空白折叠。
匹配不上返回 None——这就是幻觉过滤器。
"""

from __future__ import annotations

import unicodedata

from app.domain.models import TextSpan
from app.extraction.store import DocumentStore


class CanonicalSpanLocator:
    """ports.SpanLocator。多次命中用 hint_start 或块边界消歧。"""

    def __init__(self, docs: DocumentStore) -> None:
        self._docs = docs

    def locate(self, doc_id: str, quote: str, hint_start: int | None = None) -> TextSpan | None:
        if not quote or not quote.strip():
            return None
        doc = self._docs.get(doc_id)
        if doc is None:
            return None
        hits = find_hits(doc.canonical_text, quote)
        if not hits:
            return None
        start, end = pick_hit(hits, hint_start, doc.char_index.blocks)
        page, bbox = doc.char_index.span_geometry(start, end)
        return TextSpan(doc_id=doc_id, start=start, end=end, page_index=page, bbox=bbox)


def find_hits(text: str, quote: str) -> list[tuple[int, int]]:
    exact = _exact_hits(text, quote)
    if exact:
        return exact
    folded_text, index_map = fold(text)
    folded_quote, _ = fold(quote)
    if not folded_quote:
        return []
    hits: list[tuple[int, int]] = []
    start = 0
    while True:
        i = folded_text.find(folded_quote, start)
        if i < 0:
            break
        orig_start = index_map[i]
        orig_end = index_map[i + len(folded_quote) - 1] + 1
        hits.append((orig_start, orig_end))
        start = i + 1
    return hits


def _exact_hits(text: str, quote: str) -> list[tuple[int, int]]:
    hits: list[tuple[int, int]] = []
    start = 0
    qlen = len(quote)
    while True:
        i = text.find(quote, start)
        if i < 0:
            break
        hits.append((i, i + qlen))
        start = i + 1
    return hits


def fold(text: str) -> tuple[str, list[int]]:
    """NFKC + 去掉空白，返回折叠串及其每个字符对应的原文下标。"""
    out: list[str] = []
    index_map: list[int] = []
    for i, ch in enumerate(text):
        for sub in unicodedata.normalize("NFKC", ch):
            if sub.isspace():
                continue
            out.append(sub)
            index_map.append(i)
    return "".join(out), index_map


def pick_hit(
    hits: list[tuple[int, int]],
    hint_start: int | None,
    blocks: list[dict] | None,
) -> tuple[int, int]:
    if len(hits) == 1:
        return hits[0]
    candidates = hits
    if hint_start is not None and blocks:
        for blk in blocks:
            bs, be = int(blk["start"]), int(blk["end"])
            if bs <= hint_start < be:
                in_block = [h for h in hits if bs <= h[0] < be]
                if in_block:
                    candidates = in_block
                break
    if hint_start is not None:
        return min(candidates, key=lambda h: abs(h[0] - hint_start))
    return candidates[0]
