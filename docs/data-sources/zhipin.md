# BOSS 直聘采集

验证对象：[qsllv/boss-zhipin-scraper](https://github.com/qsllv/boss-zhipin-scraper)（2026-08-28 浅克隆到 `/tmp/boss-zhipin-scraper`，README 仍署 eatmoreduck）。JobE 没有 vendoring 该仓，只复用其「已登录 Chrome + CDP 注入 XHR 调 wapi」这条路径。

## 结论

列表接口能返回技能标签和明文字符串薪资，但不够做技能抽取。完整 JD 在详情接口的 `jobInfo.postDescription`。qsllv 用详情页 HTML；JobE 改为同一套 CDP 会话里带 `securityId` 调 `/wapi/zpgeek/job/detail.json`。

本机没有打通真实详情。未登录直接 GET wapi 返回 `code=37`（环境存在异常 + seed），没有 `jobList`。仓库里没有 `data/auth/zhipin.json`，本机 9222 上也没有已登录 Chrome。没有假装成功。

## qsllv 在做什么

1. 启动隔离 Chrome profile（`~/.boss-zhipin-scraper/chrome-profile`），用户在里面登录 zhipin.com。
2. 连 `127.0.0.1:9222` 的 CDP WebSocket。
3. 打开搜索页，用同步 XHR 调 `/wapi/zpgeek/search/joblist.json`，拿明文 `salaryDesc`（避开 DOM 字体反爬）。
4. 详情：打开 `https://www.zhipin.com/job_detail/{encryptJobId}.html?lid=...&securityId=...`，从 `.job-sec` / `.job-detail-section` 抽正文。没有调详情 wapi。
5. 必须已登录 Chrome。未登录时列表里 `salaryDesc` 为空，脚本视为失败。

## 接口

### 列表 `GET /wapi/zpgeek/search/joblist.json`

| 参数 | 值 |
|---|---|
| scene | `1` |
| query | 关键词 |
| city | 城市代码，如北京 `101010100` |
| page | 从 1 |
| pageSize | qsllv 用 30；检索页常见 15 |

返回 `code == 0` 时 `zpData.jobList[]` 常见字段：`jobName`、`salaryDesc`、`jobExperience`、`jobDegree`、`cityName`、`areaDistrict`、`brandName`、`brandScaleName`、`brandStageName`、`brandIndustry`、`jobLabels`、`skills`、`welfareList`、`encryptJobId`、`encryptBrandId`、`securityId`、`lid`、`bossName`。`hasMore` 控制翻页。

`skills` / `jobLabels` 是短标签（三到八个词），不是任职要求正文。

### 详情：另一个 wapi，不是只能爬 HTML

`GET /wapi/zpgeek/job/detail.json?securityId={securityId}`

可选再带 `lid`、`encryptJobId`。`securityId` 来自列表，过期快，不要写进快照。

`zpData.jobInfo.postDescription` 才是 JD 正文。同级还有 `brandComInfo`、`bossInfo`（HR 姓名，写入前丢掉）。

qsllv 走 HTML 是因为它要在页面上滚一滚再抽 DOM。JobE 要的是正文，wapi 更稳，也少一次渲染。

### 登录与 Cookie

必须。未登录或环境被判定异常时：

- HTTP 仍可能是 200
- `code=37`，`message=您的环境存在异常.`，`zpData` 只有 `seed` / `ts` / `name`
- 没有 `jobList`，更没有 `postDescription`

本机探测（2026-08-28，无 Cookie、无 CDP，各打一次列表和详情）：两次都是 `code=37`。裸 `httpx`/`curl` 过不了这层。不要在采集器里解 seed、不要过滑块。

## 列表字段够不够抽技能

不够。列表 `skills` 只能当弱信号。生产路径必须拉详情 `postDescription`。采集器把两者都放进 `payload.job`：标签保留，正文放 `postDescription`（并复制一份 `description` 方便映射）。

## JobE 采集器

`backend/app/collectors/zhipin.py`

- `enabled=False`（默认）时 `collect()` 直接返回，零网络。
- 优先 `playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")`，在已登录页里 `fetch` 调两个 wapi。
- CDP 不通时退回 Playwright + `data/auth/zhipin.json`。
- 验证码 HTML、`code=37`、403/429/5xx → `ZhipinHalted`，立刻停。
- 列表无明文 `salaryDesc` → `ZhipinUnavailable`（未登录）。
- 默认关键词：机器学习、后端、大数据、物联网。默认城市：北京 / 上海 / 深圳 / 杭州。
- `drop_pii` + `content_hash`。`bossName` / `bossInfo` 已加入 `pii.py` 的丢弃键；`securityId` 用完即丢，不进 payload。

单元测试全 mock，见 `backend/tests/collectors/test_zhipin.py` 与 `fixtures/zhipin_joblist.json`、`zhipin_details.json`。CI 不会访问 zhipin.com。

## 开关（不要改 config.py）

`Settings.zhipin_enabled` 已经是 `False`，环境变量 `ZHIPIN_ENABLED`。`.env.example` 里已有 `ZHIPIN_ENABLED=false`。

接线时按猎聘同样方式读取，不要在 `collect()` 里再写死 True：

```python
ZhipinCollector(
    enabled=settings.zhipin_enabled,
    limiter=limiter,
    max_items=max_items,
    delay_seconds=delay,
)
```

开发保持 `false`。要跑真实采集时：`ZHIPIN_ENABLED=true`，并先准备好 Cookie 或 CDP。

## 最小人工步骤（Cookie / Chrome）

路径 `data/auth/zhipin.json` 已在 `.gitignore`（`data/auth/`）。不要提交。

**做法 A：已登录 Chrome + CDP（优先）**

```bash
# 用隔离目录，不要拿日常 Chrome profile
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$PWD/data/auth/zhipin-chrome" \
  --no-first-run --no-default-browser-check
```

在弹出的窗口打开 zhipin.com 并登录。保持该 Chrome 开着，再把 `ZHIPIN_ENABLED=true` 后跑采集。登录态在 `data/auth/zhipin-chrome`，机器重启后还在。

**做法 B：Playwright storage_state（CDP 退路）**

```python
from pathlib import Path
from playwright.sync_api import sync_playwright

Path("data/auth").mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://www.zhipin.com/web/user/")
    input("登录完成后回车")
    context.storage_state(path="data/auth/zhipin.json")
    browser.close()
```

文件里应有 `.zhipin.com` 的 Cookie（常见名字含 `wt2`、`__zp_stoken__`）。没有这个文件且 9222 没人听，采集器抛 `ZhipinUnavailable`。

## 本机真实详情

没有打通。卡在：无 Cookie、无 CDP、未登录 GET 被 `code=37` 挡住。接口本身（路径、字段名）与 qsllv / 公开 wapi 文档一致，没有证据表明 list/detail 路径已经改名。要验证真详情，按上一节起 Chrome 后用 `max_items=1` 打一条即可。

## 父代理可粘贴

### `sources.py`

```python
ZHIPIN = Source(
    id="zhipin",
    name="BOSS直聘",
    license="登录态 CDP/Playwright 采集；开发默认关闭",
    requires_login=True,
    is_leading_indicator=False,
)

ALL_SOURCES: tuple[Source, ...] = (MOHRSS, MOKA, LIEPIN, ZHIPIN)
```

采集器里 `source_id` 目前写死 `"zhipin"`，避免在 `ZHIPIN` 登记前进 import。登记后可改成 `ZHIPIN.id`。

### `postings.py`：`_map_zhipin` + 分支

```python
import re

_SALARY_DESC_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[-–~]\s*(\d+(?:\.\d+)?)\s*([Kk千])?"
)


def _parse_salary_desc(text: str) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    match = _SALARY_DESC_RE.search(text.replace(" ", ""))
    if not match:
        return None, None
    low, high, unit = match.group(1), match.group(2), match.group(3)
    factor = 1000 if unit or float(low) < 1000 else 1
    return int(float(low) * factor), int(float(high) * factor)


def _map_zhipin(snapshot: Snapshot) -> Posting:
    payload = snapshot.payload
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    raw_desc = job.get("postDescription") or job.get("description") or ""
    description = redact_pii(html_to_text(raw_desc)) if raw_desc else None
    salary_min, salary_max = _parse_salary_desc(str(job.get("salaryDesc") or ""))
    native = str(job.get("encryptJobId") or snapshot.content_hash[:32])
    published = job.get("lastModifyTime")
    if isinstance(published, (int, float)) and published > 10_000_000_000:
        published = datetime.fromtimestamp(published / 1000, UTC).date()
    return Posting(
        id=f"{snapshot.source_id}:{native}",
        source_id=snapshot.source_id,
        snapshot_id=snapshot.id,
        title=str(job.get("jobName") or job.get("title") or ""),
        company=job.get("brandName") or payload.get("company"),
        city=job.get("cityName") or payload.get("city"),
        published_at=_parse_date(published),
        updated_at=None,
        description=description,
        occupation_code=None,
        salary_min=salary_min,
        salary_max=salary_max,
    )
```

`posting_from_snapshot` 里在 moka 分支后加上：

```python
    elif snapshot.source_id == "zhipin":
        posting = _map_zhipin(snapshot)
```

`datetime` / `UTC` 若该文件未导入，一并补上。

### 其它接线（本任务未改）

`collect.py` / `collect_once.py`：与猎聘一样，`settings.zhipin_enabled` 为真才放进 collectors 字典。

`run.py`：现在只捕获 `LiepinHalted`。BOSS 风控要停采集，加上：

```python
from app.collectors.zhipin import ZhipinHalted
# ...
except (LiepinHalted, ZhipinHalted) as exc:
```

`test_router.py`：来源列表断言补上 `"zhipin"`。
