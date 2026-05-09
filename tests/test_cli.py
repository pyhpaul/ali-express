import argparse
from datetime import datetime
from pathlib import Path

import pytest

from ali_mvp.cli import build_output_dir, build_parser


def test_scrape_parser_defaults_pages_to_none():
    parser = build_parser()
    args = parser.parse_args(["scrape", "--keyword", "women dress"])

    assert args.pages is None


def test_scrape_parser_accepts_browser_profile_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "scrape",
            "--keyword",
            "women dress",
            "--max-items",
            "20",
            "--user-data-dir",
            ".browser-profile",
            "--port",
            "9333",
        ]
    )

    assert args.keyword == "women dress"
    assert args.user_data_dir == ".browser-profile"
    assert args.port == 9333


def test_scrape_parser_accepts_pages_option():
    parser = build_parser()
    args = parser.parse_args(["scrape", "--keyword", "women dress", "--pages", "3"])

    assert args.pages == 3


def test_scrape_parser_accepts_enrich_detail_option():
    parser = build_parser()
    args = parser.parse_args(["scrape", "--keyword", "women dress", "--enrich-detail"])

    assert args.enrich_detail is True


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


def test_scrape_parser_rejects_removed_detail_rating_flags():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["scrape", "--keyword", "women dress", "--enrich-detail-rating"])

    with pytest.raises(SystemExit):
        parser.parse_args(["scrape", "--keyword", "women dress", "--detail-limit", "3"])


def test_run_scrape_filters_products_before_writing_outputs(monkeypatch, tmp_path):
    from ali_mvp import cli
    from ali_mvp.scoring import ProductRecord

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

    captured: dict[str, list[object]] = {}

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


def test_build_output_dir_groups_keyword_runs_by_slug_and_timestamp():
    run_at = datetime(2026, 5, 8, 22, 45, 30)

    path = build_output_dir(Path("data"), source_type="keyword", source_value="women dress", run_at=run_at)

    assert path == Path("data") / "women-dress" / "20260508_224530"


def test_build_output_dir_groups_url_runs_under_url_slug():
    run_at = datetime(2026, 5, 8, 22, 45, 30)

    path = build_output_dir(Path("data"), source_type="url", source_value="https://example.test/x", run_at=run_at)

    assert path == Path("data") / "url" / "20260508_224530"


def test_scrape_parser_accepts_category_url_source():
    parser = build_parser()
    args = parser.parse_args(
        [
            "scrape",
            "--category-url",
            "https://www.aliexpress.com/category/100003109/women-clothing.html",
        ]
    )

    assert args.category_url == "https://www.aliexpress.com/category/100003109/women-clothing.html"


def test_build_output_dir_groups_category_url_by_category_slug():
    run_at = datetime(2026, 5, 8, 22, 45, 30)

    path = build_output_dir(
        Path("data"),
        source_type="category",
        source_value="https://www.aliexpress.com/category/100003109/women-clothing.html",
        run_at=run_at,
    )

    assert path == Path("data") / "category-women-clothing" / "20260508_224530"


def test_build_output_dir_falls_back_for_category_url_without_slug():
    run_at = datetime(2026, 5, 8, 22, 45, 30)

    path = build_output_dir(
        Path("data"),
        source_type="category",
        source_value="https://www.aliexpress.com/category/",
        run_at=run_at,
    )

    assert path == Path("data") / "category" / "20260508_224530"
