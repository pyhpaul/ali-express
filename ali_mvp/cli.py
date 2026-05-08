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
