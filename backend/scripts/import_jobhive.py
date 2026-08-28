"""一次性导入 jobhive 北森 / Moka 切片。默认只读本地 parquet，不打网。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.api.routers.collect import _get_pool
from app.collectors.jobhive import JobhiveCollector
from app.collectors.run import run_collect
from app.collectors.sources import SOURCES_BY_ID
from app.storage.postings import PgPostingStore
from app.storage.snapshots import PgSnapshotStore


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="导入 jobhive 北森/Moka 中国切片")
    parser.add_argument("--ats", choices=("beisen", "moka", "both"), default="both")
    parser.add_argument("--max-items", type=int, default=2000)
    parser.add_argument("--path", type=Path, default=None, help="单个 parquet/jsonl 路径")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument(
        "--download",
        action="store_true",
        help="本地没有切片时按 manifest 下载 beisen/moka parquet",
    )
    args = parser.parse_args(argv)

    if args.path is not None and args.ats == "both":
        print("--path 时必须指定 --ats=beisen 或 --ats=moka", file=sys.stderr)
        return 2

    ats_list = ("beisen", "moka") if args.ats == "both" else (args.ats,)
    collectors = {
        f"jobhive_{ats}": JobhiveCollector(
            ats=ats,
            path=args.path,
            data_dir=args.data_dir,
            max_items=args.max_items,
            allow_download=args.download,
        )
        for ats in ats_list
    }

    pool = _get_pool()
    snapshots = PgSnapshotStore(pool)
    for ats in ats_list:
        snapshots.ensure_source(SOURCES_BY_ID[f"jobhive_{ats}"])
    result = run_collect(
        collectors=collectors,
        snapshot_store=snapshots,
        posting_store=PgPostingStore(pool),
        source_id=None,
        since=None,
        max_items=args.max_items,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
