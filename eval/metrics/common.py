"""评测公共函数：读 JSONL、集合 F1、Cohen's κ、排序指标、错误行。"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def load_jsonl(path: Path | str) -> list[dict]:
    rows: list[dict] = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dump_jsonl(path: Path | str, rows: Iterable[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def dump_json(path: Path | str, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def index_by_id(rows: list[dict], key: str = "id") -> dict[str, dict]:
    return {str(r[key]): r for r in rows}


def prf(pred: set[str], gold: set[str]) -> dict[str, float]:
    tp = len(pred & gold)
    fp = len(pred - gold)
    fn = len(gold - pred)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {
        "precision": p,
        "recall": r,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def cohens_kappa(pairs: list[tuple[str, str]]) -> float:
    """两列名义标注的 Cohen's κ。pairs 为 (annotator_a, annotator_b)。"""
    if not pairs:
        return 0.0
    n = len(pairs)
    po = sum(1 for a, b in pairs if a == b) / n
    labels_a = Counter(a for a, _ in pairs)
    labels_b = Counter(b for _, b in pairs)
    labels = set(labels_a) | set(labels_b)
    pe = sum((labels_a[l] / n) * (labels_b[l] / n) for l in labels)
    if pe >= 1.0:
        return 1.0 if po >= 1.0 else 0.0
    return (po - pe) / (1.0 - pe)


def binary_presence_kappa(
    sets_a: dict[str, set[str]],
    sets_b: dict[str, set[str]],
) -> float:
    """每个「文档 × 技能点」是否出现，视为二元分类。

    词表取两名标注员在全部文档上的技能点并集（含真阴性）。
    若只在单篇文档的并集上展开，会没有 (0,0)，κ 会被系统性压低甚至变负。
    """
    vocab: set[str] = set()
    for s in sets_a.values():
        vocab |= s
    for s in sets_b.values():
        vocab |= s
    pairs: list[tuple[str, str]] = []
    ids = set(sets_a) | set(sets_b)
    for doc_id in ids:
        for name in vocab:
            a = "1" if name in sets_a.get(doc_id, set()) else "0"
            b = "1" if name in sets_b.get(doc_id, set()) else "0"
            pairs.append((a, b))
    return cohens_kappa(pairs)


def spearman(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    rx = _ranks(xs)
    ry = _ranks(ys)
    n = len(xs)
    mx = mean(rx)
    my = mean(ry)
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    denx = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n)))
    deny = math.sqrt(sum((ry[i] - my) ** 2 for i in range(n)))
    if denx == 0 or deny == 0:
        return 0.0
    return num / (denx * deny)


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def ndcg_at_k(y_true: list[float], y_score: list[float], k: int = 5) -> float:
    """y_true 是相关性，y_score 是系统打分（高者应排前）。"""
    if not y_true:
        return 0.0
    k = min(k, len(y_true))
    order = sorted(range(len(y_score)), key=lambda i: y_score[i], reverse=True)[:k]
    dcg = sum(y_true[i] / math.log2(rank + 2) for rank, i in enumerate(order))
    ideal = sorted(y_true, reverse=True)[:k]
    idcg = sum(rel / math.log2(rank + 2) for rank, rel in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def iou(a: list[float] | tuple[float, ...], b: list[float] | tuple[float, ...] | None) -> float:
    if not a or not b or len(a) != 4 or len(b) != 4:
        return 0.0
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union else 0.0


def span_exact(pred: dict | None, gold: dict | None) -> bool:
    if not pred or not gold:
        return False
    return int(pred.get("start", -1)) == int(gold.get("start", -2)) and int(
        pred.get("end", -1)
    ) == int(gold.get("end", -2))


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def write_report(path: Path | str, title: str, sections: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = f"# {title}\n\n" + "\n\n".join(sections) + "\n"
    path.write_text(body, encoding="utf-8")
