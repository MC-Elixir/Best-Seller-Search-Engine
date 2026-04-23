"""Amazon FBA 费用估算（简化版）。

实际费率以 Amazon 2024+ 官方表格为准，MVP 使用分段近似，
方便 pipeline 有数可用。接入真实报价后替换 `estimate_fba_fee`。
"""
from __future__ import annotations


def estimate_fba_fee(weight_kg: float | None, price_usd: float | None = None) -> float:
    """返回单件 FBA 配送费（USD）。"""
    if weight_kg is None or weight_kg <= 0:
        weight_kg = 0.3  # 默认当作小件
    w = float(weight_kg)

    # 分段：近似 2024 standard size 费率
    if w <= 0.1:
        base = 3.22
    elif w <= 0.25:
        base = 3.75
    elif w <= 0.5:
        base = 4.45
    elif w <= 1.0:
        base = 5.30
    elif w <= 1.5:
        base = 6.20
    elif w <= 3.0:
        base = 6.20 + (w - 1.5) * 0.45
    else:
        base = 6.20 + 1.5 * 0.45 + (w - 3.0) * 0.40

    # 低价商品常见 Low-Price FBA 折扣
    if price_usd is not None and price_usd < 10.0:
        base *= 0.85
    return round(base, 2)
