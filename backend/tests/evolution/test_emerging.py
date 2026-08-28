"""新兴岗位发现：每个关卡都能单独否决；正式区 / 萌芽观察区分开。"""

from __future__ import annotations

from app.domain.models import Burst, PublishState
from app.evolution.cluster import Cooccurrence
from app.evolution.emerging import (
    GATE_BURST_SKILLS,
    GATE_CATALOG,
    GATE_CROSS_SOURCE,
    GATE_NEW_CLUSTER,
    GATE_ROLE_DIFF,
    ExistingRoleSkills,
    OccupationEntry,
    discover_emerging,
    evaluate_cluster,
)

NEW = ["llm", "rag", "agent", "eval"]
OLD = ["java", "spring", "mysql"]


def _burst(skill_id: str, source: str = "boss") -> Burst:
    return Burst(
        skill_id=skill_id,
        source_id=source,
        start_period="2024Q1",
        end_period="2024Q4",
        level=1,
        weight=4.0,
    )


def _clique(skills: list[str], source: str, period: str, weight: float = 4.0) -> list[Cooccurrence]:
    return [
        Cooccurrence(source, period, a, b, weight)
        for i, a in enumerate(skills)
        for b in skills[i + 1 :]
    ]


def _recent_two_sources() -> list[Cooccurrence]:
    edges: list[Cooccurrence] = []
    for period in ("2024Q1", "2024Q2", "2024Q3", "2024Q4"):
        edges.extend(_clique(NEW, "boss", period))
        edges.extend(_clique(NEW, "liepin", period))
    return edges


def _earlier_emptyish() -> list[Cooccurrence]:
    # 前期只有老簇，新簇尚未形成
    edges: list[Cooccurrence] = []
    for period in ("2023Q1", "2023Q2", "2023Q3", "2023Q4"):
        edges.extend(_clique(OLD, "boss", period, weight=2.0))
    return edges


def _passing_kwargs(**overrides):
    base = {
        "skill_ids": list(NEW),
        "recent_edges": _recent_two_sources(),
        "earlier_edges": _earlier_emptyish(),
        "bursts": [_burst(s) for s in NEW[:3]],
        "existing_roles": [ExistingRoleSkills("backend", tuple(OLD))],
        "catalog": [OccupationEntry("4-05-02-01", "软件开发工程师", tuple(OLD))],
        "name_hint": "llm-rag-agent",
    }
    base.update(overrides)
    return base


def test_gate_new_cluster_vetoes_stable_dense_cluster() -> None:
    earlier = []
    for period in ("2023Q1", "2023Q2", "2023Q3", "2023Q4"):
        earlier.extend(_clique(NEW, "boss", period))
        earlier.extend(_clique(NEW, "liepin", period))
    result = evaluate_cluster(**_passing_kwargs(earlier_edges=earlier))
    assert result.failed_gate == GATE_NEW_CLUSTER
    assert result.passed_all is False


def test_gate_burst_skills_vetoes_single_burst() -> None:
    result = evaluate_cluster(**_passing_kwargs(bursts=[_burst("llm")]))
    assert result.failed_gate == GATE_BURST_SKILLS


def test_gate_cross_source_vetoes_single_source() -> None:
    recent = []
    for period in ("2024Q1", "2024Q2", "2024Q3", "2024Q4"):
        recent.extend(_clique(NEW, "boss", period))
    result = evaluate_cluster(**_passing_kwargs(recent_edges=recent))
    assert result.failed_gate == GATE_CROSS_SOURCE


def test_gate_role_diff_vetoes_existing_variant() -> None:
    result = evaluate_cluster(
        **_passing_kwargs(existing_roles=[ExistingRoleSkills("llm-eng", tuple(NEW))])
    )
    assert result.failed_gate == GATE_ROLE_DIFF


def test_gate_catalog_vetoes_national_occupation() -> None:
    result = evaluate_cluster(
        **_passing_kwargs(catalog=[OccupationEntry("9-99-99-01", "智能体工程师", tuple(NEW))])
    )
    assert result.failed_gate == GATE_CATALOG


def test_all_gates_pass() -> None:
    result = evaluate_cluster(**_passing_kwargs())
    assert result.passed_all
    assert result.failed_gate is None
    assert result.signal_strength > 0
    assert result.evidence_count >= 2


def test_discover_splits_publish_and_watch_zones() -> None:
    edges = _earlier_emptyish() + _recent_two_sources()
    for period in ("2024Q1", "2024Q2", "2024Q3", "2024Q4"):
        edges.extend(_clique(OLD, "boss", period, weight=2.0))
    bursts = [_burst(s) for s in NEW]
    result = discover_emerging(
        edges=edges,
        bursts=bursts,
        existing_roles=[ExistingRoleSkills("backend", tuple(OLD))],
        catalog=[OccupationEntry("4-05-02-01", "软件开发工程师", tuple(OLD))],
        ontology_version="v0",
        current_period="2024Q4",
    )
    found = result.publish_queue + result.watch_zone
    assert found, "通过全部关卡的簇应进入某一区"
    overlapping = [c for c in found if set(NEW) & set(c.skill_ids)]
    assert overlapping
    for cand in result.publish_queue:
        assert cand.zone == "publish"
        assert cand.role.state == PublishState.HELD
        assert cand.role.occupation_code is None
        assert cand.role.is_emerging is False
    for cand in result.watch_zone:
        assert cand.zone == "watch"
        assert cand.role.state == PublishState.UNVERIFIED


def test_namer_runs_only_after_gates() -> None:
    called: list[list[str]] = []

    def namer(skill_ids: list[str]) -> tuple[str, str]:
        called.append(skill_ids)
        return "智能体应用工程师", "负责检索增强与多智能体编排"

    edges = _earlier_emptyish() + _recent_two_sources()
    discover_emerging(
        edges=edges,
        bursts=[_burst(s) for s in NEW],
        existing_roles=[ExistingRoleSkills("backend", tuple(OLD))],
        catalog=[],
        ontology_version="v0",
        current_period="2024Q4",
        namer=namer,
    )
    assert called, "过关后才命名"
    # 被否决的老簇不应触发命名：namer 只拿到含新技能的簇
    assert all("llm" in ids or "rag" in ids for ids in called)


def test_catalog_name_match_without_skill_ids() -> None:
    result = evaluate_cluster(
        **_passing_kwargs(catalog=[OccupationEntry("9-99-99-01", "llm-rag-agent")])
    )
    assert result.failed_gate == GATE_CATALOG


def test_empty_existing_roles_and_empty_graph() -> None:
    result = evaluate_cluster(**_passing_kwargs(existing_roles=[]))
    assert result.passed_all
    empty = discover_emerging([], [], [], [], "v0")
    assert empty.publish_queue == []
    assert empty.watch_zone == []


def test_watch_zone_for_borderline_signal() -> None:
    """密度刚翻倍、仅 2 个突增、与既有岗位半重叠 → 过关但进萌芽观察区。"""
    weak = ["cuda", "triton", "cutlass"]
    earlier: list[Cooccurrence] = []
    recent: list[Cooccurrence] = []
    for period in ("2023Q1", "2023Q2", "2023Q3", "2023Q4"):
        earlier.extend(_clique(weak, "boss", period, weight=2.0))
        earlier.extend(_clique(weak, "liepin", period, weight=2.0))
    for period in ("2024Q1", "2024Q2", "2024Q3", "2024Q4"):
        recent.extend(_clique(weak, "boss", period, weight=4.0))
        recent.extend(_clique(weak, "liepin", period, weight=4.0))
    result = evaluate_cluster(
        skill_ids=weak,
        recent_edges=recent,
        earlier_edges=earlier,
        bursts=[_burst("cuda"), _burst("triton")],
        existing_roles=[ExistingRoleSkills("gpu-eng", ("cuda", "triton", "python"))],
        catalog=[],
        name_hint="cuda-triton-cutlass",
    )
    assert result.passed_all
    assert result.signal_strength < 0.65

    edges = earlier + recent
    discovered = discover_emerging(
        edges=edges,
        bursts=[_burst("cuda"), _burst("triton")],
        existing_roles=[ExistingRoleSkills("gpu-eng", ("cuda", "triton", "python"))],
        catalog=[],
        ontology_version="v0",
        current_period="2024Q4",
    )
    assert discovered.watch_zone
    assert all(c.zone == "watch" for c in discovered.watch_zone)
