"""指标脚本对人造 pred 能跑通，且错误分析指向改对的那几条。"""

import json
import subprocess
import sys
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1]
PY = sys.executable
FIX = EVAL / "metrics" / "fixtures"


def _run(script: str, extra: list[str]) -> dict:
    cmd = [PY, str(EVAL / "metrics" / script), *extra]
    out = subprocess.check_output(cmd, text=True)
    return json.loads(out.strip().splitlines()[-1])


def test_jd_parse_detects_field_and_skill_errors():
    s = _run(
        "jd_parse.py",
        ["--pred", str(FIX / "jd_pred.jsonl"), "--gold", str(FIX / "jd_gold.jsonl")],
    )
    assert s["n_gold"] == 3
    assert s["field_accuracy"]["city"] < 1.0
    assert s["skill_f1"] < 1.0


def test_resume_extract_trace():
    s = _run(
        "resume_extract.py",
        ["--pred", str(FIX / "resume_pred.jsonl"), "--gold", str(FIX / "resume_gold.jsonl")],
    )
    assert "trace_accuracy" in s
    assert s["n_gold"] == 2


def test_match_tier_and_ranking():
    s = _run(
        "match_tier.py",
        [
            "--pred",
            str(FIX / "match_pred.jsonl"),
            "--gold",
            str(FIX / "match_gold.jsonl"),
            "--rank-pred",
            str(FIX / "rank_pred.jsonl"),
            "--rank-gold",
            str(FIX / "rank_gold.jsonl"),
        ],
    )
    assert s["tier_accuracy"] < 1.0
    assert s["ranking"]["n_groups"] == 1


def test_evidence_trace():
    s = _run(
        "evidence_trace.py",
        ["--pred", str(FIX / "evidence_pred.jsonl"), "--gold", str(FIX / "jd_gold.jsonl")],
    )
    assert s["n_claims"] > 0
    assert 0 <= s["evidence_traceable_rate"] <= 1
