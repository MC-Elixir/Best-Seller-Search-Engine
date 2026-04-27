"""代理池：验证、轮换、健康检查。

支持:
- 环境变量配置静态代理 (HTTP_PROXY / HTTPS_PROXY)
- 文件加载代理列表 (每行一个: protocol://user:pass@host:port)
- 轮换策略: round-robin / random / lowest-latency
- 自动健康检查: 启动时过滤不可用代理
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


# ── 代理对象 ──────────────────────────────────────────────
@dataclass
class Proxy:
    url: str
    protocol: str = "http"        # http / https / socks5
    host: str = ""
    port: int = 0
    username: str | None = None
    password: str | None = None
    last_used: float = 0.0
    fail_count: int = 0
    latency_ms: float = 0.0
    enabled: bool = True

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        self.protocol = parsed.scheme or "http"
        self.host = parsed.hostname or ""
        self.port = parsed.port or (1080 if self.protocol == "socks5" else 8888)
        self.username = parsed.username
        self.password = parsed.password

    @property
    def httpx_format(self) -> str:
        """返回 httpx 可用的代理 URL 格式 (http://host:port)"""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"

    def record_success(self, latency: float = 0.0) -> None:
        self.last_used = time.time()
        self.latency_ms = latency
        self.fail_count = max(0, self.fail_count - 1)

    def record_failure(self) -> None:
        self.fail_count += 1
        if self.fail_count >= 3:
            self.enabled = False


# ── 选择策略 ──────────────────────────────────────────────
class RotationStrategy(Protocol):
    def select(self, proxies: list[Proxy]) -> Proxy | None: ...


class RoundRobinStrategy:
    def __init__(self) -> None:
        self._idx = 0

    def select(self, proxies: list[Proxy]) -> Proxy | None:
        active = [p for p in proxies if p.enabled]
        if not active:
            return None
        self._idx = (self._idx + 1) % len(active)
        return active[self._idx]


class RandomStrategy:
    def select(self, proxies: list[Proxy]) -> Proxy | None:
        active = [p for p in proxies if p.enabled]
        if not active:
            return None
        return random.choice(active)


class LowestLatencyStrategy:
    def select(self, proxies: list[Proxy]) -> Proxy | None:
        active = [p for p in proxies if p.enabled and p.latency_ms > 0]
        if not active:
            active = [p for p in proxies if p.enabled]
        if not active:
            return None
        active.sort(key=lambda p: p.latency_ms)
        return active[0]


# ── 代理池 ────────────────────────────────────────────────
@dataclass
class ProxyPool:
    proxies: list[Proxy] = field(default_factory=list)
    strategy: RotationStrategy = field(default_factory=RandomStrategy)

    @property
    def active_count(self) -> int:
        return sum(1 for p in self.proxies if p.enabled)

    def add(self, proxy_url: str) -> None:
        if proxy_url.strip():
            self.proxies.append(Proxy(url=proxy_url.strip()))

    def load_from_env(self) -> None:
        for key in ("HTTP_PROXY", "HTTPS_PROXY"):
            url = getattr(settings, key.lower(), "") or ""
            if url:
                self.add(url)

    def load_from_file(self, path: str | Path) -> None:
        filepath = Path(path)
        if not filepath.exists():
            logger.warning("Proxy file not found: %s", filepath)
            return
        lines = filepath.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                self.add(line)

    def get(self) -> Proxy | None:
        return self.strategy.select(self.proxies)

    def validate_all(self, timeout: float = 8.0) -> int:
        """验证所有代理可用性，返回可用数量。

        使用 httpbin 或 Amazon 做连通性测试。
        """
        test_urls = [
            "https://httpbin.org/ip",
            "https://www.amazon.com",
        ]
        valid = 0
        for proxy in self.proxies:
            try:
                start = time.monotonic()
                with httpx.Client(proxy=proxy.httpx_format, timeout=timeout) as client:
                    resp = client.get(test_urls[0])
                    if resp.status_code == 200:
                        proxy.record_success((time.monotonic() - start) * 1000)
                        valid += 1
                    else:
                        proxy.record_failure()
            except Exception as e:
                logger.debug("Proxy %s validation failed: %s", proxy.host, e)
                proxy.record_failure()
        logger.info("Proxy validation: %d/%d available", valid, len(self.proxies))
        return valid


# ── 全局单例 ──────────────────────────────────────────────
_pool: ProxyPool | None = None


def get_proxy_pool() -> ProxyPool:
    global _pool
    if _pool is None:
        _pool = ProxyPool()
        _pool.load_from_env()
        proxy_file = settings.proxy_file
        if proxy_file:
            _pool.load_from_file(proxy_file)
        if _pool.proxies:
            _pool.validate_all()
    return _pool
