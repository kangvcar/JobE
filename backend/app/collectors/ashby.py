"""Ashby Job Board 公开接口。只落 JSON 快照，不做职位解析。

GET /posting-api/job-board/{boardName}?includeCompensation=true 免鉴权。
正文在 descriptionHtml，薪资在 compensation.compensationTiers。
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

API_BASE = "https://api.ashbyhq.com/posting-api/job-board"
USER_AGENT = "JobE/0.1 (research; job-evolution study)"
BOARDS_FILE = Path(__file__).with_name("ashby_boards.txt")


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


def _iso_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


class AshbyCollector:
    source_id = "ashby"

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
                self._limiter.wait()
                url = f"{API_BASE}/{token}"
                response = client.get(url, params={"includeCompensation": "true"})
                response.raise_for_status()
                body = response.json()
                jobs = body.get("jobs") if isinstance(body, dict) else None
                if not jobs:
                    continue
                fetched_at = datetime.now(UTC)
                for job in jobs:
                    if not isinstance(job, dict):
                        continue
                    if since is not None:
                        job_day = _iso_date(job.get("publishedAt"))
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
                        url=str(job.get("jobUrl") or url),
                        content_hash=digest,
                        payload=payload,
                    )
                    yielded += 1
                    if yielded >= self._max_items:
                        break
        finally:
            if own_client:
                client.close()
