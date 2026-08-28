from datetime import date

from app.domain.models import Posting, Skill, SkillObservation
from app.extraction.ontology import SkillVocabEntry
from app.graph.repository import PUT_OBSERVATIONS, UPSERT_ROLES, UPSERT_SKILL, Neo4jGraphRepository
from app.pages.service import previous_period
from app.pipeline.ingest import extract_and_observe, role_id_for, run_pipeline, write_graph
from tests.graph.fakes import FakeExecutor


def test_role_id_stable_under_title_variants() -> None:
    a = role_id_for("Java开发工程师")
    b = role_id_for("JAVA 开发")
    assert a is not None and a == b
    assert a.startswith("role.")


def test_role_id_strips_region_and_batch_noise() -> None:
    a = role_id_for("渠道经理-华南")
    b = role_id_for("渠道经理-中西")
    c = role_id_for("【星际逐梦-国际社招班】项目管理岗")
    d = role_id_for("项目管理岗")
    assert a == b
    assert c == d


def test_previous_period_wraps_year() -> None:
    assert previous_period("2026Q1") == "2025Q4"
    assert previous_period("2026Q3") == "2026Q2"


class MemoryPostings:
    def __init__(self, items: list[Posting], *, total: int | None = None) -> None:
        self.items = items
        self.total = total if total is not None else len(items)
        self.materialized = 0

    def iter_all(self):
        return list(self.items)

    def count_all(self) -> int:
        return self.total

    def upsert(self, posting: Posting) -> str:
        self.materialized += 1
        return posting.id


class MemoryDocs:
    def __init__(self) -> None:
        self.saved: list[tuple[str, str, str]] = []

    def save(self, doc_id: str, text: str, *, kind: str = "posting") -> None:
        self.saved.append((doc_id, kind, text))

    def save_many(self, rows: list[tuple[str, str, str]]) -> int:
        self.saved.extend(rows)
        return len(rows)


class MemoryEvidence:
    def __init__(self) -> None:
        self.items = []

    def save(self, evidence) -> str:
        self.items.append(evidence)
        return evidence.id

    def save_many(self, items) -> int:
        self.items.extend(items)
        return len(items)


class MemoryObs:
    def __init__(self, items: list[SkillObservation] | None = None) -> None:
        self.items = list(items or [])

    def put(self, observation: SkillObservation) -> None:
        self.items.append(observation)

    def put_many(self, items: list[SkillObservation]) -> int:
        self.items.extend(items)
        return len(items)

    def iter_all(self):
        return list(self.items)


def test_extract_and_observe_batches_and_weights() -> None:
    posting = Posting(
        id="p1",
        source_id="jobhive_moka",
        snapshot_id="s1",
        title="Python开发工程师",
        published_at=date(2026, 7, 1),
        description="岗位要求精通 Python 与 Redis",
    )
    docs = MemoryDocs()
    evidence = MemoryEvidence()
    obs = MemoryObs()
    stats = extract_and_observe(
        posting_store=MemoryPostings([posting]),  # type: ignore[arg-type]
        documents=docs,  # type: ignore[arg-type]
        evidence_store=evidence,  # type: ignore[arg-type]
        observations=obs,  # type: ignore[arg-type]
        vocab=[
            SkillVocabEntry(id="skill.python", name="Python"),
            SkillVocabEntry(id="skill.redis", name="Redis"),
        ],
        flush_every=1,
    )
    assert stats["scanned"] == 1
    assert stats["evidence"] == 2
    assert stats["observations"] == 2
    assert docs.saved == [("p1", "posting", posting.description)]
    assert {item.skill_id for item in obs.items} == {"skill.python", "skill.redis"}
    assert all(item.weight == 1.0 and item.posting_count == 1 for item in obs.items)


def test_write_graph_uses_batch_cypher() -> None:
    rid = role_id_for("Python开发工程师")
    assert rid is not None
    obs = MemoryObs(
        [
            SkillObservation(
                role_id=rid,
                skill_id="skill.python",
                period="2026Q3",
                weight=1.0,
                posting_count=1,
                total_postings=1,
                ontology_version="0.1.0",
            )
        ]
    )
    fake = FakeExecutor()
    repo = Neo4jGraphRepository(fake, "0.1.0")
    graph = write_graph(
        observations=obs,  # type: ignore[arg-type]
        repo=repo,
        role_names={rid: "Python开发工程师"},
        skills={"skill.python": Skill(id="skill.python", name="Python", ontology_version="0.1.0")},
    )
    assert graph == {"roles": 1, "skills": 1, "edges": 1}
    cyphers = [call[0] for call in fake.calls]
    assert UPSERT_ROLES in cyphers
    assert UPSERT_SKILL in cyphers
    assert PUT_OBSERVATIONS in cyphers


def test_run_pipeline_skips_materialize_when_postings_exist() -> None:
    postings = MemoryPostings([], total=3)
    fake = FakeExecutor()
    result = run_pipeline(
        snapshot_store=object(),  # type: ignore[arg-type]
        posting_store=postings,  # type: ignore[arg-type]
        documents=MemoryDocs(),  # type: ignore[arg-type]
        evidence_store=MemoryEvidence(),  # type: ignore[arg-type]
        observations=MemoryObs(),  # type: ignore[arg-type]
        repo=Neo4jGraphRepository(fake, "0.1.0"),
    )
    assert result["postings"] == 3
    assert postings.materialized == 0
    assert result["extract"]["scanned"] == 0
