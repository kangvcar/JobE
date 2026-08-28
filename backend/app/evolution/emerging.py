"""新兴岗位发现：统计信号决策，大模型只给已过关的簇命名。

关卡全部通过才成为候选岗位。严格阈值以上进正式发布流程（仍须人工拦截
首次发布），未达标进萌芽观察区并携带信号强度与证据条数。
「是不是新岗位」绝不问大模型。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import md5
from math import log2

from app.domain.models import Burst, PublishState, Role, SkillCluster
from app.evolution.cluster import (
    Cooccurrence,
    build_cooccurrence_graph,
    cluster_skills,
    induced_density,
)
from app.evolution.periods import parse_period

# --- 阈值。改默认值前先看依据；测试会覆盖部分值，但生产默认写在这里。 ---

# 最近 4 个时间片（一年）算「当前窗口」。更短会被单季噪声带动，更长会把已稳定簇当成新的。
NEW_CLUSTER_LOOKBACK = 4
# 当前窗口簇内密度相对前期翻倍，视为密度突增。与 Kleinberg s=2 同一量级直觉。
DENSITY_BURST_RATIO = 2.0
# 「多个技能点处于突增」的下限。单技能突增更像既有岗位的一项能力变化，撑不起新岗位。
MIN_BURST_SKILLS = 2
# 至少两个来源观察到该簇。单源可能是平台推荐算法扭曲；双源对应证据等级 multi_source 下限。
MIN_SOURCES = 2
# 该来源覆盖簇内至少一半技能点，才算「观察到该簇」。
MIN_SOURCE_SKILL_COVERAGE = 0.5
# 与既有岗位技能集合的 Jaccard 距离低于此，视为既有岗位变体。60% 重叠已经是同一角色。
MIN_ROLE_DIFF = 0.4
# 簇至少 3 个技能点。两个点写不出职责，也过不了「多个突增」的独立性。
MIN_CLUSTER_SIZE = 3
# 综合信号强度达线进正式发布流程，否则进萌芽观察区。
# 0.65 要求多数分项过中线，避免单科满分混进正式区。
PUBLISH_SIGNAL_THRESHOLD = 0.65

GATE_NEW_CLUSTER = "new_cluster"
GATE_BURST_SKILLS = "burst_skills"
GATE_CROSS_SOURCE = "cross_source"
GATE_ROLE_DIFF = "role_diff"
GATE_CATALOG = "occupation_catalog"

ALL_GATES = (
    GATE_NEW_CLUSTER,
    GATE_BURST_SKILLS,
    GATE_CROSS_SOURCE,
    GATE_ROLE_DIFF,
    GATE_CATALOG,
)


@dataclass(frozen=True)
class OccupationEntry:
    code: str
    name: str
    skill_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExistingRoleSkills:
    role_id: str
    skill_ids: tuple[str, ...]
    occupation_code: str | None = None


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ClusterEvaluation:
    skill_ids: list[str]
    gates: list[GateResult]
    passed_all: bool
    signal_strength: float
    evidence_count: int
    failed_gate: str | None
    density_ratio: float = 0.0
    n_burst_skills: int = 0
    n_sources: int = 0
    min_role_diff: float = 1.0


@dataclass
class EmergingCandidate:
    role: Role
    zone: str  # publish | watch
    skill_ids: list[str]
    evidence_count: int
    signal_strength: float
    gates: list[GateResult] = field(default_factory=list)


@dataclass
class EmergingDiscoveryResult:
    publish_queue: list[EmergingCandidate]
    watch_zone: list[EmergingCandidate]


def discover_emerging(
    edges: list[Cooccurrence],
    bursts: list[Burst],
    existing_roles: list[ExistingRoleSkills],
    catalog: list[OccupationEntry],
    ontology_version: str,
    current_period: str | None = None,
    *,
    namer: Callable[[list[str]], tuple[str, str]] | None = None,
) -> EmergingDiscoveryResult:
    """namer 只在全部关卡通过后调用，返回 (名称, 职责描述)。不传入则用技能点 id 拼接。"""
    recent, earlier = _split_windows(edges, current_period)
    recent_edges = [e for e in edges if e.period in recent]
    earlier_edges = [e for e in edges if e.period in earlier]
    clusters = [
        c
        for c in cluster_skills(recent_edges, ontology_version)
        if len(c.skill_ids) >= MIN_CLUSTER_SIZE
    ]
    publish_queue: list[EmergingCandidate] = []
    watch_zone: list[EmergingCandidate] = []
    for cluster in clusters:
        evaluation = evaluate_cluster(
            cluster.skill_ids,
            recent_edges=recent_edges,
            earlier_edges=earlier_edges,
            bursts=bursts,
            existing_roles=existing_roles,
            catalog=catalog,
            name_hint=cluster.name,
        )
        if not evaluation.passed_all:
            continue
        candidate = _to_candidate(cluster, evaluation, ontology_version, namer)
        if candidate.zone == "publish":
            publish_queue.append(candidate)
        else:
            watch_zone.append(candidate)
    publish_queue.sort(key=lambda c: c.signal_strength, reverse=True)
    watch_zone.sort(key=lambda c: c.signal_strength, reverse=True)
    return EmergingDiscoveryResult(publish_queue=publish_queue, watch_zone=watch_zone)


def evaluate_cluster(
    skill_ids: list[str],
    *,
    recent_edges: list[Cooccurrence],
    earlier_edges: list[Cooccurrence],
    bursts: list[Burst],
    existing_roles: list[ExistingRoleSkills],
    catalog: list[OccupationEntry],
    name_hint: str = "",
) -> ClusterEvaluation:
    ids = set(skill_ids)
    recent_g = build_cooccurrence_graph(recent_edges)
    earlier_g = build_cooccurrence_graph(earlier_edges)
    dens_now = induced_density(recent_g, ids)
    dens_then = induced_density(earlier_g, ids)
    if dens_then <= 0:
        density_ratio = float("inf") if dens_now > 0 else 0.0
        is_new = dens_now > 0
    else:
        density_ratio = dens_now / dens_then
        is_new = density_ratio >= DENSITY_BURST_RATIO
    bursting = {b.skill_id for b in bursts if b.skill_id in ids}
    n_burst = len(bursting)
    sources = _sources_observing(ids, recent_edges)
    n_sources = len(sources)
    min_diff, nearest = _min_role_diff(ids, existing_roles)
    catalog_hit = _catalog_match(ids, name_hint, catalog)

    gates = [
        GateResult(
            GATE_NEW_CLUSTER,
            is_new,
            f"density_ratio={density_ratio if density_ratio != float('inf') else 'inf'}",
        ),
        GateResult(GATE_BURST_SKILLS, n_burst >= MIN_BURST_SKILLS, f"n_burst={n_burst}"),
        GateResult(GATE_CROSS_SOURCE, n_sources >= MIN_SOURCES, f"n_sources={n_sources}"),
        GateResult(
            GATE_ROLE_DIFF,
            min_diff >= MIN_ROLE_DIFF,
            f"min_jaccard_distance={min_diff:.3f} nearest={nearest}",
        ),
        GateResult(
            GATE_CATALOG,
            catalog_hit is None,
            "no catalog entry" if catalog_hit is None else f"matched {catalog_hit}",
        ),
    ]
    failed = next((g.name for g in gates if not g.passed), None)
    evidence_count = n_sources + n_burst + _internal_edge_count(recent_g, ids)
    strength = _signal_strength(n_burst, len(ids), n_sources, min_diff, density_ratio)
    return ClusterEvaluation(
        skill_ids=sorted(ids),
        gates=gates,
        passed_all=failed is None,
        signal_strength=strength,
        evidence_count=evidence_count,
        failed_gate=failed,
        density_ratio=density_ratio if density_ratio != float("inf") else 99.0,
        n_burst_skills=n_burst,
        n_sources=n_sources,
        min_role_diff=min_diff,
    )


def _to_candidate(
    cluster: SkillCluster,
    evaluation: ClusterEvaluation,
    ontology_version: str,
    namer: Callable[[list[str]], tuple[str, str]] | None,
) -> EmergingCandidate:
    if namer is not None:
        name, responsibility = namer(evaluation.skill_ids)
        responsibilities = [responsibility] if responsibility else []
    else:
        name = cluster.name
        responsibilities = []
    digest = md5(
        f"{ontology_version}:{','.join(evaluation.skill_ids)}".encode(), usedforsecurity=False
    ).hexdigest()[:12]
    zone = "publish" if evaluation.signal_strength >= PUBLISH_SIGNAL_THRESHOLD else "watch"
    role = Role(
        id=f"cand-{digest}",
        name=name,
        occupation_code=None,
        is_emerging=False,
        state=PublishState.HELD if zone == "publish" else PublishState.UNVERIFIED,
        signal_strength=evaluation.signal_strength,
        evidence_ids=[],
        responsibilities=responsibilities,
    )
    return EmergingCandidate(
        role=role,
        zone=zone,
        skill_ids=evaluation.skill_ids,
        evidence_count=evaluation.evidence_count,
        signal_strength=evaluation.signal_strength,
        gates=evaluation.gates,
    )


def _split_windows(
    edges: list[Cooccurrence], current_period: str | None
) -> tuple[set[str], set[str]]:
    periods = sorted({e.period for e in edges}, key=parse_period)
    if not periods:
        return set(), set()
    if current_period and current_period in periods:
        periods = [p for p in periods if parse_period(p) <= parse_period(current_period)]
    recent = set(periods[-NEW_CLUSTER_LOOKBACK:])
    if len(periods) > NEW_CLUSTER_LOOKBACK:
        earlier = set(periods[:-NEW_CLUSTER_LOOKBACK])
    else:
        earlier = set()
    return recent, earlier


def _sources_observing(skill_ids: set[str], edges: list[Cooccurrence]) -> set[str]:
    by_source: dict[str, set[str]] = {}
    internal: dict[str, int] = {}
    for edge in edges:
        if edge.skill_a in skill_ids:
            by_source.setdefault(edge.source_id, set()).add(edge.skill_a)
        if edge.skill_b in skill_ids:
            by_source.setdefault(edge.source_id, set()).add(edge.skill_b)
        if edge.skill_a in skill_ids and edge.skill_b in skill_ids:
            internal[edge.source_id] = internal.get(edge.source_id, 0) + 1
    need = max(2, int(MIN_SOURCE_SKILL_COVERAGE * len(skill_ids) + 0.999))
    observed: set[str] = set()
    for source_id, nodes in by_source.items():
        if len(nodes) >= need and internal.get(source_id, 0) >= 1:
            observed.add(source_id)
    return observed


def _min_role_diff(
    skill_ids: set[str], existing_roles: list[ExistingRoleSkills]
) -> tuple[float, str]:
    if not existing_roles:
        return 1.0, ""
    best = 1.0
    nearest = ""
    for role in existing_roles:
        other = set(role.skill_ids)
        union = skill_ids | other
        if not union:
            continue
        dist = 1.0 - len(skill_ids & other) / len(union)
        if dist < best:
            best = dist
            nearest = role.role_id
    return best, nearest


def _catalog_match(
    skill_ids: set[str], name_hint: str, catalog: list[OccupationEntry]
) -> str | None:
    hint = _norm_name(name_hint)
    for entry in catalog:
        if entry.skill_ids:
            other = set(entry.skill_ids)
            union = skill_ids | other
            if union and 1.0 - len(skill_ids & other) / len(union) < MIN_ROLE_DIFF:
                return entry.code
        entry_name = _norm_name(entry.name)
        if entry_name and hint and (entry_name in hint or hint in entry_name):
            return entry.code
    return None


def _norm_name(name: str) -> str:
    return "".join(name.lower().split())


def _internal_edge_count(graph, skill_ids: set[str]) -> int:
    nodes = [n for n in skill_ids if n in graph]
    count = 0
    for i, a in enumerate(nodes):
        for b in nodes[i + 1 :]:
            if graph.has_edge(a, b):
                count += 1
    return count


def _signal_strength(
    n_burst: int,
    n_skills: int,
    n_sources: int,
    min_role_diff: float,
    density_ratio: float,
) -> float:
    """四项简单平均，不搞不可解释的加权。每项 [0,1]。"""
    burst_frac = n_burst / n_skills if n_skills else 0.0
    source_score = min(n_sources / 3.0, 1.0)
    diff_score = min(min_role_diff / 0.8, 1.0)
    if density_ratio == float("inf"):
        density_score = 1.0
    elif density_ratio <= 1.0:
        density_score = 0.0
    else:
        # log2(ratio)/2：翻倍→0.5，四倍→1.0
        density_score = min(log2(density_ratio) / 2.0, 1.0)
    return (burst_frac + source_score + diff_score + density_score) / 4.0
