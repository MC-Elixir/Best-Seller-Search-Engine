"""头程物流费用估算。"""
from __future__ import annotations

from typing import Literal

from config import settings

ShipMode = Literal["air", "sea"]


def estimate_logistics_cost(weight_kg: float | None, mode: ShipMode = "sea") -> float:
    """返回每件头程物流费（USD），基于每 kg 价格 * 重量。"""
    if weight_kg is None or weight_kg <= 0:
        weight_kg = 0.3

    cny_per_kg = (
        settings.profit.air_freight_cny_per_kg
        if mode == "air"
        else settings.profit.sea_freight_cny_per_kg
    )
    cost_cny = cny_per_kg * float(weight_kg)
    cost_usd = cost_cny * settings.profit.cny_to_usd
    return round(cost_usd, 2)
