"""猎聘适配器。开发默认关闭，避免无登录态时空打。

验证码、异常状态码或空结果集立即停止，由调用方决定是否换会话再跑。
Playwright 为可选依赖，未安装时给出明确错误。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from pathlib import Path

from bs4 import BeautifulSoup

from app.collectors.hashing import content_hash
from app.collectors.pii import drop_pii
from app.collectors.rate_limit import RateLimiter
from app.collectors.sources import LIEPIN
from app.domain.models import Snapshot

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:  # 可选依赖组 browser 未装
    PlaywrightError = Exception  # type: ignore[misc,assignment]
    sync_playwright = None

LIST_URL = "https://www.liepin.com/zhaopin/"
STORAGE_STATE = Path("data/auth/liepin.json")
USER_AGENT = "JobE/0.1 (research; job-evolution study)"
CAPTCHA_MARKERS = ("验证码", "geetest", "captcha", "滑动验证", "人机验证")


class LiepinHalted(RuntimeError):
    """验证码、异常码或空结果——立即停止并告警，不重试。"""


class LiepinUnavailable(RuntimeError):
    """Playwright 未安装或登录态缺失。"""


def _looks_like_captcha(html: str) -> bool:
    lowered = html.lower()
    return any(marker.lower() in lowered for marker in CAPTCHA_MARKERS)


class LiepinCollector:
    source_id = LIEPIN.id

    def __init__(
        self,
        *,
        enabled: bool = False,
        limiter: RateLimiter | None = None,
        delay_seconds: float = 3.0,
        storage_state: Path | None = None,
        max_items: int = 2000,
        fetch_listing: Callable[[], tuple[int, str]] | None = None,
    ) -> None:
        self.enabled = enabled
        self._limiter = limiter or RateLimiter(delay_seconds, jitter=True, min_seconds=3.0)
        self._storage_state = storage_state or STORAGE_STATE
        self._max_items = max_items
        self._fetch_listing = fetch_listing

    def collect(self, since: date | None = None) -> Iterable[Snapshot]:
        del since
        if not self.enabled:
            return
        html = self._load_listing()
        cards = self._extract_cards(html)
        fetched_at = datetime.now(UTC)
        for i, card in enumerate(cards[: self._max_items]):
            payload = drop_pii(card)
            digest = content_hash(payload)
            yield Snapshot(
                id=f"{self.source_id}:{digest}",
                source_id=self.source_id,
                fetched_at=fetched_at,
                url=str(payload.get("href") or LIST_URL),
                content_hash=digest,
                payload=payload,
            )
            if i + 1 >= self._max_items:
                break

    def _load_listing(self) -> str:
        if self._fetch_listing is not None:
            self._limiter.wait()
            status, html = self._fetch_listing()
            self._check_response(status, html)
            return html
        if sync_playwright is None:
            raise LiepinUnavailable(
                "猎聘适配器需要 Playwright。"
                "安装可选依赖：uv sync --extra browser && playwright install chromium"
            )
        if not self._storage_state.exists():
            raise LiepinUnavailable(
                f"缺少登录态 {self._storage_state}。请用专用测试账号扫码登录后"
                "将 Playwright storage_state 保存到 data/auth/（该目录已 gitignore）"
            )
        self._limiter.wait()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    storage_state=str(self._storage_state),
                    user_agent=USER_AGENT,
                )
                page = context.new_page()
                response = page.goto(LIST_URL, wait_until="domcontentloaded")
                status = response.status if response is not None else 0
                html = page.content()
                context.close()
            except PlaywrightError as exc:
                raise LiepinHalted(f"页面异常，立即停止：{exc}") from exc
            finally:
                browser.close()
        self._check_response(status, html)
        return html

    def _check_response(self, status: int, html: str) -> None:
        if status in {403, 429, 503} or status >= 500:
            raise LiepinHalted(f"异常状态码 {status}，立即停止，不重试")
        if status and status >= 400:
            raise LiepinHalted(f"异常状态码 {status}，立即停止，不重试")
        if _looks_like_captcha(html):
            raise LiepinHalted("检测到验证码，立即停止，不重试")

    def _extract_cards(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        cards: list[dict] = []
        for node in soup.select("a[href*='/zhaopin/'], .job-card, [data-job-id]"):
            href = node.get("href") or ""
            if "?" in href:
                continue
            if href and not href.startswith("/zhaopin/") and "/zhaopin/" not in href:
                if "data-job-id" not in node.attrs and "job-card" not in node.get("class", []):
                    continue
            text = " ".join(node.get_text(" ", strip=True).split())
            if not text:
                continue
            cards.append({"href": href or LIST_URL, "text": text})
        if not cards:
            raise LiepinHalted("空结果集，立即停止，不重试")
        return cards
