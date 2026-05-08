# DrissionPage AliExpress MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Python CLI that uses DrissionPage to collect AliExpress product list data from a keyword or URL and export product and heat-score CSV files.

**Architecture:** Keep browser automation at the edge and isolate deterministic logic in small modules. `cli.py` orchestrates, `browser.py` navigates and scrolls, `extractor.py` normalizes DOM results, `scoring.py` computes metrics, and `output.py` writes CSV files.

**Tech Stack:** Python 3.10+, DrissionPage, pytest, stdlib argparse/csv/dataclasses.

---

## File Structure

- Create `.gitignore`: ignore Python caches, virtualenvs, pytest cache, and generated data.
- Create `requirements.txt`: runtime and test dependencies.
- Create `README.md`: setup, login, and usage instructions.
- Create `ali_mvp/__init__.py`: package marker and version.
- Create `ali_mvp/scoring.py`: parse numeric text and aggregate heat scores.
- Create `ali_mvp/output.py`: write products and ranking CSV files.
- Create `ali_mvp/extractor.py`: normalize product dictionaries returned from browser-side JavaScript.
- Create `ali_mvp/browser.py`: DrissionPage browser/page wrapper.
- Create `ali_mvp/cli.py`: command-line parser and orchestration.
- Create `ali_mvp/__main__.py`: `python -m ali_mvp` entrypoint.
- Create `tests/test_scoring.py`: deterministic scoring tests.
- Create `tests/test_output.py`: deterministic CSV output tests.
- Create `tests/test_extractor.py`: product normalization tests.

## Task 1: Repository Baseline

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `README.md`
- Modify: `docs/superpowers/specs/2026-05-08-drissionpage-aliexpress-mvp-design.md`
- Create: `docs/superpowers/plans/2026-05-08-drissionpage-aliexpress-mvp.md`

- [ ] **Step 1: Create ignore and dependency files**

Create `.gitignore` with:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
data/
*.csv
```

Create `requirements.txt` with:

```text
DrissionPage>=4.1.0
pytest>=8.0.0
```

- [ ] **Step 2: Create README**

Create `README.md` with:

```markdown
# AliExpress DrissionPage MVP

Local MVP for validating AliExpress product-selection logic without an AliExpress API key.

## Setup

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Login

Open AliExpress in the browser profile used by DrissionPage and log in manually before scraping.

## Usage

```bash
python -m ali_mvp scrape --keyword "women dress" --max-items 80
python -m ali_mvp scrape --url "https://www.aliexpress.com/..." --max-items 80
```

Outputs:

- `data/products.csv`
- `data/category_rank.csv`

## Limitations

This MVP is for low-frequency validation. It does not handle proxy pools, CAPTCHA solving, account pools, checkout, or official AliExpress API access.
```

- [ ] **Step 3: Commit baseline**

Run:

```bash
git add .gitignore requirements.txt README.md docs/superpowers/specs/2026-05-08-drissionpage-aliexpress-mvp-design.md docs/superpowers/plans/2026-05-08-drissionpage-aliexpress-mvp.md
git commit -m "docs: add aliexpress mvp plan" -m "Why:`n- Capture the approved MVP design and implementation plan before coding.`n`nWhat:`n- Add project ignore rules, dependencies, README, spec, and plan.`n`nTest:`n- not run (documentation and metadata only)"
```

Expected: commit succeeds.

## Task 2: Scoring Logic

**Files:**
- Create: `ali_mvp/__init__.py`
- Create: `ali_mvp/scoring.py`
- Test: `tests/test_scoring.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_scoring.py` with:

```python
from ali_mvp.scoring import ProductRecord, aggregate_rank, parse_count, parse_float


def test_parse_count_handles_plain_commas_and_suffixes():
    assert parse_count("1,234 sold") == 1234
    assert parse_count("2.5K+ sold") == 2500
    assert parse_count("1.2M sold") == 1200000
    assert parse_count("") == 0
    assert parse_count(None) == 0


def test_parse_float_extracts_first_decimal_number():
    assert parse_float("4.8 stars") == 4.8
    assert parse_float("Rating: 5") == 5.0
    assert parse_float("") == 0.0
    assert parse_float(None) == 0.0


def test_aggregate_rank_groups_by_source_and_scores_heat():
    products = [
        ProductRecord(
            source_type="keyword",
            source_value="women dress",
            title="A",
            price="12.50",
            sold_count=100,
            rating=4.8,
            review_count=20,
            product_url="https://example.test/a",
            image_url="https://example.test/a.jpg",
            scraped_at="2026-05-08T00:00:00Z",
        ),
        ProductRecord(
            source_type="keyword",
            source_value="women dress",
            title="B",
            price="15.00",
            sold_count=200,
            rating=4.6,
            review_count=40,
            product_url="https://example.test/b",
            image_url="https://example.test/b.jpg",
            scraped_at="2026-05-08T00:00:00Z",
        ),
    ]

    rows = aggregate_rank(products)

    assert len(rows) == 1
    row = rows[0]
    assert row.source_value == "women dress"
    assert row.product_count == 2
    assert row.total_sold_count == 300
    assert row.avg_rating == 4.7
    assert row.avg_review_count == 30.0
    assert row.heat_score == 427.0
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
python -m pytest tests/test_scoring.py -v
```

Expected: FAIL because `ali_mvp` or `ali_mvp.scoring` does not exist.

- [ ] **Step 3: Implement scoring**

Create `ali_mvp/__init__.py` with:

```python
"""AliExpress DrissionPage MVP package."""

__version__ = "0.1.0"
```

Create `ali_mvp/scoring.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


COUNT_RE = re.compile(r"(\d+(?:[,.]\d+)*)\s*([kKmM])?")
FLOAT_RE = re.compile(r"\d+(?:\.\d+)?")


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
    scraped_at: str


@dataclass(frozen=True)
class RankRecord:
    source_value: str
    product_count: int
    total_sold_count: int
    avg_rating: float
    avg_review_count: float
    heat_score: float


def parse_count(value: str | None) -> int:
    if not value:
        return 0
    match = COUNT_RE.search(value)
    if not match:
        return 0
    number_text, suffix = match.groups()
    multiplier = 1
    if suffix and suffix.lower() == "k":
        multiplier = 1_000
    elif suffix and suffix.lower() == "m":
        multiplier = 1_000_000
    normalized = number_text.replace(",", "")
    return int(float(normalized) * multiplier)


def parse_float(value: str | None) -> float:
    if not value:
        return 0.0
    match = FLOAT_RE.search(value)
    if not match:
        return 0.0
    return float(match.group(0))


def aggregate_rank(products: Iterable[ProductRecord]) -> list[RankRecord]:
    grouped: dict[str, list[ProductRecord]] = {}
    for product in products:
        grouped.setdefault(product.source_value, []).append(product)

    rows = [_build_rank(source_value, items) for source_value, items in grouped.items()]
    return sorted(rows, key=lambda row: row.heat_score, reverse=True)


def _build_rank(source_value: str, products: list[ProductRecord]) -> RankRecord:
    product_count = len(products)
    total_sold = sum(product.sold_count for product in products)
    total_reviews = sum(product.review_count for product in products)
    avg_rating = round(sum(product.rating for product in products) / product_count, 2)
    avg_reviews = round(total_reviews / product_count, 2)
    heat_score = round(total_sold + total_reviews + product_count * 10 + avg_rating * 10, 2)
    return RankRecord(
        source_value=source_value,
        product_count=product_count,
        total_sold_count=total_sold,
        avg_rating=avg_rating,
        avg_review_count=avg_reviews,
        heat_score=heat_score,
    )
```

- [ ] **Step 4: Verify scoring tests pass**

Run:

```bash
python -m pytest tests/test_scoring.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit scoring**

Run:

```bash
git add ali_mvp/__init__.py ali_mvp/scoring.py tests/test_scoring.py
git commit -m "feat: add product scoring logic" -m "Why:`n- Support deterministic heat scoring for AliExpress selection validation.`n`nWhat:`n- Add product and rank records, numeric parsers, and source-level aggregation.`n`nTest:`n- python -m pytest tests/test_scoring.py -v"
```

Expected: commit succeeds.

## Task 3: CSV Output

**Files:**
- Create: `ali_mvp/output.py`
- Test: `tests/test_output.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_output.py` with:

```python
import csv

from ali_mvp.output import write_products_csv, write_rank_csv
from ali_mvp.scoring import ProductRecord, RankRecord


def test_write_products_csv_writes_header_and_rows(tmp_path):
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
            scraped_at="2026-05-08T00:00:00Z",
        )
    ]

    write_products_csv(path, products)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["title"] == "Dress"
    assert rows[0]["sold_count"] == "100"


def test_write_rank_csv_writes_header_and_rows(tmp_path):
    path = tmp_path / "category_rank.csv"
    rows = [
        RankRecord(
            source_value="women dress",
            product_count=2,
            total_sold_count=300,
            avg_rating=4.7,
            avg_review_count=30.0,
            heat_score=377.0,
        )
    ]

    write_rank_csv(path, rows)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        loaded = list(csv.DictReader(handle))
    assert loaded[0]["source_value"] == "women dress"
    assert loaded[0]["heat_score"] == "377.0"
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
python -m pytest tests/test_output.py -v
```

Expected: FAIL because `ali_mvp.output` does not exist.

- [ ] **Step 3: Implement CSV output**

Create `ali_mvp/output.py` with:

```python
from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .scoring import ProductRecord, RankRecord


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
    "scraped_at",
]

RANK_FIELDS = [
    "source_value",
    "product_count",
    "total_sold_count",
    "avg_rating",
    "avg_review_count",
    "heat_score",
]


def write_products_csv(path: Path, products: Iterable[ProductRecord]) -> None:
    _write_dataclass_csv(path, PRODUCT_FIELDS, products)


def write_rank_csv(path: Path, rows: Iterable[RankRecord]) -> None:
    _write_dataclass_csv(path, RANK_FIELDS, rows)


def _write_dataclass_csv(path: Path, fieldnames: list[str], rows: Iterable[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
```

- [ ] **Step 4: Verify output tests pass**

Run:

```bash
python -m pytest tests/test_output.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit output**

Run:

```bash
git add ali_mvp/output.py tests/test_output.py
git commit -m "feat: add csv output writers" -m "Why:`n- Persist scraped products and ranked sources for analysis.`n`nWhat:`n- Add UTF-8 CSV writers for product and rank records.`n`nTest:`n- python -m pytest tests/test_output.py -v"
```

Expected: commit succeeds.

## Task 4: Product Extraction Normalization

**Files:**
- Create: `ali_mvp/extractor.py`
- Test: `tests/test_extractor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_extractor.py` with:

```python
from ali_mvp.extractor import normalize_products


def test_normalize_products_deduplicates_urls_and_parses_numbers():
    raw = [
        {
            "title": " Dress ",
            "price": "$12.50",
            "soldText": "1.2K sold",
            "ratingText": "4.8",
            "reviewText": "32 reviews",
            "url": "//www.aliexpress.com/item/100500.html",
            "image": "//ae01.alicdn.com/item.jpg",
        },
        {
            "title": "Duplicate",
            "price": "$13.00",
            "soldText": "10 sold",
            "ratingText": "4.5",
            "reviewText": "5 reviews",
            "url": "https://www.aliexpress.com/item/100500.html",
            "image": "",
        },
    ]

    products = normalize_products(
        raw,
        source_type="keyword",
        source_value="women dress",
        scraped_at="2026-05-08T00:00:00Z",
    )

    assert len(products) == 1
    product = products[0]
    assert product.title == "Dress"
    assert product.sold_count == 1200
    assert product.rating == 4.8
    assert product.review_count == 32
    assert product.product_url == "https://www.aliexpress.com/item/100500.html"
    assert product.image_url == "https://ae01.alicdn.com/item.jpg"
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
python -m pytest tests/test_extractor.py -v
```

Expected: FAIL because `ali_mvp.extractor` does not exist.

- [ ] **Step 3: Implement normalization**

Create `ali_mvp/extractor.py` with:

```python
from __future__ import annotations

from collections.abc import Mapping

from .scoring import ProductRecord, parse_count, parse_float


def normalize_products(
    raw_products: list[Mapping[str, object]],
    *,
    source_type: str,
    source_value: str,
    scraped_at: str,
) -> list[ProductRecord]:
    products: list[ProductRecord] = []
    seen_urls: set[str] = set()

    for raw in raw_products:
        title = _clean_text(raw.get("title"))
        url = _normalize_url(_clean_text(raw.get("url")))
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
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
                scraped_at=scraped_at,
            )
        )

    return products


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _normalize_url(value: str) -> str:
    if value.startswith("//"):
        return f"https:{value}"
    return value
```

- [ ] **Step 4: Verify extractor tests pass**

Run:

```bash
python -m pytest tests/test_extractor.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit extractor**

Run:

```bash
git add ali_mvp/extractor.py tests/test_extractor.py
git commit -m "feat: normalize extracted products" -m "Why:`n- Convert browser-side product dictionaries into stable records for scoring and CSV output.`n`nWhat:`n- Add URL normalization, de-duplication, text cleanup, and numeric parsing integration.`n`nTest:`n- python -m pytest tests/test_extractor.py -v"
```

Expected: commit succeeds.

## Task 5: Browser and CLI MVP

**Files:**
- Create: `ali_mvp/browser.py`
- Create: `ali_mvp/cli.py`
- Create: `ali_mvp/__main__.py`
- Modify: `README.md`

- [ ] **Step 1: Implement browser wrapper**

Create `ali_mvp/browser.py` with:

```python
from __future__ import annotations

import time

from DrissionPage import ChromiumPage


PRODUCT_SCRIPT = r"""
(() => {
  const cards = Array.from(document.querySelectorAll('a[href*="/item/"], a[href*="item/"]'));
  const results = [];
  const seen = new Set();
  for (const link of cards) {
    const url = link.href || link.getAttribute('href') || '';
    if (!url || seen.has(url)) continue;
    seen.add(url);
    const card = link.closest('[class*="product"], [class*="item"], [data-product-id], li, div') || link;
    const text = (card.innerText || link.innerText || '').trim();
    const lines = text.split('\n').map(line => line.trim()).filter(Boolean);
    const img = card.querySelector('img') || link.querySelector('img');
    const priceLine = lines.find(line => /[$€£¥]|US\s*\$|\d+[,.]\d{2}/i.test(line)) || '';
    const soldLine = lines.find(line => /sold|orders|已售|售出/i.test(line)) || '';
    const ratingLine = lines.find(line => /\b[1-5](?:\.\d)?\b/.test(line) && /star|rating|reviews?|评价|评星/i.test(line)) || '';
    const reviewLine = lines.find(line => /reviews?|评价/i.test(line)) || '';
    const title = (img && (img.alt || img.title)) || lines.find(line => line.length > 12) || link.textContent || '';
    results.push({
      title,
      price: priceLine,
      soldText: soldLine,
      ratingText: ratingLine,
      reviewText: reviewLine,
      url,
      image: img ? (img.src || img.getAttribute('data-src') || '') : ''
    });
  }
  return results;
})()
"""


def collect_raw_products(url: str, max_items: int, scroll_rounds: int = 8) -> list[dict[str, object]]:
    page = ChromiumPage()
    page.get(url)
    time.sleep(3)
    for _ in range(scroll_rounds):
        page.run_js("window.scrollBy(0, Math.max(900, window.innerHeight || 900));")
        time.sleep(1)
        raw = page.run_js(PRODUCT_SCRIPT)
        if isinstance(raw, list) and len(raw) >= max_items:
            return raw[:max_items]
    raw = page.run_js(PRODUCT_SCRIPT)
    if not isinstance(raw, list):
        return []
    return raw[:max_items]
```

- [ ] **Step 2: Implement CLI orchestration**

Create `ali_mvp/cli.py` with:

```python
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

from .browser import collect_raw_products
from .extractor import normalize_products
from .output import write_products_csv, write_rank_csv
from .scoring import aggregate_rank


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ali_mvp")
    subparsers = parser.add_subparsers(dest="command", required=True)
    scrape = subparsers.add_parser("scrape", help="Scrape AliExpress product listings.")
    source = scrape.add_mutually_exclusive_group(required=True)
    source.add_argument("--keyword", help="AliExpress search keyword.")
    source.add_argument("--url", help="AliExpress listing or search URL.")
    scrape.add_argument("--max-items", type=int, default=80)
    scrape.add_argument("--output-dir", default="data")
    scrape.set_defaults(func=run_scrape)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def run_scrape(args: argparse.Namespace) -> int:
    source_type = "keyword" if args.keyword else "url"
    source_value = args.keyword or args.url
    url = _build_search_url(args.keyword) if args.keyword else args.url
    if args.max_items < 1:
        raise SystemExit("--max-items must be greater than 0")

    scraped_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    raw_products = collect_raw_products(url, args.max_items)
    products = normalize_products(
        raw_products,
        source_type=source_type,
        source_value=source_value,
        scraped_at=scraped_at,
    )
    output_dir = Path(args.output_dir)
    write_products_csv(output_dir / "products.csv", products)
    write_rank_csv(output_dir / "category_rank.csv", aggregate_rank(products))

    print(f"Scraped raw items: {len(raw_products)}")
    print(f"Normalized products: {len(products)}")
    print(f"Wrote: {output_dir / 'products.csv'}")
    print(f"Wrote: {output_dir / 'category_rank.csv'}")
    if not products:
        print("No products extracted. Check login state, region redirects, CAPTCHA, or page selector changes.")
        return 2
    return 0


def _build_search_url(keyword: str) -> str:
    return f"https://www.aliexpress.com/wholesale?SearchText={quote_plus(keyword)}"
```

Create `ali_mvp/__main__.py` with:

```python
from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Update README usage notes**

Append to `README.md`:

```markdown

## Manual Validation

After logging in, run:

```bash
python -m ali_mvp scrape --keyword "women dress" --max-items 20
```

If no products are extracted, open the browser window and check for region selection, CAPTCHA, cookie banners, or page layout changes.
```

- [ ] **Step 4: Run full tests**

Run:

```bash
python -m pytest -v
```

Expected: all deterministic tests pass.

- [ ] **Step 5: Commit CLI/browser MVP**

Run:

```bash
git add ali_mvp/browser.py ali_mvp/cli.py ali_mvp/__main__.py README.md
git commit -m "feat: add drissionpage scrape cli" -m "Why:`n- Provide the browser-backed MVP entrypoint for AliExpress selection validation.`n`nWhat:`n- Add DrissionPage collection, CLI orchestration, and manual validation docs.`n`nTest:`n- python -m pytest -v"
```

Expected: commit succeeds.

## Task 6: Final Verification

**Files:**
- No required code changes unless verification finds a defect.

- [ ] **Step 1: Run static syntax validation**

Run:

```bash
python -m compileall ali_mvp tests
```

Expected: compile succeeds with no syntax errors.

- [ ] **Step 2: Run deterministic tests**

Run:

```bash
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Inspect git status**

Run:

```bash
git status --short
```

Expected: clean worktree or only intentionally untracked local data.

- [ ] **Step 4: Optional live scrape validation**

After manually logging into AliExpress in the DrissionPage Chromium profile, run:

```bash
python -m ali_mvp scrape --keyword "women dress" --max-items 20
```

Expected:

- `data/products.csv` exists.
- `data/category_rank.csv` exists.
- CLI reports the number of raw and normalized products.

If this returns 2 with no products, inspect the opened page for login prompts, CAPTCHA, region dialogs, or changed listing markup.
