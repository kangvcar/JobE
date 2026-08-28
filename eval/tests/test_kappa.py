"""Cohen's κ 必须算对：这是金标准可信度的唯一数字。"""

from metrics.common import binary_presence_kappa, cohens_kappa


def test_perfect_agreement():
    pairs = [("strong", "strong")] * 20 + [("gapped", "gapped")] * 10
    assert cohens_kappa(pairs) == 1.0


def test_empty():
    assert cohens_kappa([]) == 0.0


def test_classic_2x2():
    # A yes=25, A no=25; B yes=30, B no=20; both yes=20, both no=15
    pairs = (
        [("yes", "yes")] * 20
        + [("yes", "no")] * 5
        + [("no", "yes")] * 10
        + [("no", "no")] * 15
    )
    kappa = cohens_kappa(pairs)
    # po=0.70, pe=0.5*0.6 + 0.5*0.4=0.50, κ=0.40
    assert abs(kappa - 0.40) < 1e-9


def test_chance_level_independent():
    # 完全按边际独立乱配时 κ 接近 0
    pairs = [("a", "a")] * 25 + [("a", "b")] * 25 + [("b", "a")] * 25 + [("b", "b")] * 25
    assert abs(cohens_kappa(pairs)) < 1e-9


def test_all_same_label():
    pairs = [("x", "x")] * 40
    assert cohens_kappa(pairs) == 1.0


def test_binary_presence_kappa_perfect():
    a = {"d1": {"Python", "Spark"}, "d2": {"MQTT"}}
    b = {"d1": {"Python", "Spark"}, "d2": {"MQTT"}}
    assert binary_presence_kappa(a, b) == 1.0


def test_binary_presence_kappa_uses_true_negatives():
    # 两篇文档、三个技能点；只在一篇上有一处分歧时 κ 应明显大于 0
    a = {"d1": {"Python", "Spark"}, "d2": {"MQTT"}}
    b = {"d1": {"Python", "Spark", "Hive"}, "d2": {"MQTT"}}
    k = binary_presence_kappa(a, b)
    assert k > 0.5
