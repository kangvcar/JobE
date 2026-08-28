from __future__ import annotations

import json

from app.extraction.ontology import SkillVocabEntry, load_skill_vocab


def test_load_missing_dir(tmp_path, caplog):
    caplog.set_level("WARNING")
    assert load_skill_vocab(tmp_path, "v0") == []
    assert "技能词表不存在" in caplog.text


def test_load_from_data_dir_merges_alias_table(tmp_path):
    """本体构建脚本产出到 data/，别名表另存一份。两者都要读到。"""
    data = tmp_path / "data"
    data.mkdir()
    (data / "skills.jsonl").write_text(
        '{"id": "skill.rust", "name": "Rust", "aliases": ["rust"]}\n'
        '{"id": "skill.css", "name": "CSS"}\n',
        encoding="utf-8",
    )
    (data / "aliases.jsonl").write_text(
        '{"skill_id": "skill.rust", "surface": "Rust语言", "surface_folded": "rust语言"}\n'
        '{"skill_id": "skill.rust", "surface": "rust"}\n'
        '{"skill_id": "skill.unknown", "surface": "野别名"}\n',
        encoding="utf-8",
    )
    items = {i.id: i for i in load_skill_vocab(tmp_path, "0.1.0")}
    assert set(items) == {"skill.rust", "skill.css"}
    # 别名表的 surface 并入，重复的不重复计入，surface_folded 不采纳
    assert items["skill.rust"].aliases == ["rust", "Rust语言"]
    assert items["skill.css"].aliases == []


def test_version_dir_wins_over_data_dir(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "skills.jsonl").write_text('{"id": "d", "name": "D"}\n', encoding="utf-8")
    pinned = tmp_path / "0.9.0"
    pinned.mkdir()
    (pinned / "skills.jsonl").write_text('{"id": "p", "name": "P"}\n', encoding="utf-8")
    assert [i.id for i in load_skill_vocab(tmp_path, "0.9.0")] == ["p"]


def test_load_jsonl_and_wrapped(tmp_path):
    v = tmp_path / "v1"
    v.mkdir()
    (v / "skills.jsonl").write_text(
        '{"id": "a", "name": "A"}\n{"id": "b", "name": "B", "aliases": "bee"}\n',
        encoding="utf-8",
    )
    items = load_skill_vocab(tmp_path, "v1")
    assert {i.id for i in items} == {"a", "b"}
    assert items[1].aliases == ["bee"]

    v2 = tmp_path / "v2"
    v2.mkdir()
    (v2 / "skills.json").write_text(
        json.dumps({"skills": [{"id": "c", "name": "C", "aliases": ["cc"]}]}),
        encoding="utf-8",
    )
    wrapped = load_skill_vocab(tmp_path, "v2")
    assert wrapped == [SkillVocabEntry(id="c", name="C", aliases=["cc"])]
