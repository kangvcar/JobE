"""职业分类大典骨架。数据来自 2022 年版社会公示稿抽取，正式发布口径 1639 个职业。"""

from __future__ import annotations

import json
from pathlib import Path

CATALOG = Path(__file__).resolve().parent
EXTRACT = CATALOG / "occupation_extract.json"

# 公示稿换行截断，对照定义标题补全。
NAME_FIXES = {
    "2-02-10-06": ("嵌入式系统设计工程技术人员", True, False),
    "2-02-10-08": ("信息系统运行维护工程技术人员", True, False),
    "2-02-07-10": ("特种设备管理和应用工程技术人员", False, False),
    "2-02-09-04": ("电子仪器与电子测量工程技术人员", False, False),
}

# 新一代信息技术相关小类：精抽到职业（细类）级，并挂已知工种。
IT_SMALL_PREFIXES = (
    "2-02-07",
    "2-02-09",
    "2-02-10",
    "2-02-38",
    "4-04-01",
    "4-04-02",
    "4-04-03",
    "4-04-04",
    "4-04-05",
    "4-04-99",
    "6-25-01",
    "6-25-02",
    "6-25-03",
    "6-25-04",
    "6-25-99",
    "6-31-07",
    "2-06-14",
    "4-01-06",
    "4-12-02",
)

# 大典正文写明的工种，没有独立细类编码。
JOB_TYPES = [
    {
        "code": "4-04-05-05-jt-01",
        "name": "数据标注员",
        "parent_code": "4-04-05-05",
        "is_digital": True,
        "is_green": False,
        "source_note": "人工智能训练师职业下工种，见人社厅发〔2020〕17号",
    },
    {
        "code": "4-04-05-05-jt-02",
        "name": "人工智能算法测试员",
        "parent_code": "4-04-05-05",
        "is_digital": True,
        "is_green": False,
        "source_note": "人工智能训练师职业下工种，见人社厅发〔2020〕17号",
    },
]


def _parent_code(code: str) -> str | None:
    parts = code.split("-")
    if len(parts) <= 1:
        return None
    return "-".join(parts[:-1])


def _is_it(code: str) -> bool:
    return any(code == p or code.startswith(p + "-") for p in IT_SMALL_PREFIXES)


def load_extract() -> dict:
    return json.loads(EXTRACT.read_text(encoding="utf-8"))


def iter_occupations(version: str) -> list[dict]:
    data = load_extract()
    rows: list[dict] = []

    def add(level: str, code: str, name: str, gbm: str | None, parent: str | None,
            is_digital: bool, is_green: bool, placeholder: bool, extra: dict | None = None) -> None:
        rec = {
            "id": f"occ.{code}",
            "code": code,
            "gbm": gbm,
            "name": name,
            "level": level,
            "parent_code": parent,
            "is_digital": is_digital,
            "is_green": is_green,
            "is_it_related": _is_it(code),
            "is_placeholder": placeholder,
            "ontology_version": version,
            "source": "职业分类大典2022公示稿",
        }
        if extra:
            rec.update(extra)
        rows.append(rec)

    for m in data["majors"]:
        add("major", m["code"], m["name"], m.get("gbm"), None, False, False, False)
    for m in data["mids"]:
        add("mid", m["code"], m["name"], m.get("gbm"), _parent_code(m["code"]), False, False, False)
    for s in data["smalls"]:
        add(
            "small",
            s["code"],
            s["name"],
            s.get("gbm"),
            _parent_code(s["code"]),
            False,
            False,
            not _is_it(s["code"]),
        )
    for o in data["occupations"]:
        code = o["code"]
        name, is_d, is_g = o["name"], o.get("is_digital", False), o.get("is_green", False)
        if code in NAME_FIXES:
            name, is_d, is_g = NAME_FIXES[code]
        it = _is_it(code)
        add(
            "occupation",
            code,
            name,
            None,
            _parent_code(code),
            is_d,
            is_g,
            placeholder=not it,
        )
    for jt in JOB_TYPES:
        add(
            "job_type",
            jt["code"],
            jt["name"],
            None,
            jt["parent_code"],
            jt["is_digital"],
            jt["is_green"],
            False,
            extra={"source_note": jt["source_note"]},
        )

    meta = {
        "id": "occ._meta",
        "code": "_meta",
        "gbm": None,
        "name": "职业分类大典元数据",
        "level": "meta",
        "parent_code": None,
        "is_digital": False,
        "is_green": False,
        "is_it_related": False,
        "is_placeholder": False,
        "ontology_version": version,
        "source": "职业分类大典2022公示稿",
        "draft_occupation_count": data["draft_occupation_count"],
        "official_occupation_count": data["official_occupation_count"],
        "note": data["source_note"],
        "digital_flag_in_draft": sum(1 for o in data["occupations"] if o.get("is_digital")),
        "official_digital_count": data["digital_occupation_count_official"],
        "official_green_count": data["green_occupation_count_official"],
        "pending": "正式版相对公示稿多出的 3 个职业名称待对照纸质书；数字职业 97 个与公示稿 S 标记 89 个的差额待对照正式版补旗标。",
    }
    rows.append(meta)
    rows.sort(key=lambda r: (r["level"] != "meta", r["code"]))
    return rows
