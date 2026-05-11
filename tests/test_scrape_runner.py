from __future__ import annotations

import json
from dataclasses import asdict
from importlib import import_module

from ali_mvp.filtering import FilterGroup
from ali_mvp.run_state import RunManifest
from ali_mvp.scoring import ProductRecord


def _manifest(tmp_path, *, pages: int | None = 1, enrich_detail: bool = True) -> RunManifest:
    return RunManifest(
        source_type="keyword",
        source_value="women dress",
        url="https://www.aliexpress.com/wholesale?SearchText=women+dress",
        max_items=20,
        pages=pages,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=enrich_detail,
        blacklist_file=None,
        reject_keyword=[],
        browser_hardening="minimal",
        created_at="2026-05-11T08:00:00Z",
    )


def _product_record(*, product_url: str, title: str, scraped_at: str = "2026-05-11T08:00:00Z") -> ProductRecord:
    return ProductRecord(
        source_type="keyword",
        source_value="women dress",
        title=title,
        price="$12.50",
        sold_count=100,
        rating=4.8,
        review_count=20,
        product_url=product_url,
        search_card_url=product_url,
        image_url=f"{product_url}.jpg",
        entry_type="item_card",
        is_promoted=False,
        promo_channel="",
        promotion_text="",
        promo_landing_url="",
        shop_name="Example Store",
        shipping_text="Free shipping",
        detail_rating=4.9,
        detail_review_count=25,
        breadcrumb="Home > Dresses",
        attributes_text='{"Material":"Cotton"}',
        description_text="Long sleeve dress",
        scraped_at=scraped_at,
        detail_status="detail_enriched",
    )


def test_run_new_scrape_marks_blocked_run_and_writes_outputs(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")

    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress"

    raw_product = {
        "title": "Dress A",
        "url": "https://www.aliexpress.com/item/1001.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
    }

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", lambda page: [dict(raw_product)])
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", lambda products, seen_keys: products)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )
    monkeypatch.setattr(
        scrape_runner,
        "enrich_single_product_detail",
        lambda page, product: "captcha_blocked",
    )
    monkeypatch.setattr(scrape_runner, "advance_listing_page", lambda page, target_page: False)

    result = scrape_runner.run_new_scrape(
        manifest=_manifest(tmp_path, pages=1, enrich_detail=True),
        groups=[FilterGroup(name="cli_extra")],
        run_dir=tmp_path,
    )

    assert result == scrape_runner.RunResult(exit_code=3, accepted_count=0, blocked=True)

    state = json.loads((tmp_path / "run_state.json").read_text(encoding="utf-8"))
    summary = json.loads((tmp_path / "run_summary.json").read_text(encoding="utf-8"))

    assert state["status"] == "blocked"
    assert state["last_block_reason"] == "captcha_blocked"
    assert state["last_blocked_url"] == "https://www.aliexpress.com/item/1001.html"
    assert state["pending_detail_queue"] == ["https://www.aliexpress.com/item/1001.html"]
    assert summary["resume_recommended"] is True

    assert (tmp_path / "products.csv").exists()
    assert (tmp_path / "products_filter_audit.csv").exists()
    assert (tmp_path / "products_review.csv").exists()
    assert (tmp_path / "category_rank.csv").exists()


def test_run_new_scrape_checkpoints_across_multiple_pages(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")

    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress"

    pages = {
        1: [
            {
                "title": "Dress A",
                "url": "https://www.aliexpress.com/item/1001.html",
                "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
            }
        ],
        2: [
            {
                "title": "Dress B",
                "url": "https://www.aliexpress.com/item/1002.html",
                "resolvedProductUrl": "https://www.aliexpress.com/item/1002.html",
            }
        ],
    }
    current_page = {"value": 1}

    def fake_collect(page):
        return [dict(item) for item in pages[current_page["value"]]]

    def fake_dedupe(products, seen_keys):
        unique = []
        for product in products:
            key = product["resolvedProductUrl"]
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(product)
        return unique

    def fake_advance(page, target_page):
        if target_page > 2:
            return False
        current_page["value"] = target_page
        return True

    def fake_normalize(products, *, source_type, source_value, scraped_at):
        return [
            _product_record(
                product_url=str(product["resolvedProductUrl"]),
                title=str(product["title"]),
                scraped_at=scraped_at,
            )
            for product in products
        ]

    def fake_filter(products, groups):
        return (
            list(products),
            [
                {
                    "source_type": product.source_type,
                    "source_value": product.source_value,
                    "title": product.title,
                    "product_url": product.product_url,
                    "filter_decision": "accepted",
                    "filter_stage": "accepted",
                    "reject_groups": "",
                    "reject_terms": "",
                    "reject_fields": "",
                    "warning_groups": "",
                    "warning_terms": "",
                    "warning_fields": "",
                }
                for product in products
            ],
        )

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", fake_collect)
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", fake_dedupe)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )
    monkeypatch.setattr(scrape_runner, "normalize_products", fake_normalize)
    monkeypatch.setattr(scrape_runner, "filter_products", fake_filter)
    monkeypatch.setattr(scrape_runner, "advance_listing_page", fake_advance)

    result = scrape_runner.run_new_scrape(
        manifest=_manifest(tmp_path, pages=2, enrich_detail=False),
        groups=[],
        run_dir=tmp_path,
    )

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=2, blocked=False)

    state = json.loads((tmp_path / "run_state.json").read_text(encoding="utf-8"))
    summary = json.loads((tmp_path / "run_summary.json").read_text(encoding="utf-8"))

    assert state["status"] == "completed"
    assert state["current_listing_page"] == 2
    assert state["accepted_count"] == 2
    assert state["seen_product_keys"] == [
        "https://www.aliexpress.com/item/1001.html",
        "https://www.aliexpress.com/item/1002.html",
    ]
    assert len(state["audit_rows"]) == 2
    assert len(state["accepted_products"]) == 2
    assert state["accepted_products"][0] == asdict(_product_record(product_url="https://www.aliexpress.com/item/1001.html", title="Dress A"))
    assert summary["status"] == "completed"
    assert summary["resume_recommended"] is False


def test_run_new_scrape_attaches_listing_context_before_detail_enrich(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")

    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress&page=2"

    raw_product = {
        "title": "Dress A",
        "url": "https://www.aliexpress.com/item/1001.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
    }
    seen_contexts: list[dict[str, object]] = []

    def fake_enrich(page, product):
        seen_contexts.append(
            {
                "_listingBaseUrl": product.get("_listingBaseUrl"),
                "_listingPageUrl": product.get("_listingPageUrl"),
                "_listingPageNumber": product.get("_listingPageNumber"),
            }
        )
        return "detail_enriched"

    def fake_attach(products, *, base_url, page_url, page_number):
        for product in products:
            product["_listingBaseUrl"] = base_url
            product["_listingPageUrl"] = page_url
            product["_listingPageNumber"] = page_number

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", lambda page: [dict(raw_product)])
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", lambda products, seen_keys: products)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )
    monkeypatch.setattr(scrape_runner, "_attach_listing_context", fake_attach)
    monkeypatch.setattr(scrape_runner, "enrich_single_product_detail", fake_enrich)
    monkeypatch.setattr(
        scrape_runner,
        "normalize_products",
        lambda products, *, source_type, source_value, scraped_at: [
            _product_record(product_url=str(product["resolvedProductUrl"]), title=str(product["title"]), scraped_at=scraped_at)
            for product in products
        ],
    )
    monkeypatch.setattr(
        scrape_runner,
        "filter_products",
        lambda products, groups: (
            list(products),
            [
                {
                    "source_type": product.source_type,
                    "source_value": product.source_value,
                    "title": product.title,
                    "product_url": product.product_url,
                    "filter_decision": "accepted",
                    "filter_stage": "accepted",
                    "reject_groups": "",
                    "reject_terms": "",
                    "reject_fields": "",
                    "warning_groups": "",
                    "warning_terms": "",
                    "warning_fields": "",
                }
                for product in products
            ],
        ),
    )
    monkeypatch.setattr(scrape_runner, "advance_listing_page", lambda page, target_page: False)

    manifest = _manifest(tmp_path, pages=2, enrich_detail=True)
    result = scrape_runner.run_new_scrape(
        manifest=manifest,
        groups=[],
        run_dir=tmp_path,
    )

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=1, blocked=False)
    assert seen_contexts == [
        {
            "_listingBaseUrl": manifest.url,
            "_listingPageUrl": "https://www.aliexpress.com/wholesale?SearchText=women+dress&page=2",
            "_listingPageNumber": 1,
        }
    ]


def test_run_new_scrape_preserves_seen_product_key_order_with_multiple_new_items_on_one_page(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")

    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress"

    page_products = [
        {
            "title": "Dress B",
            "url": "https://www.aliexpress.com/item/1002.html",
            "resolvedProductUrl": "https://www.aliexpress.com/item/1002.html",
        },
        {
            "title": "Dress A",
            "url": "https://www.aliexpress.com/item/1001.html",
            "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
        },
        {
            "title": "Dress C",
            "url": "https://www.aliexpress.com/item/1003.html",
            "resolvedProductUrl": "https://www.aliexpress.com/item/1003.html",
        },
    ]

    def fake_dedupe(products, seen_keys):
        unique = []
        for product in products:
            key = str(product["resolvedProductUrl"])
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(product)
        return unique

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", lambda page: [dict(item) for item in page_products])
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", fake_dedupe)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )
    monkeypatch.setattr(
        scrape_runner,
        "normalize_products",
        lambda products, *, source_type, source_value, scraped_at: [
            _product_record(product_url=str(product["resolvedProductUrl"]), title=str(product["title"]), scraped_at=scraped_at)
            for product in products
        ],
    )
    monkeypatch.setattr(
        scrape_runner,
        "filter_products",
        lambda products, groups: (
            list(products),
            [
                {
                    "source_type": product.source_type,
                    "source_value": product.source_value,
                    "title": product.title,
                    "product_url": product.product_url,
                    "filter_decision": "accepted",
                    "filter_stage": "accepted",
                    "reject_groups": "",
                    "reject_terms": "",
                    "reject_fields": "",
                    "warning_groups": "",
                    "warning_terms": "",
                    "warning_fields": "",
                }
                for product in products
            ],
        ),
    )
    monkeypatch.setattr(scrape_runner, "advance_listing_page", lambda page, target_page: False)

    scrape_runner.run_new_scrape(
        manifest=_manifest(tmp_path, pages=1, enrich_detail=False),
        groups=[],
        run_dir=tmp_path,
    )

    state = json.loads((tmp_path / "run_state.json").read_text(encoding="utf-8"))

    assert state["seen_product_keys"] == [
        "https://www.aliexpress.com/item/1002.html",
        "https://www.aliexpress.com/item/1001.html",
        "https://www.aliexpress.com/item/1003.html",
    ]
