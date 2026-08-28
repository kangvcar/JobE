from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from neo4j import RoutingControl

from app.graph.migrate import SCHEMA_PATH, apply_schema, iter_schema_statements
from app.graph.session import Neo4jExecutor, create_driver
from tests.graph.fakes import FakeExecutor


def test_iter_schema_statements_skips_comments() -> None:
    text = """
// comment
CREATE CONSTRAINT role_id IF NOT EXISTS FOR (r:Role) REQUIRE r.id IS UNIQUE;
CREATE INDEX skill_name IF NOT EXISTS FOR (s:Skill) ON (s.name);
"""
    stmts = iter_schema_statements(text)
    assert len(stmts) == 2
    assert "CONSTRAINT role_id" in stmts[0]
    assert not stmts[0].endswith(";")
    assert "INDEX skill_name" in stmts[1]


def test_apply_schema_runs_real_file() -> None:
    executor = FakeExecutor()
    count = apply_schema(executor, SCHEMA_PATH)
    # 不断言条数，否则每加一条约束都要改测试。要保证的是每条都被当写操作执行、
    # 且都带 IF NOT EXISTS（apply_schema 允许反复调用）。
    assert count == len(executor.calls) > 0
    assert all(write for _, _, write in executor.calls)
    assert all("IF NOT EXISTS" in cypher for cypher, _, _ in executor.calls)
    joined = " ".join(cypher for cypher, _, _ in executor.calls)
    assert "CREATE CONSTRAINT role_id IF NOT EXISTS" in joined
    assert "CREATE INDEX skill_ontology IF NOT EXISTS" in joined
    # MERGE (ch:CompetencyChange {id}) 依赖这条约束才并发安全
    assert "CREATE CONSTRAINT change_id IF NOT EXISTS" in joined
    # 跨多行的复合关系索引也要能被拆出来
    assert "ON (req.period, req.ontology_version)" in joined
    assert SCHEMA_PATH == Path(__file__).resolve().parents[2] / "graph_schema.cypher"


def test_create_driver_uses_settings() -> None:
    settings = SimpleNamespace(
        neo4j_uri="bolt://example:7687",
        neo4j_user="neo4j",
        neo4j_password="secret",
    )
    with (
        patch("app.graph.session.get_settings", return_value=settings),
        patch("app.graph.session.GraphDatabase.driver") as driver_ctor,
    ):
        create_driver()
    driver_ctor.assert_called_once_with("bolt://example:7687", auth=("neo4j", "secret"))


def test_neo4j_executor_run_write_and_read() -> None:
    record = MagicMock()
    record.data.return_value = {"id": "r1"}
    driver = MagicMock()
    driver.execute_query.return_value = ([record], None, None)
    executor = Neo4jExecutor(driver, database="neo4j")

    rows = executor.run("RETURN 1", {"x": 1}, write=True)
    assert rows == [{"id": "r1"}]
    driver.execute_query.assert_called_with(
        "RETURN 1",
        {"x": 1},
        database_="neo4j",
        routing_=RoutingControl.WRITE,
    )

    executor.run("MATCH (n) RETURN n")
    assert driver.execute_query.call_args.kwargs["routing_"] == RoutingControl.READ
