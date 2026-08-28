#!/usr/bin/env python3
"""构造「简历 × 岗位」匹配金标准。档位由 assign_tier 机械判定，禁止事后改档。"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "metrics"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assign import TIER_ORDER, assign_tier, rank_roles  # noqa: E402
from metrics.common import dump_jsonl  # noqa: E402

TARGET = {"gapped": 0.45, "adequate": 0.25, "mismatch": 0.20, "strong": 0.10}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def jd_min_years(jd: dict) -> int | None:
    if jd.get("min_years"):
        return int(jd["min_years"])
    exp = ((jd.get("fields") or {}).get("experience") or {}).get("value") or ""
    if "应届" in str(exp):
        return 0
    import re

    m = re.search(r"(\d+)", str(exp))
    return int(m.group(1)) if m else None


def pair_record(pid: str, resume: dict, jd: dict) -> dict:
    edu_p = ((resume.get("fields") or {}).get("education") or {}).get("value")
    if edu_p and "本科" in str(edu_p):
        edu_p = "本科"
    elif edu_p and "硕士" in str(edu_p):
        edu_p = "硕士"
    elif edu_p and "博士" in str(edu_p):
        edu_p = "博士"
    edu_j = ((jd.get("fields") or {}).get("education") or {}).get("value")
    assignment = assign_tier(
        resume["skills"],
        jd["skills"],
        jd["family"],
        profile_edu=edu_p,
        jd_edu=edu_j,
        profile_years=resume.get("years"),
        jd_min_years=jd_min_years(jd),
    )
    return {
        "id": pid,
        "profile_id": resume["id"],
        "role_id": jd["id"],
        "jd_family": jd["family"],
        "resume_family": resume.get("family"),
        "tier": assignment["tier"],
        "rule": assignment["rule"],
        "coverage": assignment["coverage"],
        "skill_judgments": assignment["judgments"],
        "surplus": assignment["surplus"],
        "assignment": assignment,
    }


def sample_distribution(cands: list[dict], n: int, rng: random.Random) -> list[dict]:
    by = defaultdict(list)
    for c in cands:
        by[c["tier"]].append(c)
    for k in by:
        rng.shuffle(by[k])
    quotas = {t: int(n * p) for t, p in TARGET.items()}
    # 余数给 gapped
    quotas["gapped"] += n - sum(quotas.values())
    picked: list[dict] = []
    for t, q in quotas.items():
        take = by[t][:q]
        picked.extend(take)
        by[t] = by[t][q:]
    # 不够的用剩余填
    leftover = [c for t in ("gapped", "adequate", "mismatch", "strong") for c in by[t]]
    while len(picked) < n and leftover:
        picked.append(leftover.pop(0))
    rng.shuffle(picked)
    return picked[:n]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", type=Path, default=ROOT / "datasets" / "resume" / "gold.jsonl")
    parser.add_argument("--jd", type=Path, default=ROOT / "datasets" / "jd" / "gold.jsonl")
    parser.add_argument("--n-pairs", type=int, default=220)
    parser.add_argument("--n-rank", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    resumes = load_jsonl(args.resume)
    jds = load_jsonl(args.jd)
    cands = []
    # 先纳入锚点对（技能重叠是构造出来的），再补同族与跨族
    anchors_used = set()
    for resume in resumes:
        aid = resume.get("anchor_role_id")
        if aid:
            jd = next((j for j in jds if j["id"] == aid), None)
            if jd:
                rec = pair_record("tmp", resume, jd)
                cands.append(rec)
                anchors_used.add((resume["id"], jd["id"]))
        same = [j for j in jds if j["family"] == resume.get("family")]
        other = [j for j in jds if j["family"] != resume.get("family")]
        rng.shuffle(same)
        rng.shuffle(other)
        for jd in same + other[:1]:
            if (resume["id"], jd["id"]) in anchors_used:
                continue
            cands.append(pair_record("tmp", resume, jd))

    pairs = sample_distribution(cands, args.n_pairs, rng)
    for i, p in enumerate(pairs, start=1):
        p["id"] = f"pair_{i:03d}"

    dump_jsonl(args.out / "pairs.jsonl", pairs)

    # 排序组：20 份简历，各配 10 个岗位
    rank_resumes = resumes[: args.n_rank]
    ranking = []
    for i, resume in enumerate(rank_resumes, start=1):
        same = [j for j in jds if j["family"] == resume.get("family")]
        other = [j for j in jds if j["family"] != resume.get("family")]
        rng.shuffle(same)
        rng.shuffle(other)
        roles_jd = (same[:6] + other[:4])[:10]
        if len(roles_jd) < 10:
            extra = [j for j in jds if j not in roles_jd]
            roles_jd.extend(extra[: 10 - len(roles_jd)])
        role_recs = []
        for jd in roles_jd[:10]:
            rec = pair_record("x", resume, jd)
            role_recs.append({"id": jd["id"], "assignment": rec["assignment"], "tier": rec["tier"]})
        order = rank_roles(resume, role_recs)
        ranking.append(
            {
                "id": f"rank_{i:02d}",
                "profile_id": resume["id"],
                "role_ids": order,
                "tiers": [next(r["tier"] for r in role_recs if r["id"] == rid) for rid in order],
            }
        )
    dump_jsonl(args.out / "ranking.jsonl", ranking)

    dist = defaultdict(int)
    for p in pairs:
        dist[p["tier"]] += 1
    print(json.dumps({"n_pairs": len(pairs), "n_rank": len(ranking), "tier_dist": dict(dist)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
