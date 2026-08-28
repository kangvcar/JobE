"""把已采集的快照物化为职位、观测与图谱。"""

from __future__ import annotations

from app.config import get_settings
from app.graph.migrate import apply_schema
from app.graph.repository import Neo4jGraphRepository
from app.graph.session import Neo4jExecutor, create_driver
from app.pipeline.ingest import run_pipeline
from app.storage.documents import PgDocumentStore
from app.storage.evidence import PgEvidenceStore
from app.storage.observations import ObservationStore
from app.storage.pool import PgPool
from app.storage.postings import PgPostingStore
from app.storage.snapshots import PgSnapshotStore


def main() -> int:
    settings = get_settings()
    pool = PgPool()
    driver = create_driver()
    driver.verify_connectivity()
    executor = Neo4jExecutor(driver)
    apply_schema(executor)
    print("清空旧观测与图谱…", flush=True)
    executor.run("MATCH (n) DETACH DELETE n", write=True)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE skill_observations")
            cur.execute("TRUNCATE evidence, documents, skill_profiles RESTART IDENTITY CASCADE")
    repo = Neo4jGraphRepository(executor, settings.ontology_version)
    result = run_pipeline(
        snapshot_store=PgSnapshotStore(pool),
        posting_store=PgPostingStore(pool),
        documents=PgDocumentStore(pool),
        evidence_store=PgEvidenceStore(pool),
        observations=ObservationStore(pool),
        repo=repo,
    )
    print(result)
    driver.close()
    pool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
