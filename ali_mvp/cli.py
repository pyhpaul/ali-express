from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.parse import quote_plus
from urllib.parse import urlparse

from .browser import (
    _attach_listing_context,
    advance_listing_page,
    collect_listing_page_products,
    collect_raw_products,
    dedupe_listing_products,
    enrich_listing_products,
    open_listing_page,
)
from .extractor import normalize_products
from .filtering import FilterGroup, filter_products, load_filter_groups, prefilter_listing_products
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


def _collect_products_with_blacklist(
    *,
    url: str,
    max_items: int,
    source_type: str,
    source_value: str,
    scraped_at: str,
    groups: list[FilterGroup],
    user_data_dir: str,
    port: int,
    enrich_detail: bool,
    pages: int | None,
) -> tuple[list[object], list[dict[str, str]], int, int]:
    page = open_listing_page(url, user_data_dir=user_data_dir, port=port)
    accepted_products = []
    audit_rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    current_page = 1
    raw_products_count = 0
    normalized_count = 0

    while len(accepted_products) < max_items:
        current_raw = collect_listing_page_products(page)
        page_products = dedupe_listing_products(current_raw, seen_keys)
        raw_products_count += len(page_products)
        listing_survivors, listing_audit = prefilter_listing_products(
            page_products,
            groups,
            source_type=source_type,
            source_value=source_value,
        )
        audit_rows.extend(listing_audit)

        if enrich_detail and listing_survivors:
            _attach_listing_context(
                listing_survivors,
                base_url=url,
                page_url=str(getattr(page, "url", "") or url),
                page_number=current_page,
            )
            enrich_listing_products(page, listing_survivors)

        normalized = normalize_products(
            listing_survivors,
            source_type=source_type,
            source_value=source_value,
            scraped_at=scraped_at,
        )
        normalized_count += len(normalized)
        page_accepted, page_audit = filter_products(normalized, groups)

        remaining = max_items - len(accepted_products)
        accepted_products.extend(page_accepted[:remaining])

        accepted_audit_count = 0
        for row in page_audit:
            if row["filter_decision"] == "accepted":
                if accepted_audit_count >= remaining:
                    continue
                accepted_audit_count += 1
            audit_rows.append(row)

        if len(accepted_products) >= max_items:
            break
        if pages is not None and current_page >= pages:
            break
        next_page = current_page + 1
        if not advance_listing_page(page, next_page):
            break
        current_page = next_page

    return accepted_products, audit_rows, raw_products_count, normalized_count


def run_scrape(args: argparse.Namespace) -> int:
    source_type, source_value, url = _resolve_source(args)
    if args.max_items < 1:
        raise SystemExit("--max-items must be greater than 0")
    if args.pages is not None and args.pages < 1:
        raise SystemExit("--pages must be greater than 0")

    run_at = datetime.now().replace(microsecond=0)
    scraped_at = run_at.astimezone(timezone.utc).isoformat()
    groups = load_filter_groups(args.blacklist_file, args.reject_keyword)

    if groups:
        accepted_products, audit_rows, raw_products_count, normalized_count = _collect_products_with_blacklist(
            url=url,
            max_items=args.max_items,
            source_type=source_type,
            source_value=source_value,
            scraped_at=scraped_at,
            groups=groups,
            user_data_dir=args.user_data_dir,
            port=args.port,
            enrich_detail=args.enrich_detail,
            pages=args.pages,
        )
    else:
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
        accepted_products, audit_rows = filter_products(products, groups)
        raw_products_count = len(raw_products)
        normalized_count = len(products)

    output_dir = build_output_dir(Path(args.output_dir), source_type=source_type, source_value=source_value, run_at=run_at)
    write_products_csv(output_dir / "products.csv", accepted_products)
    write_filter_audit_csv(output_dir / "products_filter_audit.csv", audit_rows)
    write_rank_csv(output_dir / "category_rank.csv", aggregate_rank(accepted_products))

    print(f"Scraped raw items: {raw_products_count}")
    print(f"Normalized products: {normalized_count}")
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
