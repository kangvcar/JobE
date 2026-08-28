"""规范化文档正文。证据的字符偏移相对于 canonical_text。"""

from __future__ import annotations

from collections.abc import Sequence

from psycopg.types.json import Jsonb

from app.storage.pool import PgPool

UPSERT_DOC = """
INSERT INTO documents (id, kind, canonical_text, char_index)
VALUES (%s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    canonical_text = EXCLUDED.canonical_text,
    char_index = EXCLUDED.char_index
"""

GET_DOC = """
SELECT id, kind, canonical_text, char_index FROM documents WHERE id = %s
"""


class PgDocumentStore:
    def __init__(self, pool: PgPool) -> None:
        self._pool = pool

    def save(self, doc_id: str, text: str, *, kind: str = "posting") -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(UPSERT_DOC, (doc_id, kind, text, Jsonb([])))

    def save_many(self, rows: Sequence[tuple[str, str, str]]) -> int:
        """rows: (doc_id, kind, text)"""
        if not rows:
            return 0
        payload = [(doc_id, kind, text, Jsonb([])) for doc_id, kind, text in rows]
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(UPSERT_DOC, payload)
        return len(payload)

    def get(self, doc_id: str) -> dict | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(GET_DOC, (doc_id,))
                return cur.fetchone()
