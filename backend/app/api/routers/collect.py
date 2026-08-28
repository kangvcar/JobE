from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException

from app.collectors.ashby import AshbyCollector
from app.collectors.greenhouse import GreenhouseCollector
from app.collectors.lever import LeverCollector
from app.collectors.liepin import LiepinCollector
from app.collectors.mohrss import MohrssCollector
from app.collectors.moka import MokaCollector
from app.collectors.rate_limit import RateLimiter
from app.collectors.run import get_status, run_collect
from app.collectors.sources import ALL_SOURCES, SOURCES_BY_ID
from app.collectors.zhipin import ZhipinCollector
from app.config import get_settings
from app.storage.pool import PgPool
from app.storage.postings import PgPostingStore
from app.storage.snapshots import PgSnapshotStore

router = APIRouter(prefix="/api/collect", tags=["collect"])

_pool: PgPool | None = None


def _get_pool() -> PgPool:
    global _pool
    if _pool is None:
        _pool = PgPool()
    return _pool


def _collectors(
    max_items: int,
    delay: float,
    liepin_enabled: bool,
    zhipin_enabled: bool = False,
) -> dict:
    limiter = RateLimiter(delay)
    out: dict = {
        "mohrss": MohrssCollector(limiter=limiter, max_items=max_items, delay_seconds=delay),
        "moka": MokaCollector(
            limiter=limiter,
            max_items=max_items,
            delay_seconds=delay,
            max_per_org=40,
        ),
        "greenhouse": GreenhouseCollector(
            limiter=limiter, max_items=max_items, delay_seconds=delay
        ),
        "lever": LeverCollector(
            limiter=limiter, max_items=max_items, delay_seconds=delay
        ),
        "ashby": AshbyCollector(
            limiter=limiter, max_items=max_items, delay_seconds=delay
        ),
    }
    if liepin_enabled:
        out["liepin"] = LiepinCollector(
            enabled=True,
            limiter=RateLimiter(delay, jitter=True, min_seconds=3.0),
            delay_seconds=delay,
            max_items=max_items,
        )
    if zhipin_enabled:
        out["zhipin"] = ZhipinCollector(
            enabled=True,
            limiter=limiter,
            delay_seconds=delay,
            max_items=max_items,
        )
    return out


@router.get("/sources")
def list_sources() -> list[dict]:
    return [s.model_dump() for s in ALL_SOURCES]


@router.get("/status")
def collect_status() -> dict:
    return get_status()


@router.post("/run")
def trigger_collect(
    source_id: str | None = None,
    since: date | None = None,
    max_items: int | None = None,
) -> dict:
    if source_id and source_id not in SOURCES_BY_ID:
        raise HTTPException(status_code=404, detail=f"未知来源: {source_id}")
    settings = get_settings()
    cap = min(max_items or settings.collect_max_items, settings.collect_max_items)
    pool = _get_pool()
    snapshots = PgSnapshotStore(pool)
    if source_id:
        snapshots.ensure_source(SOURCES_BY_ID[source_id])
    else:
        for source in ALL_SOURCES:
            snapshots.ensure_source(source)
    return run_collect(
        collectors=_collectors(
            cap,
            settings.collect_delay_seconds,
            settings.liepin_enabled,
            settings.zhipin_enabled,
        ),
        snapshot_store=snapshots,
        posting_store=PgPostingStore(pool),
        source_id=source_id,
        since=since,
        max_items=cap,
    )
