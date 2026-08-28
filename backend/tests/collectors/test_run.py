from __future__ import annotations

from datetime import UTC, date, datetime

from app.collectors.hashing import content_hash
from app.collectors.liepin import LiepinHalted
from app.collectors.run import get_status, run_collect
from app.domain.models import Posting, Snapshot


class MemorySnapshotStore:
    def __init__(self) -> None:
        self.items: dict[str, Snapshot] = {}

    def save(self, snapshot: Snapshot) -> str:
        self.items[snapshot.id] = snapshot
        return snapshot.id

    def exists(self, content_hash: str) -> bool:
        return any(s.content_hash == content_hash for s in self.items.values())

    def iter_by_source(self, source_id: str):
        return [s for s in self.items.values() if s.source_id == source_id]


class MemoryPostingStore:
    def __init__(self) -> None:
        self.items: dict[str, Posting] = {}

    def upsert(self, posting: Posting) -> str:
        self.items[posting.id] = posting
        return posting.id

    def iter_for_period(self, period: str):
        return []

    def count_for_period(self, period: str) -> int:
        return 0


class FakeCollector:
    source_id = "mohrss"

    def __init__(self, snapshots: list[Snapshot]) -> None:
        self._snapshots = snapshots

    def collect(self, since=None):
        yield from self._snapshots


def _snap(payload: dict, sid: str) -> Snapshot:
    return Snapshot(
        id=sid,
        source_id="mohrss",
        fetched_at=datetime.now(UTC),
        url="http://example.test",
        content_hash=content_hash(payload),
        payload=payload,
    )


def test_run_collect_saves_snapshots_and_postings():
    payload = {
        "acb22a": "Java开发工程师",
        "aab004": "示例",
        "area_": "北京市",
        "s_aae395": "2026-07-01",
        "md5": "abc",
        "aca111": "2021300",
        "acb241": 10000,
        "acb242": 20000,
    }
    snaps = MemorySnapshotStore()
    posts = MemoryPostingStore()
    result = run_collect(
        collectors={"mohrss": FakeCollector([_snap(payload, "mohrss:h")])},
        snapshot_store=snaps,
        posting_store=posts,
        source_id="mohrss",
        max_items=10,
    )
    assert result["state"] == "ok"
    assert result["saved"] == 1
    assert len(posts.items) == 1
    assert get_status()["state"] == "ok"


def test_run_collect_skips_existing_hash():
    payload = {"acb22a": "x", "md5": "z"}
    snap = _snap(payload, "mohrss:h")
    store = MemorySnapshotStore()
    store.save(snap)
    result = run_collect(
        collectors={"mohrss": FakeCollector([snap])},
        snapshot_store=store,
        posting_store=MemoryPostingStore(),
        max_items=10,
    )
    assert result["saved"] == 0
    # 哈希命中仍要转成职位，否则快照表会堆着未物化的原始记录
    assert result["postings"] == 1


def test_run_collect_halt_on_liepin():
    class Boom:
        source_id = "liepin"

        def collect(self, since=None):
            raise LiepinHalted("验证码")
            yield  # pragma: no cover

    result = run_collect(
        collectors={"liepin": Boom()},
        snapshot_store=MemorySnapshotStore(),
        posting_store=MemoryPostingStore(),
        source_id="liepin",
        max_items=5,
    )
    assert result["state"] == "halted"
    assert "验证码" in result["error"]


def test_run_collect_respects_source_filter():
    class Other:
        source_id = "moka"

        def collect(self, since=None):
            raise AssertionError("不应采集未选来源")
            yield

    result = run_collect(
        collectors={"moka": Other()},
        snapshot_store=MemorySnapshotStore(),
        posting_store=MemoryPostingStore(),
        source_id="mohrss",
        since=date(2026, 1, 1),
        max_items=1,
    )
    assert result["saved"] == 0
    assert result["state"] == "ok"


def test_run_collect_flushes_in_chunks():
    class BulkSnaps(MemorySnapshotStore):
        def __init__(self) -> None:
            super().__init__()
            self.sizes: list[int] = []

        def save_many(self, snapshots):
            self.sizes.append(len(snapshots))
            for snap in snapshots:
                self.save(snap)
            return len(snapshots)

    class BulkPosts(MemoryPostingStore):
        def __init__(self) -> None:
            super().__init__()
            self.sizes: list[int] = []

        def upsert_many(self, postings):
            self.sizes.append(len(postings))
            for posting in postings:
                self.upsert(posting)
            return len(postings)

    snaps = [
        _snap({"acb22a": f"Java{i}", "md5": str(i), "aab004": "示例", "area_": "北京市"}, f"mohrss:{i}")
        for i in range(5)
    ]
    snap_store = BulkSnaps()
    post_store = BulkPosts()
    result = run_collect(
        collectors={"mohrss": FakeCollector(snaps)},
        snapshot_store=snap_store,
        posting_store=post_store,
        max_items=None,
        flush_every=2,
        detect_peer_boilerplate=False,
    )
    assert result["state"] == "ok"
    assert snap_store.sizes == [2, 2, 1]
    assert post_store.sizes == [2, 2, 1]
    assert result["postings"] == 5
    assert len(post_store.items) == 5
