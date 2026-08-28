"""把已落库的快照变成职位、技能观测和图谱边。

高精度通道只用 Aho-Corasick，不调大模型：有正文就能抽技能点，证据落在原文偏移上。
岗位按标题归一化聚类——语义合并是图谱层的事，这里只保证同一写法进同一个岗位。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
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
) -> dict[str, int]:
    vocab = vocab if vocab is not None else load_skill_vocab()
    ac, skill_ids = build_automaton(vocab)
    version = get_settings().ontology_version
    fetched_at = datetime.now(UTC)

    # role_id -> name
    role_names: dict[str, str] = {}
    # (role_id, period) -> posting ids that have description
    role_period_posts: dict[tuple[str, str], set[str]] = defaultdict(set)
    # (role_id, period, skill_id) -> posting ids mentioning the skill
    role_skill_posts: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    skills_of: dict[tuple[str, str], set[str]] = defaultdict(set)
    evidence_n = 0
    scanned = 0

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
        documents.save(posting.id, text, kind="posting")
        role_period_posts[(rid, period)].add(posting.id)
        seen: set[str] = set()
        for start, end, skill_id, surface in scan_text(text, ac, skill_ids):
            if skill_id in seen:
                continue
            seen.add(skill_id)
            role_skill_posts[(rid, period, skill_id)].add(posting.id)
            skills_of[(rid, period)].add(skill_id)
            ev = Evidence(
                id=f"ev.{posting.id}.{skill_id}.{start}",
                source_id=posting.source_id,
                span=TextSpan(doc_id=posting.id, start=start, end=end),
                quote=surface,
                fetched_at=fetched_at,
                extractor=f"{EXTRACTOR}:{skill_id}",
                confidence=0.9,
                posting_id=posting.id,
            )
            evidence_store.save(ev)
            evidence_n += 1

    obs_n = 0
    for (rid, period), posts in role_period_posts.items():
        total = len(posts)
        if total == 0:
            continue
        skill_keys = skills_of.get((rid, period), set())
        for skill_id in skill_keys:
            count = len(role_skill_posts[(rid, period, skill_id)])
            observations.put(
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
            obs_n += 1

    return {
        "roles": len(role_names),
        "scanned": scanned,
        "evidence": evidence_n,
        "observations": obs_n,
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
    roles_n = 0
    skills_n = 0
    edges_n = 0
    written_skills: set[str] = set()
    written_roles: set[str] = set()

    for obs in observations.iter_all():
        if not obs.role_id:
            continue
        if obs.role_id not in written_roles:
            repo.upsert_role(
                Role(
                    id=obs.role_id,
                    name=role_names.get(obs.role_id, obs.role_id),
                    state=PublishState.PUBLISHED,
                )
            )
            written_roles.add(obs.role_id)
            roles_n += 1
        if obs.skill_id not in written_skills:
            skill = skills.get(obs.skill_id) or Skill(
                id=obs.skill_id,
                name=obs.skill_id,
                ontology_version=obs.ontology_version,
            )
            repo.upsert_skill(skill)
            written_skills.add(obs.skill_id)
            skills_n += 1
        repo.put_observation(obs)
        edges_n += 1
    return {"roles": roles_n, "skills": skills_n, "edges": edges_n}


def run_pipeline(
    *,
    snapshot_store: PgSnapshotStore,
    posting_store: PgPostingStore,
    documents: PgDocumentStore,
    evidence_store: PgEvidenceStore,
    observations: ObservationStore,
    repo: Neo4jGraphRepository,
) -> dict:
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
