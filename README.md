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

## Limitations

This MVP is for low-frequency validation. It does not handle proxy pools, CAPTCHA solving, account pools, checkout, or official AliExpress API access.

## Manual Validation

After logging in, run:

```bash
python -m ali_mvp scrape --keyword "women dress" --max-items 20
```

If no products are extracted, open the browser window and check for region selection, CAPTCHA, cookie banners, or page layout changes.
