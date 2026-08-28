"""带权拓扑排序：依赖约束、紧迫度、成环降级。"""

from __future__ import annotations

from app.domain.models import Gap, GapKind
from app.matching.path import plan_learning_path

from .fakes import FakePrereqs


def _gap(skill_id: str, urgency: float, kind: GapKind = GapKind.MISSING) -> Gap:
    return Gap(
        skill_id=skill_id,
        kind=kind,
        required_importance=1.0,
        held_level=0,
        urgency=urgency,
    )


def _ids(path) -> list[str]:
    return [s.skill_id for s in path.steps]


def test_chain_respects_prerequisites():
    path = plan_learning_path(
        profile_id="p1",
        role_id="r1",
        gaps=[_gap("transformer", 0.9), _gap("torch", 0.5), _gap("python", 0.2)],
        prereq_source=FakePrereqs({"transformer": ["torch"], "torch": ["python"], "python": []}),
        satisfied=set(),
    )
    assert _ids(path) == ["python", "torch", "transformer"]
    assert path.steps[0].order == 1
    assert "torch" in path.steps[2].prerequisites


def test_urgency_orders_ready_nodes():
    # sql 与 python 都无前置；python 更紧迫所以在前，torch 等 python
    path = plan_learning_path(
        profile_id="p1",
        role_id="r1",
        gaps=[_gap("torch", 0.9), _gap("sql", 0.4), _gap("python", 0.7)],
        prereq_source=FakePrereqs({"torch": ["python"]}),
        satisfied=set(),
    )
    assert _ids(path) == ["python", "torch", "sql"]


def test_cycle_terminates_and_degrades_by_urgency():
    path = plan_learning_path(
        profile_id="p1",
        role_id="r1",
        gaps=[_gap("a", 3.0), _gap("b", 2.0), _gap("c", 1.0)],
        prereq_source=FakePrereqs({"a": ["c"], "b": ["a"], "c": ["b"]}),
        satisfied=set(),
    )
    assert set(_ids(path)) == {"a", "b", "c"}
    assert len(path.steps) == 3
    assert _ids(path) == ["a", "b", "c"]
    assert all("环" in s.reason for s in path.steps)


def test_cycle_does_not_reorder_downstream_outside_scc():
    # a→b→a 成环，d 依赖 a。d 不得排到环之前
    path = plan_learning_path(
        profile_id="p1",
        role_id="r1",
        gaps=[_gap("a", 1.0), _gap("b", 1.0), _gap("d", 9.0)],
        prereq_source=FakePrereqs({"a": ["b"], "b": ["a"], "d": ["a"]}),
        satisfied=set(),
    )
    ids = _ids(path)
    assert ids.index("a") < ids.index("d")
    assert ids.index("b") < ids.index("d")
    d_step = next(s for s in path.steps if s.skill_id == "d")
    assert "环" not in d_step.reason


def test_self_loop_is_ignored_and_emitted_once():
    path = plan_learning_path(
        profile_id="p1",
        role_id="r1",
        gaps=[_gap("loop", 1.0)],
        prereq_source=FakePrereqs({"loop": ["loop"]}),
        satisfied=set(),
    )
    assert _ids(path) == ["loop"]


def test_implicit_prereq_is_inserted_when_unsatisfied():
    path = plan_learning_path(
        profile_id="p1",
        role_id="r1",
        gaps=[_gap("torch", 0.8)],
        prereq_source=FakePrereqs({"torch": ["python"], "python": []}),
        satisfied=set(),
    )
    assert _ids(path) == ["python", "torch"]
    py = path.steps[0]
    assert "前置" in py.reason


def test_satisfied_prereq_is_not_a_step():
    path = plan_learning_path(
        profile_id="p1",
        role_id="r1",
        gaps=[_gap("torch", 0.8)],
        prereq_source=FakePrereqs({"torch": ["python"]}),
        satisfied={"python"},
    )
    assert _ids(path) == ["torch"]
    assert "python" in path.steps[0].prerequisites


def test_surplus_gaps_are_excluded():
    path = plan_learning_path(
        profile_id="p1",
        role_id="r1",
        gaps=[
            _gap("excel", 0.0, kind=GapKind.SURPLUS),
            _gap("python", 0.5),
        ],
        prereq_source=FakePrereqs(),
        satisfied=set(),
    )
    assert _ids(path) == ["python"]


def test_empty_gaps_yield_empty_path():
    path = plan_learning_path(
        profile_id="p1",
        role_id="r1",
        gaps=[],
        prereq_source=FakePrereqs(),
        satisfied=set(),
    )
    assert path.steps == []


def test_reason_explains_position():
    path = plan_learning_path(
        profile_id="p1",
        role_id="r1",
        gaps=[_gap("python", 1.2)],
        prereq_source=FakePrereqs(),
        satisfied=set(),
    )
    assert "当前可学" in path.steps[0].reason
    assert "1.20" in path.steps[0].reason
