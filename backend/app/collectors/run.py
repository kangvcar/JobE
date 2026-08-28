"""同步采集循环。无后台队列；条数受 collect_max_items 上限约束。"""

from __future__ import annotations

import threading
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from typing import Any

from app.collectors.liepin import LiepinHalted
from app.collectors.postings import snapshots_to_postings
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


def run_collect(
    *,
    collectors: Mapping[str, Collector],
    snapshot_store: SnapshotStore,
    posting_store: PostingStore,
    source_id: str | None = None,
    since: date | None = None,
    max_items: int = 2000,
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
                stream: Iterable[Snapshot] = collector.collect(since=since)
                for snapshot in stream:
                    if snapshot_store.exists(snapshot.content_hash):
                        # 快照去重不等于职位已物化：上次若在 save 之后、转职位之前中断，
                        # 这里必须把已有快照继续送进 snapshots_to_postings。
                        batch.append(snapshot)
                    else:
                        snapshot_store.save(snapshot)
                        batch.append(snapshot)
                        saved += 1
                    if saved >= max_items:
                        break
            except LiepinHalted as exc:
                _set_status(
                    state="halted",
                    saved=saved,
                    postings=posting_count,
                    source_id=sid,
                    error=str(exc),
                    finished_at=datetime.now(UTC).isoformat(),
                )
                if batch:
                    governed = snapshots_to_postings(batch, existing=existing)
                    for posting in governed:
                        posting_store.upsert(posting)
                        posting_count += 1
                    _set_status(postings=posting_count)
                return get_status()
            governed = snapshots_to_postings(batch, existing=existing)
            for posting in governed:
                posting_store.upsert(posting)
                posting_count += 1
            if saved >= max_items:
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
