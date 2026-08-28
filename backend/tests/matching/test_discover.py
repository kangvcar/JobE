"""反向推荐：按连续分值排序。"""

from __future__ import annotations

from app.domain.models import MatchTier, Role
from app.matching.discover import recommend_roles

from .fakes import FakeRequirements, numbered_specs, profile_holding, spec


def _role(role_id: str, name: str) -> Role:
    return Role(id=role_id, name=name)


def test_orders_by_continuous_score():
    source = FakeRequirements(
        roles={
            "intern": _role("intern", "Python 实习"),
            "data": _role("data", "数据工程"),
            "ml": _role("ml", "机器学习"),
        },
        specs={
            "intern": [spec("python")],
            "data": [spec("python"), spec("sql"), spec("spark"), spec("airflow")],
            "ml": [spec("python"), spec("torch"), spec("sql"), spec("spark"), spec("k8s")],
        },
    )
    profile = profile_holding(["python", "sql", "spark"])
    items = recommend_roles(profile, source, top_k=5)
    assert [i.role_id for i in items] == ["intern", "data", "ml"]
    assert items[0].score > items[1].score > items[2].score
    assert items[0].tier is MatchTier.STRONG
    assert items[1].tier is MatchTier.ADEQUATE
    assert all(0.0 <= i.score <= 1.0 for i in items)
    # 同档也可能分值不同：再造两个基本匹配
    assert items[1].coverage > items[2].coverage


def test_skips_roles_without_specs():
    source = FakeRequirements(
        roles={"empty": _role("empty", "空"), "ok": _role("ok", "有要求")},
        specs={"ok": numbered_specs(4)},
    )
    items = recommend_roles(profile_holding(["s00", "s01", "s02", "s03"]), source)
    assert [i.role_id for i in items] == ["ok"]


def test_exclude_role_id():
    source = FakeRequirements(
        roles={"a": _role("a", "A"), "b": _role("b", "B")},
        specs={"a": numbered_specs(3), "b": numbered_specs(3)},
    )
    items = recommend_roles(profile_holding(["s00", "s01", "s02"]), source, exclude_role_id="a")
    assert [i.role_id for i in items] == ["b"]


def test_top_k():
    source = FakeRequirements(
        roles={f"r{i}": _role(f"r{i}", f"岗{i}") for i in range(6)},
        specs={f"r{i}": numbered_specs(5) for i in range(6)},
    )
    items = recommend_roles(profile_holding(["s00"]), source, top_k=3)
    assert len(items) == 3


def test_tie_breaks_by_role_id():
    source = FakeRequirements(
        roles={"b": _role("b", "B"), "a": _role("a", "A")},
        specs={"a": numbered_specs(2), "b": numbered_specs(2)},
    )
    items = recommend_roles(profile_holding(["s00", "s01"]), source)
    assert [i.role_id for i in items] == ["a", "b"]
