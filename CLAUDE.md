# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the arbitration pipeline (MVP: uses mock data, no credentials needed)
python main.py --limit 5 --offers 3

# Run with specific options
python main.py --platforms amazon               # single platform
python main.py --min-margin 0.30 --ship-mode air
python main.py --limit 10 --offers 5

# Production run (single shot, USE_MOCK_DATA=false)
python main.py --once --limit 100 --offers 10
python scheduler.py --once --platforms amazon --limit 100

# Launch scheduler daemon (background, cron-driven)
python scheduler.py                    # or: python main.py --schedule
python scheduler.py --once-amazon      # one-shot Amazon only
python scheduler.py --once-temu        # one-shot Temu only

# Streamlit dashboard
streamlit run ui/dashboard.py

# Run all tests
pytest tests -q

# Run a single test
pytest tests/test_profit.py::test_profit_basic -q
```

## Architecture

A multi-stage arbitrage pipeline: **scrape → match → verify → calculate → store**.

### Data flow

1. **Scrapers** (`scrapers/`) — Fetch bestseller products from Amazon (Playwright) and Temu (XHR-replay, TBD). Both inherit from `BaseScraper` which handles rate-limiting, UA rotation, retry via tenacity, proxy rotation, anti-detection (playwright-stealth + anti-webdriver injection), CAPTCHA detection, and human behavior simulation (scroll, hover). The unified output is `ScrapedProduct` (a Pydantic model). When `USE_MOCK_DATA=true` (default), scrapers return hardcoded seed data — no network calls needed. When live, `AmazonScraper` crawls 15+ categories across multiple pages with robust multi-selector fallback.

2. **Matchers** (`matchers/`) — Three stages:
   - `AlibabaMatcher` searches 1688 for supplier offers by keyword. Mock mode generates deterministic fake offers keyed by the search term hash.
   - `TextMatcher` scores title similarity. Default: character n-gram + Jaccard similarity (no model needed). Opt-in: `USE_EMBEDDINGS=true` switches to `sentence-transformers`.
   - `LLMJudge` makes the final same-product decision. Provider priority: Anthropic → OpenAI → heuristic (uses similarity ≥ 0.25 threshold as fallback). Returns `JudgeResult` with `same_product` boolean.

3. **Calculators** (`calculators/`) — `compute_profit()` chains: supplier price × CNY→USD rate → FBA fee estimate (piecewise by weight) → logistics cost (air/sea × kg) → referral fee (15% of sell price) → final margin. Returns a `ProfitBreakdown` dataclass.

4. **Storage** (`storage/`) — SQLAlchemy + SQLite with three tables: `source_products`, `matched_suppliers`, `arbitrage_opportunities`. `Database.session()` is a context manager that auto-commits on success and rolls back on exception. Tables are auto-created on first `get_db()` call.

5. **Pipeline** (`pipeline/`) — `ArbitragePipeline.run()` orchestrates the full flow: scrape → persist source → search 1688 → filter by similarity → LLM judge → compute profit → filter by min_margin → store opportunity. All in a single DB transaction.

6. **UI** (`ui/dashboard.py`) — Streamlit dashboard with sidebar controls for re-running the pipeline and three tabs (opportunities, sources, suppliers) backed by live DB queries with pandas DataFrames.

### Configuration

`config/settings.py` — All config via `Settings` dataclass populated from env vars (loaded by `python-dotenv` from `.env`). Instance is `settings` singleton. Key env vars: `USE_MOCK_DATA` (default `true`), `USE_STEALTH` (default `true`), `DATABASE_URL`, `LOG_LEVEL`, `PROXY_FILE`, `SCHEDULE_ENABLED`, `SCHEDULE_CRON`.

`config/proxy.py` — `ProxyPool` singleton manages proxy rotation with multiple strategies (round-robin, random, lowest-latency). Supports HTTP/HTTPS/SOCKS5 proxies from env vars or file. Auto-validates on first load, auto-disables after 3 consecutive failures. Called via `get_proxy_pool()` or `BaseScraper._resolve_proxy()`.

`scheduler.py` — APScheduler-based daemon with 3 cron jobs: `full_pipeline` (daily), `amazon_scrape` (every 6h), `temu_scrape` (every 12h). Configurable via `SCHEDULE_CRON_FULL`, `SCHEDULE_CRON_AMAZON`, `SCHEDULE_CRON_TEMU` env vars. Also supports `--once` / `--once-amazon` / `--once-temu` for one-shot runs.

### Key design decisions

- **Mock-first**: `USE_MOCK_DATA=true` by default. Every layer (scrapers, matchers, LLM judge) has a mock/fallback path, so the full pipeline runs with zero credentials.
- **Fallback chain**: Each layer tries the "real" implementation first, catches exceptions, and falls back to mock/deterministic behavior. The pipeline never crashes on missing external services.
- **No async**: The pipeline is synchronous throughout (httpx sync client, no asyncio). Async is a deliberate future TODO (Celery/RQ).
- **DB is local**: Default `sqlite:///./data/arbitrage.db`. Single-file, zero-config.
- **Weight estimation**: Products carry an estimated `weight_kg` field. Mock data has hardcoded values; real scrapers use category + price heuristics. Key input to both FBA and logistics cost calculations.
- **Scheduler is separate**: APScheduler runs as a background daemon, not baked into the pipeline. This keeps the pipeline callable both from CLI and scheduler.
- **Production mode**: Set `USE_MOCK_DATA=false` to enable real scraping. Requires Playwright browsers installed (`playwright install chromium`) and optionally proxy credentials. The scrapers still fall back to mock on failure — they never crash the pipeline.
