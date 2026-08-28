#!/usr/bin/env python3
"""简历抽取准确率：字段级、技能点级，以及溯源准确率（span + bbox）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import dump_json, index_by_id, iou, load_jsonl, markdown_table, mean, prf, span_exact, write_report  # noqa: E402

FIELD_KEYS = ["name", "phone", "email", "city", "education"]
IOU_TH = 0.5


def _val(block):
    if block is None:
        return None
    if isinstance(block, dict) and "value" in block:
        return block["value"]
    return block


def _span(block):
    if isinstance(block, dict):
        return block.get("span")
    return None


def _bbox(block):
    if isinstance(block, dict):
        return block.get("bbox")
    return None


def field_equal(key: str, pred, gold) -> bool:
    if pred is None and gold is None:
        return True
    ps, gs = ("" if pred is None else str(pred).strip()), ("" if gold is None else str(gold).strip())
    if key == "education":
        for token in ("博士", "硕士", "本科", "大专"):
            if token in gs or token in ps:
                return token in ps and token in gs
    if key == "city":
        ps2 = ps[:-1] if ps.endswith("市") else ps
        gs2 = gs[:-1] if gs.endswith("市") else gs
        return ps2 == gs2 or ps in gs or gs in ps
    return ps == gs


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pred", required=True)
    p.add_argument("--gold", required=True)
    p.add_argument("--out-dir", default=None)
    args = p.parse_args()
    pred_rows = index_by_id(load_jsonl(args.pred))
    gold_rows = index_by_id(load_jsonl(args.gold))

    field_hits = {k: [] for k in FIELD_KEYS}
    field_errors = []
    skill_metrics = []
    skill_errors = []
    trace_hits = []
    trace_errors = []
    missing = []

    for gid, gold in gold_rows.items():
        pred = pred_rows.get(gid)
        if pred is None:
            missing.append(gid)
            for k in FIELD_KEYS:
                field_hits[k].append(0.0)
            continue
        gfields, pfields = gold.get("fields") or {}, pred.get("fields") or {}
        for k in FIELD_KEYS:
            ok = field_equal(k, _val(pfields.get(k)), _val(gfields.get(k)))
            field_hits[k].append(1.0 if ok else 0.0)
            if not ok:
                field_errors.append({"id": gid, "field": k, "gold": _val(gfields.get(k)), "pred": _val(pfields.get(k))})
        gsk = {s["name"]: s for s in gold.get("skills") or []}
        psk = {s["name"]: s for s in pred.get("skills") or []}
        m = prf(set(psk), set(gsk))
        skill_metrics.append(m)
        if set(psk) - set(gsk) or set(gsk) - set(psk):
            skill_errors.append({"id": gid, "fp": sorted(set(psk) - set(gsk)), "fn": sorted(set(gsk) - set(psk))})
        # 溯源：对预测中与金标准同名的技能点，检查 span 精确 + bbox IoU
        for name, ps in psk.items():
            gs = gsk.get(name)
            if gs is None:
                continue
            span_ok = span_exact(_span(ps), _span(gs))
            bbox_ok = True
            if _bbox(gs) is not None:
                bbox_ok = iou(_bbox(ps) or [], _bbox(gs)) >= IOU_TH
            # 字符区间必须指向原文对应位置
            gtext = gold.get("text") or ""
            pspan = _span(ps) or {}
            quote_ok = True
            if "start" in pspan and "end" in pspan:
                frag = gtext[int(pspan["start"]) : int(pspan["end"])]
                surface = ps.get("surface_form") or ps.get("name") or ""
                quote_ok = frag == surface or frag.casefold() == str(surface).casefold()
            ok = span_ok and bbox_ok and quote_ok
            trace_hits.append(1.0 if ok else 0.0)
            if not ok:
                trace_errors.append(
                    {
                        "id": gid,
                        "skill": name,
                        "span_ok": span_ok,
                        "bbox_ok": bbox_ok,
                        "quote_ok": quote_ok,
                        "pred_span": _span(ps),
                        "gold_span": _span(gs),
                    }
                )

    field_micro = mean([x for xs in field_hits.values() for x in xs])
    tp = sum(r["tp"] for r in skill_metrics)
    fp = sum(r["fp"] for r in skill_metrics)
    fn = sum(r["fn"] for r in skill_metrics)
    p_micro = tp / (tp + fp) if tp + fp else 0.0
    r_micro = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p_micro * r_micro / (p_micro + r_micro) if p_micro + r_micro else 0.0
    trace = mean(trace_hits)
    summary = {
        "n_gold": len(gold_rows),
        "n_pred_missing": len(missing),
        "field_accuracy_micro": round(field_micro, 4),
        "field_accuracy": {k: round(mean(v), 4) for k, v in field_hits.items()},
        "skill_precision": round(p_micro, 4),
        "skill_recall": round(r_micro, 4),
        "skill_f1": round(f1, 4),
        "trace_accuracy": round(trace, 4),
        "field_pass": field_micro >= 0.95,
        "skill_pass": f1 >= 0.90,
    }
    print(json.dumps(summary, ensure_ascii=False))
    if args.out_dir:
        out = Path(args.out_dir)
        dump_json(
            out / "resume_extract_errors.json",
            {"fields": field_errors, "skills": skill_errors, "trace": trace_errors, "missing": missing},
        )
        write_report(
            out / "resume_extract_report.md",
            "简历抽取评测报告",
            [
                "## 字段级（目标 ≥ 95%）\n\n"
                + markdown_table(
                    ["字段", "准确率"],
                    [[k, f"{mean(field_hits[k]):.2%}"] for k in FIELD_KEYS] + [["micro", f"{field_micro:.2%}"]],
                ),
                "## 技能点级（目标 F1 ≥ 90%）\n\n"
                + markdown_table(["指标", "值"], [["P", f"{p_micro:.2%}"], ["R", f"{r_micro:.2%}"], ["F1", f"{f1:.2%}"]]),
                f"## 溯源准确率\n\n{trace:.2%}（span 严格对齐且 bbox IoU ≥ {IOU_TH}，且区间原文等于 surface_form）。",
                f"错误明细：字段 {len(field_errors)}，技能集合 {len(skill_errors)}，溯源 {len(trace_errors)}。见 resume_extract_errors.json。",
            ],
        )


if __name__ == "__main__":
    main()
