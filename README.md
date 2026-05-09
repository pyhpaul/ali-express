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
python -m ali_mvp scrape --keyword "women dress" --max-items 80 --pages 2
python -m ali_mvp scrape --url "https://www.aliexpress.com/..." --max-items 80
python -m ali_mvp scrape --category-url "https://www.aliexpress.com/category/100003109/women-clothing.html" --max-items 80
```

Pagination semantics:

- `--max-items` is the total number of products requested for the run.
- `--pages` is an optional maximum page limit.
- If `--pages` is omitted, the scraper auto-advances until `--max-items` is reached or no next page is available.
- If you only want the first listing page, pass `--pages 1`.

Optional detail-page enrichment:

```bash
python -m ali_mvp scrape --keyword "women dress" --max-items 20 --enrich-detail
```

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
