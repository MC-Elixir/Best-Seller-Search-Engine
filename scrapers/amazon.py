"""Amazon Best Sellers 抓取。

MVP 策略：
- 真实抓取使用 Playwright（动态页面）。
- 未安装 Playwright 或 settings.use_mock_data=True 时返回一批样例数据，
  便于没有外网/代理条件下走通整个流程。
"""
from __future__ import annotations

import logging
from typing import Any

from config import settings

from .base import BaseScraper, ScrapedProduct

logger = logging.getLogger(__name__)


_MOCK_BESTSELLERS: list[dict[str, Any]] = [
    {
        "external_id": "B0CHX3QBCH",
        "title": "Silicone Stretch Lids, 12 Pack Reusable Food Covers",
        "category": "Home & Kitchen",
        "url": "https://www.amazon.com/dp/B0CHX3QBCH",
        "image_url": "https://m.media-amazon.com/images/I/71xMock1.jpg",
        "price_usd": 12.99,
        "rating": 4.5,
        "review_count": 18432,
        "rank": 1,
        "weight_kg": 0.25,
    },
    {
        "external_id": "B09V7GB7YH",
        "title": "LED Strip Lights 50ft RGB Color Changing with Remote",
        "category": "Tools & Home Improvement",
        "url": "https://www.amazon.com/dp/B09V7GB7YH",
        "image_url": "https://m.media-amazon.com/images/I/71yMock2.jpg",
        "price_usd": 15.49,
        "rating": 4.6,
        "review_count": 92011,
        "rank": 2,
        "weight_kg": 0.5,
    },
    {
        "external_id": "B0B8QX6D2T",
        "title": "Portable Handheld Mini Fan, Rechargeable USB Desk Fan",
        "category": "Home & Kitchen",
        "url": "https://www.amazon.com/dp/B0B8QX6D2T",
        "image_url": "https://m.media-amazon.com/images/I/61zMock3.jpg",
        "price_usd": 19.99,
        "rating": 4.4,
        "review_count": 22110,
        "rank": 3,
        "weight_kg": 0.4,
    },
    {
        "external_id": "B0CJX9K4MM",
        "title": "Magnetic Phone Car Mount, 360° Rotation Dashboard Holder",
        "category": "Cell Phones & Accessories",
        "url": "https://www.amazon.com/dp/B0CJX9K4MM",
        "image_url": "https://m.media-amazon.com/images/I/61aMock4.jpg",
        "price_usd": 9.99,
        "rating": 4.5,
        "review_count": 5120,
        "rank": 4,
        "weight_kg": 0.15,
    },
    {
        "external_id": "B0BZYCJK8P",
        "title": "Stainless Steel Insulated Water Bottle 32oz with Straw",
        "category": "Sports & Outdoors",
        "url": "https://www.amazon.com/dp/B0BZYCJK8P",
        "image_url": "https://m.media-amazon.com/images/I/71bMock5.jpg",
        "price_usd": 24.99,
        "rating": 4.7,
        "review_count": 44210,
        "rank": 5,
        "weight_kg": 0.6,
    },
]


class AmazonScraper(BaseScraper):
    platform = "amazon"

    def fetch_bestsellers(self, limit: int = 20, category_url: str | None = None, **_: Any) -> list[ScrapedProduct]:
        if settings.use_mock_data:
            logger.info("[amazon] USE_MOCK_DATA=true, returning seed bestsellers")
            return [
                ScrapedProduct(platform=self.platform, **item)
                for item in _MOCK_BESTSELLERS[:limit]
            ]

        try:
            return self._fetch_with_playwright(limit=limit, category_url=category_url)
        except Exception as e:  # pragma: no cover - network dependent
            logger.warning("[amazon] real scrape failed (%s), falling back to mock data", e)
            return [
                ScrapedProduct(platform=self.platform, **item)
                for item in _MOCK_BESTSELLERS[:limit]
            ]

    def _fetch_with_playwright(self, limit: int, category_url: str | None) -> list[ScrapedProduct]:  # pragma: no cover
        from playwright.sync_api import sync_playwright

        url = category_url or settings.platform.amazon_bestseller_url
        products: list[ScrapedProduct] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=self.client.headers.get("User-Agent"))
            page = ctx.new_page()
            page.goto(url, timeout=self.timeout * 1000)
            page.wait_for_selector("#gridItemRoot", timeout=self.timeout * 1000)
            items = page.query_selector_all("#gridItemRoot")
            for idx, item in enumerate(items[:limit], start=1):
                title_el = item.query_selector("div._cDEzb_p13n-sc-css-line-clamp-3_g3dy1, span a div")
                link_el = item.query_selector("a.a-link-normal")
                price_el = item.query_selector("span._cDEzb_p13n-sc-price_3mJ9Z, span.p13n-sc-price")
                img_el = item.query_selector("img")
                rank_el = item.query_selector("span.zg-bdg-text")

                title = title_el.inner_text().strip() if title_el else ""
                href = link_el.get_attribute("href") if link_el else ""
                price_text = price_el.inner_text().strip().replace("$", "").replace(",", "") if price_el else ""
                img = img_el.get_attribute("src") if img_el else None
                rank = int((rank_el.inner_text() or "#0").lstrip("#")) if rank_el else idx
                asin = self._asin_from_url(href) or f"unknown-{idx}"
                try:
                    price = float(price_text) if price_text else None
                except ValueError:
                    price = None
                products.append(
                    ScrapedProduct(
                        platform=self.platform,
                        external_id=asin,
                        title=title,
                        url=f"https://www.amazon.com{href}" if href and href.startswith("/") else href,
                        image_url=img,
                        price_usd=price,
                        rank=rank,
                    )
                )
            browser.close()
        return products

    @staticmethod
    def _asin_from_url(href: str | None) -> str | None:
        if not href:
            return None
        for part in href.split("/"):
            if len(part) == 10 and part.isalnum() and part.isupper():
                return part
        return None
