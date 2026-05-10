# Task 3: Define review row assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure `build_review_rows(...)` join that merges product context into audit rows by `product_url`.

**Architecture:** Keep the implementation in a single focused module, `ali_mvp/review.py`. Build a product index keyed by `product_url`, then emit review rows by copying each audit row and overlaying product context fields in the existing review schema order. Missing product context should degrade to empty strings so rejected rows without products still remain reviewable.

**Tech Stack:** Python 3.13, `pytest`, standard library only

---

### Task 1: Add failing tests for review row join behavior

**Files:**
- Create: `tests/test_review.py`

- [ ] **Step 1: Write the failing tests**

```python
from ali_mvp.review import build_review_rows


def test_build_review_rows_merges_product_context_into_audit_rows():
    products = [
        {
            "title": "Shock pad",
            "product_url": "https://example.test/item/1",
            "image_url": "https://example.test/img.jpg",
            "price": "$1.00",
            "search_card_url": "https://example.test/card/1",
            "entry_type": "item_card",
            "is_promoted": "False",
            "promo_channel": "",
            "promotion_text": "",
            "shop_name": "Store A",
            "shipping_text": "Free shipping",
            "attributes_text": "{\"Type\":\"Pad\"}",
            "description_text": "Accessory",
            "detail_status": "",
        }
    ]
    audit_rows = [
        {
            "title": "Shock pad",
            "product_url": "https://example.test/item/1",
            "filter_decision": "accepted",
            "filter_stage": "accepted",
            "reject_groups": "",
            "reject_terms": "",
            "reject_fields": "",
            "warning_groups": "",
            "warning_terms": "",
            "warning_fields": "",
            "source_type": "keyword",
            "source_value": "home appliance accessories",
        }
    ]

    review_rows = build_review_rows(products, audit_rows)

    assert review_rows[0]["shop_name"] == "Store A"
    assert review_rows[0]["filter_decision"] == "accepted"


def test_build_review_rows_keeps_listing_prefilter_rejections_without_product_context():
    review_rows = build_review_rows(
        [],
        [
            {
                "title": "Battery charger board",
                "product_url": "https://example.test/item/2",
                "filter_decision": "rejected",
                "filter_stage": "listing_title",
                "source_type": "keyword",
                "source_value": "home appliance accessories",
                "reject_groups": "electrical_power",
                "reject_terms": "battery",
                "reject_fields": "title",
                "warning_groups": "",
                "warning_terms": "",
                "warning_fields": "",
            }
        ],
    )

    assert review_rows[0]["title"] == "Battery charger board"
    assert review_rows[0]["image_url"] == ""
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_review.py::test_build_review_rows_merges_product_context_into_audit_rows -q`
Expected: FAIL with `ModuleNotFoundError` for `ali_mvp.review`

### Task 2: Implement review row assembly

**Files:**
- Create: `ali_mvp/review.py`

- [ ] **Step 1: Add the minimal implementation**

```python
from __future__ import annotations

from typing import Iterable


PRODUCT_CONTEXT_FIELDS = (
    "image_url",
    "price",
    "search_card_url",
    "entry_type",
    "is_promoted",
    "promo_channel",
    "promotion_text",
    "shop_name",
    "shipping_text",
    "attributes_text",
    "description_text",
    "detail_status",
)


def build_review_rows(products: Iterable[dict[str, str]], audit_rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    product_index = {row.get("product_url", ""): row for row in products if row.get("product_url")}
    result: list[dict[str, str]] = []
    for audit in audit_rows:
        merged = dict(audit)
        product = product_index.get(audit.get("product_url", ""), {})
        for field in PRODUCT_CONTEXT_FIELDS:
            merged[field] = str(product.get(field, ""))
        result.append(merged)
    return result
```

- [ ] **Step 2: Run the full review test module**

Run: `python -m pytest tests/test_review.py -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add ali_mvp/review.py tests/test_review.py docs/superpowers/plans/2026-05-11-postprocess-zh-browser-hardening-task3.md
git commit -m "feat(review): add review row join model"
```
