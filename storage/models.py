"""SQLAlchemy ORM 模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class SourceProduct(Base):
    """目标平台上的热销商品（Amazon / Temu）。"""

    __tablename__ = "source_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(32), index=True, nullable=False)  # amazon / temu
    external_id = Column(String(128), index=True, nullable=False)  # ASIN / Temu goodsId
    title = Column(Text, nullable=False)
    category = Column(String(128))
    url = Column(Text)
    image_url = Column(Text)
    price_usd = Column(Float)
    rating = Column(Float)
    review_count = Column(Integer)
    rank = Column(Integer)
    weight_kg = Column(Float)  # 估算重量，用于计算物流
    created_at = Column(DateTime, default=datetime.utcnow)

    suppliers = relationship("MatchedSupplier", back_populates="source", cascade="all, delete-orphan")


class MatchedSupplier(Base):
    """在 1688 匹配到的货源。"""

    __tablename__ = "matched_suppliers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("source_products.id", ondelete="CASCADE"), index=True)
    offer_id = Column(String(128), index=True)
    title_cn = Column(Text)
    title_en = Column(Text)  # 翻译后
    url = Column(Text)
    image_url = Column(Text)
    price_cny = Column(Float)
    moq = Column(Integer)  # 起订量
    similarity = Column(Float)  # 文本/图像相似度
    llm_same_product = Column(Integer)  # 0/1, LLM 判断是否同款
    llm_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("SourceProduct", back_populates="suppliers")


class ArbitrageOpportunity(Base):
    """最终筛选出的套利机会。"""

    __tablename__ = "arbitrage_opportunities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("source_products.id", ondelete="CASCADE"), index=True)
    supplier_id = Column(Integer, ForeignKey("matched_suppliers.id", ondelete="CASCADE"), index=True)
    sell_price_usd = Column(Float, nullable=False)
    cost_usd = Column(Float, nullable=False)
    fba_fee_usd = Column(Float, nullable=False)
    logistics_usd = Column(Float, nullable=False)
    referral_fee_usd = Column(Float, nullable=False)
    profit_usd = Column(Float, nullable=False)
    margin = Column(Float, nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
