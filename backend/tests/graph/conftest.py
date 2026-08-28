"""图谱层测试夹具。"""


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "integration: 需要真实 Neo4j")
