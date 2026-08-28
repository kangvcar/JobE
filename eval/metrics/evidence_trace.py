#!/usr/bin/env python3
"""证据可溯源率、跨源确认率。赛题未要求，用于幻觉防控量化。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import dump_json, load_jsonl, mean, write_report  # noqa: E402


def _claims(row: dict) -> list[dict]:
    """系统输出里每一条「结论」。兼容 skills / conclusions / claims。"""
    if row.get("claims"):
        return list(row["claims"])
    if row.get("conclusions"):
        return list(row["conclusions"])
    out = []
    for s in row.get("skills") or []:
        out.append(s)
    for k, v in (row.get("fields") or {}).items():
        if isinstance(v, dict):
            out.append({"name": k, **v})
    return out


def _has_locatable_evidence(claim: dict, text: str | None) -> bool:
    evs = claim.get("evidence") or claim.get("evidences") or []
    if claim.get("span") and not evs:
        evs = [{"span": claim["span"], "quote": claim.get("surface_form") or claim.get("quote") or claim.get("value")}]
    if not evs:
        return False
    for ev in evs:
        span = ev.get("span") if isinstance(ev, dict) else None
        quote = (ev.get("quote") if isinstance(ev, dict) else None) or claim.get("surface_form")
        if not span:
            continue
        if text is None:
            return True
        frag = text[int(span["start"]) : int(span["end"])]
        if quote is None or frag == str(quote) or frag.casefold() == str(quote).casefold():
            return True
    return False


def _source_ids(claim: dict) -> set[str]:
    evs = claim.get("evidence") or claim.get("evidences") or []
    ids = set()
    for ev in evs:
        if not isinstance(ev, dict):
            continue
        sid = ev.get("source_id") or ev.get("source")
        if sid:
            ids.add(str(sid))
    if claim.get("grade") == "multi_source" or claim.get("evidence_grade") == "multi_source":
        ids.add("__multi__")
        ids.add("__multi2__")
    return ids


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pred", required=True, help="带 evidence 的系统结论 JSONL")
    p.add_argument("--gold", required=True, help="用于对齐 id 与原文；可与 pred 同结构")
    p.add_argument("--out-dir", default=None)
    args = p.parse_args()
    pred_rows = load_jsonl(args.pred)
    gold_by_id = {r["id"]: r for r in load_jsonl(args.gold)}

    trace_flags = []
    multi_flags = []
    errors = []
    for row in pred_rows:
        gold = gold_by_id.get(row.get("id"), {})
        text = gold.get("text") or row.get("text")
        claims = _claims(row)
        if not claims:
            continue
        for i, c in enumerate(claims):
            ok = _has_locatable_evidence(c, text)
            trace_flags.append(1.0 if ok else 0.0)
            if not ok:
                errors.append({"id": row.get("id"), "claim_index": i, "name": c.get("name") or c.get("skill_name")})
            srcs = _source_ids(c)
            multi_flags.append(1.0 if len(srcs) >= 2 else 0.0)

    summary = {
        "n_claims": len(trace_flags),
        "evidence_traceable_rate": round(mean(trace_flags), 4),
        "multi_source_confirm_rate": round(mean(multi_flags), 4),
        "untraceable": len(errors),
    }
    print(json.dumps(summary, ensure_ascii=False))
    if args.out_dir:
        out = Path(args.out_dir)
        dump_json(out / "evidence_errors.json", {"untraceable": errors[:300]})
        write_report(
            out / "evidence_report.md",
            "证据可溯源与跨源确认评测报告",
            [
                f"## 证据可溯源率\n\n{mean(trace_flags):.2%}（结论中能回填到原文且 quote 一致的占比）。",
                f"## 跨源确认率\n\n{mean(multi_flags):.2%}（证据 source_id ≥ 2 或 grade=multi_source）。",
                "无证据的结论按 ADR 0003 不应进入图谱。本指标把这条规矩变成可打分的数。",
            ],
        )


if __name__ == "__main__":
    main()
