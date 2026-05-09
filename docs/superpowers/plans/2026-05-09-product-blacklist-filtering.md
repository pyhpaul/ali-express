# Product Blacklist Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a blacklist-based product filtering stage that excludes disallowed products from `products.csv`, preserves accepted-only ranking output, and writes a full audit CSV with reject and warning reasons.

**Architecture:** Keep filtering separate from scraping and normalization by introducing a focused `ali_mvp/filtering.py` module. The CLI will load rules from a JSON file and repeatable CLI keywords, run filtering after `normalize_products()`, write accepted products to the existing outputs, and write a new audit CSV for all products.

**Tech Stack:** Python 3, argparse, dataclasses, csv, pytest

---

## File Structure

- Create: `ali_mvp/filtering.py`
  - Load blacklist rules from file and CLI
  - Classify fields into strong and weak text buckets
  - Match blacklist terms case-insensitively
  - Return accepted products plus audit rows
- Create: `tests/test_filtering.py`
  - Cover strong-field rejection, weak-field warnings, CLI keyword merging, and no-rule passthrough
- Create: `rules/product_blacklist.json`
  - Provide a baseline blacklist file for electrical / chip-like products
- Modify: `ali_mvp/cli.py`
  - Parse `--blacklist-file` and repeatable `--reject-keyword`
  - Invoke filtering after normalization
  - Write `products_filter_audit.csv`
- Modify: `ali_mvp/output.py`
  - Add audit CSV schema and writer
- Modify: `tests/test_cli.py`
  - Add parser tests for blacklist options
  - Add CLI behavior tests around rule loading defaults if practical
- Modify: `tests/test_output.py`
  - Add audit CSV writing coverage
- Modify: `README.md`
  - Document filtering options, output semantics, and audit file

### Task 1: Define filtering core module

**Files:**
- Create: `ali_mvp/filtering.py`
- Test: `tests/test_filtering.py`

- [ ] **Step 1: Write the failing tests for strong reject, weak warning, and no-rule passthrough**

```python
from ali_mvp.filtering import FilterGroup, filter_products
from ali_mvp.scoring import ProductRecord


def make_product(
    *,
    title: str,
    attributes_text: str = "",
    breadcrumb: str = "",
    description_text: str = "",
) -> ProductRecord:
    return ProductRecord(
        source_type="keyword",
        source_value="home appliance accessories",
        title=title,
        price="$1.00",
        sold_count=0,
        rating=0.0,
        review_count=0,
        product_url="https://example.test/item",
        search_card_url="https://example.test/item",
        image_url="https://example.test/item.jpg",
        entry_type="item_card",
        is_promoted=False,
        promo_channel="",
        promotion_text="",
        promo_landing_url="",
        shop_name="",
        shipping_text="",
        detail_rating=0.0,
        detail_review_count=0,
        breadcrumb=breadcrumb,
        attributes_text=attributes_text,
        description_text=description_text,
        scraped_at="2026-05-09T00:00:00Z",
    )


def test_filter_products_rejects_when_title_hits_strong_blacklist():
    groups = [FilterGroup(name="electrical_power", terms=("battery",))]
    products = [make_product(title="Portable battery charger")]

    accepted, audit_rows = filter_products(products, groups)

    assert accepted == []
    assert audit_rows[0]["filter_decision"] == "rejected"
    assert audit_rows[0]["reject_groups"] == "electrical_power"
    assert audit_rows[0]["reject_terms"] == "battery"
    assert audit_rows[0]["reject_fields"] == "title"


def test_filter_products_warns_without_reject_when_only_description_hits():
    groups = [FilterGroup(name="electrical_power", terms=("battery",))]
    products = [
        make_product(
            title="Washing machine anti-slip stand",
            description_text="Suitable for battery powered devices and large appliances.",
        )
    ]

    accepted, audit_rows = filter_products(products, groups)

    assert [product.title for product in accepted] == ["Washing machine anti-slip stand"]
    assert audit_rows[0]["filter_decision"] == "accepted"
    assert audit_rows[0]["reject_terms"] == ""
    assert audit_rows[0]["warning_terms"] == "battery"
    assert audit_rows[0]["warning_fields"] == "description_text"


def test_filter_products_passes_through_when_no_groups_are_configured():
    products = [make_product(title="Universal appliance shock pad")]

    accepted, audit_rows = filter_products(products, [])

    assert [product.title for product in accepted] == ["Universal appliance shock pad"]
    assert audit_rows[0]["filter_decision"] == "accepted"
    assert audit_rows[0]["reject_terms"] == ""
    assert audit_rows[0]["warning_terms"] == ""
```

- [ ] **Step 2: Run the targeted filtering tests to verify they fail**

Run: `python -m pytest tests/test_filtering.py -q`

Expected: FAIL with import or missing symbol errors for `ali_mvp.filtering`

- [ ] **Step 3: Write the minimal filtering implementation**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .scoring import ProductRecord


@dataclass(frozen=True)
class FilterGroup:
    name: str
    terms: tuple[str, ...]


def filter_products(
    products: list[ProductRecord],
    groups: list[FilterGroup],
) -> tuple[list[ProductRecord], list[dict[str, str]]]:
    accepted: list[ProductRecord] = []
    audit_rows: list[dict[str, str]] = []

    for product in products:
        reject_hits = _collect_hits(product, groups, fields=("title", "attributes_text"))
        warning_hits = _collect_hits(product, groups, fields=("breadcrumb", "description_text"))
        decision = "rejected" if reject_hits else "accepted"
        if decision == "accepted":
            accepted.append(product)
        audit_rows.append(
            {
                "source_type": product.source_type,
                "source_value": product.source_value,
                "title": product.title,
                "product_url": product.product_url,
                "filter_decision": decision,
                "reject_groups": _join_unique(hit["group"] for hit in reject_hits),
                "reject_terms": _join_unique(hit["term"] for hit in reject_hits),
                "reject_fields": _join_unique(hit["field"] for hit in reject_hits),
                "warning_groups": _join_unique(hit["group"] for hit in warning_hits),
                "warning_terms": _join_unique(hit["term"] for hit in warning_hits),
                "warning_fields": _join_unique(hit["field"] for hit in warning_hits),
            }
        )
    return accepted, audit_rows


def _collect_hits(
    product: ProductRecord,
    groups: Iterable[FilterGroup],
    *,
    fields: tuple[str, ...],
) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for field in fields:
        haystack = getattr(product, field, "").lower()
        if not haystack:
            continue
        for group in groups:
            for term in group.terms:
                normalized = term.strip().lower()
                if normalized and normalized in haystack:
                    hits.append({"group": group.name, "term": term, "field": field})
    return hits


def _join_unique(values: Iterable[str]) -> str:
    ordered: list[str] = []
    for value in values:
        if value and value not in ordered:
            ordered.append(value)
    return " | ".join(ordered)
```

- [ ] **Step 4: Run the targeted filtering tests to verify they pass**

Run: `python -m pytest tests/test_filtering.py -q`

Expected: PASS

- [ ] **Step 5: Commit the filtering core**

```bash
git add ali_mvp/filtering.py tests/test_filtering.py
git commit -m "feat(filtering): add blacklist decision engine"
```

### Task 2: Add rule loading from JSON file and CLI keywords

**Files:**
- Modify: `ali_mvp/filtering.py`
- Modify: `tests/test_filtering.py`
- Create: `rules/product_blacklist.json`

- [ ] **Step 1: Write the failing tests for JSON loading and CLI keyword merging**

```python
import json

from ali_mvp.filtering import FilterGroup, load_filter_groups


def test_load_filter_groups_reads_json_file_and_cli_keywords(tmp_path):
    path = tmp_path / "blacklist.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "groups": [
                    {"name": "chip_pcb", "terms": ["pcb", "circuit board"]},
                ],
            }
        ),
        encoding="utf-8",
    )

    groups = load_filter_groups(path, ["sensor", "relay"])

    assert groups == [
        FilterGroup(name="chip_pcb", terms=("pcb", "circuit board")),
        FilterGroup(name="cli_extra", terms=("sensor", "relay")),
    ]


def test_load_filter_groups_returns_empty_when_no_sources_are_provided():
    groups = load_filter_groups(None, [])

    assert groups == []
```

- [ ] **Step 2: Run the targeted rule-loading tests to verify they fail**

Run: `python -m pytest tests/test_filtering.py::test_load_filter_groups_reads_json_file_and_cli_keywords tests/test_filtering.py::test_load_filter_groups_returns_empty_when_no_sources_are_provided -q`

Expected: FAIL because `load_filter_groups` does not exist

- [ ] **Step 3: Extend filtering implementation with rule loading and create the baseline rules file**

```python
import json
from pathlib import Path


def load_filter_groups(
    blacklist_file: str | Path | None,
    reject_keywords: list[str],
) -> list[FilterGroup]:
    groups: list[FilterGroup] = []
    if blacklist_file:
        payload = json.loads(Path(blacklist_file).read_text(encoding="utf-8"))
        for item in payload.get("groups", []):
            name = str(item.get("name") or "").strip()
            terms = tuple(_normalize_terms(item.get("terms", [])))
            if name and terms:
                groups.append(FilterGroup(name=name, terms=terms))
    cli_terms = tuple(_normalize_terms(reject_keywords))
    if cli_terms:
        groups.append(FilterGroup(name="cli_extra", terms=cli_terms))
    return groups


def _normalize_terms(values: Iterable[object]) -> list[str]:
    terms: list[str] = []
    for value in values:
        term = " ".join(str(value or "").split())
        if term and term not in terms:
            terms.append(term)
    return terms
```

```json
{
  "version": 1,
  "groups": [
    {
      "name": "electrical_power",
      "terms": ["battery", "lithium battery", "rechargeable", "charger", "power bank"]
    },
    {
      "name": "chip_pcb",
      "terms": ["chip", "ic", "integrated circuit", "pcb", "pcba", "circuit board", "motherboard"]
    }
  ]
}
```

- [ ] **Step 4: Run the targeted filtering tests to verify they pass**

Run: `python -m pytest tests/test_filtering.py -q`

Expected: PASS

- [ ] **Step 5: Commit rule loading support**

```bash
git add ali_mvp/filtering.py tests/test_filtering.py rules/product_blacklist.json
git commit -m "feat(filtering): load blacklist groups from file and cli"
```

### Task 3: Add CLI options and integrate filtering into scrape flow

**Files:**
- Modify: `ali_mvp/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI parser and flow tests**

```python
from pathlib import Path

from ali_mvp.cli import build_parser


def test_scrape_parser_accepts_blacklist_file_and_repeatable_reject_keyword():
    parser = build_parser()

    args = parser.parse_args(
        [
            "scrape",
            "--keyword",
            "home appliance accessories",
            "--blacklist-file",
            "rules/product_blacklist.json",
            "--reject-keyword",
            "sensor",
            "--reject-keyword",
            "relay",
        ]
    )

    assert args.blacklist_file == "rules/product_blacklist.json"
    assert args.reject_keyword == ["sensor", "relay"]
```

```python
import argparse

from ali_mvp import cli
from ali_mvp.scoring import ProductRecord


def test_run_scrape_filters_products_before_writing_outputs(monkeypatch, tmp_path):
    args = argparse.Namespace(
        keyword="home appliance accessories",
        url=None,
        category_url=None,
        max_items=20,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        pages=1,
        blacklist_file=None,
        reject_keyword=["battery"],
    )

    product = ProductRecord(
        source_type="keyword",
        source_value="home appliance accessories",
        title="Battery charger board",
        price="$1.00",
        sold_count=0,
        rating=0.0,
        review_count=0,
        product_url="https://example.test/item",
        search_card_url="https://example.test/item",
        image_url="https://example.test/item.jpg",
        entry_type="item_card",
        is_promoted=False,
        promo_channel="",
        promotion_text="",
        promo_landing_url="",
        shop_name="",
        shipping_text="",
        detail_rating=0.0,
        detail_review_count=0,
        breadcrumb="",
        attributes_text="",
        description_text="",
        scraped_at="2026-05-09T00:00:00Z",
    )

    captured = {}

    monkeypatch.setattr(cli, "collect_raw_products", lambda *a, **k: [{"title": product.title, "url": product.product_url}])
    monkeypatch.setattr(cli, "normalize_products", lambda *a, **k: [product])
    monkeypatch.setattr(cli, "load_filter_groups", lambda path, keywords: [])
    monkeypatch.setattr(
        cli,
        "filter_products",
        lambda products, groups: (
            [],
            [
                {
                    "source_type": product.source_type,
                    "source_value": product.source_value,
                    "title": product.title,
                    "product_url": product.product_url,
                    "filter_decision": "rejected",
                    "reject_groups": "cli_extra",
                    "reject_terms": "battery",
                    "reject_fields": "title",
                    "warning_groups": "",
                    "warning_terms": "",
                    "warning_fields": "",
                }
            ],
        ),
    )
    monkeypatch.setattr(cli, "write_products_csv", lambda path, products: captured.setdefault("products", list(products)))
    monkeypatch.setattr(cli, "write_rank_csv", lambda path, rows: captured.setdefault("rank", list(rows)))
    monkeypatch.setattr(cli, "write_filter_audit_csv", lambda path, rows: captured.setdefault("audit", list(rows)))

    code = cli.run_scrape(args)

    assert code == 2
    assert captured["products"] == []
    assert captured["audit"][0]["filter_decision"] == "rejected"
```

- [ ] **Step 2: Run the targeted CLI tests to verify they fail**

Run: `python -m pytest tests/test_cli.py::test_scrape_parser_accepts_blacklist_file_and_repeatable_reject_keyword tests/test_cli.py::test_run_scrape_filters_products_before_writing_outputs -q`

Expected: FAIL because parser options and filter integration do not exist

- [ ] **Step 3: Integrate filtering into the CLI**

```python
from .filtering import filter_products, load_filter_groups
from .output import write_filter_audit_csv, write_products_csv, write_rank_csv
```

```python
    scrape.add_argument(
        "--blacklist-file",
        help="Optional JSON blacklist file used to reject disallowed products before writing products.csv.",
    )
    scrape.add_argument(
        "--reject-keyword",
        action="append",
        default=[],
        help="Repeatable extra blacklist term added for this run.",
    )
```

```python
    groups = load_filter_groups(args.blacklist_file, args.reject_keyword)
    accepted_products, audit_rows = filter_products(products, groups)
    output_dir = build_output_dir(Path(args.output_dir), source_type=source_type, source_value=source_value, run_at=run_at)
    write_products_csv(output_dir / "products.csv", accepted_products)
    write_filter_audit_csv(output_dir / "products_filter_audit.csv", audit_rows)
    write_rank_csv(output_dir / "category_rank.csv", aggregate_rank(accepted_products))

    print(f"Scraped raw items: {len(raw_products)}")
    print(f"Normalized products: {len(products)}")
    print(f"Accepted products: {len(accepted_products)}")
    print(f"Wrote: {output_dir / 'products.csv'}")
    print(f"Wrote: {output_dir / 'products_filter_audit.csv'}")
    print(f"Wrote: {output_dir / 'category_rank.csv'}")
    if not accepted_products:
        print("No accepted products extracted. Check login state, CAPTCHA, selector changes, or blacklist rules.")
        return 2
```

- [ ] **Step 4: Run the targeted CLI tests to verify they pass**

Run: `python -m pytest tests/test_cli.py::test_scrape_parser_accepts_blacklist_file_and_repeatable_reject_keyword tests/test_cli.py::test_run_scrape_filters_products_before_writing_outputs -q`

Expected: PASS

- [ ] **Step 5: Commit CLI integration**

```bash
git add ali_mvp/cli.py tests/test_cli.py
git commit -m "feat(cli): wire product blacklist filtering into scrape flow"
```

### Task 4: Add audit CSV writing support

**Files:**
- Modify: `ali_mvp/output.py`
- Modify: `tests/test_output.py`

- [ ] **Step 1: Write the failing audit CSV output test**

```python
import csv

from ali_mvp.output import write_filter_audit_csv


def test_write_filter_audit_csv_writes_expected_columns(tmp_path):
    path = tmp_path / "products_filter_audit.csv"
    rows = [
        {
            "source_type": "keyword",
            "source_value": "home appliance accessories",
            "title": "Battery charger board",
            "product_url": "https://example.test/item",
            "filter_decision": "rejected",
            "reject_groups": "electrical_power",
            "reject_terms": "battery",
            "reject_fields": "title",
            "warning_groups": "",
            "warning_terms": "",
            "warning_fields": "",
        }
    ]

    write_filter_audit_csv(path, rows)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        written_rows = list(csv.DictReader(handle))

    assert written_rows[0]["filter_decision"] == "rejected"
    assert written_rows[0]["reject_terms"] == "battery"
    assert written_rows[0]["warning_terms"] == ""
```

- [ ] **Step 2: Run the targeted audit CSV test to verify it fails**

Run: `python -m pytest tests/test_output.py::test_write_filter_audit_csv_writes_expected_columns -q`

Expected: FAIL because `write_filter_audit_csv` does not exist

- [ ] **Step 3: Implement audit CSV writing**

```python
FILTER_AUDIT_FIELDS = [
    "source_type",
    "source_value",
    "title",
    "product_url",
    "filter_decision",
    "reject_groups",
    "reject_terms",
    "reject_fields",
    "warning_groups",
    "warning_terms",
    "warning_fields",
]


def write_filter_audit_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FILTER_AUDIT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FILTER_AUDIT_FIELDS})
```

- [ ] **Step 4: Run the targeted audit CSV test to verify it passes**

Run: `python -m pytest tests/test_output.py::test_write_filter_audit_csv_writes_expected_columns -q`

Expected: PASS

- [ ] **Step 5: Commit audit CSV support**

```bash
git add ali_mvp/output.py tests/test_output.py
git commit -m "feat(output): add filter audit csv writer"
```

### Task 5: Document the filtering workflow and verify end to end

**Files:**
- Modify: `README.md`
- Test: `tests/test_filtering.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_output.py`

- [ ] **Step 1: Add the baseline real-world regression test for the accessory false-positive concern**

```python
def test_filter_products_keeps_accessory_when_only_weak_fields_reference_appliances():
    groups = [FilterGroup(name="electrical_power", terms=("battery", "charger"))]
    products = [
        make_product(
            title="Universal washing machine stand",
            breadcrumb="Home > Appliance Parts",
            description_text="Compatible with charging equipment, battery powered washers, and other appliances.",
        )
    ]

    accepted, audit_rows = filter_products(products, groups)

    assert [product.title for product in accepted] == ["Universal washing machine stand"]
    assert audit_rows[0]["filter_decision"] == "accepted"
    assert audit_rows[0]["warning_terms"] == "battery | charger"
```

- [ ] **Step 2: Run the filtering regression test to verify it passes**

Run: `python -m pytest tests/test_filtering.py::test_filter_products_keeps_accessory_when_only_weak_fields_reference_appliances -q`

Expected: PASS

- [ ] **Step 3: Update README with blacklist filtering usage and output semantics**

```markdown
Optional product blacklist filtering:

```bash
python -m ali_mvp scrape --keyword "Home appliance accessories" --blacklist-file rules/product_blacklist.json
python -m ali_mvp scrape --keyword "Home appliance accessories" --blacklist-file rules/product_blacklist.json --reject-keyword sensor --reject-keyword relay
```

- `products.csv` only contains accepted products.
- `products_filter_audit.csv` contains all products and records reject / warning reasons.
- Blacklist matching is field-layered:
  - `title` and `attributes_text` can reject directly
  - `breadcrumb` and `description_text` only create warnings
```

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest -q`

Expected: PASS with all tests green

- [ ] **Step 5: Run one manual verification scrape with blacklist rules**

Run: `python -m ali_mvp scrape --keyword "Home appliance accessories" --max-items 20 --pages 1 --enrich-detail --blacklist-file rules/product_blacklist.json --port 9333 --user-data-dir .browser-profile --output-dir data/filter-check`

Expected:
- `products.csv` exists and only includes accepted products
- `products_filter_audit.csv` exists and includes all accepted / rejected products
- accessory-like products mentioning appliances only in `description_text` remain accepted
- obvious battery / pcb-like products are rejected with populated `reject_*` fields

- [ ] **Step 6: Commit docs and end-to-end verification updates**

```bash
git add README.md tests/test_filtering.py
git commit -m "docs(filtering): document blacklist filtering workflow"
```
