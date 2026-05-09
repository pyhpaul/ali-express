# Detail Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `--enrich-detail` mode that opens every final product detail page and writes selected detail fields into `products.csv`, while removing the old rating-only detail flags.

**Architecture:** Keep list-page collection and pagination unchanged, then run a second sequential enrichment pass over the final capped product set. Extend the raw product dictionaries first, then update normalization, dataclasses, CSV output, and CLI together so the new fields flow through one consistent path.

**Tech Stack:** Python 3.13, argparse, pytest, DrissionPage, csv, dataclasses

---

### Task 1: Replace the old rating-only CLI flags with `--enrich-detail`

**Files:**
- Modify: `ali_mvp/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI tests for the new flag and removed old flags**

```python
def test_scrape_parser_accepts_enrich_detail_option():
    parser = build_parser()
    args = parser.parse_args(["scrape", "--keyword", "women dress", "--enrich-detail"])

    assert args.enrich_detail is True


def test_scrape_parser_rejects_removed_detail_rating_flags():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["scrape", "--keyword", "women dress", "--enrich-detail-rating"])

    with pytest.raises(SystemExit):
        parser.parse_args(["scrape", "--keyword", "women dress", "--detail-limit", "3"])
```

- [ ] **Step 2: Run the focused CLI tests to verify they fail for the expected reason**

Run: `python -m pytest tests/test_cli.py::test_scrape_parser_accepts_enrich_detail_option tests/test_cli.py::test_scrape_parser_rejects_removed_detail_rating_flags -q`

Expected: FAIL because `--enrich-detail` does not exist yet and the old flags still parse

- [ ] **Step 3: Update the existing run-scrape validation test to stop referencing removed flags**

```python
def test_run_scrape_rejects_non_positive_pages():
    from ali_mvp import cli

    args = argparse.Namespace(
        keyword="women dress",
        url=None,
        category_url=None,
        max_items=20,
        output_dir="data",
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        pages=0,
    )

    with pytest.raises(SystemExit, match="--pages must be greater than 0"):
        cli.run_scrape(args)
```

- [ ] **Step 4: Run the page-validation test to make sure it still passes independently**

Run: `python -m pytest tests/test_cli.py::test_run_scrape_rejects_non_positive_pages -q`

Expected: PASS

- [ ] **Step 5: Write the minimal CLI implementation**

```python
scrape.add_argument(
    "--enrich-detail",
    action="store_true",
    help="Visit each final product detail page and enrich products.csv with detail fields.",
)
```

```python
raw_products = collect_raw_products(
    url,
    args.max_items,
    user_data_dir=args.user_data_dir,
    port=args.port,
    enrich_detail=args.enrich_detail,
    pages=args.pages,
)
```

- [ ] **Step 6: Run the full CLI test file to verify it passes**

Run: `python -m pytest tests/test_cli.py -q`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add ali_mvp/cli.py tests/test_cli.py
git commit -m "refactor: replace rating-only detail flags"
```

### Task 2: Extend product schemas and CSV output for detail fields

**Files:**
- Modify: `ali_mvp/scoring.py`
- Modify: `ali_mvp/output.py`
- Modify: `ali_mvp/extractor.py`
- Test: `tests/test_output.py`

- [ ] **Step 1: Write the failing CSV-output test for the new detail columns**

```python
def test_write_products_csv_includes_detail_enrichment_fields(tmp_path):
    path = tmp_path / "products.csv"
    products = [
        ProductRecord(
            source_type="keyword",
            source_value="women dress",
            title="Dress",
            price="$12.50",
            sold_count=100,
            rating=4.8,
            review_count=20,
            product_url="https://example.test/item",
            image_url="https://example.test/item.jpg",
            shop_name="Example Store",
            shipping_text="Free shipping",
            detail_rating=4.9,
            detail_review_count=25,
            breadcrumb="Home > Dresses",
            attributes_text='{\"Material\":\"Cotton\"}',
            description_text="Long sleeve dress",
            scraped_at="2026-05-08T00:00:00Z",
        )
    ]

    write_products_csv(path, products)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["shop_name"] == "Example Store"
    assert rows[0]["attributes_text"] == '{"Material":"Cotton"}'
    assert rows[0]["description_text"] == "Long sleeve dress"
```

- [ ] **Step 2: Run the focused CSV-output test to verify it fails**

Run: `python -m pytest tests/test_output.py::test_write_products_csv_includes_detail_enrichment_fields -q`

Expected: FAIL because `ProductRecord` and `PRODUCT_FIELDS` do not include the new fields yet

- [ ] **Step 3: Add the detail fields to the product dataclass and CSV field order**

```python
@dataclass(frozen=True)
class ProductRecord:
    source_type: str
    source_value: str
    title: str
    price: str
    sold_count: int
    rating: float
    review_count: int
    product_url: str
    image_url: str
    shop_name: str
    shipping_text: str
    detail_rating: float
    detail_review_count: int
    breadcrumb: str
    attributes_text: str
    description_text: str
    scraped_at: str
```

```python
PRODUCT_FIELDS = [
    "source_type",
    "source_value",
    "title",
    "price",
    "sold_count",
    "rating",
    "review_count",
    "product_url",
    "image_url",
    "shop_name",
    "shipping_text",
    "detail_rating",
    "detail_review_count",
    "breadcrumb",
    "attributes_text",
    "description_text",
    "scraped_at",
]
```

- [ ] **Step 4: Extend normalization so missing detail fields become empty strings or zeroes**

```python
        products.append(
            ProductRecord(
                source_type=source_type,
                source_value=source_value,
                title=title,
                price=_clean_text(raw.get("price")),
                sold_count=parse_count(_clean_text(raw.get("soldText"))),
                rating=parse_float(_clean_text(raw.get("ratingText"))),
                review_count=parse_count(_clean_text(raw.get("reviewText"))),
                product_url=url,
                image_url=_normalize_url(_clean_text(raw.get("image"))),
                shop_name=_clean_text(raw.get("shopName")),
                shipping_text=_clean_text(raw.get("shippingText")),
                detail_rating=parse_float(_clean_text(raw.get("detailRatingText"))),
                detail_review_count=parse_count(_clean_text(raw.get("detailReviewText"))),
                breadcrumb=_clean_text(raw.get("breadcrumb")),
                attributes_text=_clean_text(raw.get("attributesText")),
                description_text=_clean_text(raw.get("descriptionText")),
                scraped_at=scraped_at,
            )
        )
```

- [ ] **Step 5: Run the focused CSV-output test and full output tests to verify they pass**

Run: `python -m pytest tests/test_output.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ali_mvp/scoring.py ali_mvp/output.py ali_mvp/extractor.py tests/test_output.py
git commit -m "feat: add detail enrichment product fields"
```

### Task 3: Add sequential detail-page enrichment for every final product

**Files:**
- Modify: `ali_mvp/browser.py`
- Test: `tests/test_browser.py`

- [ ] **Step 1: Write the failing browser tests for full detail enrichment**

```python
def test_finalize_products_enriches_every_final_product_when_enabled(monkeypatch):
    class FakePage:
        url = "https://www.aliexpress.com/w/wholesale-women-dress.html"

    raw = [
        {"url": "https://www.aliexpress.com/item/1.html"},
        {"url": "https://www.aliexpress.com/item/2.html"},
        {"url": "https://www.aliexpress.com/item/3.html"},
    ]
    enriched_urls = []

    def fake_enrich(page, products):
        for product in products:
            enriched_urls.append(product["url"])
            product["shopName"] = "Example Store"

    monkeypatch.setattr(browser, "_enrich_product_details", fake_enrich)

    products = browser._finalize_products(
        FakePage(),
        raw,
        max_items=2,
        enrich_detail=True,
    )

    assert enriched_urls == [
        "https://www.aliexpress.com/item/1.html",
        "https://www.aliexpress.com/item/2.html",
    ]
    assert products[0]["shopName"] == "Example Store"


def test_enrich_product_details_continues_after_single_product_failure(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-women-dress.html"

        def get(self, url):
            if url.endswith("/2.html"):
                raise RuntimeError("boom")
            self.url = url

        def run_js(self, script):
            return {
                "shopName": "Example Store",
                "shippingText": "Free shipping",
                "detailRatingText": "4.9",
                "detailReviewText": "20 reviews",
                "breadcrumb": "Home > Dresses",
                "attributesText": '{"Material":"Cotton"}',
                "descriptionText": "Long sleeve dress",
            }

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)

    products = [
        {"url": "https://www.aliexpress.com/item/1.html"},
        {"url": "https://www.aliexpress.com/item/2.html"},
        {"url": "https://www.aliexpress.com/item/3.html"},
    ]

    browser._enrich_product_details(FakePage(), products)

    assert products[0]["shopName"] == "Example Store"
    assert products[1].get("shopName", "") == ""
    assert products[2]["shopName"] == "Example Store"
```

- [ ] **Step 2: Run the focused browser tests to verify they fail**

Run: `python -m pytest tests/test_browser.py::test_finalize_products_enriches_every_final_product_when_enabled tests/test_browser.py::test_enrich_product_details_continues_after_single_product_failure -q`

Expected: FAIL because `enrich_detail` and `_enrich_product_details` do not exist yet

- [ ] **Step 3: Add a detail-page extraction script that returns the agreed fields**

```python
DETAIL_FIELDS_SCRIPT = r"""
return (() => {
  function textOf(node) {
    return node ? String(node.innerText || node.textContent || '').trim() : '';
  }

  function cleanText(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function breadcrumbText() {
    const nodes = Array.from(document.querySelectorAll('nav a, [class*="breadcrumb"] a, [class*="breadcrumb"] span'))
      .map(node => cleanText(textOf(node)))
      .filter(Boolean);
    return nodes.join(' > ');
  }

  function attributesJson() {
    const pairs = {};
    const rows = Array.from(document.querySelectorAll('li, tr, [class*="sku"] [class*="item"], [class*="property"] [class*="item"]'));
    for (const row of rows) {
      const text = cleanText(textOf(row));
      if (!text || !text.includes(':')) continue;
      const [key, ...rest] = text.split(':');
      const value = cleanText(rest.join(':'));
      if (key && value && !pairs[key]) pairs[key] = value;
    }
    return JSON.stringify(pairs);
  }

  return {
    shopName: cleanText(textOf(document.querySelector('a[href*="store"], [class*="store"] a, [class*="shop"] a'))),
    shippingText: cleanText(textOf(document.querySelector('[class*="shipping"], [data-pl="shipping"]'))),
    detailRatingText: cleanText(textOf(document.querySelector('[class*="rating"], [aria-label*="rating"]'))),
    detailReviewText: cleanText(textOf(document.querySelector('[class*="review"], a[href*="reviews"]'))),
    breadcrumb: breadcrumbText(),
    attributesText: attributesJson(),
    descriptionText: cleanText(textOf(document.querySelector('[class*="description"], [data-pl="description"], #product-description')))
  };
})()
"""
```

- [ ] **Step 4: Replace the old rating-only enrichment with whole-product detail enrichment**

```python
def collect_raw_products(
    url: str,
    max_items: int,
    scroll_rounds: int = 8,
    user_data_dir: str | None = None,
    port: int | None = None,
    enrich_detail: bool = False,
    pages: int | None = None,
) -> list[dict[str, object]]:
```

```python
def _finalize_products(
    page: ChromiumPage,
    raw: list[dict[str, object]],
    *,
    max_items: int,
    enrich_detail: bool,
) -> list[dict[str, object]]:
    products = raw[:max_items]
    if enrich_detail:
        _enrich_product_details(page, products)
    return products
```

```python
def _enrich_product_details(page: ChromiumPage, products: list[dict[str, object]]) -> None:
    listing_url = page.url
    for product in products:
        url = str(product.get("url") or "")
        if not url:
            continue
        try:
            page.get(url)
            time.sleep(2)
            detail = page.run_js(DETAIL_FIELDS_SCRIPT)
        except Exception:
            detail = {}
        if isinstance(detail, dict):
            product.update(detail)
    if listing_url:
        page.get(listing_url)
```

- [ ] **Step 5: Run the focused browser tests and then the full browser test file**

Run: `python -m pytest tests/test_browser.py::test_finalize_products_enriches_every_final_product_when_enabled tests/test_browser.py::test_enrich_product_details_continues_after_single_product_failure -q`

Expected: PASS

Run: `python -m pytest tests/test_browser.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ali_mvp/browser.py tests/test_browser.py
git commit -m "feat: enrich final products with detail pages"
```

### Task 4: Update README and run end-to-end verification

**Files:**
- Modify: `README.md`
- Verify: `tests/test_cli.py`
- Verify: `tests/test_output.py`
- Verify: `tests/test_browser.py`

- [ ] **Step 1: Update README usage and field documentation**

```markdown
python -m ali_mvp scrape --keyword "women dress" --max-items 20 --enrich-detail

- `--enrich-detail` visits every final product detail page and adds:
  - `shop_name`
  - `shipping_text`
  - `detail_rating`
  - `detail_review_count`
  - `breadcrumb`
  - `attributes_text`
  - `description_text`
```

- [ ] **Step 2: Run the full automated test suite**

Run: `python -m pytest -q`

Expected: PASS

- [ ] **Step 3: Run a manual detail-enrichment verification with the repo-local profile**

Run: `python -m ali_mvp scrape --keyword "Home appliance accessories" --max-items 5 --enrich-detail --port 9333 --user-data-dir .browser-profile --output-dir data/manual-detail-enrichment`

Expected: Exit code `0` and a `products.csv` whose rows contain non-empty detail columns for at least some products

- [ ] **Step 4: Inspect the enriched CSV for structure guarantees**

Run: `python - <<'PY'
import csv, json
from pathlib import Path
path = max(Path("data/manual-detail-enrichment/home-appliance-accessories").glob("*/products.csv"))
rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
assert rows, "no rows"
assert "description_text" in rows[0]
assert "attributes_text" in rows[0]
non_empty_description = sum(bool(row["description_text"]) for row in rows)
valid_json = 0
for row in rows:
    text = row["attributes_text"]
    if not text:
        continue
    json.loads(text)
    valid_json += 1
print({"rows": len(rows), "non_empty_description": non_empty_description, "valid_attributes_json": valid_json})
PY`

Expected: Printed summary with no exceptions

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: describe detail enrichment mode"
```
