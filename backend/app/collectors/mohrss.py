"""人社部中国公共招聘网。只抽隐藏域 JSON 落为快照，不做职位解析。

该站仅 HTTP 可用。联系人字段 aae004/aae005 必须在写入前丢弃。
已知缺陷：来源不提供职位描述正文。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.collectors.hashing import content_hash
from app.collectors.pii import drop_pii
from app.collectors.rate_limit import RateLimiter
from app.collectors.sources import MOHRSS
from app.domain.models import Snapshot

LIST_URL = "http://job.mohrss.gov.cn/cjobs/jobinfolist/listJobinfolist"
USER_AGENT = "JobE/0.1 (research; job-evolution study)"


def parse_findjoblist(page_html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(page_html, "lxml")
    el = soup.find("input", id="findjoblist")
    if el is None:
        return []
    raw = el.get("value") or ""
    if not raw.strip():
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def _item_date(item: dict[str, Any]) -> date | None:
    for key in ("s_aae397", "s_aae395"):
        value = item.get(key)
        if not value:
            continue
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            continue
    return None


class MohrssCollector:
    source_id = MOHRSS.id

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
        max_items: int = 2000,
        delay_seconds: float = 3.0,
    ) -> None:
        self._client = client
        self._limiter = limiter or RateLimiter(delay_seconds)
        self._max_items = max_items

    def collect(self, since: date | None = None) -> Iterable[Snapshot]:
        client = self._client
        own_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=30.0,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            )
        yielded = 0
        page_no = 1
        try:
            while yielded < self._max_items:
                self._limiter.wait()
                response = client.get(LIST_URL, params={"pageNo": page_no, "orderType": "score"})
                response.raise_for_status()
                items = parse_findjoblist(response.text)
                if not items:
                    break
                fetched_at = datetime.now(UTC)
                page_url = f"{LIST_URL}?pageNo={page_no}&orderType=score"
                for item in items:
                    cleaned = drop_pii(item)
                    item_date = _item_date(cleaned)
                    if since is not None and item_date is not None and item_date < since:
                        continue
                    payload = cleaned
                    digest = content_hash(payload)
                    yield Snapshot(
                        id=f"{self.source_id}:{digest}",
                        source_id=self.source_id,
                        fetched_at=fetched_at,
                        url=page_url,
                        content_hash=digest,
                        payload=payload,
                    )
                    yielded += 1
                    if yielded >= self._max_items:
                        break
                page_no += 1
        finally:
            if own_client:
                client.close()
