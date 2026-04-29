"""Runtime configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class PlatformConfig:
    amazon_bestseller_url: str = "https://www.amazon.com/Best-Sellers/zgbs"
    temu_home_url: str = "https://www.temu.com"
    request_timeout: int = 30
    max_retries: int = 3
    min_delay_sec: float = 1.0
    max_delay_sec: float = 3.0


@dataclass
class ProfitConfig:
    # 默认汇率（人民币 -> 美元）
    cny_to_usd: float = 0.14
    # Amazon referral fee 大类目常见 15%
    referral_fee_rate: float = 0.15
    # 头程物流：空运每kg价格（人民币）
    air_freight_cny_per_kg: float = 40.0
    # 头程物流：海运每kg价格（人民币）
    sea_freight_cny_per_kg: float = 15.0
    # 目标最低利润率
    min_margin: float = 0.25


@dataclass
class Settings:
    alibaba_app_key: str = field(default_factory=lambda: os.getenv("ALIBABA_APP_KEY", ""))
    alibaba_app_secret: str = field(default_factory=lambda: os.getenv("ALIBABA_APP_SECRET", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))

    http_proxy: str = field(default_factory=lambda: os.getenv("HTTP_PROXY", ""))
    https_proxy: str = field(default_factory=lambda: os.getenv("HTTPS_PROXY", ""))
    proxy_file: str = field(default_factory=lambda: os.getenv("PROXY_FILE", ""))  # 代理列表文件路径

    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'arbitrage.db'}")
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    use_mock_data: bool = field(default_factory=lambda: _env_bool("USE_MOCK_DATA", True))
    use_stealth: bool = field(default_factory=lambda: _env_bool("USE_STEALTH", True))  # playwright-stealth

    # 调度器配置
    schedule_enabled: bool = field(default_factory=lambda: _env_bool("SCHEDULE_ENABLED", False))
    schedule_cron: str = field(default_factory=lambda: os.getenv("SCHEDULE_CRON", "0 8 * * *"))  # 默认每天早8点

    platform: PlatformConfig = field(default_factory=PlatformConfig)
    profit: ProfitConfig = field(default_factory=ProfitConfig)

    @property
    def proxies(self) -> dict[str, str]:
        p: dict[str, str] = {}
        if self.http_proxy:
            p["http://"] = self.http_proxy
        if self.https_proxy:
            p["https://"] = self.https_proxy
        return p

    @property
    def has_llm(self) -> bool:
        return bool(self.openai_api_key or self.anthropic_api_key)


settings = Settings()
