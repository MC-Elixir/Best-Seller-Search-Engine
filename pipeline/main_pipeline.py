"""主流程编排：抓取 -> 匹配 -> 筛同款 -> 算利润 -> 落库。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from calculators import compute_profit
from config import settings
from matchers import AlibabaMatcher, LLMJudge, TextMatcher
from scrapers import AmazonScraper, ScrapedProduct, TemuScraper
from storage import ArbitrageOpportunity, MatchedSupplier, SourceProduct, get_db

logger = logging.getLogger(__name__)

Platform = Literal["amazon", "temu"]


@dataclass
class PipelineConfig:
    platforms: list[Platform] = field(default_factory=lambda: ["amazon", "temu"])
    limit_per_platform: int = 10
    offers_per_product: int = 5
    similarity_threshold: float = 0.2
    min_margin: float = field(default_factory=lambda: settings.profit.min_margin)
    ship_mode: Literal["air", "sea"] = "sea"


class ArbitragePipeline:
    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self.db = get_db()
        self.matcher = AlibabaMatcher()
        self.text = TextMatcher()
        self.judge = LLMJudge()

    # ---------- scraping ----------
    def _scrape(self, platform: Platform) -> list[ScrapedProduct]:
        if platform == "amazon":
            with AmazonScraper() as s:
                return s.fetch_bestsellers(limit=self.config.limit_per_platform)
        if platform == "temu":
            with TemuScraper() as s:
                return s.fetch_bestsellers(limit=self.config.limit_per_platform)
        raise ValueError(f"Unsupported platform: {platform}")

    # ---------- main ----------
    def run(self) -> dict[str, int]:
        stats = {"sources": 0, "suppliers": 0, "opportunities": 0}

        with self.db.session() as session:
            for platform in self.config.platforms:
                logger.info("Scraping %s ...", platform)
                products = self._scrape(platform)
                for product in products:
                    src = self._persist_source(session, product)
                    stats["sources"] += 1

                    offers = self.matcher.search_by_keyword(
                        product.title,
                        limit=self.config.offers_per_product,
                    )
                    for offer in offers:
                        sim = self.text.similarity(product.title, offer.title_cn)
                        if sim < self.config.similarity_threshold:
                            continue
                        verdict = self.judge.judge(
                            source_title=product.title,
                            supplier_title=offer.title_cn,
                            similarity=sim,
                            source_price_usd=product.price_usd,
                            supplier_price_cny=offer.price_cny,
                        )

                        supplier = MatchedSupplier(
                            source_id=src.id,
                            offer_id=offer.offer_id,
                            title_cn=offer.title_cn,
                            title_en=None,
                            url=offer.url,
                            image_url=offer.image_url,
                            price_cny=offer.price_cny,
                            moq=offer.moq,
                            similarity=sim,
                            llm_same_product=1 if verdict.same_product else 0,
                            llm_reason=verdict.reason,
                        )
                        session.add(supplier)
                        session.flush()
                        stats["suppliers"] += 1

                        if not verdict.same_product:
                            continue
                        if not product.price_usd:
                            continue

                        breakdown = compute_profit(
                            sell_price_usd=product.price_usd,
                            supplier_price_cny=offer.price_cny,
                            weight_kg=product.weight_kg,
                            ship_mode=self.config.ship_mode,
                        )
                        if breakdown.margin < self.config.min_margin:
                            continue

                        opp = ArbitrageOpportunity(
                            source_id=src.id,
                            supplier_id=supplier.id,
                            sell_price_usd=breakdown.sell_price_usd,
                            cost_usd=breakdown.cost_usd,
                            fba_fee_usd=breakdown.fba_fee_usd,
                            logistics_usd=breakdown.logistics_usd,
                            referral_fee_usd=breakdown.referral_fee_usd,
                            profit_usd=breakdown.profit_usd,
                            margin=breakdown.margin,
                            notes=verdict.reason,
                        )
                        session.add(opp)
                        stats["opportunities"] += 1

        logger.info("Pipeline done: %s", stats)
        return stats

    # ---------- helpers ----------
    @staticmethod
    def _persist_source(session, product: ScrapedProduct) -> SourceProduct:
        existing = (
            session.query(SourceProduct)
            .filter_by(platform=product.platform, external_id=product.external_id)
            .one_or_none()
        )
        if existing:
            # 更新可变字段
            existing.title = product.title
            existing.price_usd = product.price_usd
            existing.rating = product.rating
            existing.review_count = product.review_count
            existing.rank = product.rank
            if product.weight_kg:
                existing.weight_kg = product.weight_kg
            return existing
        src = SourceProduct(
            platform=product.platform,
            external_id=product.external_id,
            title=product.title,
            category=product.category,
            url=product.url,
            image_url=product.image_url,
            price_usd=product.price_usd,
            rating=product.rating,
            review_count=product.review_count,
            rank=product.rank,
            weight_kg=product.weight_kg,
        )
        session.add(src)
        session.flush()
        return src
