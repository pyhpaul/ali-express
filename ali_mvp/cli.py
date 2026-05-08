from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.parse import quote_plus
from urllib.parse import urlparse

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
    source.add_argument("--category-url", help="AliExpress category URL.")
    scrape.add_argument("--max-items", type=int, default=80)
    scrape.add_argument("--output-dir", default="data")
    scrape.add_argument(
        "--user-data-dir",
        default=".browser-profile",
        help="Persistent Chromium profile directory for manual AliExpress login.",
    )
    scrape.add_argument("--port", type=int, default=9333, help="Local Chromium remote debugging port.")
    scrape.add_argument(
        "--enrich-detail-rating",
        action="store_true",
        help="Visit a bounded number of product detail pages to fill missing ratings.",
    )
    scrape.add_argument("--detail-limit", type=int, default=5, help="Maximum detail pages to visit for rating enrichment.")
    scrape.set_defaults(func=run_scrape)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def run_scrape(args: argparse.Namespace) -> int:
    source_type, source_value, url = _resolve_source(args)
    if args.max_items < 1:
        raise SystemExit("--max-items must be greater than 0")
    if args.detail_limit < 0:
        raise SystemExit("--detail-limit must be 0 or greater")

    run_at = datetime.now().replace(microsecond=0)
    scraped_at = run_at.astimezone(timezone.utc).isoformat()
    raw_products = collect_raw_products(
        url,
        args.max_items,
        user_data_dir=args.user_data_dir,
        port=args.port,
        enrich_detail_rating=args.enrich_detail_rating,
        detail_limit=args.detail_limit,
    )
    products = normalize_products(
        raw_products,
        source_type=source_type,
        source_value=source_value,
        scraped_at=scraped_at,
    )
    output_dir = build_output_dir(Path(args.output_dir), source_type=source_type, source_value=source_value, run_at=run_at)
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


def _resolve_source(args: argparse.Namespace) -> tuple[str, str, str]:
    if args.keyword:
        return "keyword", args.keyword, _build_search_url(args.keyword)
    if args.category_url:
        return "category", args.category_url, args.category_url
    return "url", args.url, args.url


def build_output_dir(base_dir: Path, *, source_type: str, source_value: str, run_at: datetime) -> Path:
    source_slug = _source_slug(source_type, source_value)
    timestamp = run_at.strftime("%Y%m%d_%H%M%S")
    return base_dir / source_slug / timestamp


def _source_slug(source_type: str, source_value: str) -> str:
    if source_type == "url":
        return "url"
    if source_type == "category":
        return _category_slug(source_value)
    slug = re.sub(r"[^a-z0-9]+", "-", source_value.lower()).strip("-")
    return slug or "keyword"


def _category_slug(category_url: str) -> str:
    path_parts = [part for part in urlparse(category_url).path.split("/") if part]
    if not path_parts:
        return "category"
    candidate = path_parts[-1]
    if candidate.endswith(".html"):
        candidate = candidate[:-5]
    slug = re.sub(r"[^a-z0-9]+", "-", candidate.lower()).strip("-")
    if not slug or slug.isdigit() or slug == "category":
        return "category"
    return f"category-{slug}"
