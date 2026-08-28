"""把快照转成职位：标题归一、近重复、模板段落标记、脱敏。

只标记不删除原文。近重复用 Lightcast 两步法：三元组精确命中，再辅以标题模糊匹配；
窗口为 60 天。标题归一与时间片规则来自 domain.normalization，全项目共用一份。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup
from datasketch import MinHash, MinHashLSH
from rapidfuzz import fuzz

from app.domain.models import Posting, Snapshot
from app.domain.normalization import normalize_title

DEDUP_WINDOW_DAYS = 60
FUZZY_TITLE_THRESHOLD = 92

_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_WECHAT_RE = re.compile(
    r"(?:微信(?:号)?|wechat|wx)\s*[:：]?\s*[A-Za-z][A-Za-z0-9_\-]{5,19}",
    re.IGNORECASE,
)

# 不含能力信息、在招聘文本中反复出现的福利套话。按长度降序以免短词先吃掉长词。
BENEFIT_PHRASES = tuple(
    sorted(
        (
            "五险一金",
            "周末双休",
            "双休",
            "团队氛围好",
            "带薪年假",
            "节日福利",
            "定期体检",
            "年终奖",
            "加班费",
            "扁平化管理",
            "免费零食",
            "零食下午茶",
            "弹性工作",
            "缴纳公积金",
        ),
        key=len,
        reverse=True,
    )
)

_REDACTION = "[已脱敏]"


def redact_pii(text: str) -> str:
    text = _ID_CARD_RE.sub(_REDACTION, text)
    text = _PHONE_RE.sub(_REDACTION, text)
    text = _EMAIL_RE.sub(_REDACTION, text)
    text = _WECHAT_RE.sub(_REDACTION, text)
    return text


def html_to_text(raw: str) -> str:
    soup = BeautifulSoup(raw, "lxml")
    return soup.get_text("\n", strip=True)


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _minhash(text: str, num_perm: int = 64) -> MinHash:
    mh = MinHash(num_perm=num_perm)
    folded = text.casefold()
    if len(folded) < 3:
        mh.update(folded.encode("utf-8"))
        return mh
    for i in range(len(folded) - 2):
        mh.update(folded[i : i + 3].encode("utf-8"))
    return mh


def _blocks(text: str) -> list[tuple[int, int, str]]:
    blocks: list[tuple[int, int, str]] = []
    for match in re.finditer(r"[^\n。]+(?:[。\n]|$)", text):
        chunk = match.group().strip()
        if len(chunk) >= 8:
            blocks.append((match.start(), match.end(), chunk))
    return blocks


def _merge_spans(spans: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    ordered = sorted(spans)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def detect_boilerplate(text: str, peer_texts: Sequence[str] = ()) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    occupied = [False] * len(text)
    for phrase in BENEFIT_PHRASES:
        start = 0
        while True:
            index = text.find(phrase, start)
            if index < 0:
                break
            end = index + len(phrase)
            if not any(occupied[index:end]):
                spans.append((index, end))
                for i in range(index, end):
                    occupied[i] = True
            start = end

    lsh = MinHashLSH(threshold=0.8, num_perm=64)
    n = 0
    for peer in peer_texts:
        for _, _, chunk in _blocks(peer):
            lsh.insert(f"p{n}", _minhash(chunk))
            n += 1
    if n:
        for start, end, chunk in _blocks(text):
            if lsh.query(_minhash(chunk)):
                spans.append((start, end))
    return _merge_spans(spans)


def _within_window(left: date | None, right: date | None) -> bool:
    if left is None or right is None:
        return False
    return abs((left - right).days) <= DEDUP_WINDOW_DAYS


def find_duplicate(posting: Posting, existing: Sequence[Posting]) -> str | None:
    title = normalize_title(posting.title)
    if not title or not posting.company or not posting.city:
        return None
    anchor = posting.published_at or posting.updated_at
    for other in existing:
        if other.duplicate_of is not None:
            continue
        if other.company != posting.company or other.city != posting.city:
            continue
        other_anchor = other.published_at or other.updated_at
        if not _within_window(anchor, other_anchor):
            continue
        other_title = normalize_title(other.title)
        if other_title == title:
            return other.id
        if fuzz.ratio(title, other_title) >= FUZZY_TITLE_THRESHOLD:
            return other.id
    return None


def _map_mohrss(snapshot: Snapshot) -> Posting:
    item = snapshot.payload
    native = str(item.get("md5") or snapshot.content_hash[:32])
    return Posting(
        id=f"{snapshot.source_id}:{native}",
        source_id=snapshot.source_id,
        snapshot_id=snapshot.id,
        title=str(item.get("acb22a") or ""),
        company=item.get("aab004") or None,
        city=item.get("area_") or None,
        published_at=_parse_date(item.get("s_aae395")),
        updated_at=_parse_date(item.get("s_aae397")),
        description=None,
        occupation_code=str(item["aca111"]) if item.get("aca111") not in (None, "") else None,
        salary_min=_as_int(item.get("acb241")),
        salary_max=_as_int(item.get("acb242")),
    )


def _map_moka(snapshot: Snapshot) -> Posting:
    payload = snapshot.payload
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    raw_desc = job.get("description") or ""
    description = redact_pii(html_to_text(raw_desc)) if raw_desc else None
    locations = job.get("locations") or []
    city = None
    if locations and isinstance(locations[0], dict):
        city = locations[0].get("city")
    salary_min = _as_int(job.get("minSalary"))
    salary_max = _as_int(job.get("maxSalary"))
    # Moka 文档：薪资单位为千（K）
    if salary_min is not None and salary_min < 1000:
        salary_min *= 1000
    if salary_max is not None and salary_max < 1000:
        salary_max *= 1000
    native = str(job.get("id") or snapshot.content_hash[:32])
    return Posting(
        id=f"{snapshot.source_id}:{native}",
        source_id=snapshot.source_id,
        snapshot_id=snapshot.id,
        title=str(job.get("title") or ""),
        company=payload.get("org_name") or job.get("orgId") or payload.get("org_id"),
        city=city,
        published_at=_parse_date(job.get("openedAt") or job.get("publishedAt")),
        updated_at=_parse_date(job.get("updatedAt")),
        description=description,
        occupation_code=None,
        salary_min=salary_min,
        salary_max=salary_max,
    )


def _map_liepin(snapshot: Snapshot) -> Posting:
    payload = snapshot.payload
    text = redact_pii(str(payload.get("text") or ""))
    title = str(payload.get("title") or text[:80] or "未命名")
    return Posting(
        id=f"{snapshot.source_id}:{snapshot.content_hash[:32]}",
        source_id=snapshot.source_id,
        snapshot_id=snapshot.id,
        title=title,
        company=payload.get("company"),
        city=payload.get("city"),
        published_at=_parse_date(payload.get("published_at")),
        updated_at=None,
        description=text or None,
    )


def posting_from_snapshot(snapshot: Snapshot) -> Posting:
    if snapshot.source_id == "mohrss":
        posting = _map_mohrss(snapshot)
    elif snapshot.source_id == "moka":
        posting = _map_moka(snapshot)
    else:
        posting = _map_liepin(snapshot)
    if posting.description:
        posting = posting.model_copy(update={"description": redact_pii(posting.description)})
    if posting.title:
        posting = posting.model_copy(update={"title": redact_pii(posting.title)})
    return posting


def snapshots_to_postings(
    snapshots: Iterable[Snapshot],
    existing: Sequence[Posting] = (),
) -> list[Posting]:
    mapped = [posting_from_snapshot(s) for s in snapshots]
    corpus: dict[str, list[str]] = {}
    for posting in (*existing, *mapped):
        if posting.company and posting.description:
            corpus.setdefault(posting.company, []).append(posting.description)

    canonical: list[Posting] = [p for p in existing if p.duplicate_of is None]
    out: list[Posting] = []
    for posting in mapped:
        peers = [
            text for text in corpus.get(posting.company or "", []) if text != posting.description
        ]
        if posting.description:
            posting = posting.model_copy(
                update={"boilerplate_spans": detect_boilerplate(posting.description, peers)}
            )
        dup = find_duplicate(posting, canonical)
        if dup:
            posting = posting.model_copy(update={"duplicate_of": dup})
        else:
            canonical.append(posting)
        out.append(posting)
    return out
