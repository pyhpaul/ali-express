# AliExpress DrissionPage MVP

Local MVP for validating AliExpress product-selection logic without an AliExpress API key.

## Setup

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Login

Open AliExpress in the browser profile used by DrissionPage and log in manually before scraping.
By default the MVP stores that profile in `.browser-profile` and uses local port `9333`, avoiding conflicts with other Chrome debugging sessions.

## Usage

```bash
python -m ali_mvp scrape --keyword "women dress" --max-items 80
python -m ali_mvp scrape --url "https://www.aliexpress.com/..." --max-items 80
python -m ali_mvp scrape --category-url "https://www.aliexpress.com/category/100003109/women-clothing.html" --max-items 80
```

Optional detail-page rating enrichment:

```bash
python -m ali_mvp scrape --keyword "women dress" --max-items 20 --enrich-detail-rating --detail-limit 5
```

Outputs:

- `data/<keyword-slug>/<YYYYMMDD_HHMMSS>/products.csv`
- `data/<keyword-slug>/<YYYYMMDD_HHMMSS>/category_rank.csv`

For example, `--keyword "women dress"` writes to:

```text
data/women-dress/20260508_224530/products.csv
data/women-dress/20260508_224530/category_rank.csv
```

URL-based runs are grouped under `data/url/<YYYYMMDD_HHMMSS>/`.

Category URL runs are grouped by the category slug when the URL exposes one:

```text
data/category-women-clothing/20260508_224530/products.csv
data/category-women-clothing/20260508_224530/category_rank.csv
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
- `product_url`: product detail URL.
- `image_url`: primary image URL.
- `scraped_at`: UTC scrape timestamp.

Code locations:

- Schema/dataclass: `ali_mvp/scoring.py` -> `ProductRecord`
- CSV columns: `ali_mvp/output.py` -> `PRODUCT_FIELDS`
- CSV writer: `ali_mvp/output.py` -> `write_products_csv()`
- Raw browser extraction: `ali_mvp/browser.py` -> `PRODUCT_SCRIPT`
- Raw-to-record normalization: `ali_mvp/extractor.py` -> `normalize_products()`
- Output path and write call: `ali_mvp/cli.py` -> `run_scrape()`

### `category_rank.csv`

Purpose: source-level summary table. One row summarizes one scrape source, such as one keyword or one category URL. Use this file to compare whether a keyword/category is worth deeper analysis.

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

## Limitations

This MVP is for low-frequency validation. It does not handle proxy pools, CAPTCHA solving, account pools, checkout, or official AliExpress API access.

## Manual Validation

After logging in, run:

```bash
python -m ali_mvp scrape --keyword "women dress" --max-items 20
```

If no products are extracted, open the browser window and check for region selection, CAPTCHA, cookie banners, or page layout changes.
