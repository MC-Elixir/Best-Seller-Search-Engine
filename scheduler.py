"""自动化调度器：定时执行抓取、匹配、利润计算全流程。

使用方式:
    # 启动调度器 (常驻进程)
    python scheduler.py

    # 单次执行 (one-shot)
    python scheduler.py --once

    # 从 CLI 入口使用
    python main.py --schedule

配置 (通过 .env):
    SCHEDULE_ENABLED=true        # main.py --schedule 时可用
    SCHEDULE_CRON=0 8 * * *      # 每天早上 8 点
    SCHEDULE_CRON_AMAZON=0 */6 * * *   # Amazon 每 6 小时
    SCHEDULE_CRON_TEMU=0 */12 * * *    # Temu 每 12 小时
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from config import settings
from pipeline import ArbitragePipeline, PipelineConfig

logger = logging.getLogger(__name__)

# 默认调度策略
DEFAULT_CRON_FULL = "0 8 * * *"       # 完整 pipeline：每天早 8 点
DEFAULT_CRON_AMAZON = "0 */6 * * *"    # Amazon only：每 6 小时
DEFAULT_CRON_TEMU = "0 */12 * * *"     # Temu only：每 12 小时


def _setup_logging(level: str | None = None) -> None:
    logging.basicConfig(
        level=level or settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )


def run_pipeline(
    platforms: list[str] | None = None,
    limit: int = 100,
    offers: int = 10,
    min_margin: float | None = None,
    ship_mode: str = "sea",
) -> dict[str, int]:
    """执行一次完整的套利 pipeline。"""
    cfg = PipelineConfig(
        platforms=platforms or ["amazon", "temu"],
        limit_per_platform=limit,
        offers_per_product=offers,
        ship_mode=ship_mode,
    )
    if min_margin is not None:
        cfg.min_margin = min_margin

    logger.info("Starting pipeline: platforms=%s limit=%d offers=%d",
                cfg.platforms, cfg.limit_per_platform, cfg.offers_per_product)

    pipeline = ArbitragePipeline(cfg)
    stats = pipeline.run()
    logger.info("Pipeline complete: %s", stats)
    return stats


def run_amazon_only(limit: int = 100, offers: int = 10) -> dict[str, int]:
    """仅抓取 Amazon + 匹配。"""
    return run_pipeline(platforms=["amazon"], limit=limit, offers=offers)


def run_temu_only(limit: int = 100, offers: int = 10) -> dict[str, int]:
    """仅抓取 Temu + 匹配。"""
    return run_pipeline(platforms=["temu"], limit=limit, offers=offers)


def _job_listener(event) -> None:
    if event.exception:
        logger.error("Job %s failed: %s", event.job_id, event.exception)
    else:
        logger.info("Job %s completed successfully", event.job_id)


def create_scheduler() -> BackgroundScheduler:
    """创建并配置调度器。

    注册 3 个任务:
    - full_pipeline:  全流程 (Amazon + Temu + 匹配 + 利润)
    - amazon_only:    仅 Amazon 高频采集
    - temu_only:      仅 Temu 采集
    """
    scheduler = BackgroundScheduler(
        timezone="Asia/Shanghai",
        job_defaults={
            "coalesce": True,          # 合并错过的执行
            "max_instances": 1,        # 同一任务最多 1 个实例
            "misfire_grace_time": 300,  # 5 分钟容错窗口
        },
    )

    # 从环境变量读取 cron 表达式
    cron_full = os.getenv("SCHEDULE_CRON_FULL", DEFAULT_CRON_FULL)
    cron_amazon = os.getenv("SCHEDULE_CRON_AMAZON", DEFAULT_CRON_AMAZON)
    cron_temu = os.getenv("SCHEDULE_CRON_TEMU", DEFAULT_CRON_TEMU)

    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger.from_crontab(cron_full),
        id="full_pipeline",
        name="Full Arbitrage Pipeline",
        replace_existing=True,
    )
    logger.info("Registered job 'full_pipeline': %s", cron_full)

    scheduler.add_job(
        run_amazon_only,
        trigger=CronTrigger.from_crontab(cron_amazon),
        id="amazon_scrape",
        name="Amazon Best Sellers Scrape",
        replace_existing=True,
    )
    logger.info("Registered job 'amazon_scrape': %s", cron_amazon)

    scheduler.add_job(
        run_temu_only,
        trigger=CronTrigger.from_crontab(cron_temu),
        id="temu_scrape",
        name="Temu Trending Scrape",
        replace_existing=True,
    )
    logger.info("Registered job 'temu_scrape': %s", cron_temu)

    scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    return scheduler


def run_scheduler(block: bool = True) -> BackgroundScheduler:
    """启动调度器并返回。block=True 会阻塞直到收到 SIGINT/SIGTERM。"""
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started.")

    if block:
        def _shutdown(signum, frame):
            logger.info("Received signal %s, shutting down...", signum)
            scheduler.shutdown(wait=False)
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown(wait=False)

    return scheduler


# ── CLI ───────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Arbitrage Pipeline Scheduler")
    parser.add_argument(
        "--once",
        action="store_true",
        help="单次执行 (不启动调度器)",
    )
    parser.add_argument(
        "--once-amazon",
        action="store_true",
        help="单次执行 Amazon only",
    )
    parser.add_argument(
        "--once-temu",
        action="store_true",
        help="单次执行 Temu only",
    )
    parser.add_argument("--platforms", nargs="+", default=["amazon", "temu"])
    parser.add_argument("--limit", type=int, default=100, help="每平台商品数")
    parser.add_argument("--offers", type=int, default=10, help="每商品匹配数")
    parser.add_argument("--min-margin", type=float, default=0.25, help="最低利润率")
    parser.add_argument("--ship-mode", choices=["air", "sea"], default="sea")
    return parser.parse_args()


def main() -> None:
    _setup_logging()
    args = parse_args()

    if args.once:
        logger.info("One-shot full pipeline execution")
        stats = run_pipeline(
            platforms=args.platforms,
            limit=args.limit,
            offers=args.offers,
            min_margin=args.min_margin,
            ship_mode=args.ship_mode,
        )
        print("\n=== Pipeline Summary ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        return

    if args.once_amazon:
        logger.info("One-shot Amazon-only execution")
        stats = run_amazon_only(limit=args.limit, offers=args.offers)
        print("\n=== Amazon Pipeline Summary ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        return

    if args.once_temu:
        logger.info("One-shot Temu-only execution")
        stats = run_temu_only(limit=args.limit, offers=args.offers)
        print("\n=== Temu Pipeline Summary ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        return

    # 默认: 启动常驻调度器
    logger.info("Starting scheduler daemon...")
    run_scheduler(block=True)


if __name__ == "__main__":
    main()
