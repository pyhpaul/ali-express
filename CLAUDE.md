# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AliExpress product scraper MVP using DrissionPage for browser automation. Validates product-selection logic without an official API key. Includes blacklist filtering, LLM-based review, proxy pool rotation, and session risk management.

## Tech Stack

- **Language**: Python 3.10+
- **Browser automation**: DrissionPage (Chromium-based)
- **Testing**: pytest
- **LLM integration**: OpenAI-compatible API via `urllib` (no SDK dependency)

## Commands

```bash
# Setup
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# Run tests
python -m pytest tests/ -q
python -m pytest tests/test_filtering.py tests/test_cli.py -q  # single module

# Scrape
python -m ali_mvp scrape --keyword "women dress" --max-items 80
python -m ali_mvp scrape --keyword "women dress" --max-items 80 --enrich-detail --blacklist-file rules/product_blacklist.json

# Resume blocked run
python -m ali_mvp resume --run-dir data/<keyword>/<timestamp>

# LLM review
python -m ali_mvp llm-review --run-dir data/<keyword>/<timestamp>

# Postprocess (translate + HTML report)
python -m ali_mvp postprocess --run-dir data/<keyword>/<timestamp>

# Page probe (pagination diagnostics)
python -m ali_mvp page-probe --keyword "women dress" --pages 2 --per-page-raw-limit 5
```

## Architecture

### Pipeline Flow

```
CLI (cli.py) → ScrapeRunner (scrape_runner.py) → Browser (browser.py)
                     ↓                                      ↓
              Filtering (filtering.py)          Extractor (extractor.py)
                     ↓                                      ↓
              Output (output.py) ← Scoring (scoring.py) ←┘
                     ↓
              LLM Review (llm_review.py) → Reporting (llm_reporting.py)
```

### Key Modules

| Module | Responsibility |
|--------|----------------|
| `cli.py` | Argparse CLI, subcommands (`scrape`, `resume`, `postprocess`, `llm-review`, `page-probe`) |
| `scrape_runner.py` | Orchestrates full scrape flow: open browser → collect listings → filter → enrich details → write outputs |
| `browser.py` | DrissionPage browser control, JS injection for product extraction, pagination, detail page visits |
| `extractor.py` | Normalizes raw browser dicts into `ProductRecord` dataclass |
| `filtering.py` | Blacklist engine: `FilterGroup` with pre/post reject terms, two-stage filtering (listing title → detail post-enrich) |
| `scoring.py` | Core data models (`ProductRecord`, `RankRecord`), count/float parsing, heat score aggregation |
| `output.py` | CSV writers for all output files, field definitions |
| `run_state.py` | `RunManifest` (run config), `RunState` (progress tracking), `RunStateStore` (JSON persistence) |
| `session_guard.py` | Pre-scrape session validation: captcha detection, login check, phone verification, warm-up |
| `proxy_pool.py` | Proxy rotation with cooldown, health tracking, v2rayN sidecar integration |
| `llm_client.py` | LLM config resolution (profile → env → CLI), OpenAI-compatible HTTP client |
| `llm_review.py` | LLM-based product review: risk tagging, keep/drop decisions, caching by input hash |

### Data Flow

1. **Listing collection**: `browser.py` injects `PRODUCT_SCRIPT` JS to extract raw product cards from search results
2. **Normalization**: `extractor.py` converts raw dicts → `ProductRecord` with parsed counts/ratings
3. **Filtering**: Two stages — `prefilter_listing_products()` on titles, `filter_products()` after detail enrichment
4. **Detail enrichment**: Optional `--enrich-detail` visits each product page for shop name, shipping, attributes, description
5. **Output**: `products.csv` (accepted), `products_filter_audit.csv` (all decisions), `products_review.csv` (audit context), `category_rank.csv` (source summary)
6. **LLM review**: Optional second pass using `products_review.csv` → risk tags + keep/drop → `products_llm_review.csv`

### State Persistence

Run state is persisted to `run_state.json` in each run directory. Enables `resume` after blocks/captchas. Key fields: `status`, `current_listing_page`, `seen_product_keys`, `pending_detail_queue`, `session_risk_level`, `cooldown_until`.

## Output Structure

```
data/<keyword-slug>/<YYYYMMDD_HHMMSS>/
├── products.csv              # Accepted products only
├── products_filter_audit.csv # All filter decisions with stage/reasons
├── products_review.csv       # Review context for accepted + rejected
├── category_rank.csv         # Source-level heat score summary
├── run_manifest.json         # Run configuration snapshot
├── run_state.json            # Progress and session state
├── run_summary.json          # Final counts
├── products_llm_review.csv   # LLM review results (if --llm-review)
├── products_final_keep.csv   # LLM keep decisions
├── products_final_drop.csv   # LLM drop decisions
└── products_llm_report.html  # LLM review HTML report
```

## LLM Configuration

Resolution order: CLI args → `ALI_MVP_LLM_*` env vars → selected profile → `OPENAI_*` env vars.

Profiles stored in `~/.config/llm-profiles/profiles.toml` (see `config/llm-profiles.example.toml`).

## Key Design Decisions

- **No Selenium/Playwright**: DrissionPage connects to existing Chrome via CDP, reuses manual login sessions
- **Browser profile persistence**: `.browser-profile/` stores login state across runs
- **Two-stage filtering**: Listing-title prefilter avoids unnecessary detail page visits for obvious blacklist hits
- **Proxy cooldown**: Blocked proxies enter cooldown period, persisted to `_proxy_health.json`
- **Session risk tracking**: Captcha/login/phone-verify states tracked across runs in `run_state.json`
- **LLM caching**: Input hash prevents re-reviewing unchanged rows across runs
