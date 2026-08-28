"""Moka ATS 公开招聘官网接口。只落 JSON 快照，不做职位解析。

GET /api-platform/v1/jobs/{orgId}?mode=social|campus 免鉴权。
负责人姓名/电话/邮箱属于个人信息，写入前丢弃。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from app.collectors.hashing import content_hash
from app.collectors.pii import drop_pii
from app.collectors.rate_limit import RateLimiter
from app.collectors.sources import MOKA
from app.domain.models import Snapshot

API_BASE = "https://api.mokahr.com/api-platform/v1/jobs"
USER_AGENT = "JobE/0.1 (research; job-evolution study)"
ORGS_FILE = Path(__file__).with_name("moka_orgs.txt")
PAGE_SIZE = 30


def load_orgs(path: Path | None = None) -> list[tuple[str, str]]:
    target = path or ORGS_FILE
    if not target.exists():
        return []
    orgs: list[tuple[str, str]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("\t", 1)
        org_id = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else org_id
        if org_id:
            orgs.append((org_id, name))
    return orgs


class MokaCollector:
    source_id = MOKA.id

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
        max_items: int = 2000,
        delay_seconds: float = 3.0,
        orgs: list[tuple[str, str]] | None = None,
        modes: tuple[str, ...] = ("social", "campus"),
    ) -> None:
        self._client = client
        self._limiter = limiter or RateLimiter(delay_seconds)
        self._max_items = max_items
        self._orgs = orgs if orgs is not None else load_orgs()
        self._modes = modes

    def collect(self, since: date | None = None) -> Iterable[Snapshot]:
        if not self._orgs:
            return
        client = self._client
        own_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=30.0,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            )
        yielded = 0
        try:
            for org_id, org_name in self._orgs:
                if yielded >= self._max_items:
                    break
                for mode in self._modes:
                    offset = 0
                    while yielded < self._max_items:
                        self._limiter.wait()
                        params: dict[str, Any] = {
                            "mode": mode,
                            "limit": PAGE_SIZE,
                            "offset": offset,
                            "status": "open",
                        }
                        if since is not None:
                            params["updatedFromAt"] = since.isoformat()
                        url = f"{API_BASE}/{org_id}"
                        response = client.get(url, params=params)
                        response.raise_for_status()
                        body = response.json()
                        jobs = body.get("jobs") if isinstance(body, dict) else None
                        if not jobs:
                            break
                        fetched_at = datetime.now(UTC)
                        for job in jobs:
                            if not isinstance(job, dict):
                                continue
                            payload = {
                                "org_id": org_id,
                                "org_name": org_name,
                                "mode": mode,
                                "job": drop_pii(job),
                            }
                            digest = content_hash(payload)
                            yield Snapshot(
                                id=f"{self.source_id}:{digest}",
                                source_id=self.source_id,
                                fetched_at=fetched_at,
                                url=f"{url}?mode={mode}",
                                content_hash=digest,
                                payload=payload,
                            )
                            yielded += 1
                            if yielded >= self._max_items:
                                break
                        if len(jobs) < PAGE_SIZE:
                            break
                        offset += PAGE_SIZE
        finally:
            if own_client:
                client.close()
