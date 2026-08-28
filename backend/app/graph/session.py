"""Neo4j 连接与薄执行器。测试注入假执行器，不连真实数据库。"""

from __future__ import annotations

from typing import Any, Protocol

from neo4j import Driver, GraphDatabase, RoutingControl

from app.config import get_settings


class CypherExecutor(Protocol):
    """Cypher 执行缝。仓储与查询只依赖这个协议，方便单测断言语句与参数。"""

    def run(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        *,
        write: bool = False,
    ) -> list[dict[str, Any]]: ...


class Neo4jExecutor:
    def __init__(self, driver: Driver, database: str = "neo4j") -> None:
        self._driver = driver
        self._database = database

    def run(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        *,
        write: bool = False,
    ) -> list[dict[str, Any]]:
        routing = RoutingControl.WRITE if write else RoutingControl.READ
        records, _, _ = self._driver.execute_query(
            cypher,
            params or {},
            database_=self._database,
            routing_=routing,
        )
        return [record.data() for record in records]


def create_driver() -> Driver:
    settings = get_settings()
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
