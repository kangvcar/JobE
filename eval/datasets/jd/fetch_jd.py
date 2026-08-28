#!/usr/bin/env python3
"""从 Moka 公开接口采集职位快照。只读公开、免鉴权接口，不绕反爬。"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_PATH = ROOT / "raw" / "moka_postings.jsonl"

# 已实测对公开接口返回非空职位列表的 orgId。siteId 仅用于拼官网 URL。
ORGS: list[tuple[str, str, str]] = [
    ("cambricon", "寒武纪", "44201"),
    ("cloudwalk", "云从科技", ""),
    ("4paradigm", "第四范式", ""),
    ("moonshot", "月之暗面", ""),
    ("biren", "壁仞科技", "44726"),
    ("iluvatar", "天数智芯", ""),
    ("enflame", "燧原科技", ""),
    ("dji", "大疆", ""),
    ("dahua", "大华股份", ""),
    ("hikvision", "海康威视", ""),
    ("zte", "中兴", "47588"),
    ("sangfor", "深信服", ""),
    ("nsfocus", "绿盟科技", ""),
    ("xiaopeng", "小鹏汽车", ""),
    ("geely", "吉利", "102042"),
    ("moka", "Moka", ""),
    ("shopee", "Shopee", "2962"),
    ("high-flyer", "幻方量化", "140576"),
    ("step", "阶跃星辰", "94904"),
    ("baai", "智源研究院", "42174"),
    ("smartmore", "思谋科技", "40505"),
    ("dolphindb", "DolphinDB", "37785"),
    ("threatbook", "微步在线", "39679"),
    ("didiglobal", "滴滴", "96064"),
    ("voyah", "岚图汽车", "146292"),
    ("ninebot", "九号公司", "45627"),
    ("eastmoney", "东方财富", "57970"),
    ("zhihu", "知乎", "68321"),
    ("tecorigin", "太初元碁", "47401"),
    ("honeywell", "霍尼韦尔", ""),
    ("skyworth", "创维", ""),
    ("se", "施耐德电气", "98712"),
]

KEYWORDS = [
    "算法",
    "机器学习",
    "深度学习",
    "大模型",
    "NLP",
    "视觉",
    "推荐",
    "数据",
    "大数据",
    "Spark",
    "数仓",
    "物联网",
    "IoT",
    "嵌入式",
    "智能",
    "芯片",
    "自动驾驶",
    "机器人",
    "感知",
    "平台",
]

TITLE_FAMILY = {
    "ai": re.compile(
        r"算法|机器学习|深度学习|大模型|LLM|NLP|视觉|多模态|推荐算法|"
        r"语音|强化学习|计算机视觉|生成式|AIGC|智能驾驶算法|感知算法"
    ),
    "bigdata": re.compile(
        r"大数据|数据开发|数据仓库|数仓|数据平台|数据工程|Spark|Flink|"
        r"Hive|数据分析|数据治理|数据中台|实时计算|离线开发"
    ),
    "smart_system": re.compile(
        r"自动驾驶|智能驾驶|机器人|SLAM|规划控制|感知融合|智能系统|"
        r"智能座舱|智驾|ROS|运动控制|嵌入式软件|车载"
    ),
    "iot": re.compile(
        r"物联网|IoT|嵌入式(?!软件)|MCU|RTOS|模组|网关|边缘计算|"
        r"传感器|STM32|LoRa|MQTT|设备驱动|BSP"
    ),
}

LEVEL_PATTERNS = [
    ("expert", re.compile(r"专家|总监|首席|研究员(?!实习)|Architect|Principal|资深专家")),
    ("senior", re.compile(r"资深|高级|Senior|Lead|组长|负责人")),
    ("junior", re.compile(r"初级|实习|校招|应届|Junior|助理")),
]


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"p", "br", "li", "div", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")


def html_to_text(raw: str) -> str:
    parser = _HTMLText()
    parser.feed(raw or "")
    text = html.unescape("".join(parser.parts))
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def classify_family(title: str, text: str) -> str:
    blob = f"{title}\n{text}"
    scores = {fam: 1 if pat.search(blob) else 0 for fam, pat in TITLE_FAMILY.items()}
    # 标题命中加权
    for fam, pat in TITLE_FAMILY.items():
        if pat.search(title):
            scores[fam] += 2
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "ai"


def classify_level(title: str, min_exp: int | None) -> str:
    for level, pat in LEVEL_PATTERNS:
        if pat.search(title):
            return level
    if min_exp is not None:
        if min_exp >= 8:
            return "expert"
        if min_exp >= 3:
            return "senior"
    return "junior"


def http_get_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "JobE-eval/0.1 (research; public ATS)", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_org(org_id: str, keyword: str, limit: int = 30) -> list[dict]:
    q = urllib.parse.urlencode({"mode": "social", "limit": str(limit), "keyword": keyword})
    url = f"https://api.mokahr.com/api-platform/v1/jobs/{urllib.parse.quote(org_id)}?{q}"
    try:
        data = http_get_json(url)
    except Exception as exc:  # noqa: BLE001 — 采集层要容忍单源失败
        print(f"  skip {org_id} kw={keyword}: {exc}", file=sys.stderr)
        return []
    return data.get("jobs") or []


def normalize_job(org_id: str, company: str, site_id: str, job: dict) -> dict | None:
    desc_html = job.get("description") or ""
    text = html_to_text(desc_html)
    if len(text) < 80:
        return None
    locs = job.get("locations") or []
    cities = []
    for loc in locs:
        city = (loc or {}).get("city") or (loc or {}).get("province")
        if city and city not in cities:
            cities.append(city)
    job_id = job.get("id") or ""
    site = site_id or "1"
    url = f"https://app.mokahr.com/social-recruitment/{org_id}/{site}#/job/{job_id}"
    title = (job.get("title") or "").strip()
    min_exp = job.get("minExperience")
    try:
        min_exp_i = int(min_exp) if min_exp is not None else None
    except (TypeError, ValueError):
        min_exp_i = None
    return {
        "source": "moka",
        "org_id": org_id,
        "job_id": job_id,
        "url": url,
        "company": company,
        "title": title,
        "city": cities[0] if cities else None,
        "cities": cities,
        "salary_min": job.get("minSalary"),
        "salary_max": job.get("maxSalary"),
        "education": job.get("education"),
        "min_experience": min_exp_i,
        "max_experience": job.get("maxExperience"),
        "commitment": job.get("commitment"),
        "department": (job.get("department") or {}).get("name"),
        "description_html": desc_html,
        "text": text,
        "family": classify_family(title, text),
        "level": classify_level(title, min_exp_i),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sleep", type=float, default=0.15, help="请求间隔秒")
    parser.add_argument("--limit-per-query", type=int, default=30)
    parser.add_argument("--out", type=Path, default=RAW_PATH)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    rows: list[dict] = []
    for org_id, company, site_id in ORGS:
        print(f"fetch {org_id} ({company})", file=sys.stderr)
        for kw in KEYWORDS:
            jobs = fetch_org(org_id, kw, limit=args.limit_per_query)
            time.sleep(args.sleep)
            for job in jobs:
                key = f"{org_id}:{job.get('id')}"
                if key in seen:
                    continue
                rec = normalize_job(org_id, company, site_id, job)
                if rec is None:
                    continue
                seen.add(key)
                rows.append(rec)
        print(f"  kept {len(rows)} unique so far", file=sys.stderr)

    with args.out.open("w", encoding="utf-8") as f:
        for rec in rows:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    families: dict[str, int] = {}
    for rec in rows:
        families[rec["family"]] = families.get(rec["family"], 0) + 1
    print(f"wrote {len(rows)} postings -> {args.out}", file=sys.stderr)
    print("family", families, file=sys.stderr)


if __name__ == "__main__":
    main()
