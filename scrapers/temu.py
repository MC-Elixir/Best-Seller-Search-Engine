"""Temu 热门商品抓取 (生产级)。

Temu 数据采集策略:
- Temu 没有公开 API，使用反抓包重放方式
- 关键 XHR 接口:
  - 首页推荐: https://www.temu.com/api/poppy/v2/search
  - 类目商品: https://www.temu.com/api/poppy/v2/category
  - 商品搜索: https://www.temu.com/api/poppy/v2/search_goods
- 标配反爬: Akamai + 自定义 header 校验 + 设备指纹
- MVP 回退 mock，后续接入真实接口只需替换 _fetch_real
"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

import httpx

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
    {
        "external_id": "601099512345004",
        "title": "Stainless Steel Tumbler 40oz with Handle and Straw",
        "category": "Home & Garden",
        "url": "https://www.temu.com/--g-601099512345004.html",
        "image_url": "https://img.kwcdn.com/mock/tumbler.jpg",
        "price_usd": 8.99,
        "rating": 4.5,
        "review_count": 25310,
        "rank": 4,
        "weight_kg": 0.55,
    },
    {
        "external_id": "601099512345005",
        "title": "Wireless Bluetooth Earbuds with Charging Case",
        "category": "Electronics",
        "url": "https://www.temu.com/--g-601099512345005.html",
        "image_url": "https://img.kwcdn.com/mock/earbuds.jpg",
        "price_usd": 3.99,
        "rating": 4.4,
        "review_count": 38420,
        "rank": 5,
        "weight_kg": 0.08,
    },
    {
        "external_id": "601099512345006",
        "title": "Cordless Electric Spin Scrubber with 4 Brush Heads",
        "category": "Home & Garden",
        "url": "https://www.temu.com/--g-601099512345006.html",
        "image_url": "https://img.kwcdn.com/mock/scrubber.jpg",
        "price_usd": 12.49,
        "rating": 4.6,
        "review_count": 12100,
        "rank": 6,
        "weight_kg": 0.70,
    },
    {
        "external_id": "601099512345007",
        "title": "Adjustable Posture Corrector for Men and Women",
        "category": "Health & Beauty",
        "url": "https://www.temu.com/--g-601099512345007.html",
        "image_url": "https://img.kwcdn.com/mock/posture.jpg",
        "price_usd": 2.89,
        "rating": 4.3,
        "review_count": 18900,
        "rank": 7,
        "weight_kg": 0.12,
    },
    {
        "external_id": "601099512345008",
        "title": "Car Phone Holder Dashboard Mount Adjustable",
        "category": "Automotive",
        "url": "https://www.temu.com/--g-601099512345008.html",
        "image_url": "https://img.kwcdn.com/mock/car-mount.jpg",
        "price_usd": 2.49,
        "rating": 4.5,
        "review_count": 22100,
        "rank": 8,
        "weight_kg": 0.10,
    },
    {
        "external_id": "601099512345009",
        "title": "4 Pack Packing Cubes Luggage Travel Organizer Bags",
        "category": "Travel",
        "url": "https://www.temu.com/--g-601099512345009.html",
        "image_url": "https://img.kwcdn.com/mock/packing-cubes.jpg",
        "price_usd": 4.99,
        "rating": 4.7,
        "review_count": 14300,
        "rank": 9,
        "weight_kg": 0.30,
    },
    {
        "external_id": "601099512345010",
        "title": "Portable Bluetooth Speaker Waterproof IPX7 Mini",
        "category": "Electronics",
        "url": "https://www.temu.com/--g-601099512345010.html",
        "image_url": "https://img.kwcdn.com/mock/speaker.jpg",
        "price_usd": 6.99,
        "rating": 4.4,
        "review_count": 28000,
        "rank": 10,
        "weight_kg": 0.20,
    },
]


class TemuScraper(BaseScraper):
    platform = "temu"

    # Temu API 端点 (需要抓包获取最新参数)
    _SEARCH_API = "https://www.temu.com/api/poppy/v2/search_goods"
    _CATEGORY_API = "https://www.temu.com/api/poppy/v2/category"
    _RECOMMEND_API = "https://www.temu.com/api/poppy/v2/recommend"

    # Temu 需要的特殊 headers (会随时间过期)
    _API_HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://www.temu.com",
        "Referer": "https://www.temu.com/",
    }

    def __init__(self, timeout: int | None = None) -> None:
        super().__init__(timeout)
        self._proxy_url = self._resolve_proxy()

    def fetch_bestsellers(
        self,
        limit: int = 100,
        category_id: str | None = None,
        **_: Any,
    ) -> list[ScrapedProduct]:
        """抓取 Temu 热门商品。

        生产模式策略:
        1. 尝试 XHR API 重放 (需要定期更新签名参数)
        2. 失败回退 Playwright 爬页面
        3. 再失败回退 mock
        """
        if settings.use_mock_data:
            logger.info("[temu] USE_MOCK_DATA=true, returning seed trending list")
            return [ScrapedProduct(platform=self.platform, **item) for item in _MOCK_TRENDING[:limit]]

        try:
            return self._fetch_real(limit=limit, category_id=category_id)
        except Exception as e:
            logger.warning("[temu] real scrape failed (%s), falling back to mock data", e)
            return [ScrapedProduct(platform=self.platform, **item) for item in _MOCK_TRENDING[:limit]]

    def _fetch_real(self, limit: int, category_id: str | None = None) -> list[ScrapedProduct]:
        """真实抓取。优先 XHR API，失败回退浏览器。"""
        # 先尝试 XHR API
        try:
            return self._fetch_via_api(limit=limit, category_id=category_id)
        except Exception as e:
            logger.debug("[temu] API fetch failed: %s, trying browser", e)

        # 回退 Playwright 浏览器
        try:
            return self._fetch_via_browser(limit=limit)
        except Exception as e:
            logger.warning("[temu] browser fetch also failed: %s", e)
            raise

    def _fetch_via_api(self, limit: int, category_id: str | None = None) -> list[ScrapedProduct]:
        """通过 XHR API 重放采集。

        注意: Temu 的反爬签名机制定期更新，需要维护以下参数:
        - api_uid: 设备指纹
        - verify_authentication: 页面级 token
        - sign: 请求签名
        """
        params = {
            "page_el_sn": None,
            "cat_id": category_id or "recommend",
            "sort_type": "3",        # 销量排序
            "page_size": min(limit, 50),
            "offset": 0,
        }

        headers = {**self._API_HEADERS, "User-Agent": _random_ua_fallback()}

        try:
            resp = self.client.post(
                self._RECOMMEND_API,
                json=params,
                headers=headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.error("[temu] API request failed: %s", e)
            raise

        return self._parse_api_response(data, limit)

    def _fetch_via_browser(self, limit: int) -> list[ScrapedProduct]:
        """通过 Playwright 浏览器采集 Temu 页面。"""
        import re

        products: list[ScrapedProduct] = []

        with self.browser_context(headless=True) as (browser, context, page):
            url = "https://www.temu.com/best-sellers.html"
            try:
                page.goto(url, timeout=self.timeout * 1000, wait_until="domcontentloaded")
            except Exception as e:
                logger.warning("[temu] page load failed: %s", e)

            if self.detect_captcha(page):
                logger.warning("[temu] CAPTCHA detected")

            self.simulate_human_scroll(page, scrolls=5)
            time.sleep(random.uniform(2, 4))

            items = page.query_selector_all("div[data-type='goods']")
            if not items:
                items = page.query_selector_all("div[class*='goods']")

            rank = 1
            for item in items[:limit]:
                try:
                    title_el = item.query_selector("div[class*='title'], span[class*='title'], p")
                    title = title_el.inner_text().strip() if title_el else ""

                    price_el = item.query_selector("span[class*='price'], div[class*='price']")
                    price_text = ""
                    if price_el:
                        price_text = re.sub(r"[^\d.]", "", price_el.inner_text())

                    img_el = item.query_selector("img")
                    image_url = img_el.get_attribute("src") if img_el else None

                    link_el = item.query_selector("a")
                    href = link_el.get_attribute("href") if link_el else ""

                    external_id = f"temu-{rank}-{hash(title) % 100000:05d}"

                    try:
                        price = float(price_text) if price_text else None
                    except ValueError:
                        price = None

                    products.append(
                        ScrapedProduct(
                            platform=self.platform,
                            external_id=external_id,
                            title=title,
                            url=f"https://www.temu.com{href}" if href.startswith("/") else href,
                            image_url=image_url,
                            price_usd=price,
                            rank=rank,
                            weight_kg=_estimate_weight(price),
                        )
                    )
                    rank += 1
                except Exception as e:
                    logger.debug("[temu] parse item error: %s", e)
                    continue

        return products

    def _parse_api_response(self, data: dict, limit: int) -> list[ScrapedProduct]:
        """解析 Temu API 响应为 ScrapedProduct 列表。"""
        products: list[ScrapedProduct] = []
        goods_list = data.get("data", {}).get("goods_list") or data.get("data", {}).get("items") or []

        for rank, item in enumerate(goods_list[:limit], start=1):
            goods_id = str(item.get("goods_id", ""))
            title = item.get("goods_name", "") or item.get("title", "")
            price = None
            price_info = item.get("price_info") or item.get("price") or {}
            min_price = price_info.get("min_price")
            if min_price:
                try:
                    price = float(min_price) / 100  # Temu 价格以分为单位
                except (ValueError, TypeError):
                    pass

            products.append(
                ScrapedProduct(
                    platform=self.platform,
                    external_id=goods_id,
                    title=title,
                    url=f"https://www.temu.com/--g-{goods_id}.html",
                    image_url=item.get("thumb_url") or item.get("image_url"),
                    price_usd=price,
                    rating=item.get("rating"),
                    review_count=item.get("sales") or item.get("sales_tip"),
                    rank=rank,
                    weight_kg=_estimate_weight(price),
                )
            )

        return products


def _random_ua_fallback() -> str:
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )


def _estimate_weight(price_usd: float | None) -> float:
    """基于价格估算 Temu 商品重量。Temu 商品通常较轻。"""
    if price_usd is None:
        return 0.2
    if price_usd < 3:
        return round(random.uniform(0.02, 0.08), 3)
    if price_usd < 7:
        return round(random.uniform(0.05, 0.25), 3)
    if price_usd < 15:
        return round(random.uniform(0.15, 0.60), 3)
    return round(random.uniform(0.30, 1.20), 3)
