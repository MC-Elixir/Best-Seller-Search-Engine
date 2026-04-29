"""端到端利润率计算。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from config import settings

from .fba_fees import estimate_fba_fee
from .logistics import ShipMode, estimate_logistics_cost


@dataclass
class ProfitBreakdown:
    sell_price_usd: float
    cost_usd: float
    referral_fee_usd: float
    fba_fee_usd: float
    logistics_usd: float
    profit_usd: float
    margin: float

    def as_dict(self) -> dict[str, float]:
        return {
            "sell_price_usd": self.sell_price_usd,
            "cost_usd": self.cost_usd,
            "referral_fee_usd": self.referral_fee_usd,
            "fba_fee_usd": self.fba_fee_usd,
            "logistics_usd": self.logistics_usd,
            "profit_usd": self.profit_usd,
            "margin": self.margin,
        }


def compute_profit(
    sell_price_usd: float,
    supplier_price_cny: float,
    weight_kg: float | None,
    ship_mode: ShipMode = "sea",
    referral_fee_rate: float | None = None,
    cny_to_usd: float | None = None,
) -> ProfitBreakdown:
    fx = cny_to_usd if cny_to_usd is not None else settings.profit.cny_to_usd
    rate = referral_fee_rate if referral_fee_rate is not None else settings.profit.referral_fee_rate

    cost_usd = round(supplier_price_cny * fx, 2)
    fba = estimate_fba_fee(weight_kg, price_usd=sell_price_usd)
    logistics = estimate_logistics_cost(weight_kg, mode=ship_mode)
    referral = round(sell_price_usd * rate, 2)

    profit = round(sell_price_usd - cost_usd - fba - logistics - referral, 2)
    margin = round(profit / sell_price_usd, 4) if sell_price_usd else 0.0

    return ProfitBreakdown(
        sell_price_usd=sell_price_usd,
        cost_usd=cost_usd,
        referral_fee_usd=referral,
        fba_fee_usd=fba,
        logistics_usd=logistics,
        profit_usd=profit,
        margin=margin,
    )
