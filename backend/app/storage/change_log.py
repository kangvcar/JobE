"""变更流水。自动发布进此表，可按状态查询并标记回滚。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.storage.pool import PgPool

INSERT_LOG = """
INSERT INTO change_log (
    id, entity_kind, entity_id, kind, before, after, reason,
    evidence_ids, occurred_on, recorded_at, state, reviewed_by, rolled_back
) VALUES (
    %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s
)
ON CONFLICT (id) DO NOTHING
RETURNING id
"""

BY_STATE = """
SELECT id, entity_kind, entity_id, kind, before, after, reason,
       evidence_ids, occurred_on, recorded_at, state, reviewed_by, rolled_back
FROM change_log
WHERE state = %s
ORDER BY recorded_at
"""

MARK_ROLLBACK = """
UPDATE change_log SET rolled_back = TRUE WHERE id = %s
"""


class ChangeLogEntry(BaseModel):
    id: str
    entity_kind: str
    entity_id: str
    kind: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    occurred_on: date
    recorded_at: datetime
    state: str
    reviewed_by: str | None = None
    rolled_back: bool = False


def _row_to_entry(row: dict) -> ChangeLogEntry:
    return ChangeLogEntry(
        id=row["id"],
        entity_kind=row["entity_kind"],
        entity_id=row["entity_id"],
        kind=row["kind"],
        before=row["before"],
        after=row["after"],
        reason=row["reason"],
        evidence_ids=list(row["evidence_ids"] or []),
        occurred_on=row["occurred_on"],
        recorded_at=row["recorded_at"],
        state=row["state"],
        reviewed_by=row["reviewed_by"],
        rolled_back=bool(row["rolled_back"]),
    )


class ChangeLogStore:
    def __init__(self, pool: PgPool) -> None:
        self._pool = pool

    def save(self, entry: ChangeLogEntry) -> str:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    INSERT_LOG,
                    (
                        entry.id,
                        entry.entity_kind,
                        entry.entity_id,
                        entry.kind,
                        Jsonb(entry.before) if entry.before is not None else None,
                        Jsonb(entry.after) if entry.after is not None else None,
                        entry.reason,
                        Jsonb(entry.evidence_ids),
                        entry.occurred_on,
                        entry.recorded_at,
                        entry.state,
                        entry.reviewed_by,
                        entry.rolled_back,
                    ),
                )
                row = cur.fetchone()
                return row["id"] if row else entry.id

    def iter_by_state(self, state: str) -> Iterable[ChangeLogEntry]:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(BY_STATE, (state,))
                rows = cur.fetchall()
        for row in rows:
            yield _row_to_entry(row)

    def mark_rolled_back(self, entry_id: str) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(MARK_ROLLBACK, (entry_id,))
