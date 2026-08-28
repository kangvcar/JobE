"""快照一经写入不再修改。冲突时返回已有 id，绝不 UPDATE。"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence

from psycopg.types.json import Jsonb

from app.domain.models import Snapshot, Source
from app.storage.pool import PgPool

INSERT_SNAPSHOT = """
INSERT INTO snapshots (id, source_id, fetched_at, url, content_hash, payload)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (source_id, content_hash) DO NOTHING
RETURNING id
"""

INSERT_SNAPSHOT_BATCH = """
INSERT INTO snapshots (id, source_id, fetched_at, url, content_hash, payload)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (source_id, content_hash) DO NOTHING
"""

SELECT_BY_HASH = """
SELECT id FROM snapshots WHERE source_id = %s AND content_hash = %s
"""

EXISTS_HASH = """
SELECT 1 FROM snapshots WHERE content_hash = %s LIMIT 1
"""

ITER_BY_SOURCE = """
SELECT id, source_id, fetched_at, url, content_hash, payload
FROM snapshots
WHERE source_id = %s
ORDER BY fetched_at
"""

UPSERT_SOURCE = """
INSERT INTO sources (id, name, license, requires_login, is_leading_indicator)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING
"""


def _row_to_snapshot(row: dict) -> Snapshot:
    payload = row["payload"]
    if not isinstance(payload, dict):
        payload = json.loads(payload)
    return Snapshot(
        id=row["id"],
        source_id=row["source_id"],
        fetched_at=row["fetched_at"],
        url=row["url"],
        content_hash=row["content_hash"],
        payload=payload,
    )


class PgSnapshotStore:
    def __init__(self, pool: PgPool) -> None:
        self._pool = pool

    def ensure_source(self, source: Source) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    UPSERT_SOURCE,
                    (
                        source.id,
                        source.name,
                        source.license,
                        source.requires_login,
                        source.is_leading_indicator,
                    ),
                )

    def save(self, snapshot: Snapshot) -> str:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    INSERT_SNAPSHOT,
                    (
                        snapshot.id,
                        snapshot.source_id,
                        snapshot.fetched_at,
                        snapshot.url,
                        snapshot.content_hash,
                        Jsonb(snapshot.payload),
                    ),
                )
                row = cur.fetchone()
                if row:
                    return row["id"]
                cur.execute(SELECT_BY_HASH, (snapshot.source_id, snapshot.content_hash))
                existing = cur.fetchone()
                if existing is None:
                    raise RuntimeError("快照写入冲突后未能读到已有记录")
                return existing["id"]

    def save_many(self, snapshots: Sequence[Snapshot]) -> int:
        if not snapshots:
            return 0
        rows = [
            (
                snap.id,
                snap.source_id,
                snap.fetched_at,
                snap.url,
                snap.content_hash,
                Jsonb(snap.payload),
            )
            for snap in snapshots
        ]
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(INSERT_SNAPSHOT_BATCH, rows)
        return len(snapshots)

    def exists(self, content_hash: str) -> bool:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(EXISTS_HASH, (content_hash,))
                return cur.fetchone() is not None

    def iter_by_source(self, source_id: str) -> Iterable[Snapshot]:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(ITER_BY_SOURCE, (source_id,))
                rows = cur.fetchall()
        for row in rows:
            yield _row_to_snapshot(row)
