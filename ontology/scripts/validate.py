"""校验本体：id 唯一、别名无跨技能点冲突、parent_id 存在、无环、必填字段齐全。"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

REQUIRED_SKILL = (
    "id",
    "name",
    "name_zh",
    "name_en",
    "aliases",
    "cluster",
    "direction",
    "sources",
    "ontology_version",
)


def load_jsonl(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        raise SystemExit(f"缺少 {path}，先跑 build.py")
    rows = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{name}:{i} JSON 无法解析: {e}") from e
    return rows


def main() -> int:
    errors: list[str] = []
    skills = load_jsonl("skills.jsonl")
    aliases = load_jsonl("aliases.jsonl")
    clusters = load_jsonl("clusters.jsonl")
    occupations = load_jsonl("occupations.jsonl")
    new_occs = load_jsonl("new_occupations.jsonl")

    if len(skills) < 600:
        errors.append(f"技能点 {len(skills)} 条，少于 600")
    if len(aliases) < 2 * len(skills):
        errors.append(f"别名 {len(aliases)} 条，不足技能点数量的 2 倍（{2 * len(skills)}）")

    skill_ids: set[str] = set()
    for s in skills:
        sid = s.get("id")
        if not sid:
            errors.append("技能点缺 id")
            continue
        if sid in skill_ids:
            errors.append(f"技能点 id 重复: {sid}")
        skill_ids.add(sid)
        for key in REQUIRED_SKILL:
            if key not in s or s[key] in (None, "", []):
                errors.append(f"{sid} 缺必填字段 {key}")
        if not isinstance(s.get("aliases"), list) or len(s.get("aliases") or []) < 1:
            errors.append(f"{sid} 别名不足 1 个")
        if s.get("direction") not in {"ai", "bigdata", "intelligent_systems", "iot"}:
            errors.append(f"{sid} 所属方向非法: {s.get('direction')}")
        if not str(sid).startswith("skill."):
            errors.append(f"{sid} 不是 skill.slug 形式")

    cluster_ids = {c["id"] for c in clusters}
    for s in skills:
        cid = s.get("cluster_id") or s.get("cluster")
        if cid not in cluster_ids:
            errors.append(f"{s.get('id')} cluster 不存在: {cid}")

    parent_of = {}
    for s in skills:
        pid = s.get("parent_id")
        if not pid:
            continue
        if pid not in skill_ids:
            errors.append(f"{s['id']} parent_id 不存在: {pid}")
            continue
        parent_of[s["id"]] = pid

    for sid in list(parent_of):
        seen = set()
        cur = sid
        while cur in parent_of:
            if cur in seen:
                errors.append(f"parent_id 成环，涉及 {sid}")
                break
            seen.add(cur)
            cur = parent_of[cur]

    by_surface: dict[str, set[str]] = defaultdict(set)
    for a in aliases:
        surface = (a.get("surface_folded") or a.get("surface") or "").casefold()
        if not surface:
            errors.append(f"别名缺表面形式: {a}")
            continue
        by_surface[surface].add(a["skill_id"])
        if a.get("skill_id") not in skill_ids:
            errors.append(f"别名指向不存在的技能点: {a.get('skill_id')} ({a.get('surface')})")
    for surface, ids in by_surface.items():
        if len(ids) > 1:
            errors.append(f"别名跨技能点冲突 {surface!r} → {sorted(ids)}")

    occ_ids = set()
    occ_codes = set()
    for o in occupations:
        oid, code = o.get("id"), o.get("code")
        if oid in occ_ids:
            errors.append(f"职业 id 重复: {oid}")
        occ_ids.add(oid)
        if code and code != "_meta":
            if code in occ_codes:
                errors.append(f"职业编码重复: {code}")
            occ_codes.add(code)
    for o in occupations:
        parent = o.get("parent_code")
        if parent and parent not in occ_codes:
            errors.append(f"{o.get('id')} parent_code 不存在: {parent}")

    published = [n for n in new_occs if n.get("kind") == "occupation" and n.get("status") == "published"]
    if len(published) != 110:
        errors.append(f"已发布新职业 {len(published)} 条，应为 110")
    for n in new_occs:
        if not n.get("public_comment_date"):
            errors.append(f"{n.get('id')} 缺公示日期")
        if not n.get("official_url"):
            errors.append(f"{n.get('id')} 缺官方链接")
        if not n.get("batch"):
            errors.append(f"{n.get('id')} 缺批次")

    batches = {n["batch"] for n in new_occs}
    if not {1, 2, 3, 4, 5, 6, 7, 8}.issubset(batches):
        errors.append(f"新职业批次不完整: {sorted(batches)}")

    if errors:
        print(f"FAIL {len(errors)} 项")
        for e in errors[:80]:
            print(" -", e)
        if len(errors) > 80:
            print(f" ... 另有 {len(errors) - 80} 项")
        return 1

    by_dir = defaultdict(int)
    for s in skills:
        by_dir[s["direction"]] += 1
    print("OK")
    print(f"  skills={len(skills)} aliases={len(aliases)} clusters={len(clusters)}")
    print(f"  occupations={len(occupations)} new_occupations={len(new_occs)}")
    print("  directions:", dict(by_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
