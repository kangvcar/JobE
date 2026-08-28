from __future__ import annotations

from psycopg.types.json import Jsonb

from app.domain.models import Evidence, TextSpan
from app.storage.pool import PgPool

INSERT_EVIDENCE = """
INSERT INTO evidence (
    id, source_id, posting_id, doc_id, span_start, span_end,
    page_index, bbox, quote, fetched_at, extractor, confidence
) VALUES (
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s
)
ON CONFLICT (id) DO NOTHING
RETURNING id
"""

GET_ONE = """
SELECT id, source_id, posting_id, doc_id, span_start, span_end,
       page_index, bbox, quote, fetched_at, extractor, confidence
FROM evidence
WHERE id = %s
"""

GET_MANY = """
SELECT id, source_id, posting_id, doc_id, span_start, span_end,
       page_index, bbox, quote, fetched_at, extractor, confidence
FROM evidence
WHERE id = ANY(%s)
"""


def _row_to_evidence(row: dict) -> Evidence:
    bbox = row["bbox"]
    if isinstance(bbox, list) and len(bbox) == 4:
        bbox_t = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    else:
        bbox_t = None
    return Evidence(
        id=row["id"],
        source_id=row["source_id"],
        posting_id=row["posting_id"],
        span=TextSpan(
            doc_id=row["doc_id"] or "",
            start=row["span_start"],
            end=row["span_end"],
            page_index=row["page_index"],
            bbox=bbox_t,
        ),
        quote=row["quote"],
        fetched_at=row["fetched_at"],
        extractor=row["extractor"],
        confidence=row["confidence"],
    )


class PgEvidenceStore:
    def __init__(self, pool: PgPool) -> None:
        self._pool = pool

    def save(self, evidence: Evidence) -> str:
        bbox = list(evidence.span.bbox) if evidence.span.bbox else None
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    INSERT_EVIDENCE,
                    (
                        evidence.id,
                        evidence.source_id,
                        evidence.posting_id,
                        evidence.span.doc_id,
                        evidence.span.start,
                        evidence.span.end,
                        evidence.span.page_index,
                        Jsonb(bbox) if bbox is not None else None,
                        evidence.quote,
                        evidence.fetched_at,
                        evidence.extractor,
                        evidence.confidence,
                    ),
                )
                row = cur.fetchone()
                return row["id"] if row else evidence.id

    def get(self, evidence_id: str) -> Evidence | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(GET_ONE, (evidence_id,))
                row = cur.fetchone()
        return _row_to_evidence(row) if row else None

    def get_many(self, ids: list[str]) -> list[Evidence]:
        if not ids:
            return []
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(GET_MANY, (ids,))
                rows = cur.fetchall()
        by_id = {row["id"]: _row_to_evidence(row) for row in rows}
        return [by_id[i] for i in ids if i in by_id]
