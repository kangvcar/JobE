"""按《匹配档位判定准则》第 3 节顺序判定。金标准必须走这里，禁止手改档位。"""

from __future__ import annotations

from typing import Iterable

TIER_ORDER = {"strong": 3, "adequate": 2, "gapped": 1, "mismatch": 0}
EDU_ORDER = {"不限": 0, "大专": 1, "本科": 2, "硕士": 3, "博士": 4}

SOFT = "soft"
GENERAL = "general"


def _norm(name: str) -> str:
    return (name or "").strip().casefold()


def coverage_bundle(
    profile_skills: Iterable[dict],
    jd_skills: Iterable[dict],
    jd_family: str,
) -> dict:
    profile = {_norm(s["name"]): int(s.get("level", 2)) for s in profile_skills}
    required: list[dict] = []
    directional: list[dict] = []
    all_tech: list[dict] = []
    for s in jd_skills:
        if s.get("family") == SOFT:
            continue
        all_tech.append(s)
        if s.get("necessity", "required") == "required":
            required.append(s)
            if s.get("family") == jd_family:
                directional.append(s)
    if not required:
        required = list(all_tech)
        directional = [s for s in required if s.get("family") == jd_family]

    def required_level(skill: dict) -> int:
        hint = skill.get("level_hint")
        if hint is not None:
            return int(hint)
        return 2 if skill.get("necessity", "required") == "required" else 1

    judgments = []
    sat_required: list[str] = []
    sat_dir: list[str] = []
    for s in all_tech:
        key = _norm(s["name"])
        need = required_level(s)
        held = profile.get(key)
        if held is None:
            verdict = "missing"
        elif held >= need:
            verdict = "satisfied"
        else:
            verdict = "insufficient"
        rec = {
            "skill_name": s["name"],
            "required": s.get("necessity", "required") == "required",
            "verdict": verdict,
            "held_level": held,
            "required_level": need,
        }
        judgments.append(rec)
        if rec["required"] and verdict == "satisfied":
            sat_required.append(s["name"])
            if s.get("family") == jd_family:
                sat_dir.append(s["name"])

    r_names = [s["name"] for s in required]
    d_names = [s["name"] for s in directional]
    c = len(sat_required) / len(r_names) if r_names else 1.0
    c_dir = len(sat_dir) / len(d_names) if d_names else 1.0
    n_dir_miss = len(d_names) - len(sat_dir)

    surplus = []
    jd_keys = {_norm(s["name"]) for s in jd_skills}
    for name, level in profile.items():
        if name not in jd_keys:
            surplus.append({"skill_name": name, "kind": "surplus", "held_level": level})

    return {
        "coverage": c,
        "direction_coverage": c_dir,
        "n_dir_miss": n_dir_miss,
        "n_required": len(r_names),
        "judgments": judgments,
        "surplus": surplus,
        "required_names": r_names,
        "directional_names": d_names,
    }


def profile_family(profile_skills: Iterable[dict]) -> str | None:
    counts: dict[str, int] = {}
    for s in profile_skills:
        fam = s.get("family")
        if fam in {None, SOFT, GENERAL}:
            continue
        counts[fam] = counts.get(fam, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def edu_ok(profile_edu: str | None, jd_edu: str | None) -> bool:
    if not jd_edu or jd_edu == "不限":
        return True
    if not profile_edu:
        return False
    return EDU_ORDER.get(profile_edu, 0) >= EDU_ORDER.get(jd_edu, 0)


def exp_ok(profile_years: float | None, jd_min_years: int | None) -> bool:
    if jd_min_years is None or jd_min_years <= 0:
        return True
    if profile_years is None:
        return False
    return float(profile_years) >= float(jd_min_years)


def assign_tier(
    profile_skills: list[dict],
    jd_skills: list[dict],
    jd_family: str,
    profile_edu: str | None = None,
    jd_edu: str | None = None,
    profile_years: float | None = None,
    jd_min_years: int | None = None,
) -> dict:
    bundle = coverage_bundle(profile_skills, jd_skills, jd_family)
    c = bundle["coverage"]
    c_dir = bundle["direction_coverage"]
    n_dir_miss = bundle["n_dir_miss"]
    pf = profile_family(profile_skills)
    family_mismatch = pf is not None and pf != jd_family and c_dir < 0.20
    e_ok = edu_ok(profile_edu, jd_edu)
    x_ok = exp_ok(profile_years, jd_min_years)

    rule = "R7"
    tier = "mismatch"
    if family_mismatch:
        rule, tier = "R1", "mismatch"
    elif c < 0.30:
        rule, tier = "R2", "mismatch"
    elif c < 0.40 and (not e_ok) and (not x_ok):
        rule, tier = "R3", "mismatch"
    elif c >= 0.90 and n_dir_miss == 0 and (e_ok or x_ok):
        rule, tier = "R4", "strong"
    elif c >= 0.70 and n_dir_miss <= 1:
        rule, tier = "R5", "adequate"
    elif c >= 0.40:
        rule, tier = "R6", "gapped"
    else:
        rule, tier = "R7", "mismatch"

    return {
        "tier": tier,
        "rule": rule,
        "coverage": round(c, 6),
        "direction_coverage": round(c_dir, 6),
        "n_dir_miss": n_dir_miss,
        "family_mismatch": family_mismatch,
        "edu_ok": e_ok,
        "exp_ok": x_ok,
        "profile_family": pf,
        "judgments": bundle["judgments"],
        "surplus": bundle["surplus"],
    }


def rank_roles(profile: dict, roles: list[dict]) -> list[str]:
    """roles 已含 assign_tier 结果。排序键见准则第 6 节。"""
    def key(role: dict) -> tuple:
        a = role["assignment"]
        return (
            -TIER_ORDER[a["tier"]],
            -a["coverage"],
            a["n_dir_miss"],
            role["id"],
        )
    return [r["id"] for r in sorted(roles, key=key)]
