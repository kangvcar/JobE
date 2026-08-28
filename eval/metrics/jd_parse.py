#!/usr/bin/env python3
"""JD 解析准确率：字段级严格匹配 + 技能点级 P/R/F1。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import dump_json, index_by_id, load_jsonl, markdown_table, mean, prf, write_report  # noqa: E402

FIELD_KEYS = ["title", "company", "city", "salary_min", "salary_max", "education", "experience"]


def _val(block: dict | None):
    if block is None:
        return None
    if isinstance(block, dict) and "value" in block:
        return block["value"]
    return block


def _norm_city(v):
    if v is None:
        return None
    s = str(v).strip()
    return s[:-1] if s.endswith("市") else s


def field_equal(key: str, pred, gold) -> bool:
    if key == "city":
        return _norm_city(pred) == _norm_city(gold)
    if key in {"salary_min", "salary_max"}:
        if pred is None and gold is None:
            return True
        try:
            return int(pred) == int(gold)
        except (TypeError, ValueError):
            return pred == gold
    if pred is None and gold is None:
        return True
    return ("" if pred is None else str(pred).strip()) == ("" if gold is None else str(gold).strip())


def skill_names(row: dict) -> set[str]:
    return {s["name"].strip() for s in row.get("skills") or [] if s.get("name")}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pred", required=True)
    p.add_argument("--gold", required=True)
    p.add_argument("--out-dir", default=None, help="写 report.md 与 errors.json")
    args = p.parse_args()
    pred_rows = index_by_id(load_jsonl(args.pred))
    gold_rows = index_by_id(load_jsonl(args.gold))

    field_hits = {k: [] for k in FIELD_KEYS}
    field_errors = []
    skill_rows = []
    skill_errors = []
    missing_ids = []

    for gid, gold in gold_rows.items():
        pred = pred_rows.get(gid)
        if pred is None:
            missing_ids.append(gid)
            for k in FIELD_KEYS:
                field_hits[k].append(0.0)
            continue
        gfields = gold.get("fields") or {}
        pfields = pred.get("fields") or {}
        for k in FIELD_KEYS:
            ok = field_equal(k, _val(pfields.get(k)), _val(gfields.get(k)))
            field_hits[k].append(1.0 if ok else 0.0)
            if not ok:
                field_errors.append(
                    {"id": gid, "field": k, "gold": _val(gfields.get(k)), "pred": _val(pfields.get(k))}
                )
        gsk, psk = skill_names(gold), skill_names(pred)
        m = prf(psk, gsk)
        skill_rows.append(m)
        if psk - gsk or gsk - psk:
            skill_errors.append(
                {
                    "id": gid,
                    "false_positive": sorted(psk - gsk),
                    "false_negative": sorted(gsk - psk),
                }
            )

    per_field = {k: mean(v) for k, v in field_hits.items()}
    field_micro = mean([x for xs in field_hits.values() for x in xs])
    # 技能点：micro（先加总 tp/fp/fn）
    tp = sum(r["tp"] for r in skill_rows)
    fp = sum(r["fp"] for r in skill_rows)
    fn = sum(r["fn"] for r in skill_rows)
    p_micro = tp / (tp + fp) if tp + fp else 0.0
    r_micro = tp / (tp + fn) if tp + fn else 0.0
    f1_micro = 2 * p_micro * r_micro / (p_micro + r_micro) if p_micro + r_micro else 0.0
    f1_macro = mean([r["f1"] for r in skill_rows])

    summary = {
        "n_gold": len(gold_rows),
        "n_pred_missing": len(missing_ids),
        "field_accuracy_micro": round(field_micro, 4),
        "field_accuracy": {k: round(v, 4) for k, v in per_field.items()},
        "skill_precision": round(p_micro, 4),
        "skill_recall": round(r_micro, 4),
        "skill_f1": round(f1_micro, 4),
        "skill_f1_macro": round(f1_macro, 4),
        "targets": {"field": 0.95, "skill_f1": 0.90},
        "field_pass": field_micro >= 0.95,
        "skill_pass": f1_micro >= 0.90,
    }
    print(json.dumps(summary, ensure_ascii=False))

    if args.out_dir:
        out = Path(args.out_dir)
        dump_json(out / "jd_parse_errors.json", {"fields": field_errors, "skills": skill_errors, "missing": missing_ids})
        sections = [
            "## 字段级严格匹配准确率（目标 ≥ 95%）",
            markdown_table(
                ["字段", "准确率"],
                [[k, f"{per_field[k]:.2%}"] for k in FIELD_KEYS] + [["micro", f"{field_micro:.2%}"]],
            ),
            "## 技能点级（严格匹配，目标 F1 ≥ 90%）",
            markdown_table(
                ["指标", "值"],
                [["P", f"{p_micro:.2%}"], ["R", f"{r_micro:.2%}"], ["F1 micro", f"{f1_micro:.2%}"], ["F1 macro", f"{f1_macro:.2%}"]],
            ),
            f"## 错误分析\n\n字段错误 {len(field_errors)} 条，技能点集合不一致 {len(skill_errors)} 条。"
            + (" 缺失预测 id: " + ", ".join(missing_ids[:20]) if missing_ids else ""),
            "技能点假阳性/假阴性见 `jd_parse_errors.json`。假阳性优先查切分过粗或误标品德；假阴性优先查词表漏召回与斜杠列举未拆。",
        ]
        write_report(out / "jd_parse_report.md", "JD 解析评测报告", sections)


if __name__ == "__main__":
    main()
