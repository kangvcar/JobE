#!/usr/bin/env python3
"""一条命令：单元测试 + 人造 pred 自测 + 写出 Markdown 报告。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1]
PY = sys.executable
FIX = EVAL / "metrics" / "fixtures"
REPORTS = EVAL / "reports"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(EVAL))


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    run([PY, "-m", "pytest", str(EVAL / "tests")])
    jobs = [
        [
            PY,
            str(EVAL / "metrics" / "jd_parse.py"),
            "--pred",
            str(FIX / "jd_pred.jsonl"),
            "--gold",
            str(FIX / "jd_gold.jsonl"),
            "--out-dir",
            str(REPORTS),
        ],
        [
            PY,
            str(EVAL / "metrics" / "resume_extract.py"),
            "--pred",
            str(FIX / "resume_pred.jsonl"),
            "--gold",
            str(FIX / "resume_gold.jsonl"),
            "--out-dir",
            str(REPORTS),
        ],
        [
            PY,
            str(EVAL / "metrics" / "match_tier.py"),
            "--pred",
            str(FIX / "match_pred.jsonl"),
            "--gold",
            str(FIX / "match_gold.jsonl"),
            "--rank-pred",
            str(FIX / "rank_pred.jsonl"),
            "--rank-gold",
            str(FIX / "rank_gold.jsonl"),
            "--out-dir",
            str(REPORTS),
        ],
        [
            PY,
            str(EVAL / "metrics" / "evidence_trace.py"),
            "--pred",
            str(FIX / "evidence_pred.jsonl"),
            "--gold",
            str(FIX / "jd_gold.jsonl"),
            "--out-dir",
            str(REPORTS),
        ],
    ]
    for cmd in jobs:
        run(cmd)
    run(
        [
            PY,
            str(EVAL / "metrics" / "report.py"),
            "--reports-dir",
            str(REPORTS),
            "--out",
            str(REPORTS / "SUMMARY.md"),
        ]
    )
    stats = {}
    for name, path in [
        ("jd_gold", EVAL / "datasets" / "jd" / "gold.jsonl"),
        ("resume_gold", EVAL / "datasets" / "resume" / "gold.jsonl"),
        ("match_pairs", EVAL / "datasets" / "match" / "pairs.jsonl"),
        ("ranking", EVAL / "datasets" / "match" / "ranking.jsonl"),
    ]:
        if path.exists():
            stats[name] = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    agree = EVAL / "datasets" / "jd" / "annotations" / "agreement.json"
    if agree.exists():
        stats["agreement"] = json.loads(agree.read_text(encoding="utf-8"))
    print(json.dumps({"dataset_stats": stats, "reports": str(REPORTS / "SUMMARY.md")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
