#!/usr/bin/env python3
"""人岗匹配：档位一致率、技能级判定准确率、排序 Spearman 与 NDCG@5。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import dump_json, index_by_id, load_jsonl, markdown_table, mean, ndcg_at_k, spearman, write_report  # noqa: E402

TIER_REL = {"strong": 3.0, "adequate": 2.0, "gapped": 1.0, "mismatch": 0.0}


def _judgments(row: dict) -> dict[str, str]:
    out = {}
    for j in row.get("skill_judgments") or row.get("judgments") or []:
        name = j.get("skill_name") or j.get("name")
        if name:
            out[name] = j.get("verdict")
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pred", required=True, help="pairs 预测 JSONL")
    p.add_argument("--gold", required=True, help="pairs 金标准 JSONL")
    p.add_argument("--rank-pred", default=None, help="排序预测 JSONL，可选")
    p.add_argument("--rank-gold", default=None, help="排序金标准 JSONL，可选")
    p.add_argument("--out-dir", default=None)
    args = p.parse_args()

    pred = index_by_id(load_jsonl(args.pred))
    gold = index_by_id(load_jsonl(args.gold))
    tier_ok = []
    tier_errors = []
    skill_ok = []
    skill_errors = []
    missing = []
    for gid, g in gold.items():
        pr = pred.get(gid)
        if pr is None:
            missing.append(gid)
            tier_ok.append(0.0)
            continue
        same = (pr.get("tier") == g.get("tier"))
        tier_ok.append(1.0 if same else 0.0)
        if not same:
            tier_errors.append({"id": gid, "gold": g.get("tier"), "pred": pr.get("tier"), "profile_id": g.get("profile_id"), "role_id": g.get("role_id")})
        gj, pj = _judgments(g), _judgments(pr)
        for name, gv in gj.items():
            hit = pj.get(name) == gv
            skill_ok.append(1.0 if hit else 0.0)
            if not hit:
                skill_errors.append({"id": gid, "skill": name, "gold": gv, "pred": pj.get(name)})

    rank_stats = None
    rank_errors = []
    if args.rank_pred and args.rank_gold:
        rp = index_by_id(load_jsonl(args.rank_pred))
        rg = index_by_id(load_jsonl(args.rank_gold))
        rhos, ndcgs = [], []
        for rid, g in rg.items():
            pr = rp.get(rid)
            gold_ids = list(g.get("role_ids") or [])
            gold_tiers = list(g.get("tiers") or [])
            rel_of = {gold_ids[i]: TIER_REL.get(gold_tiers[i], 0.0) for i in range(min(len(gold_ids), len(gold_tiers)))}
            if pr is None:
                rhos.append(0.0)
                ndcgs.append(0.0)
                rank_errors.append({"id": rid, "reason": "missing"})
                continue
            pred_ids = list(pr.get("role_ids") or [])
            # Spearman：金标准名次 vs 系统名次
            gold_rank = {rid_: i for i, rid_ in enumerate(gold_ids)}
            pred_rank = {rid_: i for i, rid_ in enumerate(pred_ids)}
            common = [x for x in gold_ids if x in pred_rank]
            xs = [float(gold_rank[x]) for x in common]
            ys = [float(pred_rank[x]) for x in common]
            rho = spearman(xs, ys)
            # 名次同向：两者都是「越小越好」，相关应为正。若系统完全反序则为负。
            rhos.append(rho)
            y_true = [rel_of.get(x, 0.0) for x in gold_ids]
            y_score = [-pred_rank.get(x, 99) for x in gold_ids]
            ndcgs.append(ndcg_at_k(y_true, y_score, k=5))
            if rho < 0.99:
                rank_errors.append({"id": rid, "spearman": round(rho, 4), "gold": gold_ids, "pred": pred_ids})
        rank_stats = {"spearman": round(mean(rhos), 4), "ndcg_at_5": round(mean(ndcgs), 4), "n_groups": len(rg)}

    summary = {
        "n_gold": len(gold),
        "n_pred_missing": len(missing),
        "tier_accuracy": round(mean(tier_ok), 4),
        "skill_judgment_accuracy": round(mean(skill_ok), 4),
        "ranking": rank_stats,
        "tier_pass": mean(tier_ok) >= 0.90,
        "skill_pass": mean(skill_ok) >= 0.90,
    }
    print(json.dumps(summary, ensure_ascii=False))
    if args.out_dir:
        out = Path(args.out_dir)
        dump_json(
            out / "match_errors.json",
            {"tier": tier_errors, "skill_judgments": skill_errors[:200], "ranking": rank_errors, "missing": missing},
        )
        sections = [
            "## 档位一致率（主指标，目标 ≥ 90%）\n\n" + f"{mean(tier_ok):.2%}",
            "## 技能级判定准确率\n\n" + f"{mean(skill_ok):.2%}",
            "## 排序一致性\n\n"
            + (
                markdown_table(["指标", "值"], [["Spearman", rank_stats["spearman"]], ["NDCG@5", rank_stats["ndcg_at_5"]]])
                if rank_stats
                else "未提供 --rank-pred / --rank-gold。"
            ),
            f"档位错误 {len(tier_errors)} 对。优先按金标准 `rule` 字段看是卡在 R1 岗位族错位还是覆盖率阈值。"
            f"技能级错误抽 {min(20, len(skill_errors))} 条见 JSON。",
        ]
        write_report(out / "match_report.md", "人岗匹配评测报告", sections)


if __name__ == "__main__":
    main()
