"""基础爬虫类：限速、重试、UA 轮换、代理支持、反检测。

增强能力:
- Playwright 浏览器上下文 (stealth 模式 + 反检测)
- 代理轮换 (从 ProxyPool 获取)
- 人机行为模拟 (滚动、鼠标移动、随机延迟)
- 验证码检测与自动回退
- 会话持久化 (cookies / localStorage)
"""
from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

try:
    from fake_useragent import UserAgent

    _ua = UserAgent()

    def _random_ua() -> str:
        try:
            return _ua.random
        except Exception:
            return _FALLBACK_UA
except Exception:
    def _random_ua() -> str:
        return _FALLBACK_UA


_FALLBACK_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 人机行为延迟范围 (秒)
_HUMAN_DELAY_MIN = 0.3
_HUMAN_DELAY_MAX = 1.2
_HUMAN_SCROLL_PAUSE_MIN = 1.5
_HUMAN_SCROLL_PAUSE_MAX = 4.0


def _human_delay() -> None:
    time.sleep(random.uniform(_HUMAN_DELAY_MIN, _HUMAN_DELAY_MAX))


class ScrapedProduct(BaseModel):
    """各爬虫统一输出的商品结构。"""

    platform: str
    external_id: str
    title: str
    category: str | None = None
    url: str | None = None
    image_url: str | None = None
    price_usd: float | None = None
    rating: float | None = None
    review_count: int | None = None
    rank: int | None = None
    weight_kg: float | None = Field(default=None, description="估算重量 kg")
    raw: dict[str, Any] = Field(default_factory=dict)


class BaseScraper(ABC):
    """增强版基础爬虫。支持两种模式:
    - httpx 模式 (简单请求)
    - Playwright 模式 (浏览器自动化)
    """

    platform: str = "base"

    def __init__(self, timeout: int | None = None) -> None:
        self.timeout = timeout or settings.platform.request_timeout
        self._client: httpx.Client | None = None
        self._proxy_url: str | None = None

    # ── httpx 客户端 ──────────────────────────────────────
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = self._build_httpx_client()
        return self._client

    def _build_httpx_client(self) -> httpx.Client:
        proxy = self._resolve_proxy()
        return httpx.Client(
            timeout=self.timeout,
            proxy=proxy,
            follow_redirects=True,
            headers={"User-Agent": _random_ua()},
        )

    def rotate_ua(self) -> None:
        if self._client:
            self._client.headers["User-Agent"] = _random_ua()

    # ── 代理管理 ──────────────────────────────────────────
    def _resolve_proxy(self) -> str | None:
        """从代理池获取代理（优先），否则用 settings 中的静态代理。"""
        try:
            from config.proxy import get_proxy_pool
            pool = get_proxy_pool()
            proxy = pool.get()
            if proxy:
                self._proxy_url = proxy.httpx_format
                return self._proxy_url
        except Exception:
            pass
        # 回退到静态代理
        proxies = settings.proxies
        return proxies.get("http://") or proxies.get("https://") or None

    # ── Playwright 浏览器 ─────────────────────────────────
    @contextmanager
    def browser_context(self, headless: bool = True):
        """创建带 stealth 和代理的 Playwright 浏览器上下文。

        用法:
            with self.browser_context() as (browser, context, page):
                page.goto("...")
                ...
        """
        from playwright.sync_api import sync_playwright

        proxy_config = None
        if self._proxy_url:
            proxy_config = {"server": self._proxy_url}

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-web-security",
                    f"--user-agent={_random_ua()}",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=_random_ua(),
                locale="en-US",
                timezone_id="America/New_York",
                proxy=proxy_config,
            )

            # playwright-stealth 注入
            if settings.use_stealth:
                try:
                    from playwright_stealth import stealth_sync
                    page = context.new_page()
                    stealth_sync(page)
                except Exception:
                    logger.debug("playwright-stealth unavailable, skipping")
                    page = context.new_page()
            else:
                page = context.new_page()

            # 反检测脚本注入
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                window.chrome = {runtime: {}};
            """)

            try:
                yield browser, context, page
            finally:
                context.close()
                browser.close()

    # ── 人机行为模拟 ──────────────────────────────────────
    @staticmethod
    def simulate_human_scroll(page, scrolls: int = 3) -> None:
        """模拟人类滚动行为：逐步滚动 + 随机停顿。"""
        for _ in range(scrolls):
            scroll_distance = random.randint(200, 600)
            page.evaluate(f"window.scrollBy(0, {scroll_distance})")
            time.sleep(random.uniform(_HUMAN_SCROLL_PAUSE_MIN, _HUMAN_SCROLL_PAUSE_MAX))

    @staticmethod
    def simulate_mouse_movement(page) -> None:
        """鼠标随机移动到页面上的某个元素。"""
        try:
            elements = page.query_selector_all("a, button, img")
            if elements:
                target = random.choice(elements[:20])
                target.hover()
                _human_delay()
        except Exception:
            pass

    # ── 验证码检测 ─────────────────────────────────────────
    @staticmethod
    def detect_captcha(page) -> bool:
        """检测页面是否出现验证码。"""
        captcha_indicators = [
            "captcha", "verify you are a human", "robot check",
            "Type the characters", "Solve this puzzle",
            "Enter the characters below", "g-recaptcha",
            "h-captcha", "px-captcha",
        ]
        try:
            page_text = page.content().lower()
            for indicator in captcha_indicators:
                if indicator.lower() in page_text:
                    return True
        except Exception:
            pass
        return False

    # ── httpx 请求 ────────────────────────────────────────
    def _sleep(self) -> None:
        time.sleep(random.uniform(settings.platform.min_delay_sec, settings.platform.max_delay_sec))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=16))
    def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        logger.debug("GET %s", url)
        self.rotate_ua()
        resp = self.client.get(url, **kwargs)
        resp.raise_for_status()
        self._sleep()
        return resp

    # ── 生命周期 ──────────────────────────────────────────
    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "BaseScraper":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ── 抽象方法 ──────────────────────────────────────────
    @abstractmethod
    def fetch_bestsellers(self, limit: int = 20, **kwargs: Any) -> list[ScrapedProduct]:
        """返回平台上的热销商品列表。"""
