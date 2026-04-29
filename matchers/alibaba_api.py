"""1688 搜索封装。

MVP：
- 真实调用需要 1688 开放平台授权 (alibaba_app_key / secret)，签名流程较繁琐，
  这里把接口抽象成 `search_by_keyword` 和 `search_by_image`，方便后续替换。
- 未配置或 USE_MOCK_DATA=true 时使用本地生成的货源。
"""
from __future__ import annotations

import hashlib
import logging
import random
from typing import Any

from pydantic import BaseModel, Field

from config import settings

logger = logging.getLogger(__name__)


class SupplierOffer(BaseModel):
    offer_id: str
    title_cn: str
    url: str | None = None
    image_url: str | None = None
    price_cny: float
    moq: int = 1
    raw: dict[str, Any] = Field(default_factory=dict)


def _deterministic_price(seed: str, lo: float, hi: float) -> float:
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    rng = random.Random(h)
    return round(rng.uniform(lo, hi), 2)


class AlibabaMatcher:
    def __init__(self) -> None:
        self.app_key = settings.alibaba_app_key
        self.app_secret = settings.alibaba_app_secret

    @property
    def is_configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    def search_by_keyword(self, keyword: str, limit: int = 5) -> list[SupplierOffer]:
        if settings.use_mock_data or not self.is_configured:
            return self._mock_offers(keyword, limit)
        try:
            return self._real_keyword_search(keyword=keyword, limit=limit)
        except Exception as e:  # pragma: no cover
            logger.warning("[1688] keyword search failed (%s), falling back to mock", e)
            return self._mock_offers(keyword, limit)

    def search_by_image(self, image_url: str, limit: int = 5) -> list[SupplierOffer]:
        if settings.use_mock_data or not self.is_configured:
            return self._mock_offers(image_url, limit, tag="img")
        try:
            return self._real_image_search(image_url=image_url, limit=limit)
        except Exception as e:  # pragma: no cover
            logger.warning("[1688] image search failed (%s), falling back to mock", e)
            return self._mock_offers(image_url, limit, tag="img")

    def _real_keyword_search(self, keyword: str, limit: int) -> list[SupplierOffer]:  # pragma: no cover
        raise NotImplementedError("接入 alibaba.product.search 接口后替换此方法")

    def _real_image_search(self, image_url: str, limit: int) -> list[SupplierOffer]:  # pragma: no cover
        raise NotImplementedError("接入 alibaba.image.search 接口后替换此方法")

    @staticmethod
    def _mock_offers(seed: str, limit: int, tag: str = "kw") -> list[SupplierOffer]:
        offers: list[SupplierOffer] = []
        for i in range(limit):
            oid = hashlib.md5(f"{tag}:{seed}:{i}".encode()).hexdigest()[:12]
            price = _deterministic_price(f"{tag}:{seed}:{i}", 8, 60)
            offers.append(
                SupplierOffer(
                    offer_id=oid,
                    title_cn=f"{seed[:30]} 工厂直供 现货 #{i + 1}",
                    url=f"https://detail.1688.com/offer/{oid}.html",
                    image_url=f"https://cbu01.alicdn.com/mock/{oid}.jpg",
                    price_cny=price,
                    moq=random.Random(oid).choice([1, 2, 5, 10, 20]),
                )
            )
        return offers
