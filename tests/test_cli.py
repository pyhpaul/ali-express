from datetime import datetime
from pathlib import Path

from ali_mvp.cli import build_output_dir, build_parser


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


def test_scrape_parser_accepts_detail_rating_enrichment_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "scrape",
            "--keyword",
            "women dress",
            "--enrich-detail-rating",
            "--detail-limit",
            "3",
        ]
    )

    assert args.enrich_detail_rating is True
    assert args.detail_limit == 3


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
