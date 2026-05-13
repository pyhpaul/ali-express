# AliExpress DrissionPage MVP

Local MVP for validating AliExpress product-selection logic without an AliExpress API key.

## Setup

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## LLM Review Setup

Configure the OpenAI-compatible endpoint in a local project `.env` file:

```dotenv
ALI_MVP_LLM_BASE_URL=https://example.test/v1
ALI_MVP_LLM_API_KEY=sk-example
ALI_MVP_LLM_MODEL=gpt-4.1-mini
```

CLI flags can override `.env` for a single run:

- `--llm-base-url`
- `--llm-api-key`
- `--llm-model`

## Login

Open AliExpress in the browser profile used by DrissionPage and log in manually before scraping.
By default the MVP stores that profile in `.browser-profile` and uses local port `9333`, avoiding conflicts with other Chrome debugging sessions.

## Usage

```bash
python -m ali_mvp scrape --keyword "women dress" --max-items 80
python -m ali_mvp scrape --keyword "women dress" --max-items 80 --pages 2
python -m ali_mvp scrape --url "https://www.aliexpress.com/..." --max-items 80
python -m ali_mvp scrape --category-url "https://www.aliexpress.com/category/100003109/women-clothing.html" --max-items 80
```

Browser hardening:

- `--browser-hardening off|minimal`
- default: `minimal`

Proxy and browser identity:

- `--proxy http://127.0.0.1:8080`
- `--proxy-file proxies.txt`
- `--max-blocks-per-proxy 2`
- `--user-agent "ua-fixed"`
- `--accept-language "en-US,en;q=0.9"`

Recommended default for a single-account workflow:

- keep one logged-in profile stable
- keep one exit path stable
- keep one stable browser major version / UA pair per account
- do not enable proxy-pool rotation unless you explicitly need a fallback path
- if you do not pass `--proxy` or `--proxy-file`, the default `--proxy-provider manual` mode runs without a proxy pool
- treat `--proxy-provider v2rayn` as an opt-in fallback mode, not the default path

### v2rayN sidecar proxy pool

Use the local v2rayN installation as a proxy source:

```bash
python -m ali_mvp scrape \
  --keyword "Home appliance accessories" \
  --proxy-provider v2rayn \
  --v2rayn-dir "C:\Users\lxy\Desktop\v2rayN-windows-64" \
  --enrich-detail \
  --user-data-dir .browser-profile
```

Behavior in this phase:

- reads nodes from `guiConfigs/guiNDB.db -> ProfileItem`
- generates per-node sidecar `xray` configs under `<run_dir>/proxy_runtime`
- probes each local socks5 endpoint before opening the browser
- picks one healthy endpoint for the current run
- attempts to restore the last persisted proxy selection on `resume` when that proxy is still eligible
- proxy health cooldown is fallback memory, not a periodic rotation scheduler
- cleans sidecar processes on exit

Current limitations:

- no mid-run live proxy hot-swap inside one browser session
- no automatic CAPTCHA solving
- no adaptive long-term health scoring beyond startup probe and per-run rotation

Pagination semantics:

- `--max-items` is the total number of products requested for the run.
- `--pages` is an optional maximum page limit.
- If `--pages` is omitted, the scraper auto-advances until `--max-items` is reached or no next page is available.
- If you only want the first listing page, pass `--pages 1`.

Optional detail-page enrichment:

```bash
python -m ali_mvp scrape --keyword "women dress" --max-items 20 --enrich-detail
```

Optional product blacklist filtering:

```bash
python -m ali_mvp scrape --keyword "Home appliance accessories" --blacklist-file rules/product_blacklist.json
python -m ali_mvp scrape --keyword "Home appliance accessories" --blacklist-file rules/product_blacklist.json --reject-keyword sensor --reject-keyword relay
```

Run a standalone LLM review for an existing run:

```bash
python -m ali_mvp llm-review --run-dir data/home-appliance-accessories/20260513_151040
python -m ali_mvp llm-review --run-dir data/home-appliance-accessories/20260513_151040 --llm-max-items 5
```

Chain LLM review after scrape:

```bash
python -m ali_mvp scrape --keyword "Home appliance accessories" --max-items 20 --llm-review
python -m ali_mvp scrape --keyword "Home appliance accessories" --max-items 20 --llm-review --llm-force
```

Resume a blocked run:

```bash
python -m ali_mvp resume --run-dir data/home-appliance-accessories/20260511_120000
```

Retry only unfinished details:

```bash
python -m ali_mvp resume --run-dir data/home-appliance-accessories/20260511_120000 --details-only
```

Resume with temporary proxy or browser identity override:

```bash
python -m ali_mvp resume --run-dir data/home-appliance-accessories/20260511_120000 --proxy http://127.0.0.1:8080 --user-agent "ua-fixed" --accept-language "en-US,en;q=0.9"
```

Notes for `resume`:

- `resume` attempts to restore the last persisted proxy selection when that proxy is still eligible after health / cooldown filtering
- if the persisted proxy is no longer eligible, `resume` falls back to another eligible proxy
- proxy overrides apply when a new browser session is opened for `resume`
- `resume` does not do live proxy swap inside one browser session after the browser is already open

Detail enrichment adds these columns to `products.csv`:

- `entry_type`
- `search_card_url`
- `is_promoted`
- `promo_channel`
- `promotion_text`
- `promo_landing_url`
- `shop_name`
- `shipping_text`
- `detail_rating`
- `detail_review_count`
- `breadcrumb`
- `attributes_text`
- `description_text`

Outputs:

- `data/<keyword-slug>/<YYYYMMDD_HHMMSS>/products.csv`
- `data/<keyword-slug>/<YYYYMMDD_HHMMSS>/products_filter_audit.csv`
- `data/<keyword-slug>/<YYYYMMDD_HHMMSS>/products_review.csv`
- `data/<keyword-slug>/<YYYYMMDD_HHMMSS>/category_rank.csv`
- `data/<keyword-slug>/<YYYYMMDD_HHMMSS>/run_manifest.json`
- `data/<keyword-slug>/<YYYYMMDD_HHMMSS>/run_state.json`
- `data/<keyword-slug>/<YYYYMMDD_HHMMSS>/run_summary.json`

For example, `--keyword "women dress"` writes to:

```text
data/women-dress/20260508_224530/products.csv
data/women-dress/20260508_224530/products_filter_audit.csv
data/women-dress/20260508_224530/products_review.csv
data/women-dress/20260508_224530/category_rank.csv
```

URL-based runs are grouped under `data/url/<YYYYMMDD_HHMMSS>/`.

Category URL runs are grouped by the category slug when the URL exposes one:

```text
data/category-women-clothing/20260508_224530/products.csv
data/category-women-clothing/20260508_224530/products_filter_audit.csv
data/category-women-clothing/20260508_224530/products_review.csv
data/category-women-clothing/20260508_224530/category_rank.csv
```

Postprocess outputs:

```bash
python -m ali_mvp postprocess --run-dir data/home-appliance-accessories/20260511_120000
```

Use MyMemory for free zh translation:

```bash
python -m ali_mvp postprocess --run-dir data/home-appliance-accessories/20260511_120000 --translator mymemory
```

Optional higher-quota hint for MyMemory:

```bash
python -m ali_mvp postprocess --run-dir data/home-appliance-accessories/20260511_120000 --translator mymemory --translator-email you@example.com
```

Additional outputs:

- `products_zh.csv`
- `products_filter_audit_zh.csv`
- `review_only.csv`
- `products_report.html`
- `translation_cache.json`

LLM review outputs:

- `products_llm_review.csv`
- `products_final_keep.csv`
- `products_final_drop.csv`
- `products_llm_report.html`

LLM review behavior:

- `llm-review` reads `products_review.csv` from one existing run directory
- `scrape --llm-review` only triggers the LLM step after scrape exits with `0` or `2`
- `--llm-force` ignores reusable cached rows and re-runs all eligible rows
- `--llm-max-items` only limits the current LLM review batch for debugging

Recommended review workflow for non-technical staff:

1. Open `products_report.html`
   - Use the built-in filters to switch between:
     - `只看拒绝入库`
     - `只看建议入库`
     - specific reject reasons such as `遥控控制类` or `点火控制类`
2. Use `review_only.csv` for spreadsheet review
   - This is the compact handoff file for staff
   - Key columns:
     - `title` / `title_zh`
     - `decision_label`
     - `stage_label`
     - `review_note`
3. Use `products_zh.csv` only when more product context is needed
   - It keeps the fuller translated dataset for deeper review
4. Use `products_filter_audit_zh.csv` when blacklist hit details must be audited
   - It retains the rule-hit columns and zh labels

Blacklist filtering semantics:

- When blacklist filtering is enabled, `--max-items` means final accepted product count.
- The scraper first runs a listing-title prefilter and skips detail-page visits for obvious blacklist hits.
- Remaining products can still be rejected after detail enrichment from `title` and `attributes_text`.
- `breadcrumb` and `description_text` only create warnings.
- `products.csv` only contains accepted products.
- `products_filter_audit.csv` contains all accepted/rejected decisions that were kept for the run and adds `filter_stage`:
  - `listing_title`
  - `detail_post_enrich`
  - `accepted`

Local-first verification before any live-site validation:

```bash
python -m pytest tests/test_filtering.py tests/test_cli.py tests/test_output.py tests/test_browser.py -q
```

## Output Files and Code Map

### `products.csv`

Purpose: product-level detail table. One row is one scraped product. Use this file to inspect and filter individual products.

Columns:

- `source_type`: scrape source type, one of `keyword`, `category`, or `url`.
- `source_value`: keyword, category URL, or generic URL used for this run.
- `title`: product title.
- `price`: displayed listing price.
- `sold_count`: parsed sold/order count.
- `rating`: parsed product rating; `0.0` means the listing/detail page did not expose a reliable rating.
- `review_count`: parsed review count; currently often `0` because AliExpress listing cards do not consistently expose it.
- `product_url`: resolved product detail URL. For promo cards, this is the resolved item URL.
- `search_card_url`: original search-card URL before any promo resolution.
- `image_url`: primary image URL.
- `entry_type`: `item_card` for normal item cards, `promo_card` for `BundleDeals2 / Dollar Express` cards.
- `is_promoted`: whether the row came through a promo landing flow.
- `promo_channel`: promo channel name, such as `Dollar Express`.
- `promotion_text`: flattened promo text such as `Free shipping on 3 items | Free returns | Buy more,save more`.
- `promo_landing_url`: promo landing page URL for promo cards; empty for normal item cards.
- `shop_name`: store name from the product detail page when `--enrich-detail` is enabled.
- `shipping_text`: shipping-related text from the product detail page when available.
- `detail_rating`: rating parsed from the product detail page.
- `detail_review_count`: review count parsed from the product detail page.
- `breadcrumb`: flattened breadcrumb text from the product detail page.
- `attributes_text`: JSON string of detail-page attribute key/value pairs.
- `description_text`: cleaned plain-text product description from the detail page.
- `scraped_at`: UTC scrape timestamp.

Promo-card behavior:

- Search results may contain `Dollar Express / BundleDeals2` cards whose href is not `/item/...`.
- The scraper keeps those rows as valid search hits when the card itself carries product content.
- For promo rows, the scraper resolves the entry product's real `/item/<id>.html` URL and stores that in `product_url`.
- The scraper does not expand all products inside the promo landing page; it only follows the entry product and preserves promo metadata.

Code locations:

- Schema/dataclass: `ali_mvp/scoring.py` -> `ProductRecord`
- CSV columns: `ali_mvp/output.py` -> `PRODUCT_FIELDS`
- CSV writer: `ali_mvp/output.py` -> `write_products_csv()`
- Raw browser extraction: `ali_mvp/browser.py` -> `PRODUCT_SCRIPT`
- Raw-to-record normalization: `ali_mvp/extractor.py` -> `normalize_products()`
- Output path and write call: `ali_mvp/cli.py` -> `run_scrape()`

### `category_rank.csv`

Purpose: source-level summary table. One row summarizes one scrape source, such as one keyword or one category URL. Use this file to compare whether a keyword/category is worth deeper analysis.

This file is calculated from accepted products only when blacklist filtering is enabled.

Columns:

- `source_value`: keyword, category URL, or generic URL being summarized.
- `product_count`: number of normalized products in this run.
- `total_sold_count`: sum of `sold_count`.
- `avg_rating`: average `rating`.
- `avg_review_count`: average `review_count`.
- `heat_score`: simple ranking score for quick comparison.

Current heat score formula:

```text
heat_score = total_sold_count + total_review_count + product_count * 10 + avg_rating * 10
```

Code locations:

- Schema/dataclass: `ali_mvp/scoring.py` -> `RankRecord`
- Aggregation and formula: `ali_mvp/scoring.py` -> `aggregate_rank()` and `_build_rank()`
- CSV columns: `ali_mvp/output.py` -> `RANK_FIELDS`
- CSV writer: `ali_mvp/output.py` -> `write_rank_csv()`
- Output path and write call: `ali_mvp/cli.py` -> `run_scrape()`

### `products_filter_audit.csv`

Purpose: filtering audit table. This file records the accepted/rejected decisions kept for the current run, including rejected rows from the `listing_title` prefilter stage before detail enrichment. Because of that prefilter stage, rows do not only correspond to normalized products.

Columns:

- `source_type`: scrape source type.
- `source_value`: keyword, category URL, or generic URL used for this run.
- `title`: product title.
- `product_url`: resolved product detail URL.
- `filter_decision`: `accepted` or `rejected`.
- `filter_stage`: decision stage for the row:
  - `listing_title`
  - `detail_post_enrich`
  - `accepted`
- `reject_groups`: matched blacklist group names from strong fields.
- `reject_terms`: matched blacklist terms from strong fields.
- `reject_fields`: strong fields that triggered rejection.
- `warning_groups`: matched blacklist group names from weak fields.
- `warning_terms`: matched blacklist terms from weak fields.
- `warning_fields`: weak fields that produced warnings.

Code locations:

- Filter engine: `ali_mvp/filtering.py`
- CSV columns: `ali_mvp/output.py` -> `FILTER_AUDIT_FIELDS`
- CSV writer: `ali_mvp/output.py` -> `write_filter_audit_csv()`
- Output path and write call: `ali_mvp/cli.py` -> `run_scrape()`

### `products_review.csv`

Purpose: review-oriented table for accepted and rejected rows with enough product context to audit blacklist decisions quickly.

Columns:

- `source_type`
- `source_value`
- `title`
- `product_url`
- `image_url`
- `price`
- `search_card_url`
- `entry_type`
- `is_promoted`
- `promo_channel`
- `promotion_text`
- `shop_name`
- `shipping_text`
- `attributes_text`
- `description_text`
- `detail_status`
- `filter_decision`
- `filter_stage`
- `reject_groups`
- `reject_terms`
- `reject_fields`
- `warning_groups`
- `warning_terms`
- `warning_fields`

Code locations:

- Review row join: `ali_mvp/review.py` -> `build_review_rows()`
- CSV columns: `ali_mvp/output.py` -> `REVIEW_FIELDS`
- Output path and write call: `ali_mvp/cli.py` -> `run_scrape()`

### LLM review artifacts

Run with either:

```bash
python -m ali_mvp llm-review --run-dir data/home-appliance-accessories/20260513_151040
python -m ali_mvp scrape --keyword "Home appliance accessories" --max-items 20 --llm-review
```

Generated files:

- `products_llm_review.csv`
  - full LLM review table for all processed `products_review.csv` rows
  - keeps product context, rule-layer context, LLM decision, risk tags, summary, model, prompt version, input hash, and any row-level error
- `products_final_keep.csv`
  - subset where `llm_decision == keep`
- `products_final_drop.csv`
  - subset where `llm_decision == drop`
- `products_llm_report.html`
  - HTML review page grouped into keep / drop / error

Code locations:

- Config resolution and OpenAI-compatible client: `ali_mvp/llm_client.py`
- Review orchestration, reuse, keep/drop slicing: `ali_mvp/llm_review.py`
- HTML rendering: `ali_mvp/llm_reporting.py`
- CLI entrypoints: `ali_mvp/cli.py` -> `run_llm_review()` and `run_scrape()`

### Postprocess artifacts

`python -m ali_mvp postprocess --run-dir ...` reads the scrape outputs in one run directory and generates:

- `products_review.csv`
- `products_zh.csv`
- `products_filter_audit_zh.csv`
- `review_only.csv`
- `products_report.html`
- `translation_cache.json`

Suggested reviewer usage:

- `products_report.html`
  - visual review page
  - best for quick pass/fail inspection and reason filtering
- `review_only.csv`
  - smallest handoff file for staff
  - sorted for manual review with rejected rows first
- `products_zh.csv`
  - fuller translated product dataset
- `products_filter_audit_zh.csv`
  - full blacklist audit trail with zh labels

Translator options:

- `--translator identity|mymemory`
- `--translator-email you@example.com` for optional MyMemory `de` parameter

Code locations:

- Orchestration: `ali_mvp/postprocess.py` -> `run_postprocess_for_dir()`
- HTML rendering: `ali_mvp/reporting.py` -> `render_report_html()`
- Translation/cache: `ali_mvp/translation.py`

## Limitations

This MVP is for low-frequency validation. It now supports a minimal sequential proxy pool and fixed browser identity per run, but it still does not handle automated CAPTCHA solving, account pools, checkout, or official AliExpress API access.

Current anti-risk status:

- Done in this phase:
  - session preflight + warm-up
  - session risk persistence
  - proxy health / cooldown
  - browser identity warning
  - optional browser pacing / stealth hardening via `--browser-hardening off|minimal`
  - single-proxy or proxy-file based sequential rotation via `--proxy`, `--proxy-file`, and `--max-blocks-per-proxy`
  - fixed browser identity per run via `--user-agent` and `--accept-language`
  - preflight stops the run before scraping when AliExpress is on login, phone verification, or captcha pages
  - captcha page detection
  - manual captcha wait-and-resume flow
  - graceful detail-status fallback when captcha is not cleared
- Not done in this phase:
  - automatic slider / captcha solving
  - aggressive header / fingerprint pool rotation
  - proxy health scoring or adaptive pool management
  - fully automated recovery under sustained risk-control pressure
  - live proxy swap inside one browser session

## Manual Validation

After logging in, run:

```bash
python -m ali_mvp scrape --keyword "Home appliance accessories" --max-items 20 --enrich-detail --blacklist-file rules/product_blacklist.json --user-data-dir .browser-profile
```

If the run is blocked, clear the CAPTCHA manually in the same profile and then resume:

```bash
python -m ali_mvp resume --run-dir data/home-appliance-accessories/<timestamp>
```

If no products are extracted, open the browser window and check for region selection, CAPTCHA, cookie banners, or page layout changes.
