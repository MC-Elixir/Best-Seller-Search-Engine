# Best-Seller-Search-Engine

A cross-platform arbitrage discovery system. 抓取 Amazon / Temu 的热销商品，
在 1688 匹配同款货源，估算 FBA + 头程 + 佣金后给出利润率，筛出可套利商品。

## 目录结构

```
config/       # API keys、平台参数
scrapers/     # Amazon / Temu 采集（Playwright + httpx）
matchers/     # 1688 搜索、文本相似度、LLM 同款判断
calculators/  # 利润率、FBA 费、头程物流
storage/      # SQLAlchemy + SQLite
pipeline/     # 主流程编排
ui/           # Streamlit 面板
main.py       # CLI 入口
tests/        # pytest
```

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env   # 可选：填入 1688 / LLM API key

# MVP 默认 USE_MOCK_DATA=true，使用内置种子数据，无需任何外部凭证
python main.py --limit 5 --offers 3

# 可视化面板
streamlit run ui/dashboard.py
```

## MVP 说明

- **采集层**：`USE_MOCK_DATA=true` 时返回内置样例；关闭后 Amazon 使用 Playwright
  抓取 Best Sellers，Temu 真实接口位置已预留 (`_fetch_real`)。
- **匹配层**：1688 未配置 key 时走 deterministic mock；文本相似度默认
  字符 n-gram + Jaccard，配置 `USE_EMBEDDINGS=true` 可切 sentence-transformers；
  LLM 优先使用 Anthropic，其次 OpenAI，否则退回启发式。
- **计算层**：FBA 分段近似、头程按 kg 单价估算、利润率 = (售价 - 成本 - FBA
  - 头程 - 佣金) / 售价。
- **存储层**：SQLite 自动建表，三张表：source_products / matched_suppliers /
  arbitrage_opportunities。

## 测试

```bash
pytest tests -q
```

## 后续 TODO

- 接入真实 1688 图搜 / 关键词搜索签名
- 接入 Temu XHR 接口重放
- 引入 deep-translator 补齐中英文商品名互译
- 代理池 & 风控
- Celery / RQ 异步化
