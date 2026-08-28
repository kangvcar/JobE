"""同步采集循环。无后台队列；条数受 collect_max_items 上限约束。"""

from __future__ import annotations

import threading
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

from app.collectors.liepin import LiepinHalted
from app.collectors.postings import snapshots_to_postings
from app.collectors.zhipin import ZhipinHalted
from app.domain.models import Posting, Snapshot
from app.domain.normalization import period_from_date
from app.domain.ports import Collector, PostingStore, SnapshotStore

_lock = threading.Lock()
_status: dict[str, Any] = {
    "state": "idle",
    "saved": 0,
    "postings": 0,
    "source_id": None,
    "error": None,
    "finished_at": None,
}


def get_status() -> dict[str, Any]:
    with _lock:
        return dict(_status)


def _set_status(**fields: Any) -> None:
    with _lock:
        _status.update(fields)


def _recent_periods(today: date | None = None) -> list[str]:
    today = today or date.today()
    current = period_from_date(today)
    assert current is not None
    q = (today.month - 1) // 3 + 1
    previous = f"{today.year - 1}Q4" if q == 1 else f"{today.year}Q{q - 1}"
    return [current, previous]


def _load_existing(store: PostingStore) -> list[Posting]:
    found: list[Posting] = []
    for period in _recent_periods():
        found.extend(list(store.iter_for_period(period)))
    return found


def _save_batch(snapshot_store: SnapshotStore, batch: Sequence[Snapshot]) -> int:
    saver = getattr(snapshot_store, "save_many", None)
    if callable(saver):
        return int(saver(batch) or 0)
    saved = 0
    for snapshot in batch:
        if snapshot_store.exists(snapshot.content_hash):
            continue
        snapshot_store.save(snapshot)
        saved += 1
    return saved


def _upsert_batch(posting_store: PostingStore, postings: Sequence[Posting]) -> int:
    writer = getattr(posting_store, "upsert_many", None)
    if callable(writer):
        return int(writer(postings) or 0)
    for posting in postings:
        posting_store.upsert(posting)
    return len(postings)


def _flush_batch(
    batch: list[Snapshot],
    *,
    snapshot_store: SnapshotStore,
    posting_store: PostingStore,
    existing: list[Posting],
    detect_peer_boilerplate: bool,
) -> tuple[int, int]:
    if not batch:
        return 0, 0
    saved = _save_batch(snapshot_store, batch)
    governed = snapshots_to_postings(
        batch, existing=existing, detect_peer_boilerplate=detect_peer_boilerplate
    )
    written = _upsert_batch(posting_store, governed)
    existing.extend(p for p in governed if p.duplicate_of is None)
    batch.clear()
    return saved, written


def run_collect(
    *,
    collectors: Mapping[str, Collector],
    snapshot_store: SnapshotStore,
    posting_store: PostingStore,
    source_id: str | None = None,
    since: date | None = None,
    max_items: int | None = 2000,
    flush_every: int | None = None,
    detect_peer_boilerplate: bool = True,
) -> dict[str, Any]:
    _set_status(
        state="running",
        saved=0,
        postings=0,
        source_id=source_id,
        error=None,
        finished_at=None,
    )
    saved = 0
    posting_count = 0
    try:
        for sid, collector in collectors.items():
            if source_id and sid != source_id:
                continue
            existing = _load_existing(posting_store)
            batch: list[Snapshot] = []
            try:
                if flush_every:
                    stream: Iterable[Snapshot] = collector.collect(since=since)
                    for snapshot in stream:
                        batch.append(snapshot)
                        if len(batch) >= flush_every:
                            ins, posts = _flush_batch(
                                batch,
                                snapshot_store=snapshot_store,
                                posting_store=posting_store,
                                existing=existing,
                                detect_peer_boilerplate=detect_peer_boilerplate,
                            )
                            saved += ins
                            posting_count += posts
                            _set_status(saved=saved, postings=posting_count, source_id=sid)
                        if max_items is not None and saved >= max_items:
                            break
                    ins, posts = _flush_batch(
                        batch,
                        snapshot_store=snapshot_store,
                        posting_store=posting_store,
                        existing=existing,
                        detect_peer_boilerplate=detect_peer_boilerplate,
                    )
                    saved += ins
                    posting_count += posts
                else:
                    stream = collector.collect(since=since)
                    for snapshot in stream:
                        if snapshot_store.exists(snapshot.content_hash):
                            # 快照去重不等于职位已物化：上次若在 save 之后、转职位之前中断，
                            # 这里必须把已有快照继续送进 snapshots_to_postings。
                            batch.append(snapshot)
                        else:
                            snapshot_store.save(snapshot)
                            batch.append(snapshot)
                            saved += 1
                        if max_items is not None and saved >= max_items:
                            break
            except (LiepinHalted, ZhipinHalted) as exc:
                _set_status(
                    state="halted",
                    saved=saved,
                    postings=posting_count,
                    source_id=sid,
                    error=str(exc),
                    finished_at=datetime.now(UTC).isoformat(),
                )
                if batch:
                    if flush_every:
                        ins, posts = _flush_batch(
                            batch,
                            snapshot_store=snapshot_store,
                            posting_store=posting_store,
                            existing=existing,
                            detect_peer_boilerplate=detect_peer_boilerplate,
                        )
                        saved += ins
                        posting_count += posts
                    else:
                        governed = snapshots_to_postings(
                            batch,
                            existing=existing,
                            detect_peer_boilerplate=detect_peer_boilerplate,
                        )
                        for posting in governed:
                            posting_store.upsert(posting)
                            posting_count += 1
                    _set_status(postings=posting_count)
                return get_status()
            if not flush_every:
                governed = snapshots_to_postings(
                    batch, existing=existing, detect_peer_boilerplate=detect_peer_boilerplate
                )
                for posting in governed:
                    posting_store.upsert(posting)
                    posting_count += 1
            if max_items is not None and saved >= max_items:
                break
        _set_status(
            state="ok",
            saved=saved,
            postings=posting_count,
            source_id=source_id,
            error=None,
            finished_at=datetime.now(UTC).isoformat(),
        )
    except Exception as exc:
        _set_status(
            state="error",
            saved=saved,
            postings=posting_count,
            error=str(exc),
            finished_at=datetime.now(UTC).isoformat(),
        )
        raise
    return get_status()
