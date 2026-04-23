"""命令行入口。

用法:
    python main.py                         # 默认 amazon + temu，各抓 10 条
    python main.py --platforms amazon
    python main.py --limit 5 --offers 3
"""
from __future__ import annotations

import argparse
import logging

from config import settings
from pipeline import ArbitragePipeline, PipelineConfig


def _setup_logging() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cross-platform arbitrage discovery pipeline")
    parser.add_argument("--platforms", nargs="+", default=["amazon", "temu"], choices=["amazon", "temu"])
    parser.add_argument("--limit", type=int, default=10, help="每个平台抓取的商品数")
    parser.add_argument("--offers", type=int, default=5, help="每个商品在 1688 上匹配的货源数")
    parser.add_argument("--min-margin", type=float, default=None, help="最低利润率阈值")
    parser.add_argument("--ship-mode", choices=["air", "sea"], default="sea")
    return parser.parse_args()


def main() -> None:
    _setup_logging()
    args = parse_args()
    cfg = PipelineConfig(
        platforms=args.platforms,
        limit_per_platform=args.limit,
        offers_per_product=args.offers,
        ship_mode=args.ship_mode,
    )
    if args.min_margin is not None:
        cfg.min_margin = args.min_margin

    pipeline = ArbitragePipeline(cfg)
    stats = pipeline.run()
    print("\n=== Pipeline Summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("\n运行 `streamlit run ui/dashboard.py` 查看结果。")


if __name__ == "__main__":
    main()
