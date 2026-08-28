from app.pages.service import previous_period
from app.pipeline.ingest import role_id_for


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
