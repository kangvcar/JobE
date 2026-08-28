#!/usr/bin/env python3
"""合成简历评测集。固定种子，ground truth 随排版同时写出。

不使用真实简历。个人信息层用 faker(zh_CN)；正文用模板植入技能点原文，
保证 span 与 bbox 精确可知。扫描件路径：先栅格化再包回 PDF。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "metrics"))

from lexicon.skills import BY_NAME, SKILLS  # noqa: E402
from metrics.common import dump_jsonl  # noqa: E402

PAGE_W, PAGE_H = 595.0, 842.0
FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]

FAMILY_SKILLS = {
    "ai": [s.name for s in SKILLS if s.family == "ai"],
    "bigdata": [s.name for s in SKILLS if s.family == "bigdata"],
    "smart_system": [s.name for s in SKILLS if s.family == "smart_system"],
    "iot": [s.name for s in SKILLS if s.family == "iot"],
    "general": [s.name for s in SKILLS if s.family == "general"],
}

JOB_TITLES = {
    "ai": ["机器学习工程师", "算法工程师", "大模型工程师", "视觉算法工程师"],
    "bigdata": ["大数据开发工程师", "数据平台工程师", "数仓工程师", "实时计算工程师"],
    "smart_system": ["自动驾驶工程师", "SLAM 工程师", "规划控制工程师", "机器人软件工程师"],
    "iot": ["嵌入式工程师", "物联网开发工程师", "BSP 工程师", "MCU 软件工程师"],
}

UNIV = ["清华大学", "北京大学", "浙江大学", "上海交通大学", "复旦大学", "南京大学", "中国科学技术大学", "哈尔滨工业大学"]
DEGREES = ["本科", "硕士", "博士"]
COMPANIES = ["星河智能", "北辰数据", "临川电子", "青梧系统", "澄空智造", "雁栖计算", "浦江半导体", "灵犀车联"]


@dataclass
class Run:
    text: str
    x: float
    y: float
    size: float
    page: int
    kind: str  # body / field / skill
    field_name: str | None = None
    skill_name: str | None = None
    skill_family: str | None = None
    skill_level: int | None = None
    width: float = 0.0


@dataclass
class Doc:
    runs: list[Run] = field(default_factory=list)
    pages: int = 1


def pick_font() -> str:
    for p in FONT_PATHS:
        if Path(p).exists():
            return p
    raise FileNotFoundError("未找到中文字体")


def string_width(text: str, size: float, font_name: str, pdfmetrics, register) -> float:
    register()
    from reportlab.pdfbase.pdfmetrics import stringWidth

    return stringWidth(text, font_name, size)


def wrap(text: str, max_w: float, size: float, font_name: str, width_fn) -> list[str]:
    lines: list[str] = []
    buf = ""
    for ch in text:
        trial = buf + ch
        if width_fn(trial, size) <= max_w:
            buf = trial
        else:
            if buf:
                lines.append(buf)
            buf = ch
    if buf:
        lines.append(buf)
    return lines or [""]


def build_persona(rng: random.Random, fake, family: str, level: str, extra_skills: list[str] | None) -> dict:
    n_core = {"junior": 5, "senior": 8, "expert": 11}[level]
    core = rng.sample(FAMILY_SKILLS[family], k=min(n_core, len(FAMILY_SKILLS[family])))
    general = rng.sample(FAMILY_SKILLS["general"], k=4)
    skills = []
    seen = set()
    for name in (extra_skills or []) + core + general:
        if name in seen or name not in BY_NAME:
            continue
        seen.add(name)
        if extra_skills and name in extra_skills:
            lvl = 3 if level == "expert" else 2
        else:
            lvl = {"junior": 2, "senior": 2, "expert": 3}[level]
        if BY_NAME[name].family == "general":
            lvl = min(lvl, 2)
        skills.append({"name": name, "family": BY_NAME[name].family, "level": lvl})
    years = {"junior": rng.choice([0, 1, 2]), "senior": rng.choice([4, 5, 6, 7]), "expert": rng.choice([8, 10, 12])}[level]
    edu = rng.choice(DEGREES if level != "junior" else ["本科", "硕士"])
    if level == "expert" and rng.random() < 0.5:
        edu = rng.choice(["硕士", "博士"])
    name = fake.name()
    return {
        "name": name,
        "phone": fake.phone_number(),
        "email": fake.email(),
        "city": fake.city(),
        "education": edu,
        "university": rng.choice(UNIV),
        "years": years,
        "family": family,
        "level": level,
        "title": rng.choice(JOB_TITLES[family]),
        "skills": skills,
        "company": rng.choice(COMPANIES),
    }


def layout_single(p: dict, width_fn) -> Doc:
    doc = Doc()
    y = 56
    page = 0

    def add(text, x, y, size, kind="body", **kw) -> float:
        w = width_fn(text, size)
        doc.runs.append(Run(text, x, y, size, page, kind, width=w, **kw))
        return y + size + 6

    y = add(p["name"], 48, y, 18, "field", field_name="name")
    x = 48
    contact_y = y
    for fname, val, gap in (("phone", p["phone"], "  |  "), ("email", p["email"], "  |  "), ("city", p["city"], "")):
        w = width_fn(val, 10)
        doc.runs.append(Run(val, x, contact_y, 10, page, "field", field_name=fname, width=w))
        x += w + width_fn(gap, 10)
    y = contact_y + 16
    y = add(f"意向岗位：{p['title']}", 48, y, 11)
    y = add("教育经历", 48, y + 8, 13)
    edu_line = f"{p['university']}  {p['education']}  计算机科学与技术"
    y = add(edu_line, 48, y, 10, "field", field_name="education")
    y = add("工作经历", 48, y + 8, 13)
    y = add(f"{p['company']}  |  {p['title']}  |  {p['years']}年经验", 48, y, 10)
    bullets = _bullets(p)
    for b in bullets:
        for line in wrap("· " + b, 500, 10, "CN", width_fn):
            y = add(line, 56, y, 10)
            if y > 780:
                page += 1
                doc.pages = page + 1
                y = 56
    y = add("技能", 48, y + 8, 13)
    skill_line = "、".join(s["name"] for s in p["skills"])
    x = 48
    row_y = y
    for i, s in enumerate(p["skills"]):
        token = s["name"] if i == len(p["skills"]) - 1 else s["name"] + "、"
        w = width_fn(token, 10)
        if x + w > 540:
            x = 48
            row_y += 16
        doc.runs.append(
            Run(s["name"], x, row_y, 10, page, "skill", skill_name=s["name"], skill_family=s["family"], skill_level=s["level"], width=width_fn(s["name"], 10))
        )
        x += w
    doc.pages = page + 1
    return doc


def layout_two_column(p: dict, width_fn) -> Doc:
    doc = Doc()
    page = 0
    # 左栏
    y = 64
    doc.runs.append(Run(p["name"], 36, y, 16, page, "field", field_name="name", width=width_fn(p["name"], 16)))
    y += 28
    for fname, val in (("phone", p["phone"]), ("email", p["email"]), ("city", p["city"]), ("education", f"{p['education']} · {p['university']}")):
        doc.runs.append(Run(val, 36, y, 9, page, "field", field_name=fname, width=width_fn(val, 9)))
        y += 16
    y += 10
    doc.runs.append(Run("技能清单", 36, y, 11, page, "body", width=width_fn("技能清单", 11)))
    y += 18
    for s in p["skills"]:
        doc.runs.append(
            Run(s["name"], 36, y, 9, page, "skill", skill_name=s["name"], skill_family=s["family"], skill_level=s["level"], width=width_fn(s["name"], 9))
        )
        y += 14
    # 右栏
    y = 64
    doc.runs.append(Run("工作经历", 250, y, 13, page, "body", width=width_fn("工作经历", 13)))
    y += 22
    doc.runs.append(Run(f"{p['company']} · {p['title']}", 250, y, 10, page, "body", width=width_fn(f"{p['company']} · {p['title']}", 10)))
    y += 18
    for b in _bullets(p):
        for line in wrap("· " + b, 310, 9, "CN", width_fn):
            doc.runs.append(Run(line, 250, y, 9, page, "body", width=width_fn(line, 9)))
            y += 13
            if y > 800:
                page += 1
                doc.pages = page + 1
                y = 64
    doc.pages = page + 1
    return doc


def layout_table(p: dict, width_fn) -> Doc:
    doc = layout_single(p, width_fn)
    # 在技能区已是逐个技能 run；再加页眉页脚
    for pg in range(doc.pages):
        doc.runs.append(Run("内部简历 · 请勿外传", 48, 24, 8, pg, "body", width=width_fn("内部简历 · 请勿外传", 8)))
        foot = f"— {pg + 1}/{doc.pages} —"
        doc.runs.append(Run(foot, 280, 820, 8, pg, "body", width=width_fn(foot, 8)))
    return doc


def layout_multipage(p: dict, width_fn) -> Doc:
    # 拉长工作经历
    extra = p.copy()
    extra["skills"] = p["skills"]
    bullets = _bullets(p) * 6
    p2 = dict(p)
    p2["_bullets"] = bullets
    doc = Doc()
    y, page = 56, 0

    def add(text, size=10, **kw):
        nonlocal y, page
        for line in wrap(text, 500, size, "CN", width_fn):
            if y > 780:
                page += 1
                y = 56
            w = width_fn(line, size)
            doc.runs.append(Run(line, 48, y, size, page, kw.get("kind", "body"), width=w, **{k: v for k, v in kw.items() if k != "kind"}))
            y += size + 6

    add(p["name"], 18, kind="field", field_name="name")
    add(p["phone"], 10, kind="field", field_name="phone")
    add(p["email"], 10, kind="field", field_name="email")
    add(p["city"], 10, kind="field", field_name="city")
    add(f"{p['university']} {p['education']}", 10, kind="field", field_name="education")
    add("工作经历", 13)
    for i in range(3):
        add(f"{p['company']}{i+1} | {p['title']} | 跨页项目 {i+1}", 11)
        for b in _bullets(p):
            add("· " + b, 10)
    add("技能", 13)
    for s in p["skills"]:
        add(s["name"], 10, kind="skill", skill_name=s["name"], skill_family=s["family"], skill_level=s["level"])
    doc.pages = page + 1
    return doc


def _bullets(p: dict) -> list[str]:
    names = [s["name"] for s in p["skills"][:6]]
    while len(names) < 3:
        names.append("Linux")
    return [
        f"基于 {names[0]} 完成核心模块开发与上线，协同 {names[1]} 相关工作。",
        f"在生产环境落地 {names[2]}，编写技术文档并参与评审。",
        f"使用 {names[min(3, len(names)-1)]} 排查性能问题，沉淀可复用组件。",
    ]


def reading_order_text(doc: Doc) -> str:
    runs = sorted(doc.runs, key=lambda r: (r.page, r.y, r.x))
    parts: list[str] = []
    last = None
    for r in runs:
        if last is not None and (r.page != last.page or abs(r.y - last.y) > 2):
            parts.append("\n")
        elif last is not None and r.x > last.x + last.width + 1:
            parts.append(" ")
        parts.append(r.text)
        last = r
    return "".join(parts)


def gold_from_doc(rid: str, p: dict, doc: Doc, pdf_path: str, layout: str, scanned: bool) -> dict:
    text = reading_order_text(doc)
    fields = {}
    for r in doc.runs:
        if r.kind == "field" and r.field_name and r.field_name not in fields:
            start = text.find(r.text)
            fields[r.field_name] = {
                "value": p[r.field_name] if r.field_name in p else r.text,
                "span": {"start": start, "end": start + len(r.text)} if start >= 0 else None,
                "bbox": [r.x, r.y, r.x + r.width, r.y + r.size],
                "page_index": r.page,
            }
    skills = []
    seen = set()
    for r in doc.runs:
        if r.kind != "skill" or not r.skill_name or r.skill_name in seen:
            continue
        seen.add(r.skill_name)
        start = text.find(r.text)
        skills.append(
            {
                "name": r.skill_name,
                "family": r.skill_family,
                "level": r.skill_level,
                "surface_form": r.text,
                "span": {"start": start, "end": start + len(r.text)} if start >= 0 else None,
                "bbox": [r.x, r.y, r.x + r.width, r.y + r.size],
                "page_index": r.page,
            }
        )
    return {
        "id": rid,
        "difficulty": "scanned" if scanned else {"single_column": "easy", "two_column": "medium", "table_header": "hard", "multipage": "hard"}[layout],
        "layout": "scanned" if scanned else layout,
        "family": p["family"],
        "level": p["level"],
        "pdf_path": pdf_path,
        "text": text,
        "years": p["years"],
        "anchor_role_id": p.get("anchor_role_id"),
        "overlap_frac": p.get("overlap_frac"),
        "fields": fields,
        "skills": skills,
    }


def render_pdf(doc: Doc, path: Path, font_path: str, scanned: bool) -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    kwargs = {}
    if font_path.endswith(".ttc"):
        kwargs["subfontIndex"] = 0
    pdfmetrics.registerFont(TTFont("CN", font_path, **kwargs))
    c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    if scanned:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
        import io

        scale = 2
        font_cache: dict[float, ImageFont.FreeTypeFont] = {}

        def font(sz):
            if sz not in font_cache:
                font_cache[sz] = ImageFont.truetype(font_path, int(sz * scale))
            return font_cache[sz]

        for pg in range(doc.pages):
            img = Image.new("RGB", (int(PAGE_W * scale), int(PAGE_H * scale)), (245, 245, 240))
            dr = ImageDraw.Draw(img)
            for r in doc.runs:
                if r.page != pg:
                    continue
                dr.text((r.x * scale, r.y * scale), r.text, fill=(20, 20, 20), font=font(r.size))
            img = ImageEnhance.Contrast(img).enhance(0.92)
            img = img.filter(ImageFilter.GaussianBlur(radius=0.4))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=38)
            buf.seek(0)
            from reportlab.lib.utils import ImageReader

            c.drawImage(ImageReader(buf), 0, 0, width=PAGE_W, height=PAGE_H)
            c.showPage()
        c.save()
        return

    for pg in range(doc.pages):
        for r in doc.runs:
            if r.page != pg:
                continue
            # reportlab y 原点在底部
            c.setFont("CN", r.size)
            c.drawString(r.x, PAGE_H - r.y - r.size, r.text)
        c.showPage()
    c.save()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n", type=int, default=64)
    parser.add_argument("--jd-gold", type=Path, default=ROOT / "datasets" / "jd" / "gold.jsonl")
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()

    from faker import Faker

    rng = random.Random(args.seed)
    fake = Faker("zh_CN")
    Faker.seed(args.seed)
    fake.seed_instance(args.seed)

    font_path = pick_font()
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    kw = {"subfontIndex": 0} if font_path.endswith(".ttc") else {}
    pdfmetrics.registerFont(TTFont("CN", font_path, **kw))

    def width_fn(text: str, size: float) -> float:
        from reportlab.pdfbase.pdfmetrics import stringWidth

        return stringWidth(text, "CN", size)

    jds_by_fam: dict[str, list[dict]] = {k: [] for k in ("ai", "bigdata", "smart_system", "iot")}
    if args.jd_gold.exists():
        import json as _json

        with args.jd_gold.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    jd = _json.loads(line)
                    jds_by_fam.get(jd.get("family"), []).append(jd)

    pdf_dir = args.out_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    families = ["ai", "bigdata", "smart_system", "iot"]
    levels = ["junior", "senior", "expert"]
    layouts_cycle = ["single_column", "two_column", "table_header", "multipage"]
    # 控制与锚点岗位的技能重叠，使后续匹配集能抽出四档
    overlap_cycle = [1.0, 0.78, 0.52, 0.18]
    gold_rows = []

    n = args.n
    for i in range(n):
        family = families[i % 4]
        level = levels[i % 3]
        pool = jds_by_fam.get(family) or []
        anchor = pool[i % len(pool)] if pool else None
        frac = overlap_cycle[i % 4]
        extra = None
        if anchor:
            sk = [s for s in anchor.get("skills") or [] if s.get("family") != "soft"]
            req_dir = [s["name"] for s in sk if s.get("necessity", "required") == "required" and s.get("family") == family]
            req_oth = [s["name"] for s in sk if s.get("necessity", "required") == "required" and s.get("family") != family]
            if frac >= 0.95:
                extra = req_dir + req_oth
            elif frac >= 0.70:
                extra = (req_dir[:-1] if len(req_dir) > 1 else list(req_dir)) + req_oth[: max(1, int(0.75 * len(req_oth)) or 0)]
            elif frac >= 0.40:
                extra = req_dir[: max(1, len(req_dir) // 2)] + req_oth[: max(0, len(req_oth) // 2)]
            else:
                extra = req_oth[:2]
        p = build_persona(rng, fake, family, level, extra)
        p["anchor_role_id"] = anchor["id"] if anchor else None
        p["overlap_frac"] = frac
        layout = layouts_cycle[i % 4]
        scanned = i % 8 == 7
        if layout == "single_column":
            doc = layout_single(p, width_fn)
        elif layout == "two_column":
            doc = layout_two_column(p, width_fn)
        elif layout == "table_header":
            doc = layout_table(p, width_fn)
        else:
            doc = layout_multipage(p, width_fn)
        if layout != "multipage" and i % 11 == 0:
            # 少量强制跨页
            doc = layout_multipage(p, width_fn)
            layout = "multipage"
        rid = f"resume_{i+1:03d}"
        rel = f"pdfs/{rid}.pdf"
        path = pdf_dir / f"{rid}.pdf"
        render_pdf(doc, path, font_path, scanned=scanned)
        gold_rows.append(gold_from_doc(rid, p, doc, rel, layout, scanned))

    dump_jsonl(args.out_dir / "gold.jsonl", gold_rows)
    print(f"wrote {len(gold_rows)} resumes -> {args.out_dir}")


if __name__ == "__main__":
    main()
