"""Lever 公开职位接口。只落 JSON 快照，不做职位解析。

GET /v0/postings/{company}?mode=json 免鉴权，返回职位数组。
标题在 text，正文在 description（HTML）/ descriptionPlain。
部分公司带 salaryRange；createdAt 为毫秒时间戳。
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
from app.domain.models import Snapshot

API_BASE = "https://api.lever.co/v0/postings"
USER_AGENT = "JobE/0.1 (research; job-evolution study)"
BOARDS_FILE = Path(__file__).with_name("lever_boards.txt")
PAGE_SIZE = 100


def load_boards(path: Path | None = None) -> list[tuple[str, str]]:
    target = path or BOARDS_FILE
    if not target.exists():
        return []
    boards: list[tuple[str, str]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("\t", 1)
        token = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else token
        if token:
            boards.append((token, name))
    return boards


def _created_date(value: Any) -> date | None:
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 10_000_000_000 else float(value)
        try:
            return datetime.fromtimestamp(ts, tz=UTC).date()
        except (OSError, OverflowError, ValueError):
            return None
    return None


class LeverCollector:
    source_id = "lever"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
        max_items: int = 2000,
        delay_seconds: float = 3.0,
        boards: list[tuple[str, str]] | None = None,
    ) -> None:
        self._client = client
        self._limiter = limiter or RateLimiter(delay_seconds)
        self._max_items = max_items
        self._boards = boards if boards is not None else load_boards()

    def collect(self, since: date | None = None) -> Iterable[Snapshot]:
        if not self._boards:
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
            for token, board_name in self._boards:
                if yielded >= self._max_items:
                    break
                skip = 0
                while yielded < self._max_items:
                    self._limiter.wait()
                    url = f"{API_BASE}/{token}"
                    response = client.get(
                        url,
                        params={"mode": "json", "limit": PAGE_SIZE, "skip": skip},
                    )
                    response.raise_for_status()
                    jobs = response.json()
                    if not isinstance(jobs, list) or not jobs:
                        break
                    fetched_at = datetime.now(UTC)
                    for job in jobs:
                        if not isinstance(job, dict):
                            continue
                        if since is not None:
                            job_day = _created_date(job.get("createdAt"))
                            if job_day is not None and job_day < since:
                                continue
                        payload = {
                            "board_token": token,
                            "board_name": board_name,
                            "job": drop_pii(job),
                        }
                        digest = content_hash(payload)
                        yield Snapshot(
                            id=f"{self.source_id}:{digest}",
                            source_id=self.source_id,
                            fetched_at=fetched_at,
                            url=str(job.get("hostedUrl") or url),
                            content_hash=digest,
                            payload=payload,
                        )
                        yielded += 1
                        if yielded >= self._max_items:
                            break
                    if len(jobs) < PAGE_SIZE:
                        break
                    skip += PAGE_SIZE
        finally:
            if own_client:
                client.close()
