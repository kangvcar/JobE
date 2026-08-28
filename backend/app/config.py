from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ONTOLOGY_ROOT = Path(__file__).resolve().parents[2] / "ontology"


def default_ontology_version() -> str:
    """本体版本的唯一真源是 ontology/VERSION。

    图谱的 REQUIRES 边按 ontology_version 过滤，写入端与查询端一旦取到不同的值，
    查询会静默返回空结果而不报错。所以这里不留硬编码字面量。
    """
    version_file = ONTOLOGY_ROOT / "VERSION"
    if version_file.exists():
        version = version_file.read_text(encoding="utf-8").strip()
        if version:
            return version
    return "v0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "JobE"

    postgres_dsn: str = "postgresql://jobe:jobe@localhost:5432/jobe"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "jobe-dev-password"

    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_reviewer_model: str = "deepseek-reasoner"

    ontology_version: str = Field(default_factory=default_ontology_version)
    ontology_dir: str = str(ONTOLOGY_ROOT)

    # 采集频控。延迟只为降低空响，见 ADR 0001。
    collect_delay_seconds: float = 3.0
    collect_max_items: int = 2000
    liepin_enabled: bool = False
    zhipin_enabled: bool = False

    snapshot_dir: str = "./data/snapshots"


@lru_cache
def get_settings() -> Settings:
    return Settings()
