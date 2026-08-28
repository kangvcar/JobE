"""一次性采集：把合法来源的职位写入快照与职位表。"""

from __future__ import annotations

import logging
import sys

from app.api.routers.collect import _collectors, _get_pool
from app.collectors.run import run_collect
from app.collectors.sources import ALL_SOURCES
from app.storage.postings import PgPostingStore
from app.storage.snapshots import PgSnapshotStore


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    source_id = sys.argv[1] if len(sys.argv) > 1 else None
    max_items = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    delay = float(sys.argv[3]) if len(sys.argv) > 3 else 0.8

    pool = _get_pool()
    snapshots = PgSnapshotStore(pool)
    for src in ALL_SOURCES:
        snapshots.ensure_source(src)
    result = run_collect(
        collectors=_collectors(max_items, delay, liepin_enabled=False),
        snapshot_store=snapshots,
        posting_store=PgPostingStore(pool),
        source_id=source_id,
        since=None,
        max_items=max_items,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
