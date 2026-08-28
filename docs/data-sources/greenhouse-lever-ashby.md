# Greenhouse / Lever / Ashby 公开职位 API 探测与接线补丁

探测日期 2026-08-28。User-Agent：`JobE/0.1 (research; job-evolution study)`。采集器已落地，`sources.py` / `postings.py` / `collect.py` 未改，由父代理按本文粘贴。

采集器 `source_id` 已硬编码为 `greenhouse` / `lever` / `ashby`，与下面建议的 `Source.id` 一致。未接线前 collector 测试可独立跑。

## 1. 真实探测结果

三个接口都免鉴权。未知 token 一律 HTTP 404（空 JSON 或 HTML 错误页）。Lever 偶发 200 + 空数组 `[]`，当作无职位，不是活 board。

### Greenhouse

`GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`

响应包一层 `{ "jobs": [...], "meta": { "total": N } }`。列表一次返回全部在招职位，未见分页。`content=true` 时每条带正文。

| 字段 | 实际情况 |
| --- | --- |
| 正文 | `jobs[].content`，HTML，但 JSON 字符串里是实体转义（`&lt;h2&gt;`）。`html.unescape` 之后才是真标签。无 `content=true` 则没有该字段。 |
| salary | 列表接口**没有**结构化薪资。`metadata` 是自定义字段数组，探到的公司里没有 salary/pay range 项。薪资偶尔写在 content 正文里。 |
| location | `jobs[].location.name`（如 `San Francisco, CA`）。`offices[]` 是办公室树，城市不准，mapper 不要用它当 city。 |
| posted_at | `first_published`（ISO 带时区）。`updated_at` 是最后更新。 |

顶层职位字段（Stripe 实测）：`id`, `title`, `company_name`, `location`, `content`, `updated_at`, `first_published`, `absolute_url`, `departments`, `offices`, `metadata`, `internal_job_id`, `requisition_id`, `language`, `data_compliance`。

探活（200 且 `n>0`），优先写入 boards 的加粗：

| token | n | 备注 |
| --- | --- | --- |
| **stripe** | 579 | 起点 token，有 content |
| airbnb | 180 | |
| **databricks** | 846 | |
| **discord** | 51 | |
| **figma** | 160 | |
| **shein** | 18 | 确认是 SHEIN（洛杉矶岗位），中国出海里唯一探活的 |
| **mongodb** | 407 | |
| **cloudflare** | 310 | |
| **datadog** | 452 | |
| **anthropic** | 561 | Ashby 上 404，职位在 Greenhouse |
| **scaleai** | 219 | token 是 `scaleai` 不是 `scale` |
| **deepmind** | 9 | |
| **xai** | 249 | |
| **elastic** | 335 | |
| **vercel** | 89 | |
| **gitlab** | 217 | |
| robinhood / coinbase / brex / dropbox / lyft / instacart / pinterest / reddit / twitch | 40–298 | 活着，但方向偏业务，未进 boards |
| moonshot | 18 | **不是**月之暗面。公司在 Denton, Texas，做电力基建 |
| honor | 12 | **不是**荣耀。Honor Technology，美国养老科技 |

404（节选）：`openai`（已换 Ashby）、`notion`（Ashby）、`tiktok`、`bytedance`、`dji`、`xiaomi`、`nvidia`、`snowflake`、`cursor`。

### Lever

`GET https://api.lever.co/v0/postings/{company}?mode=json`

响应是**数组**，不是对象。`limit`/`skip` 分页可用（zoox：`limit=2&skip=0` 与 `skip=2` 返回不同 id）。

| 字段 | 实际情况 |
| --- | --- |
| 标题 | `text`，没有 `title` |
| 正文 | `description`（HTML）+ `descriptionPlain`。另有 `lists[]`（职责/要求片段）、`opening`、`additional`（福利，有时含薪资叙述） |
| salary | 部分公司有结构化 `salaryRange: {currency, interval, min, max}`（Zoox、Shield AI）。Palantir / Spotify 没有该字段，薪资写在 `additionalPlain` 里 |
| location | `categories.location`，以及 `categories.allLocations[]`、`country`、`workplaceType` |
| posted_at | `createdAt`，**毫秒 Unix 时间戳**（如 `1777936261125` → 2026-05-04）。现有 `_parse_date` 吃不下，mapper 必须自己转 |

起点 token 大半已迁走：`netflix` / `twilio` / `shopify` / `postman` 全 404。

探活：

| token | n | salaryRange | 备注 |
| --- | --- | --- | --- |
| palantir | 307 | 无（薪资在 additional 文本） | 起点里唯一仍在的大厂 |
| spotify | 89 | 无 | |
| zoox | 243 | 有，年薪 USD | fixture 取自这家 |
| waabi | 83 | 无 | 自动驾驶 / ML |
| shieldai | 439 | 有 | |
| outreach | 35 | 有 | |
| brilliant | 4 | 有 | |
| osaro | 11 | 有 | 机器人 |
| benchsci | 1 | 无 | 生命科学 |
| 15five | 1 | 无 | |

`anyscale` 返回 1 条「已搬迁」占位，不要收录。`neon` 是巴西银行，不是 Neon DB。

### Ashby

`GET https://api.ashbyhq.com/posting-api/job-board/{boardName}?includeCompensation=true`

响应 `{ "jobs": [...] }`（有的 board 还有其它顶层键，collector 只读 `jobs`）。`includeCompensation=true` 才会带 `compensation`。一次返回全部职位。

| 字段 | 实际情况 |
| --- | --- |
| 正文 | `descriptionHtml`（真 HTML）+ `descriptionPlain` |
| salary | `compensation.summaryComponents[]` 里 `compensationType == "Salary"` 的 `minValue`/`maxValue`（年薪美元整数）。同结构也在 `compensationTiers[].components[]`。不是每家都填：Linear / Cursor / Notion 的 compensation 对象在，但 Salary 分量为空 |
| location | 顶层 `location` 字符串（`San Francisco`）。更稳的城市在 `address.postalAddress.addressLocality` |
| posted_at | `publishedAt`，ISO（`2026-03-12T16:38:15.322+00:00`）。没有 updated_at |

OpenAI 样例薪资：`$257K – $335K`，`minValue=257000`，`maxValue=335000`，`interval=1 YEAR`。

探活（节选，boards 已收录加粗）：

| token | n |
| --- | --- |
| **openai** | 749 |
| **perplexity** | 99 |
| **ramp** | 137 |
| **linear** | 29 |
| **cursor** | 121 |
| **notion** | 135 |
| **replit** | 71 |
| **cohere** | 146 |
| **sentry** | 41 |
| **supabase** | 58 |
| **langchain** | 108 |
| **modal** | 31 |
| **fireworks** | 65 |
| **cognition** | 89 |
| **elevenlabs** | 249 |
| railway / midjourney / character / plaid / posthog / neon / pinecone / weaviate / anyscale / runway / pika / hex / airbyte | 1–100 | 活着，未全部进 boards |

`anthropic` 在 Ashby 404（见 Greenhouse）。`vercel` 200 但 `jobs` 为空。`lark` 是 Lark Health（美国医疗），不是飞书。Ashby `moonshot` 3 条纽约岗位，对不上月之暗面，未收录。

ByteDance / TikTok / DJI / Xiaomi 三个 ATS 全 404。

## 2. Snapshot 载荷与 Posting 映射

三个 collector 对齐 Moka：只 yield `Snapshot`，payload 形状统一。

```python
payload = {
    "board_token": token,   # URL 里的 slug
    "board_name": board_name,  # txt 第二列显示名
    "job": drop_pii(job),   # 原始职位对象
}
```

`drop_pii` 仍只删现有键名（`jobManager` 等）。这三个 ATS 的邮箱写在 HTML 正文里，键过滤去不掉，靠 mapper 里的 `redact_pii(html_to_text(...))`。

| Posting | Greenhouse | Lever | Ashby |
| --- | --- | --- | --- |
| id | `greenhouse:{job.id}` | `lever:{job.id}` | `ashby:{job.id}` |
| title | `job.title` | `job.text` | `job.title` |
| company | `job.company_name` 或 `board_name` | `board_name`（接口无公司名） | `board_name` |
| city | `job.location.name` | `job.categories.location` | `address.postalAddress.addressLocality`，否则 `job.location` |
| published_at | `first_published` | `createdAt` / 1000 → date | `publishedAt` |
| updated_at | `updated_at` | 无，填 None | 无，填 None |
| description | `unescape(content)` → `html_to_text` → `redact_pii` | `description` HTML，否则 `descriptionPlain` | `descriptionHtml`，否则 `descriptionPlain` |
| salary_min/max | None（接口无结构字段） | `salaryRange.min/max` | Salary 分量的 `minValue`/`maxValue` |

fixture（已删邮箱电话）：

- `backend/tests/collectors/fixtures/greenhouse_jobs.json`：Stripe 2 条
- `backend/tests/collectors/fixtures/lever_jobs.json`：Zoox 2 条（带 `salaryRange`）
- `backend/tests/collectors/fixtures/ashby_jobs.json`：OpenAI 2 条（带 compensation）

boards 文件：`greenhouse_boards.txt`（15 家）、`lever_boards.txt`（10 家）、`ashby_boards.txt`（15 家）。

单元测试（respx，不打网）：

```
cd backend && PYTHONPATH=. uv run pytest tests/collectors/test_greenhouse.py tests/collectors/test_lever.py tests/collectors/test_ashby.py -q
```

15 passed。

## 3. 父代理补丁（可直接粘贴）

### 3.1 `backend/app/collectors/sources.py`

在 `LIEPIN` 之后插入，并改 `ALL_SOURCES`：

```python
GREENHOUSE = Source(
    id="greenhouse",
    name="Greenhouse Job Board API",
    license="招聘官网公开接口（免鉴权职位列表）",
    requires_login=False,
    is_leading_indicator=False,
)

LEVER = Source(
    id="lever",
    name="Lever 公开职位接口",
    license="招聘官网公开接口（免鉴权职位列表）",
    requires_login=False,
    is_leading_indicator=False,
)

ASHBY = Source(
    id="ashby",
    name="Ashby Job Board API",
    license="招聘官网公开接口（免鉴权职位列表）",
    requires_login=False,
    is_leading_indicator=False,
)

ALL_SOURCES: tuple[Source, ...] = (MOHRSS, MOKA, LIEPIN, GREENHOUSE, LEVER, ASHBY)
```

### 3.2 `backend/app/collectors/postings.py`

文件头增加：

```python
from datetime import UTC, date, datetime
from html import unescape
```

（若已有 `from datetime import date, datetime`，改成带 `UTC` 的那一行。）

在 `_map_liepin` 之前插入三个函数，并改 `posting_from_snapshot`。**不要**把新来源掉进 `else: _map_liepin`。

```python
def _map_greenhouse(snapshot: Snapshot) -> Posting:
    payload = snapshot.payload
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    raw = job.get("content") or ""
    description = redact_pii(html_to_text(unescape(raw))) if raw else None
    loc = job.get("location") if isinstance(job.get("location"), dict) else {}
    city = loc.get("name") if isinstance(loc, dict) else None
    native = str(job.get("id") or snapshot.content_hash[:32])
    return Posting(
        id=f"{snapshot.source_id}:{native}",
        source_id=snapshot.source_id,
        snapshot_id=snapshot.id,
        title=str(job.get("title") or ""),
        company=job.get("company_name") or payload.get("board_name"),
        city=str(city).strip() if city else None,
        published_at=_parse_date(job.get("first_published")),
        updated_at=_parse_date(job.get("updated_at")),
        description=description,
        occupation_code=None,
        salary_min=None,
        salary_max=None,
    )


def _lever_date(value: Any) -> date | None:
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 10_000_000_000 else float(value)
        try:
            return datetime.fromtimestamp(ts, tz=UTC).date()
        except (OSError, OverflowError, ValueError):
            return None
    return _parse_date(value)


def _map_lever(snapshot: Snapshot) -> Posting:
    payload = snapshot.payload
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    raw_html = job.get("description") or ""
    raw_plain = job.get("descriptionPlain") or ""
    if raw_html:
        description = redact_pii(html_to_text(raw_html))
    elif raw_plain:
        description = redact_pii(str(raw_plain))
    else:
        description = None
    cats = job.get("categories") if isinstance(job.get("categories"), dict) else {}
    city = cats.get("location") if isinstance(cats, dict) else None
    pay = job.get("salaryRange") if isinstance(job.get("salaryRange"), dict) else {}
    native = str(job.get("id") or snapshot.content_hash[:32])
    return Posting(
        id=f"{snapshot.source_id}:{native}",
        source_id=snapshot.source_id,
        snapshot_id=snapshot.id,
        title=str(job.get("text") or job.get("title") or ""),
        company=payload.get("board_name") or payload.get("board_token"),
        city=str(city).strip() if city else None,
        published_at=_lever_date(job.get("createdAt")),
        updated_at=None,
        description=description,
        occupation_code=None,
        salary_min=_as_int(pay.get("min")) if pay else None,
        salary_max=_as_int(pay.get("max")) if pay else None,
    )


def _ashby_city(job: dict) -> str | None:
    addr = job.get("address") if isinstance(job.get("address"), dict) else {}
    postal = addr.get("postalAddress") if isinstance(addr, dict) else None
    if isinstance(postal, dict):
        city = postal.get("addressLocality") or postal.get("addressRegion")
        if city and str(city).strip():
            return str(city).strip()
    loc = job.get("location")
    if loc and str(loc).strip():
        return str(loc).strip()
    return None


def _ashby_salary(job: dict) -> tuple[int | None, int | None]:
    comp = job.get("compensation") if isinstance(job.get("compensation"), dict) else {}
    buckets = list(comp.get("summaryComponents") or [])
    for tier in comp.get("compensationTiers") or []:
        if isinstance(tier, dict):
            buckets.extend(tier.get("components") or [])
    for item in buckets:
        if isinstance(item, dict) and item.get("compensationType") == "Salary":
            return _as_int(item.get("minValue")), _as_int(item.get("maxValue"))
    return None, None


def _map_ashby(snapshot: Snapshot) -> Posting:
    payload = snapshot.payload
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    raw_html = job.get("descriptionHtml") or ""
    raw_plain = job.get("descriptionPlain") or ""
    if raw_html:
        description = redact_pii(html_to_text(raw_html))
    elif raw_plain:
        description = redact_pii(str(raw_plain))
    else:
        description = None
    salary_min, salary_max = _ashby_salary(job)
    native = str(job.get("id") or snapshot.content_hash[:32])
    return Posting(
        id=f"{snapshot.source_id}:{native}",
        source_id=snapshot.source_id,
        snapshot_id=snapshot.id,
        title=str(job.get("title") or ""),
        company=payload.get("board_name") or payload.get("board_token"),
        city=_ashby_city(job),
        published_at=_parse_date(job.get("publishedAt")),
        updated_at=None,
        description=description,
        occupation_code=None,
        salary_min=salary_min,
        salary_max=salary_max,
    )
```

`posting_from_snapshot` 改成：

```python
def posting_from_snapshot(snapshot: Snapshot) -> Posting:
    if snapshot.source_id == "mohrss":
        posting = _map_mohrss(snapshot)
    elif snapshot.source_id == "moka":
        posting = _map_moka(snapshot)
    elif snapshot.source_id == "greenhouse":
        posting = _map_greenhouse(snapshot)
    elif snapshot.source_id == "lever":
        posting = _map_lever(snapshot)
    elif snapshot.source_id == "ashby":
        posting = _map_ashby(snapshot)
    else:
        posting = _map_liepin(snapshot)
    if posting.description:
        posting = posting.model_copy(update={"description": redact_pii(posting.description)})
    if posting.title:
        posting = posting.model_copy(update={"title": redact_pii(posting.title)})
    return posting
```

### 3.3 `backend/app/api/routers/collect.py`

增加 import：

```python
from app.collectors.ashby import AshbyCollector
from app.collectors.greenhouse import GreenhouseCollector
from app.collectors.lever import LeverCollector
```

`_collectors` 的 `out` 字典在 `moka` 之后加上：

```python
        "greenhouse": GreenhouseCollector(
            limiter=limiter, max_items=max_items, delay_seconds=delay
        ),
        "lever": LeverCollector(
            limiter=limiter, max_items=max_items, delay_seconds=delay
        ),
        "ashby": AshbyCollector(
            limiter=limiter, max_items=max_items, delay_seconds=delay
        ),
```

`collect_once.py` 走 `_collectors` 和 `ALL_SOURCES`，改完上面两处即可，脚本本身不用动。`config.py` 不用加开关，三个来源都免登录。

### 3.4 `backend/tests/collectors/test_router.py`

`test_list_sources_includes_license` 里把集合改成：

```python
    assert {"mohrss", "moka", "liepin", "greenhouse", "lever", "ashby"} <= ids
```

接线后建议再跑：

```
cd backend && PYTHONPATH=. uv run pytest tests/collectors/test_router.py tests/collectors/test_postings.py -q
```

可在 `test_postings.py` 用现成 fixture 加三条 mapper 断言：Greenhouse unescape 后正文不含 `&lt;h2&gt;`；Lever `title` 来自 `text` 且 Zoox 薪资 144000–193000；Ashby OpenAI 薪资 257000–335000、city=`San Francisco`。
