"""幂等执行 graph_schema.cypher 中的约束与索引。"""

from __future__ import annotations

from pathlib import Path

from app.graph.session import CypherExecutor

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "graph_schema.cypher"


def iter_schema_statements(text: str) -> list[str]:
    """拆出可执行语句。注释与空行丢弃；一条语句可跨多行。"""
    statements: list[str] = []
    buf: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("//"):
            continue
        buf.append(stripped)
        if stripped.endswith(";"):
            stmt = " ".join(buf).rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            buf = []
    tail = " ".join(buf).rstrip(";").strip()
    if tail:
        statements.append(tail)
    return statements


def apply_schema(executor: CypherExecutor, schema_path: Path | None = None) -> int:
    """执行约束/索引，语句均带 IF NOT EXISTS，可重复调用。返回执行条数。"""
    path = schema_path or SCHEMA_PATH
    statements = iter_schema_statements(path.read_text(encoding="utf-8"))
    for stmt in statements:
        executor.run(stmt, write=True)
    return len(statements)
