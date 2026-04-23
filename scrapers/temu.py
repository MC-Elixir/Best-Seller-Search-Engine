"""Temu 热门商品抓取。

Temu 走的是 XHR 接口，正式方案需要抓包后重放。MVP 先用种子数据跑通，
后续接入真实接口只需替换 `_fetch_real`。
"""
from __future__ import annotations

import logging
from typing import Any

from config import settings

from .base import BaseScraper, ScrapedProduct

logger = logging.getLogger(__name__)


_MOCK_TRENDING: list[dict[str, Any]] = [
    {
        "external_id": "601099512345001",
        "title": "Reusable Silicone Food Lid Covers Set of 12",
        "category": "Kitchen",
        "url": "https://www.temu.com/--g-601099512345001.html",
        "image_url": "https://img.kwcdn.com/mock/silicone-lids.jpg",
        "price_usd": 5.49,
        "rating": 4.7,
        "review_count": 9820,
        "rank": 1,
        "weight_kg": 0.23,
    },
    {
        "external_id": "601099512345002",
        "title": "50ft RGB LED Light Strip App Control",
        "category": "Home Decor",
        "url": "https://www.temu.com/--g-601099512345002.html",
        "image_url": "https://img.kwcdn.com/mock/led-strip.jpg",
        "price_usd": 6.99,
        "rating": 4.6,
        "review_count": 15032,
        "rank": 2,
        "weight_kg": 0.45,
    },
    {
        "external_id": "601099512345003",
        "title": "Mini USB Rechargeable Handheld Fan",
        "category": "Appliances",
        "url": "https://www.temu.com/--g-601099512345003.html",
        "image_url": "https://img.kwcdn.com/mock/mini-fan.jpg",
        "price_usd": 4.29,
        "rating": 4.3,
        "review_count": 6721,
        "rank": 3,
        "weight_kg": 0.35,
    },
]


class TemuScraper(BaseScraper):
    platform = "temu"

    def fetch_bestsellers(self, limit: int = 20, **_: Any) -> list[ScrapedProduct]:
        if settings.use_mock_data:
            logger.info("[temu] USE_MOCK_DATA=true, returning seed trending list")
            return [ScrapedProduct(platform=self.platform, **item) for item in _MOCK_TRENDING[:limit]]

        try:
            return self._fetch_real(limit=limit)
        except Exception as e:  # pragma: no cover
            logger.warning("[temu] real scrape failed (%s), falling back to mock data", e)
            return [ScrapedProduct(platform=self.platform, **item) for item in _MOCK_TRENDING[:limit]]

    def _fetch_real(self, limit: int) -> list[ScrapedProduct]:  # pragma: no cover
        # 预留真实接口位置。目前返回空列表 -> 外部会回退到 mock。
        raise NotImplementedError("Temu 真实接口未接入，MVP 阶段请设置 USE_MOCK_DATA=true")
