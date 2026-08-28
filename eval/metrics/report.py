#!/usr/bin/env python3
"""汇总各指标报告为评委可读的一份 Markdown。"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--reports-dir", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    d = Path(args.reports_dir)
    parts = ["# 职途罗盘 JobE 评测汇总\n"]
    for name in [
        "jd_parse_report.md",
        "resume_extract_report.md",
        "match_report.md",
        "evidence_report.md",
    ]:
        f = d / name
        if f.exists():
            parts.append(f.read_text(encoding="utf-8"))
            parts.append("\n---\n")
    Path(args.out).write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
