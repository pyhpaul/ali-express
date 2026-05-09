from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.parse import quote_plus
from urllib.parse import urlparse

from .browser import collect_raw_products
from .extractor import normalize_products
from .filtering import filter_products, load_filter_groups
from .output import write_filter_audit_csv, write_products_csv, write_rank_csv
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
        "--enrich-detail",
        action="store_true",
        help="Visit each final product detail page and enrich products.csv with detail fields.",
    )
    scrape.add_argument(
        "--pages",
        type=int,
        default=None,
        help="Maximum listing pages to visit. Omit to auto-advance until --max-items is reached or no next page is available.",
    )
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
    if args.pages is not None and args.pages < 1:
        raise SystemExit("--pages must be greater than 0")

    run_at = datetime.now().replace(microsecond=0)
    scraped_at = run_at.astimezone(timezone.utc).isoformat()
    raw_products = collect_raw_products(
        url,
        args.max_items,
        user_data_dir=args.user_data_dir,
        port=args.port,
        enrich_detail=args.enrich_detail,
        pages=args.pages,
    )
    products = normalize_products(
        raw_products,
        source_type=source_type,
        source_value=source_value,
        scraped_at=scraped_at,
    )
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
