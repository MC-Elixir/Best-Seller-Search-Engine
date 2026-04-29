import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calculators import compute_profit
from matchers.text_matcher import jaccard


def test_profit_basic():
    b = compute_profit(sell_price_usd=24.99, supplier_price_cny=30, weight_kg=0.5)
    assert b.cost_usd > 0
    assert b.fba_fee_usd > 0
    assert b.logistics_usd > 0
    assert b.margin < 1.0
    # 数值自洽
    expected = round(
        b.sell_price_usd - b.cost_usd - b.fba_fee_usd - b.logistics_usd - b.referral_fee_usd,
        2,
    )
    assert b.profit_usd == expected


def test_profit_loss():
    b = compute_profit(sell_price_usd=5.0, supplier_price_cny=50, weight_kg=1.0)
    assert b.profit_usd < 0
    assert b.margin < 0


def test_jaccard_identity():
    assert jaccard("Silicone Food Lid", "Silicone Food Lid") > 0.9


def test_jaccard_different():
    assert jaccard("apple", "banana") < 0.3
