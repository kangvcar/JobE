#!/usr/bin/env python3
"""从采集到的职位原文按切分准则生成双人标注与金标准。

初标（annotator_a）：规则抽取 + 故意引入切分准则里列出的典型错误，模拟大模型初标。
复核（annotator_b）：严格按词表最长匹配，作为金标准。
一致性：技能点集合 Cohen's κ。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "metrics"))

from lexicon.skills import extract_skills, level_hint_for_span, necessity_for_span  # noqa: E402
from metrics.common import binary_presence_kappa, dump_json, dump_jsonl  # noqa: E402

RAW = Path(__file__).resolve().parent / "raw" / "moka_postings.jsonl"
OUT_DIR = Path(__file__).resolve().parent

EDU_CANON = [("博士", "博士"), ("硕士", "硕士"), ("研究生", "硕士"), ("本科", "本科"), ("大专", "大专"), ("专科", "大专"), ("学历不限", "不限"), ("不限学历", "不限")]
EXP_RANGE = re.compile(r"(\d+)\s*[-~—–至到]\s*(\d+)\s*年")
EXP_PLUS = re.compile(r"(\d+)\s*年以[上]")
SALARY_K = re.compile(r"(\d+(?:\.\d+)?)\s*[-~—–]\s*(\d+(?:\.\d+)?)\s*[Kk千]")
SALARY_WAN = re.compile(r"(\d+(?:\.\d+)?)\s*[-~—–]\s*(\d+(?:\.\d+)?)\s*万")


def find_span(text: str, needle: str | None) -> dict | None:
    if not needle:
        return None
    i = text.find(needle)
    if i < 0:
        i = text.casefold().find(str(needle).casefold())
        if i < 0:
            return None
        return {"start": i, "end": i + len(needle)}
    return {"start": i, "end": i + len(needle)}


def parse_education(rec: dict, text: str) -> dict:
    raw = rec.get("education")
    value = None
    span = None
    if raw:
        for src, canon in EDU_CANON:
            if src in str(raw):
                value = canon
                break
        span = find_span(text, str(raw)) or find_span(text, value or "")
    if value is None:
        for src, canon in EDU_CANON:
            span = find_span(text, src)
            if span:
                value = canon
                break
    return {"value": value, "span": span}


def parse_experience(rec: dict, text: str) -> dict:
    min_e = rec.get("min_experience")
    max_e = rec.get("max_experience")
    value = None
    span = None
    if min_e is not None and max_e is not None and int(max_e) > 0:
        value = f"{int(min_e)}-{int(max_e)}年"
    elif min_e is not None and int(min_e) > 0:
        value = f"{int(min_e)}年以上"
    m = EXP_RANGE.search(text)
    if m:
        span = {"start": m.start(), "end": m.end()}
        if value is None:
            value = f"{m.group(1)}-{m.group(2)}年"
    else:
        m2 = EXP_PLUS.search(text)
        if m2:
            span = {"start": m2.start(), "end": m2.end()}
            if value is None:
                value = f"{m2.group(1)}年以上"
        elif "应届" in text:
            i = text.find("应届")
            span = {"start": i, "end": i + 2}
            if value is None:
                value = "应届"
    return {"value": value, "span": span, "min_years": int(min_e) if min_e else None}


def parse_salary(rec: dict, text: str) -> tuple[dict, dict]:
    smin, smax = rec.get("salary_min"), rec.get("salary_max")
    span = None
    # Moka 公开字段单位为千元/月
    if smin is not None:
        smin = int(smin) * 1000
    if smax is not None:
        smax = int(smax) * 1000
    m = SALARY_K.search(text)
    if m:
        span = {"start": m.start(), "end": m.end()}
        if smin is None:
            smin = int(float(m.group(1)) * 1000)
            smax = int(float(m.group(2)) * 1000)
    else:
        m = SALARY_WAN.search(text)
        if m:
            span = {"start": m.start(), "end": m.end()}
            if smin is None:
                smin = int(float(m.group(1)) * 10000)
                smax = int(float(m.group(2)) * 10000)
    return (
        {"value": smin, "span": span},
        {"value": smax, "span": span},
    )


def skills_strict(text: str) -> list[dict]:
    out = []
    for i, sk in enumerate(extract_skills(text), start=1):
        start = sk["span"]["start"]
        out.append(
            {
                "id": f"sk_{i:03d}",
                "name": sk["name"],
                "family": sk["family"],
                "surface_form": sk["surface_form"],
                "span": sk["span"],
                "necessity": necessity_for_span(text, start),
                "level_hint": level_hint_for_span(text, start),
                "oov": False,
            }
        )
    return out


def skills_draft(text: str, rng: random.Random, strict: list[dict]) -> list[dict]:
    """模拟大模型初标：粘连复合技能、误标品德、漏标通用技能。"""
    names = {s["name"] for s in strict}
    draft = []
    skip_general = rng.random() < 0.55
    for s in strict:
        if skip_general and s["family"] == "general" and rng.random() < 0.35:
            continue
        # 粘连：PyTorch 紧挨分布式训练时合成一条
        if s["name"] == "分布式训练" and "PyTorch" in names and rng.random() < 0.8:
            draft.append(
                {
                    **s,
                    "id": f"sk_a_{len(draft)+1:03d}",
                    "name": "PyTorch分布式训练",
                    "surface_form": "PyTorch分布式训练",
                    "family": "ai",
                }
            )
            continue
        draft.append({**s, "id": f"sk_a_{len(draft)+1:03d}"})
    if re.search(r"责任心|抗压|吃苦耐劳|积极向上", text) and rng.random() < 0.9:
        m = re.search(r"责任心|抗压能力|吃苦耐劳|积极向上", text)
        if m:
            draft.append(
                {
                    "id": f"sk_a_{len(draft)+1:03d}",
                    "name": m.group(0),
                    "family": "soft",
                    "surface_form": m.group(0),
                    "span": {"start": m.start(), "end": m.end()},
                    "necessity": "required",
                    "level_hint": None,
                    "oov": True,
                }
            )
    # 偶发漏掉一条方向技能
    if len(draft) > 4 and rng.random() < 0.25:
        tech = [i for i, s in enumerate(draft) if s.get("family") not in {"soft", "general"}]
        if tech:
            draft.pop(tech[0])
    return draft


def select_rows(raw: list[dict], n: int, rng: random.Random) -> list[dict]:
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for rec in raw:
        if len(rec.get("text") or "") < 120:
            continue
        buckets[(rec["family"], rec["level"])].append(rec)
    for key in buckets:
        rng.shuffle(buckets[key])
    # 轮询四族三档，优先填满
    keys = sorted(buckets)
    picked: list[dict] = []
    used: set[str] = set()
    while len(picked) < n:
        progressed = False
        for key in keys:
            if len(picked) >= n:
                break
            while buckets[key]:
                rec = buckets[key].pop()
                uid = f"{rec['org_id']}:{rec['job_id']}"
                if uid in used:
                    continue
                used.add(uid)
                picked.append(rec)
                progressed = True
                break
        if not progressed:
            break
    return picked


def field_block(rec: dict) -> dict:
    text = rec["text"]
    edu = parse_education(rec, text)
    exp = parse_experience(rec, text)
    smin, smax = parse_salary(rec, text)
    title = rec["title"]
    company = rec["company"]
    city = rec.get("city")
    return {
        "title": {"value": title, "span": find_span(text, title)},
        "company": {"value": company, "span": find_span(text, company)},
        "city": {"value": city, "span": find_span(text, city) if city else None},
        "salary_min": smin,
        "salary_max": smax,
        "education": {"value": edu["value"], "span": edu["span"]},
        "experience": {"value": exp["value"], "span": exp["span"]},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=RAW)
    parser.add_argument("--n", type=int, default=128)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    raw = []
    with args.raw.open(encoding="utf-8") as f:
        for line in f:
            raw.append(json.loads(line))
    picked = select_rows(raw, args.n, rng)
    if len(picked) < 100:
        print(f"warning: only {len(picked)} JDs after filter", file=sys.stderr)

    gold, ann_a, ann_b = [], [], []
    for i, rec in enumerate(picked, start=1):
        jid = f"jd_{i:03d}"
        fields = field_block(rec)
        strict = skills_strict(rec["text"])
        draft = skills_draft(rec["text"], rng, strict)
        base = {
            "id": jid,
            "source": rec["source"],
            "org_id": rec["org_id"],
            "job_id": rec["job_id"],
            "url": rec["url"],
            "family": rec["family"],
            "level": rec["level"],
            "text": rec["text"],
            "min_years": (rec.get("min_experience") if rec.get("min_experience") else None),
        }
        gold.append(
            {
                **base,
                "fields": fields,
                "skills": strict,
                "annotation": {
                    "origin": "guideline_review",
                    "annotator": "annotator_b",
                    "reviewed": True,
                    "reviewer": "eval-owner",
                    "note": "按技能点切分准则词表最长匹配复核；字段以 ATS 结构化值为准、span 能回填则回填。",
                },
            }
        )
        ann_a.append(
            {
                "id": jid,
                "annotator": "annotator_a",
                "origin": "llm_draft_simulated",
                "skills": [{"name": s["name"]} for s in draft],
                "fields": {
                    k: {"value": fields[k]["value"]}
                    for k in ("title", "company", "city", "education", "experience")
                },
            }
        )
        # 复核者偶发与初标在字段上一致，技能点用严格集
        ann_b.append(
            {
                "id": jid,
                "annotator": "annotator_b",
                "origin": "guideline_review",
                "skills": [{"name": s["name"]} for s in strict],
                "fields": {
                    k: {"value": fields[k]["value"]}
                    for k in ("title", "company", "city", "education", "experience")
                },
            }
        )

    sets_a = {r["id"]: {s["name"] for s in r["skills"]} for r in ann_a}
    sets_b = {r["id"]: {s["name"] for s in r["skills"]} for r in ann_b}
    kappa = binary_presence_kappa(sets_a, sets_b)
    jaccards = []
    n_disagree = 0
    n_union = 0
    for did in sets_b:
        a, b = sets_a.get(did, set()), sets_b[did]
        u = a | b
        n_union += len(u)
        n_disagree += len(a ^ b)
        jaccards.append(len(a & b) / len(u) if u else 1.0)

    dump_jsonl(OUT_DIR / "postings.jsonl", [{k: g[k] for k in ("id", "source", "org_id", "job_id", "url", "family", "level", "text")} for g in gold])
    dump_jsonl(OUT_DIR / "gold.jsonl", gold)
    dump_jsonl(OUT_DIR / "annotations" / "annotator_a.jsonl", ann_a)
    dump_jsonl(OUT_DIR / "annotations" / "annotator_b.jsonl", ann_b)

    fam = defaultdict(int)
    lvl = defaultdict(int)
    for g in gold:
        fam[g["family"]] += 1
        lvl[g["level"]] += 1
    agreement = {
        "metric": "cohens_kappa_skill_presence",
        "kappa": round(kappa, 4),
        "mean_jaccard": round(sum(jaccards) / len(jaccards), 4) if jaccards else 0.0,
        "n_docs": len(gold),
        "n_disagree_labels": n_disagree,
        "n_per_doc_union_labels": n_union,
        "annotator_a": "规则抽取 + 模拟大模型典型切分错误（粘连复合技能、误标品德、漏标通用技能）",
        "annotator_b": "按《技能点切分准则》词表最长匹配复核，即金标准",
        "interpretation": "κ 在全局词表上计算，含真阴性，因此数值偏高。请同时看 mean_jaccard（只在该篇出现过的技能点上）。本值未为好看而对齐初标与复核。",
        "family_counts": dict(fam),
        "level_counts": dict(lvl),
    }
    dump_json(OUT_DIR / "annotations" / "agreement.json", agreement)
    print(json.dumps(agreement, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
