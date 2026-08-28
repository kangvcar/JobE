"""jobhive 托管 parquet：只导入北森与 Moka 中国切片，只落快照。

默认读本地 `data/datasets/jobhive/`。无本地文件且 allow_download=False 时不打网。
海外 Ashby 等切片不导入。解析交给 postings mapper。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from app.collectors.hashing import content_hash
from app.collectors.pii import drop_pii
from app.domain.models import Snapshot

MANIFEST_URL = "https://storage.stapply.ai/jobhive/v1/manifest.json"
USER_AGENT = "JobE/0.1 (research; job-evolution study)"
ALLOWED_ATS = frozenset({"beisen", "moka"})
SOURCE_BY_ATS = {
    "beisen": "jobhive_beisen",
    "moka": "jobhive_moka",
}

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DIR = REPO_ROOT / "data" / "datasets" / "jobhive"


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, (str, int, float)):
        return value
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _jsonable(item())
        except (TypeError, ValueError, AttributeError):
            pass
    return str(value)


def iter_rows(path: Path) -> Iterable[dict]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                row = json.loads(stripped)
                if isinstance(row, dict):
                    yield row
        return
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item
        elif isinstance(data, dict):
            yield data
        return
    if suffix == ".parquet":
        yield from _iter_parquet(path)
        return
    raise ValueError(f"不支持的 jobhive 文件: {path}")


def _iter_parquet(path: Path) -> Iterable[dict]:
    import pandas as pd

    frame = pd.read_parquet(path)
    for rec in frame.to_dict(orient="records"):
        if isinstance(rec, dict):
            yield {str(k): _jsonable(v) for k, v in rec.items()}


def resolve_local_path(ats: str, data_dir: Path, explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.exists() else None
    for name in (f"{ats}.jobs.parquet", f"{ats}.parquet", f"{ats}.jsonl"):
        candidate = data_dir / name
        if candidate.exists():
            return candidate
    return None


def download_slice(
    ats: str,
    data_dir: Path,
    *,
    client: httpx.Client | None = None,
) -> Path:
    if ats not in ALLOWED_ATS:
        raise ValueError(f"jobhive 只下载 beisen/moka，收到 {ats}")
    own = client is None
    if client is None:
        client = httpx.Client(
            timeout=120.0,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
    try:
        response = client.get(MANIFEST_URL)
        response.raise_for_status()
        info = response.json().get("by_ats", {}).get(ats)
        if not isinstance(info, dict) or not info.get("parquet"):
            raise ValueError(f"manifest 缺少 {ats} parquet")
        data_dir.mkdir(parents=True, exist_ok=True)
        dest = data_dir / f"{ats}.jobs.parquet"
        with client.stream("GET", str(info["parquet"])) as streamed:
            streamed.raise_for_status()
            with dest.open("wb") as handle:
                for chunk in streamed.iter_bytes():
                    handle.write(chunk)
        return dest
    finally:
        if own:
            client.close()


class JobhiveCollector:
    def __init__(
        self,
        *,
        ats: str,
        path: Path | None = None,
        data_dir: Path | None = None,
        max_items: int = 2000,
        allow_download: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        if ats not in ALLOWED_ATS:
            raise ValueError(f"jobhive 只导入 beisen/moka，收到 {ats}")
        self.ats = ats
        self.source_id = SOURCE_BY_ATS[ats]
        self._path = path
        self._data_dir = data_dir or DEFAULT_DIR
        self._max_items = max_items
        self._allow_download = allow_download
        self._client = client

    def collect(self, since: date | None = None) -> Iterable[Snapshot]:
        path = resolve_local_path(self.ats, self._data_dir, self._path)
        if path is None and self._allow_download and self._path is None:
            path = download_slice(self.ats, self._data_dir, client=self._client)
        if path is None:
            return
        yielded = 0
        fetched_at = datetime.now(UTC)
        for row in iter_rows(path):
            if yielded >= self._max_items:
                break
            ats_type = str(row.get("ats_type") or row.get("_slice") or self.ats)
            if ats_type != self.ats:
                continue
            if since is not None:
                posted = str(row.get("posted_at") or "")[:10]
                try:
                    day = date.fromisoformat(posted)
                except ValueError:
                    day = None
                if day is not None and day < since:
                    continue
            payload = drop_pii(_jsonable(row))
            digest = content_hash(payload)
            url = str(payload.get("url") or "") or None
            yield Snapshot(
                id=f"{self.source_id}:{digest}",
                source_id=self.source_id,
                fetched_at=fetched_at,
                url=url,
                content_hash=digest,
                payload=payload,
            )
            yielded += 1
