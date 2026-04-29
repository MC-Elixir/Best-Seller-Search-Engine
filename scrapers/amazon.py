"""Amazon Best Sellers 抓取 (生产级).

策略:
- 真实抓取使用 Playwright + stealth 浏览器
- 模拟人类行为 (滚动、鼠标移动、随机延迟)
- 验证码自动检测 -> 回退 mock
- 多页翻页采集、多类目覆盖
- 商品重量智能估算
- mock 数据兜底 (USE_MOCK_DATA=true 或真实抓取失败时)
"""
from __future__ import annotations

import logging
import random
import re
import time
from typing import Any
from urllib.parse import urljoin

from config import settings
from config.proxy import get_proxy_pool

from .base import BaseScraper, ScrapedProduct

logger = logging.getLogger(__name__)

# Amazon Best Sellers 分站及热门类目
_CATEGORIES = [
    ("Home & Kitchen", "/Best-Sellers-Home-Kitchen/zgbs/home-garden/"),
    ("Electronics", "/Best-Sellers-Electronics/zgbs/electronics/"),
    ("Sports & Outdoors", "/Best-Sellers-Sports-Outdoors/zgbs/sporting-goods/"),
    ("Toys & Games", "/Best-Sellers-Toys-Games/zgbs/toys-and-games/"),
    ("Tools & Home Improvement", "/Best-Sellers-Improvement/zgbs/hi/"),
    ("Health & Household", "/Best-Sellers-Health-Personal-Care/zgbs/hpc/"),
    ("Kitchen & Dining", "/Best-Sellers-Kitchen-Dining/zgbs/kitchen/"),
    ("Pet Supplies", "/Best-Sellers-Pet-Supplies/zgbs/pet-supplies/"),
    ("Baby", "/Best-Sellers-Baby/zgbs/baby-products/"),
    ("Beauty & Personal Care", "/Best-Sellers-Beauty/zgbs/beauty/"),
    ("Office Products", "/Best-Sellers-Office-Products/zgbs/office-products/"),
    ("Clothing & Accessories", "/Best-Sellers-Clothing/zgbs/apparel/"),
    ("Garden & Outdoor", "/Best-Sellers-Garden-Outdoor/zgbs/lawn-garden/"),
    ("Automotive", "/Best-Sellers-Automotive/zgbs/automotive/"),
    ("Cell Phones & Accessories", "/Best-Sellers-Cell-Phone-Accessories/zgbs/wireless/"),
]

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

# 重量估算：基于类目和价格推测 (kg)
_WEIGHT_BY_CATEGORY: dict[str, tuple[float, float]] = {
    "Home & Kitchen": (0.15, 0.60),
    "Kitchen & Dining": (0.10, 0.50),
    "Electronics": (0.05, 0.40),
    "Sports & Outdoors": (0.20, 1.50),
    "Toys & Games": (0.10, 0.80),
    "Tools & Home Improvement": (0.10, 1.00),
    "Health & Household": (0.05, 0.30),
    "Pet Supplies": (0.15, 2.00),
    "Baby": (0.10, 0.80),
    "Beauty & Personal Care": (0.03, 0.20),
    "Office Products": (0.05, 0.30),
    "Clothing & Accessories": (0.10, 0.50),
    "Garden & Outdoor": (0.20, 3.00),
    "Automotive": (0.10, 2.00),
    "Cell Phones & Accessories": (0.02, 0.15),
}
_DEFAULT_WEIGHT_RANGE = (0.10, 0.50)


def _estimate_weight(category: str | None, price_usd: float | None) -> float:
    """基于类目和价格估算商品重量。"""
    lo, hi = _WEIGHT_BY_CATEGORY.get(category or "", _DEFAULT_WEIGHT_RANGE)
    # 价格越高 -> 重量倾向偏高
    if price_usd and price_usd > 30:
        return round(random.uniform(lo + (hi - lo) * 0.5, hi), 3)
    return round(random.uniform(lo, hi), 3)


class AmazonScraper(BaseScraper):
    platform = "amazon"
    BASE_URL = "https://www.amazon.com"

    # 多种选择器组合，兼容不同页面结构
    _ITEM_SELECTORS = [
        "#gridItemRoot",
        "div[data-component-type='s-search-result']",
        "div.zg-grid-general-faceout",
        "div.p13n-grid-content .a-carousel-card",
        "div[class*='p13n-sc-unveilable']",
    ]
    _TITLE_SELECTORS = [
        "div._cDEzb_p13n-sc-css-line-clamp-3_g3dy1",
        "div.p13n-sc-truncate-desktop-type2",
        "span.a-size-medium.a-color-base.a-text-normal",
        "h2 a span",
        "a[href*='/dp/'] span.a-text-normal",
        "div[data-cy='title-recipe'] span",
    ]
    _PRICE_SELECTORS = [
        "span._cDEzb_p13n-sc-price_3mJ9Z",
        "span.p13n-sc-price",
        "span.a-price span.a-offscreen",
        "span.a-price-whole",
    ]
    _RATING_SELECTORS = [
        "i.a-icon-star-small span",
        "span[aria-label*='out of 5']",
    ]
    _REVIEW_SELECTORS = [
        "span.a-size-small.a-color-secondary",
        "span[aria-label*='rating']",
    ]
    _IMAGE_SELECTORS = ["img", "img.s-image", "img[data-old-hires]"]
    _NEXT_PAGE_SELECTORS = [
        "a.s-pagination-next",
        "li.a-last a",
        "a[aria-label='Next page']",
        "a:has-text('Next')",
    ]

    def __init__(self, timeout: int | None = None) -> None:
        super().__init__(timeout)
        self._proxy_url = self._resolve_proxy()

    def fetch_bestsellers(
        self,
        limit: int = 100,
        category_url: str | None = None,
        categories: list[tuple[str, str]] | None = None,
        max_pages: int = 3,
        **_: Any,
    ) -> list[ScrapedProduct]:
        """抓取 Amazon Best Sellers。

        参数:
            limit: 总返回商品数上限
            category_url: 单个类目 URL (覆盖 categories 参数)
            categories: 多个类目列表 [(名称, URL路径), ...]
            max_pages: 每个类目最多翻页数

        策略: mock 模式直接返回种子数据；真实模式用 Playwright 逐类目多页抓取。
        """
        if settings.use_mock_data:
            logger.info("[amazon] USE_MOCK_DATA=true, returning seed bestsellers")
            return [
                ScrapedProduct(platform=self.platform, **item)
                for item in _MOCK_BESTSELLERS[:limit]
            ]

        try:
            return self._fetch_real(
                limit=limit,
                category_url=category_url,
                categories=categories,
                max_pages=max_pages,
            )
        except Exception as e:
            logger.warning("[amazon] real scrape failed (%s), falling back to mock", e)
            return [
                ScrapedProduct(platform=self.platform, **item)
                for item in _MOCK_BESTSELLERS[:limit]
            ]

    def _fetch_real(
        self,
        limit: int = 100,
        category_url: str | None = None,
        categories: list[tuple[str, str]] | None = None,
        max_pages: int = 3,
    ) -> list[ScrapedProduct]:
        """真实 Playwright 抓取。跨多个类目、多页采集。"""
        target_categories = categories or _CATEGORIES
        if category_url:
            target_categories = [("Custom", category_url)]

        all_products: list[ScrapedProduct] = []
        per_category_limit = max(10, limit // len(target_categories))

        with self.browser_context(headless=True) as (browser, context, page):
            for cat_name, cat_path in target_categories:
                if len(all_products) >= limit:
                    break

                url = urljoin(self.BASE_URL, cat_path)
                logger.info("[amazon] fetching %s -> %s", cat_name, url)

                products = self._scrape_category(
                    page, cat_name, url, per_category_limit, max_pages
                )
                all_products.extend(products)
                logger.info("[amazon] %s: got %d products", cat_name, len(products))

        return all_products[:limit]

    def _scrape_category(
        self,
        page,
        category_name: str,
        url: str,
        limit: int,
        max_pages: int,
    ) -> list[ScrapedProduct]:
        """抓取单个类目的商品列表 (含翻页)。"""
        products: list[ScrapedProduct] = []
        rank_offset = 1

        for page_num in range(max_pages):
            if len(products) >= limit:
                break

            try:
                page.goto(url, timeout=self.timeout * 1000, wait_until="domcontentloaded")
            except Exception as e:
                logger.warning("[amazon] page load failed: %s", e)
                break

            # 等待商品加载
            try:
                page.wait_for_selector(
                    ",".join(self._ITEM_SELECTORS[:2]),
                    timeout=15000,
                )
            except Exception:
                logger.debug("[amazon] primary selectors not found, trying alternatives")

            # 检测验证码
            if self.detect_captcha(page):
                logger.error("[amazon] CAPTCHA detected on %s, aborting", url)
                break

            # 模拟人类行为
            self.simulate_human_scroll(page, scrolls=random.randint(2, 4))
            self.simulate_mouse_movement(page)

            # 提取商品
            items = page.query_selector_all(",".join(self._ITEM_SELECTORS))
            if not items:
                items = page.query_selector_all("div[data-asin]")

            for item in items:
                if len(products) >= limit:
                    break

                try:
                    product = self._parse_item(item, category_name, rank_offset)
                    if product:
                        products.append(product)
                        rank_offset += 1
                except Exception as e:
                    logger.debug("[amazon] parse item error: %s", e)
                    continue

            # 翻页
            if len(products) >= limit:
                break

            next_url = self._get_next_page_url(page)
            if not next_url:
                break
            url = next_url
            time.sleep(random.uniform(2.0, 4.0))

        return products

    def _parse_item(self, item, category: str, rank: int) -> ScrapedProduct | None:
        """从 DOM 元素提取商品字段。"""
        title = self._extract_text(item, self._TITLE_SELECTORS)
        if not title or len(title) < 5:
            return None

        link_el = item.query_selector("a.a-link-normal")
        href = link_el.get_attribute("href") if link_el else ""

        asin = self._asin_from_url(href) or item.get_attribute("data-asin") or f"unknown-{rank}"

        price = self._extract_price(item)
        image_url = self._extract_image(item)
        rating = self._extract_rating(item)
        review_count = self._extract_review_count(item)

        full_url = (
            f"https://www.amazon.com{href}"
            if href and href.startswith("/")
            else (href or f"https://www.amazon.com/dp/{asin}")
        )

        weight_kg = _estimate_weight(category, price)

        return ScrapedProduct(
            platform=self.platform,
            external_id=asin,
            title=title,
            category=category,
            url=full_url,
            image_url=image_url,
            price_usd=price,
            rating=rating,
            review_count=review_count,
            rank=rank,
            weight_kg=weight_kg,
        )

    # ── 字段提取 ──────────────────────────────────────────
    def _extract_text(self, item, selectors: list[str]) -> str | None:
        for sel in selectors:
            el = item.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if text:
                    return text
        return None

    def _extract_price(self, item) -> float | None:
        for sel in self._PRICE_SELECTORS:
            el = item.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if text:
                    # 尝试从 aria-label 提取，如 "$24.99"
                    aria = el.get_attribute("aria-label") or ""
                    price_text = aria if "$" in aria else text
                    price_text = price_text.replace("$", "").replace(",", "").split()[0]
                    try:
                        return float(price_text)
                    except ValueError:
                        continue
        # 尝试从 a-price-whole + a-price-fraction 组装
        whole = item.query_selector("span.a-price-whole")
        fraction = item.query_selector("span.a-price-fraction")
        if whole:
            try:
                w = int(whole.inner_text().replace(",", "").strip())
                f = int(fraction.inner_text().strip()) if fraction else 0
                return float(f"{w}.{f:02d}")
            except (ValueError, AttributeError):
                pass
        return None

    def _extract_image(self, item) -> str | None:
        for sel in self._IMAGE_SELECTORS:
            el = item.query_selector(sel)
            if el:
                src = el.get_attribute("src") or el.get_attribute("data-old-hires")
                if src:
                    return src
        return None

    def _extract_rating(self, item) -> float | None:
        for sel in self._RATING_SELECTORS:
            el = item.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                match = re.search(r"(\d+\.?\d*)", text)
                if match:
                    return float(match.group(1))
        # aria-label 如 "4.5 out of 5 stars"
        for el in item.query_selector_all("span[aria-label]"):
            aria = el.get_attribute("aria-label") or ""
            match = re.search(r"(\d+\.?\d*)\s*out of", aria)
            if match:
                return float(match.group(1))
        return None

    def _extract_review_count(self, item) -> int | None:
        for sel in self._REVIEW_SELECTORS:
            el = item.query_selector(sel)
            if el:
                text = el.inner_text()
                match = re.search(r"([\d,]+)", text)
                if match:
                    return int(match.group(1).replace(",", ""))
        return None

    def _get_next_page_url(self, page) -> str | None:
        for sel in self._NEXT_PAGE_SELECTORS:
            el = page.query_selector(sel)
            if el:
                href = el.get_attribute("href")
                if href:
                    return urljoin(self.BASE_URL, href)
        return None

    @staticmethod
    def _asin_from_url(href: str | None) -> str | None:
        if not href:
            return None
        for part in href.split("/"):
            if len(part) == 10 and part.isalnum() and part.isupper():
                return part
        return None
