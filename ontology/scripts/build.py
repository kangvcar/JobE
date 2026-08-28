"""把 catalog/ 编目与 raw/ 富集结果写成 data/*.jsonl。幂等：按 id 排序、键顺序固定。"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from catalog.clusters import CLUSTERS  # noqa: E402
from catalog.new_occupations import iter_new_occupations  # noqa: E402
from catalog.occupations import iter_occupations  # noqa: E402
from catalog.skills import LLM_ALIASES, ROWS  # noqa: E402

DATA = ROOT / "data"
RAW = ROOT / "raw"
VERSION_FILE = ROOT / "VERSION"

# 这些表面形式在中文 IT 职位里歧义太大，不进 aliases.jsonl。
# 判定按 casefold 比较，所以写小写即可屏蔽全部大小写变体。
# 两三字母缩写要看它在中文技术文本里的主导含义：JS/TS/ML/AI 主导含义就是技术，留；
# 下面这些的主导含义不是技术，实测会误命中（如「SD卡驱动」判成 Stable Diffusion）。
BLOCKED_SURFACES = {
    "go",
    "r",
    "c",
    "agent",
    "ch",
    "java岛",
    "sd",  # SD卡、SD-WAN、标准差
    "tf",  # TF卡；TF-IDF 由最长匹配单独命中 skill.tfidf
}

LINGUIST_NAME = {
    "golang": "Go",
    "c-lang": "C",
    "cpp": "C++",
    "csharp": "C#",
    "fsharp": "F#",
    "r-lang": "R",
    "objc": "Objective-C",
    "wasm": "WebAssembly",
    "cuda-c": "Cuda",
    "assembly": "Assembly",
}


def version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def dump_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def parse_linguist(path: Path) -> dict[str, list[str]]:
    """只解析语言名与 aliases 列表，不引入 PyYAML。"""
    langs: dict[str, list[str]] = {}
    current: str | None = None
    in_aliases = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("#") or raw.strip() in ("", "---"):
            continue
        if not raw.startswith(" ") and raw.endswith(":"):
            current = raw[:-1]
            langs[current] = []
            in_aliases = False
            continue
        if current is None:
            continue
        stripped = raw.strip()
        if stripped == "aliases:":
            in_aliases = True
            continue
        if in_aliases and stripped.startswith("- "):
            alias = stripped[2:].strip().strip("'\"")
            if alias:
                langs[current].append(alias)
            continue
        if raw.startswith("  ") and not raw.startswith("    ") and ":" in raw:
            in_aliases = False
    return langs


def load_onet_examples(path: Path) -> dict[str, dict]:
    """Workplace Example → {hot, count}。"""
    found: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            name = (row.get("Workplace Example") or "").strip()
            if not name:
                continue
            rec = found.setdefault(name, {"hot": False, "count": 0})
            rec["count"] += 1
            if row.get("Hot Technology") == "Y":
                rec["hot"] = True
    return found


def normalize_surface(s: str) -> str:
    return " ".join(s.split()).strip()


def is_blocked(surface: str) -> bool:
    key = surface.casefold().strip()
    if len(key) < 2:
        return True
    return key in BLOCKED_SURFACES


def skill_id(slug: str) -> str:
    return f"skill.{slug}"


def build_skills(ver: str) -> tuple[list[dict], list[dict]]:
    cluster_ids = {c[0] for c in CLUSTERS}
    by_slug = {}
    for row in ROWS:
        slug, zh, en, extra, parent, cluster, direction = row
        if slug in by_slug:
            raise SystemExit(f"重复 slug: {slug}")
        if cluster not in cluster_ids:
            raise SystemExit(f"{slug} 的 cluster 不存在: {cluster}")
        by_slug[slug] = {
            "slug": slug,
            "name_zh": zh,
            "name_en": en,
            "extra": [a for a in extra.split("|") if a],
            "parent": parent or None,
            "cluster_id": cluster,
            "direction": direction,
        }

    linguist = {}
    linguist_path = RAW / "languages.yml"
    if linguist_path.exists():
        linguist = parse_linguist(linguist_path)

    onet = {}
    onet_path = RAW / "software_skills.txt"
    if onet_path.exists():
        onet = load_onet_examples(onet_path)

    # surface → (skill_id, source, priority)
    claimed: dict[str, tuple[str, str, int]] = {}
    alias_rows: list[dict] = []

    def claim(sid: str, surface: str, source: str, priority: int) -> bool:
        surface = normalize_surface(surface)
        if not surface or is_blocked(surface):
            return False
        key = surface.casefold()
        prev = claimed.get(key)
        if prev is None:
            claimed[key] = (sid, source, priority)
            alias_rows.append(
                {
                    "surface": surface,
                    "surface_folded": key,
                    "skill_id": sid,
                    "source": source,
                    "ontology_version": ver,
                }
            )
            return True
        if prev[0] == sid:
            return True
        if priority < prev[2]:
            # 更高优先级（数字更小）覆盖。重建太贵，构建时禁止覆盖，只拒绝低优先级。
            return False
        return False

    skills: list[dict] = []
    for slug, spec in sorted(by_slug.items()):
        sid = skill_id(slug)
        parent = spec["parent"]
        parent_id = skill_id(parent) if parent else None
        if parent and parent not in by_slug:
            raise SystemExit(f"{slug} 的 parent_id 不存在: {parent}")

        sources = ["curated"]
        external: dict[str, str] = {}
        aliases: list[str] = []

        def add_alias(text: str, source: str, priority: int) -> None:
            if claim(sid, text, source, priority) and text not in aliases and text != spec["name_zh"]:
                aliases.append(text)
                if source not in sources and source != "curated":
                    sources.append(source)

        add_alias(spec["name_zh"], "curated", 0)
        if spec["name_en"] != spec["name_zh"]:
            add_alias(spec["name_en"], "curated", 0)
        for a in spec["extra"]:
            add_alias(a, "curated", 1)
        if spec["name_en"].lower() != spec["name_zh"]:
            add_alias(spec["name_en"].lower(), "curated", 2)

        ling_key = LINGUIST_NAME.get(slug, spec["name_en"])
        if ling_key in linguist:
            external["linguist"] = ling_key
            sources.append("linguist")
            for a in linguist[ling_key]:
                add_alias(a, "linguist", 3)

        # O*NET 按英文名或别名精确匹配 Workplace Example
        onet_hit = None
        candidates = []
        for c in (spec["name_en"], spec["name_zh"], *spec["extra"]):
            if c and c not in candidates:
                candidates.append(c)
        for c in list(candidates):
            if c in onet:
                onet_hit = c
                break
            for example in onet:
                if example.casefold() == c.casefold():
                    onet_hit = example
                    break
            if onet_hit:
                break
        if onet_hit:
            external["onet"] = onet_hit
            if onet[onet_hit]["hot"]:
                external["onet_hot"] = "Y"
            sources.append("onet")
            add_alias(onet_hit, "onet", 3)

        for a in LLM_ALIASES.get(slug, []):
            add_alias(a, "llm", 4)

        if not aliases:
            raise SystemExit(f"{slug} 缺少别名")

        skills.append(
            {
                "id": sid,
                "name": spec["name_zh"],
                "name_zh": spec["name_zh"],
                "name_en": spec["name_en"],
                "aliases": aliases,
                "parent_id": parent_id,
                "cluster": spec["cluster_id"],
                "cluster_id": spec["cluster_id"],
                "direction": spec["direction"],
                "sources": sources,
                "source": sources[0],
                "external_ids": external,
                "ontology_version": ver,
            }
        )

    alias_rows.sort(key=lambda r: (r["surface_folded"], r["skill_id"], r["surface"]))
    skills.sort(key=lambda r: r["id"])
    return skills, alias_rows


def build_clusters(ver: str, skills: list[dict]) -> list[dict]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for s in skills:
        grouped[s["cluster_id"]].append(s["id"])
    rows = []
    for cid, name, name_en, direction in CLUSTERS:
        rows.append(
            {
                "id": cid,
                "name": name,
                "name_en": name_en,
                "direction": direction,
                "skill_ids": sorted(grouped.get(cid, [])),
                "ontology_version": ver,
            }
        )
    rows.sort(key=lambda r: r["id"])
    return rows


def main() -> int:
    ver = version()
    skills, aliases = build_skills(ver)
    clusters = build_clusters(ver, skills)
    occupations = iter_occupations(ver)
    new_occs = iter_new_occupations(ver)
    dump_jsonl(DATA / "skills.jsonl", skills)
    dump_jsonl(DATA / "aliases.jsonl", aliases)
    dump_jsonl(DATA / "clusters.jsonl", clusters)
    dump_jsonl(DATA / "occupations.jsonl", occupations)
    dump_jsonl(DATA / "new_occupations.jsonl", new_occs)
    print(
        f"version={ver} skills={len(skills)} aliases={len(aliases)} "
        f"clusters={len(clusters)} occupations={len(occupations)} "
        f"new_occupations={len(new_occs)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
