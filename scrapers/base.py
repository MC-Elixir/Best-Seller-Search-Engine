"""基础爬虫类：限速、重试、UA 轮换。"""
from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
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
except Exception:  # fake_useragent 第一次用可能联网失败
    def _random_ua() -> str:
        return _FALLBACK_UA


_FALLBACK_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


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
    platform: str = "base"

    def __init__(self, timeout: int | None = None) -> None:
        self.timeout = timeout or settings.platform.request_timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                proxies=settings.proxies or None,
                follow_redirects=True,
                headers={"User-Agent": _random_ua()},
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "BaseScraper":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _sleep(self) -> None:
        time.sleep(random.uniform(settings.platform.min_delay_sec, settings.platform.max_delay_sec))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=16))
    def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        logger.debug("GET %s", url)
        resp = self.client.get(url, **kwargs)
        resp.raise_for_status()
        self._sleep()
        return resp

    @abstractmethod
    def fetch_bestsellers(self, limit: int = 20, **kwargs: Any) -> list[ScrapedProduct]:
        """返回平台上的热销商品列表。"""
