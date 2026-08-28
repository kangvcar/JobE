from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.collectors.hashing import content_hash
from app.collectors.mohrss import parse_findjoblist
from app.collectors.pii import drop_pii
from app.collectors.postings import (
    detect_boilerplate,
    find_duplicate,
    posting_from_snapshot,
    redact_pii,
    snapshots_to_postings,
)
from app.domain.models import Posting, Snapshot
from app.domain.normalization import normalize_title, period_from_date

FIXTURES = Path(__file__).parent / "fixtures"


def _snap(source_id: str, payload: dict, sid: str = "s1") -> Snapshot:
    return Snapshot(
        id=sid,
        source_id=source_id,
        fetched_at=datetime.now(UTC),
        url="http://example.test",
        content_hash=content_hash(payload),
        payload=payload,
    )


def test_normalize_title_unifies_java_variants():
    variants = [
        "Java开发工程师",
        "JAVA 开发",
        "java研发工程师",
        "ＪＡＶＡ　开发工程师",
        "Java 开发工程师",
        "java研发",
    ]
    norms = {normalize_title(v) for v in variants}
    assert len(norms) == 1
    assert norms.pop() == "java开发"


def test_normalize_title_strips_fullwidth_and_punct():
    assert normalize_title("（高级）Python开发工程师") == "高级python开发"
    assert normalize_title("前端开发岗") == "前端开发"


def test_period_from_published_at():
    assert period_from_date(date(2026, 1, 1)) == "2026Q1"
    assert period_from_date(date(2026, 4, 15)) == "2026Q2"
    assert period_from_date(date(2026, 7, 1)) == "2026Q3"
    assert period_from_date(date(2026, 10, 31)) == "2026Q4"
    assert period_from_date(None) is None


def test_redact_phone_email_wechat_idcard():
    text = "联系人 13600136000 邮箱 hr@example.com 微信：mywxid_abc 身份证 110101199001011234"
    redacted = redact_pii(text)
    assert "13600136000" not in redacted
    assert "hr@example.com" not in redacted
    assert "mywxid_abc" not in redacted
    assert "110101199001011234" not in redacted
    assert "[已脱敏]" in redacted


def test_mohrss_pii_never_in_posting_output():
    html = (FIXTURES / "mohrss_list.html").read_text(encoding="utf-8")
    items = [drop_pii(x) for x in parse_findjoblist(html)]
    snaps = [_snap("mohrss", item, sid=f"m{i}") for i, item in enumerate(items)]
    postings = snapshots_to_postings(snaps)
    blob = json.dumps([p.model_dump(mode="json") for p in postings], ensure_ascii=False)
    assert "aae004" not in blob
    assert "aae005" not in blob
    assert "13800138001" not in blob
    assert "13800138002" not in blob


def test_dedup_within_60_day_window():
    first = Posting(
        id="a",
        source_id="mohrss",
        snapshot_id="s-a",
        title="Java开发工程师",
        company="示例科技",
        city="北京市",
        published_at=date(2026, 6, 1),
    )
    twin = Posting(
        id="b",
        source_id="moka",
        snapshot_id="s-b",
        title="JAVA 开发",
        company="示例科技",
        city="北京市",
        published_at=date(2026, 7, 15),
    )
    assert find_duplicate(twin, [first]) == "a"


def test_dedup_outside_60_day_window():
    first = Posting(
        id="a",
        source_id="mohrss",
        snapshot_id="s-a",
        title="Java开发工程师",
        company="示例科技",
        city="北京市",
        published_at=date(2026, 1, 1),
    )
    later = Posting(
        id="b",
        source_id="moka",
        snapshot_id="s-b",
        title="Java开发工程师",
        company="示例科技",
        city="北京市",
        published_at=date(2026, 1, 1) + timedelta(days=61),
    )
    assert find_duplicate(later, [first]) is None


def test_cross_posting_dedup_rate_is_80_percent():
    """20 个职位各被 5 个来源投放 → 80 条近重复 / 100 = 80%。"""
    base = date(2026, 6, 1)
    titles = ["Java开发工程师", "JAVA 开发", "java研发工程师", "Java 开发工程师", "ＪＡＶＡ开发"]
    batch: list[Posting] = []
    n = 0
    for company_i in range(20):
        for title in titles:
            n += 1
            batch.append(
                Posting(
                    id=f"p-{n}",
                    source_id="moka" if n % 2 == 0 else "mohrss",
                    snapshot_id=f"s-{n}",
                    title=title,
                    company=f"公司{company_i}",
                    city="北京市",
                    published_at=base + timedelta(days=n % 20),
                )
            )
    seen: list[Posting] = []
    marked = 0
    for posting in batch:
        dup = find_duplicate(posting, seen)
        if dup:
            marked += 1
        else:
            seen.append(posting)
    rate = marked / len(batch)
    assert rate == 0.8


def test_boilerplate_marks_without_deleting():
    repeated = "五险一金，周末双休，团队氛围好。"
    skill = "负责 JVM 调优与 Spring 服务开发。"
    text = f"{skill}\n{repeated}"
    peer = f"负责前端页面。\n{repeated}"
    spans = detect_boilerplate(text, [peer])
    assert spans
    for start, end in spans:
        assert 0 <= start < end <= len(text)
    assert "JVM" in text
    covered = "".join(text[s:e] for s, e in spans)
    assert "五险一金" in covered
    assert "团队氛围好" in covered
    assert "JVM" not in covered


def test_snapshots_to_postings_wires_duplicate_and_redaction():
    job = {
        "org_id": "geely",
        "org_name": "吉利",
        "mode": "social",
        "job": {
            "id": "j1",
            "title": "Java开发工程师",
            "description": "<p>写 Java。五险一金。联系 13600136000</p>",
            "minSalary": 20,
            "maxSalary": 35,
            "openedAt": "2026-07-01T00:00:00.000Z",
            "locations": [{"city": "杭州市"}],
        },
    }
    job2 = {
        "org_id": "geely",
        "org_name": "吉利",
        "mode": "social",
        "job": {
            "id": "j2",
            "title": "java研发工程师",
            "description": "<p>写支付。五险一金。邮箱 hr@example.com</p>",
            "minSalary": 18,
            "maxSalary": 30,
            "openedAt": "2026-07-10T00:00:00.000Z",
            "locations": [{"city": "杭州市"}],
        },
    }
    postings = snapshots_to_postings([_snap("moka", job, "s1"), _snap("moka", job2, "s2")])
    assert postings[0].salary_min == 20000
    assert postings[1].duplicate_of == postings[0].id
    assert "13600136000" not in (postings[0].description or "")
    assert "hr@example.com" not in (postings[1].description or "")
    assert postings[0].boilerplate_spans
    assert posting_from_snapshot(_snap("moka", job, "s1")).city == "杭州市"


def test_greenhouse_unescapes_content_and_drops_entities():
    body = json.loads((FIXTURES / "greenhouse_jobs.json").read_text(encoding="utf-8"))
    posting = posting_from_snapshot(
        _snap(
            "greenhouse",
            {"board_token": "stripe", "board_name": "Stripe", "job": body["jobs"][0]},
        )
    )
    assert posting.title == "Account Executive, AI Sales"
    assert posting.company == "Stripe"
    assert posting.city == "San Francisco, CA"
    assert posting.description
    assert "&lt;h2&gt;" not in posting.description
    assert "Who we are" in posting.description


def test_lever_maps_text_title_and_salary_range():
    jobs = json.loads((FIXTURES / "lever_jobs.json").read_text(encoding="utf-8"))
    posting = posting_from_snapshot(
        _snap("lever", {"board_token": "zoox", "board_name": "Zoox", "job": jobs[0]})
    )
    assert posting.title == "Autonomy System Test Engineer"
    assert posting.company == "Zoox"
    assert posting.city == "Foster City, CA"
    assert posting.salary_min == 144000
    assert posting.salary_max == 193000
    assert posting.description
    assert "autonomous" in posting.description.lower()


def test_ashby_maps_compensation_and_locality():
    body = json.loads((FIXTURES / "ashby_jobs.json").read_text(encoding="utf-8"))
    posting = posting_from_snapshot(
        _snap("ashby", {"board_token": "openai", "board_name": "OpenAI", "job": body["jobs"][0]})
    )
    assert posting.company == "OpenAI"
    assert posting.city == "San Francisco"
    assert posting.salary_min == 257000
    assert posting.salary_max == 335000
    assert posting.description
    assert "GPU" in posting.description


def test_zhipin_maps_salary_desc_and_post_description():
    posting = posting_from_snapshot(
        _snap(
            "zhipin",
            {
                "job": {
                    "encryptJobId": "aabbccddee0011223344556677889900",
                    "jobName": "后端开发工程师",
                    "brandName": "示例科技",
                    "cityName": "北京",
                    "salaryDesc": "20-35K",
                    "lastModifyTime": 1722470400000,
                    "postDescription": "岗位职责：负责 Spring 服务开发。",
                }
            },
        )
    )
    assert posting.title == "后端开发工程师"
    assert posting.company == "示例科技"
    assert posting.city == "北京"
    assert posting.salary_min == 20000
    assert posting.salary_max == 35000
    assert posting.description
    assert "Spring" in posting.description
    assert posting.published_at == date(2024, 8, 1)
