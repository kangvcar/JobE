"""把已落库的快照变成职位、技能观测和图谱边。

高精度通道只用 Aho-Corasick，不调大模型：有正文就能抽技能点，证据落在原文偏移上。
岗位按标题归一化聚类——语义合并是图谱层的事，这里只保证同一写法进同一个岗位。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime

from app.collectors.postings import find_duplicate, posting_from_snapshot
from app.collectors.sources import ALL_SOURCES
from app.config import ONTOLOGY_ROOT, get_settings
from app.domain.models import (
    Evidence,
    Posting,
    PublishState,
    Role,
    Skill,
    SkillObservation,
    TextSpan,
)
from app.domain.normalization import normalize_title, period_from_date
from app.extraction.ontology import SkillVocabEntry, load_skill_vocab
from app.extraction.resume import build_automaton, scan_text
from app.graph.repository import Neo4jGraphRepository
from app.storage.documents import PgDocumentStore
from app.storage.evidence import PgEvidenceStore
from app.storage.observations import ObservationStore
from app.storage.postings import PgPostingStore
from app.storage.snapshots import PgSnapshotStore

EXTRACTOR = "ac"
FLUSH_EVERY = 500
PROGRESS_EVERY = 5000


def _chunked(items: Sequence, size: int = FLUSH_EVERY):
    for i in range(0, len(items), size):
        yield items[i : i + size]


_BRACKET_RE = re.compile(r"【[^】]*】|\[[^\]]*\]|（[^）]*）|\([^)]*\)")
_DASH_TAIL_RE = re.compile(r"[-—–].+$")


def _strip_title_noise(title: str) -> str:
    """去掉招聘广告里的批次、地区后缀，让「渠道经理-华南」和「渠道经理-中西」进同一个岗位。"""
    text = _BRACKET_RE.sub("", title)
    text = _DASH_TAIL_RE.sub("", text)
    return text.strip() or title


def role_id_for(title: str) -> str | None:
    key = normalize_title(_strip_title_noise(title))
    if not key:
        return None
    digest = hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:10]
    return f"role.{digest}"


def _fallback_period() -> str:
    return period_from_date(date.today()) or "2026Q3"


def posting_period(posting: Posting) -> str:
    return period_from_date(posting.published_at or posting.updated_at) or _fallback_period()


def load_ontology_skills() -> dict[str, Skill]:
    settings = get_settings()
    version = settings.ontology_version
    path = ONTOLOGY_ROOT / "data" / "skills.jsonl"
    out: dict[str, Skill] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[row["id"]] = Skill(
            id=row["id"],
            name=row["name"],
            aliases=list(row.get("aliases") or []),
            parent_id=row.get("parent_id"),
            cluster_id=row.get("cluster_id") or row.get("cluster"),
            ontology_version=row.get("ontology_version") or version,
            external_ids=dict(row.get("external_ids") or {}),
        )
    return out


def load_clusters() -> dict[str, str]:
    path = ONTOLOGY_ROOT / "data" / "clusters.jsonl"
    names: dict[str, str] = {}
    if not path.exists():
        return names
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        names[row["id"]] = row.get("name") or row["id"]
    return names


def materialize_postings(snapshot_store: PgSnapshotStore, posting_store: PgPostingStore) -> int:
    """快照 → 职位。跳过 snapshots_to_postings 里的 MinHash 套话检测：

    那一步对每个职位重建一遍同公司全部正文的 LSH，2000 条会跑到十几分钟。
    套话过滤在抽取阶段用词表匹配已经够用。
    """
    existing = list(posting_store.iter_all())
    canonical = [p for p in existing if p.duplicate_of is None]
    written = 0
    for source in ALL_SOURCES:
        for snapshot in snapshot_store.iter_by_source(source.id):
            posting = posting_from_snapshot(snapshot)
            dup = find_duplicate(posting, canonical)
            if dup:
                posting = posting.model_copy(update={"duplicate_of": dup})
            else:
                canonical.append(posting)
            posting_store.upsert(posting)
            written += 1
    return written


def extract_and_observe(
    *,
    posting_store: PgPostingStore,
    documents: PgDocumentStore,
    evidence_store: PgEvidenceStore,
    observations: ObservationStore,
    vocab: list[SkillVocabEntry] | None = None,
    flush_every: int = FLUSH_EVERY,
) -> dict[str, int]:
    vocab = vocab if vocab is not None else load_skill_vocab()
    ac, skill_ids = build_automaton(vocab)
    version = get_settings().ontology_version
    fetched_at = datetime.now(UTC)

    role_names: dict[str, str] = {}
    role_period_posts: dict[tuple[str, str], set[str]] = defaultdict(set)
    role_skill_posts: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    skills_of: dict[tuple[str, str], set[str]] = defaultdict(set)
    evidence_n = 0
    scanned = 0
    doc_batch: list[tuple[str, str, str]] = []
    ev_batch: list[Evidence] = []

    def flush_docs_and_evidence() -> None:
        nonlocal evidence_n
        if doc_batch:
            saver = getattr(documents, "save_many", None)
            if saver is not None:
                saver(doc_batch)
            else:
                for doc_id, kind, text in doc_batch:
                    documents.save(doc_id, text, kind=kind)
            doc_batch.clear()
        if ev_batch:
            saver = getattr(evidence_store, "save_many", None)
            if saver is not None:
                saver(ev_batch)
            else:
                for ev in ev_batch:
                    evidence_store.save(ev)
            evidence_n += len(ev_batch)
            ev_batch.clear()

    for posting in posting_store.iter_all():
        rid = role_id_for(posting.title)
        if rid is None:
            continue
        display = _strip_title_noise(posting.title).strip() or posting.title.strip()
        role_names.setdefault(rid, display)
        period = posting_period(posting)
        text = posting.description or ""
        if not text:
            continue
        scanned += 1
        doc_batch.append((posting.id, "posting", text))
        role_period_posts[(rid, period)].add(posting.id)
        seen: set[str] = set()
        for start, end, skill_id, surface in scan_text(text, ac, skill_ids):
            if skill_id in seen:
                continue
            seen.add(skill_id)
            role_skill_posts[(rid, period, skill_id)].add(posting.id)
            skills_of[(rid, period)].add(skill_id)
            ev_batch.append(
                Evidence(
                    id=f"ev.{posting.id}.{skill_id}.{start}",
                    source_id=posting.source_id,
                    span=TextSpan(doc_id=posting.id, start=start, end=end),
                    quote=surface,
                    fetched_at=fetched_at,
                    extractor=f"{EXTRACTOR}:{skill_id}",
                    confidence=0.9,
                    posting_id=posting.id,
                )
            )
        if len(doc_batch) >= flush_every or len(ev_batch) >= flush_every:
            flush_docs_and_evidence()
        if scanned % PROGRESS_EVERY == 0:
            print(f"  已扫描 {scanned} 职位，证据 {evidence_n + len(ev_batch)}", flush=True)

    flush_docs_and_evidence()

    obs_items: list[SkillObservation] = []
    for (rid, period), posts in role_period_posts.items():
        total = len(posts)
        if total == 0:
            continue
        skill_keys = skills_of.get((rid, period), set())
        for skill_id in skill_keys:
            count = len(role_skill_posts[(rid, period, skill_id)])
            obs_items.append(
                SkillObservation(
                    role_id=rid,
                    skill_id=skill_id,
                    period=period,
                    weight=count / total,
                    posting_count=count,
                    total_postings=total,
                    ontology_version=version,
                )
            )
    putter = getattr(observations, "put_many", None)
    if putter is not None:
        for chunk in _chunked(obs_items, flush_every):
            putter(chunk)
    else:
        for obs in obs_items:
            observations.put(obs)

    return {
        "roles": len(role_names),
        "scanned": scanned,
        "evidence": evidence_n,
        "observations": len(obs_items),
        "role_names": role_names,  # type: ignore[dict-item]
    }


def write_graph(
    *,
    observations: ObservationStore,
    repo: Neo4jGraphRepository,
    role_names: dict[str, str],
    skills: dict[str, Skill] | None = None,
) -> dict[str, int]:
    skills = skills if skills is not None else load_ontology_skills()
    pending: list[SkillObservation] = []
    roles_by_id: dict[str, Role] = {}
    skill_ids: list[str] = []
    seen_skills: set[str] = set()

    for obs in observations.iter_all():
        if not obs.role_id:
            continue
        if obs.role_id not in roles_by_id:
            roles_by_id[obs.role_id] = Role(
                id=obs.role_id,
                name=role_names.get(obs.role_id, obs.role_id),
                state=PublishState.PUBLISHED,
            )
        if obs.skill_id not in seen_skills:
            seen_skills.add(obs.skill_id)
            skill_ids.append(obs.skill_id)
        pending.append(obs)

    roles = list(roles_by_id.values())
    upsert_roles = getattr(repo, "upsert_roles", None)
    if upsert_roles is not None:
        upsert_roles(roles)
    else:
        for role in roles:
            repo.upsert_role(role)

    for skill_id in skill_ids:
        skill = skills.get(skill_id) or Skill(
            id=skill_id,
            name=skill_id,
            ontology_version=get_settings().ontology_version,
        )
        repo.upsert_skill(skill)

    put_many = getattr(repo, "put_observations", None)
    if put_many is not None:
        put_many(pending)
    else:
        for obs in pending:
            repo.put_observation(obs)

    return {"roles": len(roles), "skills": len(skill_ids), "edges": len(pending)}


def run_pipeline(
    *,
    snapshot_store: PgSnapshotStore,
    posting_store: PgPostingStore,
    documents: PgDocumentStore,
    evidence_store: PgEvidenceStore,
    observations: ObservationStore,
    repo: Neo4jGraphRepository,
) -> dict:
    existing = getattr(posting_store, "count_all", lambda: 0)()
    if existing > 0:
        print(f"已有职位 {existing}，跳过物化", flush=True)
        n_postings = existing
    else:
        print("物化职位…", flush=True)
        n_postings = materialize_postings(snapshot_store, posting_store)
        print(f"  职位 {n_postings}", flush=True)
    print("抽取技能点…", flush=True)
    extracted = extract_and_observe(
        posting_store=posting_store,
        documents=documents,
        evidence_store=evidence_store,
        observations=observations,
    )
    role_names: dict[str, str] = extracted.pop("role_names")  # type: ignore[assignment]
    print(f"  观测 {extracted.get('observations')} 证据 {extracted.get('evidence')}", flush=True)
    print("写入图谱…", flush=True)
    graph = write_graph(observations=observations, repo=repo, role_names=role_names)
    print(f"  图谱 {graph}", flush=True)
    return {"postings": n_postings, "extract": extracted, "graph": graph}
