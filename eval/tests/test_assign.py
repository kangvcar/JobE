"""档位规则与准则第 3 节对齐，阈值含等号。"""

from assign import assign_tier


def _sk(name, family, necessity="required", level=2, level_hint=None):
    s = {"name": name, "family": family, "necessity": necessity, "level": level}
    if level_hint is not None:
        s["level_hint"] = level_hint
    return s


def test_r4_strong():
    profile = [_sk("PyTorch", "ai", level=2), _sk("CUDA", "ai", level=2), _sk("Linux", "general", level=2)]
    jd = [_sk("PyTorch", "ai"), _sk("CUDA", "ai"), _sk("Linux", "general")]
    out = assign_tier(profile, jd, "ai", profile_edu="硕士", jd_edu="本科", profile_years=5, jd_min_years=3)
    assert out["tier"] == "strong"
    assert out["rule"] == "R4"


def test_r5_adequate_one_dir_miss():
    profile = [
        _sk("PyTorch", "ai", level=2),
        _sk("Linux", "general", level=2),
        _sk("Git", "general", level=2),
    ]
    jd = [_sk("PyTorch", "ai"), _sk("CUDA", "ai"), _sk("Linux", "general"), _sk("Git", "general")]
    out = assign_tier(profile, jd, "ai", profile_edu="本科", jd_edu="本科", profile_years=4, jd_min_years=3)
    assert out["coverage"] >= 0.70
    assert out["n_dir_miss"] == 1
    assert out["tier"] == "adequate"


def test_r6_gapped_coverage_069():
    # 3/5 = 0.6 → gapped
    profile = [_sk("Spark", "bigdata", level=2), _sk("Hive", "bigdata", level=2), _sk("Linux", "general", level=2)]
    jd = [
        _sk("Spark", "bigdata"),
        _sk("Hive", "bigdata"),
        _sk("Flink", "bigdata"),
        _sk("Kafka", "bigdata"),
        _sk("Linux", "general"),
    ]
    out = assign_tier(profile, jd, "bigdata", profile_edu="本科", jd_edu="本科", profile_years=3, jd_min_years=3)
    assert out["tier"] == "gapped"


def test_r1_family_mismatch():
    profile = [_sk("PyTorch", "ai", level=2), _sk("Linux", "general", level=2), _sk("Git", "general", level=2)]
    jd = [_sk("STM32", "iot"), _sk("FreeRTOS", "iot"), _sk("MQTT", "iot"), _sk("Linux", "general")]
    out = assign_tier(profile, jd, "iot", profile_edu="本科", jd_edu="本科", profile_years=3, jd_min_years=1)
    assert out["family_mismatch"] is True
    assert out["tier"] == "mismatch"
    assert out["rule"] == "R1"


def test_insufficient_not_counted_as_coverage():
    profile = [_sk("PyTorch", "ai", level=1), _sk("CUDA", "ai", level=2)]
    jd = [_sk("PyTorch", "ai"), _sk("CUDA", "ai")]  # required_level default 2
    out = assign_tier(profile, jd, "ai", profile_edu="硕士", jd_edu="本科", profile_years=5, jd_min_years=1)
    py = next(j for j in out["judgments"] if j["skill_name"] == "PyTorch")
    assert py["verdict"] == "insufficient"
    assert out["coverage"] == 0.5
