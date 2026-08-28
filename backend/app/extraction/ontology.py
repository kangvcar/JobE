"""技能词表读取接口。

按顺序在这些位置找 skills.json / skills.jsonl：
  {ontology_dir}/{version}/   固定版本快照
  {ontology_dir}/data/        本体构建脚本的默认产出目录
  {ontology_dir}/

每条至少含 id、name；aliases 可选。也接受 {"skills": [...]} 包装。
同目录下若有 aliases.jsonl（skill_id + surface），其表层形式会并入对应技能点——
skills.jsonl 内嵌的 aliases 只是子集，只读它会丢掉大部分可匹配写法。

短拉丁名（Go/C/R）一律用规范大小写。这里不采纳 aliases.jsonl 里的
surface_folded（已折叠为小写），否则 "go"、"r" 这类小写形式会让匹配器满篇误命中；
大小写折叠是匹配器的事。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from app.config import ONTOLOGY_ROOT, get_settings

logger = logging.getLogger("jobe.extraction.ontology")


@dataclass(frozen=True)
class SkillVocabEntry:
    id: str
    name: str
    aliases: list[str] = field(default_factory=list)

    def surface_forms(self) -> list[str]:
        forms = [self.name, *self.aliases]
        seen: set[str] = set()
        out: list[str] = []
        for f in forms:
            if f and f not in seen:
                seen.add(f)
                out.append(f)
        return out


def default_ontology_dir() -> Path:
    return ONTOLOGY_ROOT


def _candidate_dirs(root: Path, version: str) -> Iterator[Path]:
    yield root / version
    yield root / "data"
    yield root


def load_skill_vocab(
    ontology_dir: Path | str | None = None,
    version: str | None = None,
) -> list[SkillVocabEntry]:
    root = Path(ontology_dir) if ontology_dir else default_ontology_dir()
    version = version or get_settings().ontology_version
    searched: list[Path] = []
    for directory in _candidate_dirs(root, version):
        searched.append(directory)
        for name, loader in (("skills.json", _from_json), ("skills.jsonl", _from_jsonl)):
            path = directory / name
            if path.exists():
                entries = loader(path)
                return _merge_alias_table(entries, directory / "aliases.jsonl")
    logger.warning(
        "技能词表不存在，将只用 LLM 通道。已找过：%s",
        "、".join(str(p) for p in searched),
    )
    return []


def _merge_alias_table(entries: list[SkillVocabEntry], alias_path: Path) -> list[SkillVocabEntry]:
    if not alias_path.exists():
        return entries
    extra: dict[str, list[str]] = {}
    for line in alias_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        skill_id, surface = obj.get("skill_id"), obj.get("surface")
        if skill_id and surface:
            extra.setdefault(str(skill_id), []).append(str(surface))
    if not extra:
        return entries
    merged: list[SkillVocabEntry] = []
    for entry in entries:
        surfaces = extra.get(entry.id)
        if not surfaces:
            merged.append(entry)
            continue
        aliases = list(entry.aliases)
        known = {entry.name, *aliases}
        for surface in surfaces:
            if surface not in known:
                known.add(surface)
                aliases.append(surface)
        merged.append(SkillVocabEntry(id=entry.id, name=entry.name, aliases=aliases))
    return merged


def _from_json(path: Path) -> list[SkillVocabEntry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        items = raw.get("skills") or raw.get("items") or []
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError(f"无法解析词表：{path}")
    return [_entry(x) for x in items if isinstance(x, dict) and x.get("id") and x.get("name")]


def _from_jsonl(path: Path) -> list[SkillVocabEntry]:
    items: list[SkillVocabEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if obj.get("id") and obj.get("name"):
            items.append(_entry(obj))
    return items


def _entry(obj: dict) -> SkillVocabEntry:
    aliases = obj.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    return SkillVocabEntry(
        id=str(obj["id"]), name=str(obj["name"]), aliases=[str(a) for a in aliases]
    )
