# Pagination Total Target Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `--max-items` represent the total number of products to return, while `--pages` becomes an optional maximum page limit and omitted `--pages` triggers automatic pagination until enough unique products are collected or pagination ends.

**Architecture:** Keep the CLI surface small and move the behavior change into browser orchestration. The single-page collector should gather all visible products on the current page, while the outer collection loop owns deduplication, stop conditions, optional page limits, and final total truncation.

**Tech Stack:** Python 3.13, argparse, pytest, DrissionPage

---

### Task 1: Update CLI parsing and validation for optional page limit

**Files:**
- Modify: `ali_mvp/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing parser tests for omitted and explicit `--pages`**

```python
def test_scrape_parser_defaults_pages_to_none():
    parser = build_parser()
    args = parser.parse_args(["scrape", "--keyword", "women dress"])

    assert args.pages is None


def test_scrape_parser_accepts_pages_option():
    parser = build_parser()
    args = parser.parse_args(["scrape", "--keyword", "women dress", "--pages", "3"])

    assert args.pages == 3
```

- [ ] **Step 2: Run the CLI parser tests to verify the new default test fails**

Run: `python -m pytest tests/test_cli.py::test_scrape_parser_defaults_pages_to_none tests/test_cli.py::test_scrape_parser_accepts_pages_option -q`

Expected: FAIL because `args.pages` is currently `1`, not `None`

- [ ] **Step 3: Add validation coverage for invalid explicit page limits**

```python
def test_run_scrape_rejects_non_positive_pages():
    args = argparse.Namespace(
        keyword="women dress",
        url=None,
        category_url=None,
        max_items=20,
        output_dir="data",
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail_rating=False,
        detail_limit=5,
        pages=0,
    )

    with pytest.raises(SystemExit, match="--pages must be greater than 0"):
        run_scrape(args)
```
```

- [ ] **Step 4: Run the invalid-pages test to verify it already fails or stays red for the right reason**

Run: `python -m pytest tests/test_cli.py::test_run_scrape_rejects_non_positive_pages -q`

Expected: FAIL or PASS depending on existing validation, but the first parser-default test must remain red until implementation changes

- [ ] **Step 5: Write the minimal CLI implementation**

```python
scrape.add_argument(
    "--pages",
    type=int,
    default=None,
    help="Maximum listing pages to visit. Omit to auto-advance until --max-items is reached or no next page is available.",
)

if args.pages is not None and args.pages < 1:
    raise SystemExit("--pages must be greater than 0")
```

- [ ] **Step 6: Run the focused CLI tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -q`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add ali_mvp/cli.py tests/test_cli.py
git commit -m "refactor: make pages an optional page limit"
```

### Task 2: Make single-page collection return the whole page and move total truncation outward

**Files:**
- Modify: `ali_mvp/browser.py`
- Test: `tests/test_browser.py`

- [ ] **Step 1: Write the failing tests that capture the new collection semantics**

```python
def test_collect_current_page_returns_all_products_without_max_items_cap(monkeypatch):
    class FakePage:
        def __init__(self):
            self.calls = 0

        def run_js(self, script):
            if script == PRODUCT_SCRIPT:
                self.calls += 1
                return [
                    {"url": "https://www.aliexpress.com/item/1.html"},
                    {"url": "https://www.aliexpress.com/item/2.html"},
                    {"url": "https://www.aliexpress.com/item/3.html"},
                ]
            return None

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)

    products = browser._collect_current_page(FakePage(), scroll_rounds=1)

    assert [product["url"] for product in products] == [
        "https://www.aliexpress.com/item/1.html",
        "https://www.aliexpress.com/item/2.html",
        "https://www.aliexpress.com/item/3.html",
    ]


def test_finalize_products_applies_total_cap_once():
    class FakePage:
        url = "https://www.aliexpress.com/w/wholesale-women-dress.html"

    raw = [
        {"url": "https://www.aliexpress.com/item/1.html"},
        {"url": "https://www.aliexpress.com/item/2.html"},
        {"url": "https://www.aliexpress.com/item/3.html"},
    ]

    products = browser._finalize_products(
        FakePage(),
        raw,
        max_items=2,
        enrich_detail_rating=False,
        detail_limit=0,
    )

    assert [product["url"] for product in products] == [
        "https://www.aliexpress.com/item/1.html",
        "https://www.aliexpress.com/item/2.html",
    ]
```

- [ ] **Step 2: Run the focused browser tests to verify the single-page test fails**

Run: `python -m pytest tests/test_browser.py::test_collect_current_page_returns_all_products_without_max_items_cap tests/test_browser.py::test_finalize_products_applies_total_cap_once -q`

Expected: FAIL because `_collect_current_page()` still requires `max_items` and truncates page results

- [ ] **Step 3: Write the minimal browser implementation for whole-page collection**

```python
def _collect_current_page(page: ChromiumPage, *, scroll_rounds: int) -> list[dict[str, object]]:
    best: list[dict[str, object]] = []
    for _ in range(scroll_rounds):
        page.run_js("window.scrollBy(0, Math.max(900, window.innerHeight || 900));")
        time.sleep(1)
        raw = page.run_js(PRODUCT_SCRIPT)
        if isinstance(raw, list) and len(raw) >= len(best):
            best = raw
    raw = page.run_js(PRODUCT_SCRIPT)
    if isinstance(raw, list) and len(raw) >= len(best):
        return raw
    return best
```

- [ ] **Step 4: Run the focused browser tests to verify they pass**

Run: `python -m pytest tests/test_browser.py::test_collect_current_page_returns_all_products_without_max_items_cap tests/test_browser.py::test_finalize_products_applies_total_cap_once -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ali_mvp/browser.py tests/test_browser.py
git commit -m "refactor: collect full page before total truncation"
```

### Task 3: Change pagination orchestration to auto-advance until enough unique products are collected

**Files:**
- Modify: `ali_mvp/browser.py`
- Test: `tests/test_browser.py`

- [ ] **Step 1: Write the failing orchestration tests for auto-pagination and explicit page caps**

```python
def test_collect_raw_products_auto_advances_until_total_target(monkeypatch):
    class FakePage:
        def __init__(self, *args, **kwargs):
            self.url = "https://www.aliexpress.com/w/wholesale-women-dress.html"

        def get(self, url):
            self.url = url

    pages = iter(
        [
            [
                {"url": "https://www.aliexpress.com/item/1.html"},
                {"url": "https://www.aliexpress.com/item/2.html"},
            ],
            [
                {"url": "https://www.aliexpress.com/item/3.html"},
                {"url": "https://www.aliexpress.com/item/4.html"},
            ],
        ]
    )
    next_calls = []

    monkeypatch.setattr(browser, "ChromiumPage", FakePage)
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_build_options", lambda **kwargs: object())
    monkeypatch.setattr(browser, "_collect_current_page", lambda page, scroll_rounds: next(pages))
    monkeypatch.setattr(browser, "_go_to_next_page", lambda page, target_page: next_calls.append(target_page) or True)

    products = browser.collect_raw_products("https://example.test", max_items=3, pages=None)

    assert [product["url"] for product in products] == [
        "https://www.aliexpress.com/item/1.html",
        "https://www.aliexpress.com/item/2.html",
        "https://www.aliexpress.com/item/3.html",
    ]
    assert next_calls == [2]


def test_collect_raw_products_stops_at_explicit_page_limit(monkeypatch):
    class FakePage:
        def __init__(self, *args, **kwargs):
            self.url = "https://www.aliexpress.com/w/wholesale-women-dress.html"

        def get(self, url):
            self.url = url

    page_results = [
        [
            {"url": "https://www.aliexpress.com/item/1.html"},
            {"url": "https://www.aliexpress.com/item/2.html"},
        ],
        [
            {"url": "https://www.aliexpress.com/item/3.html"},
            {"url": "https://www.aliexpress.com/item/4.html"},
        ],
    ]
    index = {"value": 0}
    next_calls = []

    def fake_collect(page, scroll_rounds):
        result = page_results[index["value"]]
        index["value"] += 1
        return result

    monkeypatch.setattr(browser, "ChromiumPage", FakePage)
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_build_options", lambda **kwargs: object())
    monkeypatch.setattr(browser, "_collect_current_page", fake_collect)
    monkeypatch.setattr(browser, "_go_to_next_page", lambda page, target_page: next_calls.append(target_page) or True)

    products = browser.collect_raw_products("https://example.test", max_items=10, pages=1)

    assert [product["url"] for product in products] == [
        "https://www.aliexpress.com/item/1.html",
        "https://www.aliexpress.com/item/2.html",
    ]
    assert next_calls == []
```

- [ ] **Step 2: Run the focused orchestration tests to verify they fail**

Run: `python -m pytest tests/test_browser.py::test_collect_raw_products_auto_advances_until_total_target tests/test_browser.py::test_collect_raw_products_stops_at_explicit_page_limit -q`

Expected: FAIL because `collect_raw_products()` still assumes `pages` is an integer and still collects `max_items` per page

- [ ] **Step 3: Write the minimal orchestration implementation**

```python
def collect_raw_products(
    url: str,
    max_items: int,
    scroll_rounds: int = 8,
    user_data_dir: str | None = None,
    port: int | None = None,
    enrich_detail_rating: bool = False,
    detail_limit: int = 5,
    pages: int | None = None,
) -> list[dict[str, object]]:
    page = ChromiumPage(_build_options(user_data_dir=user_data_dir, port=port))
    page.get(url)
    time.sleep(3)
    all_products: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    page_index = 1

    while True:
        current_products = _collect_current_page(page, scroll_rounds=scroll_rounds)
        for product in current_products:
            product_key = _product_key(product)
            if product_key and product_key not in seen_urls:
                seen_urls.add(product_key)
                all_products.append(product)
        if len(all_products) >= max_items:
            break
        if pages is not None and page_index >= pages:
            break
        page_index += 1
        if not _go_to_next_page(page, page_index):
            break

    return _finalize_products(
        page,
        all_products,
        max_items=max_items,
        enrich_detail_rating=enrich_detail_rating,
        detail_limit=detail_limit,
    )
```

- [ ] **Step 4: Run the focused orchestration tests to verify they pass**

Run: `python -m pytest tests/test_browser.py::test_collect_raw_products_auto_advances_until_total_target tests/test_browser.py::test_collect_raw_products_stops_at_explicit_page_limit -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ali_mvp/browser.py tests/test_browser.py
git commit -m "feat: auto-advance pagination toward total target"
```

### Task 4: Update user-facing docs and run full verification

**Files:**
- Modify: `README.md`
- Verify: `tests/test_browser.py`
- Verify: `tests/test_cli.py`

- [ ] **Step 1: Update the usage examples and option semantics in README**

```markdown
python -m ali_mvp scrape --keyword "women dress" --max-items 80
python -m ali_mvp scrape --keyword "women dress" --max-items 80 --pages 2

- `--max-items` is the total number of products requested for the run.
- `--pages` is an optional maximum page limit. If omitted, the scraper auto-advances until `--max-items` is reached or no next page is available.
```

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest -q`

Expected: PASS

- [ ] **Step 3: Run a manual auto-pagination verification with the repo-local profile**

Run: `python -m ali_mvp scrape --keyword "women dress" --max-items 20 --port 9333 --user-data-dir .browser-profile`

Expected: Exit code `0`, non-empty `products.csv`, and evidence that the run can paginate without an explicit `--pages`

- [ ] **Step 4: Run a manual explicit-page-cap verification with the repo-local profile**

Run: `python -m ali_mvp scrape --keyword "women dress" --max-items 80 --pages 2 --port 9333 --user-data-dir .browser-profile`

Expected: Exit code `0`, non-empty `products.csv`, and results limited to what two pages can supply

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: clarify total-target pagination behavior"
```
