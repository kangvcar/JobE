"""BOSS 直聘适配器。开发默认关闭，避免无登录态时空打。

优先连已登录 Chrome 的 CDP，在页面内 fetch 调 wapi（列表明文 salaryDesc，
详情带 securityId 拉 postDescription）。CDP 不通时再用 Playwright + storage_state。
验证码、风控码立即停止，不破解滑块。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from contextlib import suppress
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from app.collectors.hashing import content_hash
from app.collectors.pii import drop_pii
from app.collectors.rate_limit import RateLimiter
from app.domain.models import Snapshot

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:  # 可选依赖组 browser 未装
    PlaywrightError = Exception  # type: ignore[misc,assignment]
    sync_playwright = None

SOURCE_ID = "zhipin"
HOME_URL = "https://www.zhipin.com/web/geek/job"
LIST_PATH = "/wapi/zpgeek/search/joblist.json"
DETAIL_PATH = "/wapi/zpgeek/job/detail.json"
STORAGE_STATE = Path("data/auth/zhipin.json")
CDP_ENDPOINT = "http://127.0.0.1:9222"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
CAPTCHA_MARKERS = ("验证码", "geetest", "captcha", "滑动验证", "人机验证")
PAGE_SIZE = 30
DEFAULT_KEYWORDS = ("机器学习", "后端", "大数据", "物联网")
DEFAULT_CITIES: tuple[tuple[str, str], ...] = (
    ("北京", "101010100"),
    ("上海", "101020100"),
    ("深圳", "101280600"),
    ("杭州", "101210100"),
)
LIST_KEYS = (
    "encryptJobId",
    "encryptBrandId",
    "lid",
    "jobName",
    "salaryDesc",
    "jobExperience",
    "jobDegree",
    "cityName",
    "areaDistrict",
    "businessDistrict",
    "brandName",
    "brandScaleName",
    "brandStageName",
    "brandIndustry",
    "jobLabels",
    "skills",
    "welfareList",
    "lastModifyTime",
)
DETAIL_KEYS = (
    "postDescription",
    "showSkills",
    "address",
    "locationName",
    "experienceName",
    "degreeName",
)
_FETCH_JS = """
async (url) => {
    const resp = await fetch(url, { credentials: 'include' });
    return { status: resp.status, body: await resp.text() };
}
"""


class ZhipinHalted(RuntimeError):
    """验证码、风控或异常码——立即停止，不破解滑块。"""


class ZhipinUnavailable(RuntimeError):
    """Playwright 未安装、CDP 未就绪或登录态缺失。"""


def _looks_like_captcha(text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in CAPTCHA_MARKERS)


def _pick(src: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: src[k] for k in keys if k in src and src[k] not in (None, "")}


def build_list_url(keyword: str, city_code: str, page: int) -> str:
    params = {
        "scene": "1",
        "query": keyword,
        "city": city_code,
        "page": page,
        "pageSize": PAGE_SIZE,
    }
    return f"https://www.zhipin.com{LIST_PATH}?{urlencode(params)}"


def build_detail_url(job: dict[str, Any]) -> str:
    security_id = str(job.get("securityId") or "")
    params = {"securityId": security_id}
    lid = job.get("lid")
    if lid:
        params["lid"] = str(lid)
    encrypt_id = job.get("encryptJobId")
    if encrypt_id:
        params["encryptJobId"] = str(encrypt_id)
    return f"https://www.zhipin.com{DETAIL_PATH}?{urlencode(params)}"


def job_page_url(encrypt_job_id: str) -> str:
    return f"https://www.zhipin.com/job_detail/{encrypt_job_id}.html"


class ZhipinCollector:
    source_id = SOURCE_ID

    def __init__(
        self,
        *,
        enabled: bool = False,
        limiter: RateLimiter | None = None,
        delay_seconds: float = 3.0,
        storage_state: Path | None = None,
        max_items: int = 2000,
        max_pages: int = 3,
        keywords: tuple[str, ...] | None = None,
        cities: tuple[tuple[str, str], ...] | None = None,
        fetch_joblist: Callable[[str, str, int], tuple[int, dict | str]] | None = None,
        fetch_detail: Callable[[dict], tuple[int, dict | str]] | None = None,
        cdp_endpoint: str = CDP_ENDPOINT,
        want_detail: bool = True,
    ) -> None:
        self.enabled = enabled
        self._limiter = limiter or RateLimiter(delay_seconds, jitter=True, min_seconds=3.0)
        self._storage_state = storage_state or STORAGE_STATE
        self._max_items = max_items
        self._max_pages = max_pages
        self._keywords = keywords if keywords is not None else DEFAULT_KEYWORDS
        self._cities = cities if cities is not None else DEFAULT_CITIES
        self._fetch_joblist = fetch_joblist
        self._fetch_detail = fetch_detail
        self._cdp_endpoint = cdp_endpoint
        self._want_detail = want_detail
        self._page = None
        self._checked_salary = False

    def collect(self, since: date | None = None) -> Iterable[Snapshot]:
        del since
        if not self.enabled:
            return
        pw = None
        browser = None
        own_browser = False
        try:
            if self._fetch_joblist is None:
                pw, browser, self._page, own_browser = self._open_browser()
            yielded = 0
            fetched_at = datetime.now(UTC)
            for keyword in self._keywords:
                for city_name, city_code in self._cities:
                    if yielded >= self._max_items:
                        return
                    for page in range(1, self._max_pages + 1):
                        if yielded >= self._max_items:
                            return
                        data = self._load_joblist(keyword, city_code, page)
                        jobs = self._jobs_from(data)
                        if not jobs:
                            break
                        self._ensure_plaintext_salary(jobs)
                        for job in jobs:
                            if not isinstance(job, dict):
                                continue
                            detail = self._load_detail(job) if self._want_detail else None
                            payload = self._build_payload(
                                keyword, city_name, city_code, job, detail
                            )
                            digest = content_hash(payload)
                            encrypt_id = str(job.get("encryptJobId") or digest[:16])
                            yield Snapshot(
                                id=f"{self.source_id}:{digest}",
                                source_id=self.source_id,
                                fetched_at=fetched_at,
                                url=job_page_url(encrypt_id),
                                content_hash=digest,
                                payload=payload,
                            )
                            yielded += 1
                            if yielded >= self._max_items:
                                break
                        zp = data.get("zpData") if isinstance(data.get("zpData"), dict) else {}
                        if not zp.get("hasMore", len(jobs) >= PAGE_SIZE):
                            break
        finally:
            self._close_browser(pw, browser, own_browser)
            self._page = None

    def _load_joblist(self, keyword: str, city_code: str, page: int) -> dict:
        self._limiter.wait()
        if self._fetch_joblist is not None:
            status, body = self._fetch_joblist(keyword, city_code, page)
            return self._parse_api(status, body)
        return self._parse_api(*self._browser_fetch(build_list_url(keyword, city_code, page)))

    def _load_detail(self, job: dict[str, Any]) -> dict:
        if not job.get("securityId"):
            raise ZhipinHalted("列表缺少 securityId，无法拉详情，立即停止")
        self._limiter.wait()
        if self._fetch_detail is not None:
            status, body = self._fetch_detail(job)
            return self._parse_api(status, body)
        if self._fetch_joblist is not None:
            return {}
        return self._parse_api(*self._browser_fetch(build_detail_url(job)))

    def _jobs_from(self, data: dict) -> list[dict[str, Any]]:
        zp = data.get("zpData")
        if not isinstance(zp, dict):
            return []
        jobs = zp.get("jobList")
        if not isinstance(jobs, list):
            return []
        return [j for j in jobs if isinstance(j, dict)]

    def _ensure_plaintext_salary(self, jobs: list[dict[str, Any]]) -> None:
        if self._checked_salary:
            return
        self._checked_salary = True
        if not any(str(j.get("salaryDesc") or "").strip() for j in jobs):
            raise ZhipinUnavailable(
                "列表无明文 salaryDesc，视为未登录。请在专用 Chrome 登录后"
                "将 Playwright storage_state 保存到 data/auth/zhipin.json，"
                "或启动带 --remote-debugging-port=9222 的已登录 Chrome"
            )

    def _build_payload(
        self,
        keyword: str,
        city_name: str,
        city_code: str,
        job: dict[str, Any],
        detail: dict | None,
    ) -> dict[str, Any]:
        merged = _pick(job, LIST_KEYS)
        info = {}
        if isinstance(detail, dict):
            zp = detail.get("zpData") if isinstance(detail.get("zpData"), dict) else {}
            raw_info = zp.get("jobInfo") if isinstance(zp, dict) else None
            if isinstance(raw_info, dict):
                info = raw_info
        extra = _pick(info, DETAIL_KEYS)
        if extra.get("postDescription"):
            merged["postDescription"] = extra["postDescription"]
            merged["description"] = extra["postDescription"]
        for key in DETAIL_KEYS:
            if key in extra and key not in merged:
                merged[key] = extra[key]
        payload = {
            "keyword": keyword,
            "city": city_name,
            "city_code": city_code,
            "job": merged,
        }
        return drop_pii(payload)

    def _parse_api(self, status: int, body: dict | str) -> dict:
        if status in {403, 429, 503} or status >= 500:
            raise ZhipinHalted(f"异常状态码 {status}，立即停止，不重试")
        if status and status >= 400:
            raise ZhipinHalted(f"异常状态码 {status}，立即停止，不重试")
        if isinstance(body, str) and (body.lstrip().startswith("<") or _looks_like_captcha(body)):
            raise ZhipinHalted("检测到验证码，立即停止，不重试")
        if isinstance(body, dict):
            data = body
        else:
            try:
                data = json.loads(body)
            except json.JSONDecodeError as exc:
                raise ZhipinHalted("响应不是 JSON，立即停止") from exc
        if not isinstance(data, dict):
            raise ZhipinHalted("响应结构异常，立即停止")
        code = data.get("code")
        if code == 37:
            raise ZhipinHalted("风控：环境存在异常，立即停止，不破解滑块")
        blob = json.dumps(data, ensure_ascii=False)
        if _looks_like_captcha(blob):
            raise ZhipinHalted("检测到验证码，立即停止，不重试")
        msg = str(data.get("message") or data.get("msg") or "")
        if code not in (0, None):
            raise ZhipinHalted(f"接口错误 code={code} {msg}，立即停止，不重试")
        return data

    def _browser_fetch(self, url: str) -> tuple[int, str]:
        if self._page is None:
            raise ZhipinUnavailable("浏览器会话未打开")
        try:
            result = self._page.evaluate(_FETCH_JS, url)
        except PlaywrightError as exc:
            raise ZhipinHalted(f"页面异常，立即停止：{exc}") from exc
        if not isinstance(result, dict):
            raise ZhipinHalted("CDP 注入 fetch 未返回对象，立即停止")
        status = int(result.get("status") or 0)
        body = result.get("body") or ""
        return status, body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)

    def _open_browser(self):
        if sync_playwright is None:
            raise ZhipinUnavailable(
                "BOSS 适配器需要 Playwright。"
                "安装可选依赖：uv sync --extra browser && playwright install chromium"
            )
        pw = sync_playwright().start()
        browser = None
        own_browser = False
        try:
            browser = pw.chromium.connect_over_cdp(self._cdp_endpoint)
        except (PlaywrightError, OSError):
            browser = None
        if browser is None:
            if not self._storage_state.exists():
                pw.stop()
                raise ZhipinUnavailable(
                    f"CDP 未就绪且缺少登录态 {self._storage_state}。"
                    "请用专用 Chrome（--remote-debugging-port=9222）登录 zhipin.com，"
                    "或将 Playwright storage_state 保存到 data/auth/zhipin.json"
                    "（该目录已 gitignore）"
                )
            browser = pw.chromium.launch(headless=True)
            own_browser = True
            context = browser.new_context(
                storage_state=str(self._storage_state),
                user_agent=USER_AGENT,
            )
            page = context.new_page()
        else:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
        try:
            self._limiter.wait()
            response = page.goto(HOME_URL, wait_until="domcontentloaded")
            status = response.status if response is not None else 0
            html = page.content()
            if status in {403, 429, 503} or (status and status >= 400):
                raise ZhipinHalted(f"异常状态码 {status}，立即停止，不重试")
            if _looks_like_captcha(html):
                raise ZhipinHalted("检测到验证码，立即停止，不重试")
        except ZhipinHalted:
            page.close()
            if own_browser:
                browser.close()
            pw.stop()
            raise
        except PlaywrightError as exc:
            page.close()
            if own_browser:
                browser.close()
            pw.stop()
            raise ZhipinHalted(f"页面异常，立即停止：{exc}") from exc
        return pw, browser, page, own_browser

    def _close_browser(self, pw, browser, own_browser: bool) -> None:
        if self._page is not None:
            with suppress(Exception):
                self._page.close()
        if own_browser and browser is not None:
            with suppress(Exception):
                browser.close()
        if pw is not None:
            with suppress(Exception):
                pw.stop()
