from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.parse import quote_plus
from urllib.parse import urlparse

from .filtering import load_filter_groups
from .llm_client import resolve_llm_config
from .llm_review import run_llm_review_for_dir
from .output import read_csv_rows
from . import scrape_runner
from .run_state import RunManifest, RunStateStore


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
    scrape.add_argument(
        "--browser-hardening",
        choices=("off", "minimal"),
        default="minimal",
        help="Apply optional browser pacing/stealth hardening.",
    )
    scrape.add_argument(
        "--proxy-provider",
        choices=("manual", "v2rayn"),
        default="manual",
        help="Proxy provider. Default 'manual' keeps a fixed direct/manual path; 'v2rayn' opt-in enables the sidecar proxy pool.",
    )
    scrape.add_argument(
        "--v2rayn-dir",
        default="",
        help="Root directory of the local v2rayN installation when --proxy-provider v2rayn is used.",
    )
    scrape.add_argument("--proxy", default="", help="Single proxy URL for this run in manual mode.")
    scrape.add_argument("--proxy-file", default="", help="Text file with one proxy per line in manual mode.")
    scrape.add_argument(
        "--max-blocks-per-proxy",
        type=int,
        default=2,
        help="Rotate to the next proxy after this many block events.",
    )
    scrape.add_argument("--user-agent", default="", help="Optional fixed browser user agent for the full run.")
    scrape.add_argument(
        "--accept-language",
        default="en-US,en;q=0.9",
        help="Fixed browser Accept-Language value for the full run.",
    )
    scrape.add_argument(
        "--session-preflight",
        choices=("on", "off"),
        default="on",
        help="Run session preflight checks before scraping.",
    )
    _add_scrape_llm_review_args(scrape)
    scrape.set_defaults(func=run_scrape)
    page_probe = subparsers.add_parser("page-probe", help="Probe pagination with a small raw sample per listing page.")
    probe_source = page_probe.add_mutually_exclusive_group(required=True)
    probe_source.add_argument("--keyword", help="AliExpress search keyword.")
    probe_source.add_argument("--url", help="AliExpress listing or search URL.")
    probe_source.add_argument("--category-url", help="AliExpress category URL.")
    page_probe.add_argument("--pages", type=int, required=True, help="Maximum listing pages to probe.")
    page_probe.add_argument("--per-page-raw-limit", type=int, required=True, help="Maximum raw listing samples kept per page.")
    page_probe.add_argument("--output-dir", default="data/page_probe")
    page_probe.add_argument(
        "--user-data-dir",
        default=".browser-profile",
        help="Persistent Chromium profile directory for manual AliExpress login.",
    )
    page_probe.add_argument("--port", type=int, default=9333, help="Local Chromium remote debugging port.")
    page_probe.add_argument("--enrich-detail", action="store_true", help="Visit sampled product detail pages for enrichment.")
    page_probe.add_argument("--blacklist-file", help="Optional JSON blacklist file used in probe filtering.")
    page_probe.add_argument(
        "--reject-keyword",
        action="append",
        default=[],
        help="Repeatable extra blacklist term added for this probe run.",
    )
    page_probe.add_argument(
        "--browser-hardening",
        choices=("off", "minimal"),
        default="minimal",
        help="Apply optional browser pacing/stealth hardening.",
    )
    page_probe.add_argument("--user-agent", default="", help="Optional fixed browser user agent for the full run.")
    page_probe.add_argument(
        "--accept-language",
        default="en-US,en;q=0.9",
        help="Fixed browser Accept-Language value for the full run.",
    )
    page_probe.add_argument(
        "--session-preflight",
        choices=("on", "off"),
        default="on",
        help="Run session preflight checks before scraping.",
    )
    page_probe.set_defaults(func=run_page_probe)
    postprocess = subparsers.add_parser(
        "postprocess",
        help="Generate zh outputs and review report from an existing run.",
    )
    postprocess.add_argument(
        "--run-dir",
        required=True,
        help="Existing scrape run directory containing products.csv outputs.",
    )
    postprocess.add_argument(
        "--translator",
        choices=("identity", "mymemory"),
        default="identity",
        help="Translation backend for zh outputs.",
    )
    postprocess.add_argument(
        "--translator-email",
        default="",
        help="Optional email sent to MyMemory as the de parameter.",
    )
    postprocess.set_defaults(func=run_postprocess)
    resume = subparsers.add_parser(
        "resume",
        help="Resume a previously blocked scrape run.",
    )
    resume.add_argument(
        "--run-dir",
        required=True,
        help="Existing scrape run directory containing run manifest/state.",
    )
    resume.add_argument(
        "--details-only",
        action="store_true",
        help="Only resume pending detail enrichment without continuing listing collection.",
    )
    resume.add_argument("--proxy", default="", help="Optional proxy override for the resumed run.")
    resume.add_argument("--proxy-file", default="", help="Optional proxy list override for the resumed run.")
    resume.add_argument("--user-agent", default="", help="Optional fixed browser user agent override.")
    resume.add_argument("--accept-language", default="", help="Optional Accept-Language override.")
    resume.set_defaults(func=run_resume)
    llm_review = subparsers.add_parser(
        "llm-review",
        help="Run LLM review scaffolding for an existing run.",
    )
    llm_review.add_argument(
        "--run-dir",
        required=True,
        help="Existing run directory containing scrape outputs.",
    )
    _add_shared_llm_review_args(llm_review)
    llm_review.set_defaults(func=run_llm_review)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def run_postprocess(args: argparse.Namespace) -> int:
    from .postprocess import run_postprocess_for_dir
    from .translation import build_translation_cache_namespace, build_translator

    run_postprocess_for_dir(
        Path(args.run_dir),
        translator=build_translator(args.translator, email=args.translator_email),
        translation_cache_namespace=build_translation_cache_namespace(args.translator),
    )
    print(f"Wrote: {Path(args.run_dir) / 'products_review.csv'}")
    print(f"Wrote: {Path(args.run_dir) / 'products_zh.csv'}")
    print(f"Wrote: {Path(args.run_dir) / 'products_filter_audit_zh.csv'}")
    print(f"Wrote: {Path(args.run_dir) / 'review_only.csv'}")
    print(f"Wrote: {Path(args.run_dir) / 'products_report.html'}")
    return 0


def run_resume(args: argparse.Namespace) -> int:
    result = scrape_runner.resume_scrape(
        Path(args.run_dir),
        details_only=args.details_only,
        proxy_override=args.proxy,
        proxy_file_override=args.proxy_file,
        user_agent_override=args.user_agent,
        accept_language_override=args.accept_language,
    )
    print(f"Resumed run: {Path(args.run_dir)}")
    print(f"Accepted products: {result.accepted_count}")
    return result.exit_code


def run_llm_review(args: argparse.Namespace) -> int:
    _validate_llm_max_items(args)
    run_dir = Path(args.run_dir)
    config = resolve_llm_config(
        run_dir=run_dir,
        base_url=args.llm_base_url,
        api_key=args.llm_api_key,
        model=args.llm_model,
    )
    result = run_llm_review_for_dir(
        run_dir,
        config=config,
        force=args.llm_force,
        max_items=args.llm_max_items,
    )
    print(f"Reviewed rows: {result.reviewed_count}")
    print(f"Skipped rows: {result.skipped_count}")
    print(f"Failed rows: {result.failed_count}")
    print(f"Keep rows: {result.keep_count}")
    print(f"Drop rows: {result.drop_count}")
    print(f"Wrote: {run_dir / 'products_llm_review.csv'}")
    print(f"Wrote: {run_dir / 'products_final_keep.csv'}")
    print(f"Wrote: {run_dir / 'products_final_drop.csv'}")
    print(f"Wrote: {run_dir / 'products_llm_report.html'}")
    return result.exit_code


def run_scrape(args: argparse.Namespace) -> int:
    source_type, source_value, url = _resolve_source(args)
    browser_hardening = getattr(args, "browser_hardening", "minimal")
    proxy_provider = getattr(args, "proxy_provider", "manual")
    v2rayn_dir = getattr(args, "v2rayn_dir", "")
    session_preflight = getattr(args, "session_preflight", "on")
    _validate_llm_max_items(args)
    if args.max_items < 1:
        raise SystemExit("--max-items must be greater than 0")
    if args.pages is not None and args.pages < 1:
        raise SystemExit("--pages must be greater than 0")
    if proxy_provider == "v2rayn" and not v2rayn_dir:
        raise SystemExit("--v2rayn-dir is required when --proxy-provider v2rayn")
    if proxy_provider != "manual" and (args.proxy or args.proxy_file):
        raise SystemExit("--proxy and --proxy-file are only supported with --proxy-provider manual")

    run_at = datetime.now().replace(microsecond=0)
    scraped_at = run_at.astimezone(timezone.utc).isoformat()
    run_dir = build_output_dir(Path(args.output_dir), source_type=source_type, source_value=source_value, run_at=run_at)
    manifest = RunManifest(
        source_type=source_type,
        source_value=source_value,
        url=url,
        max_items=args.max_items,
        pages=args.pages,
        output_dir=str(run_dir),
        user_data_dir=args.user_data_dir,
        port=args.port,
        enrich_detail=args.enrich_detail,
        blacklist_file=args.blacklist_file,
        reject_keyword=list(args.reject_keyword),
        browser_hardening=browser_hardening,
        proxy_provider=proxy_provider,
        v2rayn_dir=v2rayn_dir,
        proxy=args.proxy,
        proxy_file=args.proxy_file,
        max_blocks_per_proxy=args.max_blocks_per_proxy,
        user_agent=args.user_agent,
        accept_language=args.accept_language,
        session_preflight=session_preflight,
        created_at=scraped_at,
    )
    groups = load_filter_groups(args.blacklist_file, args.reject_keyword)

    result = scrape_runner.run_new_scrape(
        manifest=manifest,
        groups=groups,
        run_dir=run_dir,
    )

    state = _load_run_state_if_present(run_dir)
    if state is not None:
        print(f"Scraped raw items: {state.raw_products_count}")
        print(f"Normalized products: {state.normalized_count}")
    print(f"Accepted products: {result.accepted_count}")
    print(f"Wrote: {run_dir / 'products.csv'}")
    print(f"Wrote: {run_dir / 'products_filter_audit.csv'}")
    print(f"Wrote: {run_dir / 'products_review.csv'}")
    print(f"Wrote: {run_dir / 'category_rank.csv'}")
    if result.exit_code == 2:
        print("No accepted products extracted. Check login state, CAPTCHA, selector changes, or blacklist rules.")
    if result.exit_code in (0, 2):
        if not getattr(args, "llm_review", False):
            return result.exit_code
        llm_exit_code = _run_llm_review_after_scrape(run_dir=run_dir, args=args)
        if llm_exit_code is not None:
            return llm_exit_code
        return result.exit_code
    return result.exit_code


def run_page_probe(args: argparse.Namespace) -> int:
    source_type, source_value, url = _resolve_source(args)
    browser_hardening = getattr(args, "browser_hardening", "minimal")
    session_preflight = getattr(args, "session_preflight", "on")
    if args.pages < 1:
        raise SystemExit("--pages must be greater than 0")
    if args.per_page_raw_limit < 1:
        raise SystemExit("--per-page-raw-limit must be greater than 0")

    run_at = datetime.now().replace(microsecond=0)
    run_dir = build_output_dir(Path(args.output_dir), source_type=source_type, source_value=source_value, run_at=run_at)
    groups = load_filter_groups(args.blacklist_file, args.reject_keyword)
    result = scrape_runner.run_page_probe(
        source_type=source_type,
        source_value=source_value,
        url=url,
        pages=args.pages,
        per_page_raw_limit=args.per_page_raw_limit,
        run_dir=run_dir,
        user_data_dir=args.user_data_dir,
        port=args.port,
        enrich_detail=args.enrich_detail,
        groups=groups,
        browser_hardening=browser_hardening,
        blacklist_file=args.blacklist_file,
        reject_keyword=list(args.reject_keyword),
        user_agent=args.user_agent,
        accept_language=args.accept_language,
        session_preflight=session_preflight,
    )
    print(f"Accepted products: {result.accepted_count}")
    print(f"Wrote: {run_dir / 'products.csv'}")
    print(f"Wrote: {run_dir / 'products_filter_audit.csv'}")
    print(f"Wrote: {run_dir / 'products_review.csv'}")
    print(f"Wrote: {run_dir / 'category_rank.csv'}")
    print(f"Wrote: {run_dir / 'page_probe_summary.csv'}")
    return result.exit_code


def _build_search_url(keyword: str) -> str:
    return f"https://www.aliexpress.com/wholesale?SearchText={quote_plus(keyword)}"


def _resolve_source(args: argparse.Namespace) -> tuple[str, str, str]:
    if args.keyword:
        return "keyword", args.keyword, _build_search_url(args.keyword)
    if args.category_url:
        return "category", args.category_url, args.category_url
    return "url", args.url, args.url


def _load_run_state_if_present(run_dir: Path):
    store = RunStateStore(run_dir)
    if not store.state_path.exists():
        return None
    return store.load_state()


def _run_llm_review_after_scrape(*, run_dir: Path, args: argparse.Namespace) -> int | None:
    if not getattr(args, "llm_review", False):
        return None

    review_path = run_dir / "products_review.csv"
    if not review_path.exists():
        print("Skip LLM review: products_review.csv not found.")
        return None
    if not read_csv_rows(review_path):
        print("Skip LLM review: products_review.csv is empty.")
        return None

    llm_args = argparse.Namespace(**vars(args))
    llm_args.run_dir = str(run_dir)
    return run_llm_review(llm_args)


def _add_scrape_llm_review_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--llm-review",
        action="store_true",
        help="Enable LLM review scaffolding after scraping.",
    )
    _add_shared_llm_review_args(parser)


def _add_shared_llm_review_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--llm-base-url", default="", help="Base URL for the configured LLM provider.")
    parser.add_argument("--llm-api-key", default="", help="API key for the configured LLM provider.")
    parser.add_argument("--llm-model", default="", help="Model identifier for the configured LLM provider.")
    parser.add_argument(
        "--llm-force",
        action="store_true",
        help="Force LLM review scaffolding even if prior outputs exist.",
    )
    parser.add_argument(
        "--llm-max-items",
        type=int,
        default=None,
        help="Optional maximum number of items to include in LLM review scaffolding.",
    )


def _validate_llm_max_items(args: argparse.Namespace) -> None:
    llm_max_items = getattr(args, "llm_max_items", None)
    if llm_max_items is not None and llm_max_items < 1:
        raise SystemExit("--llm-max-items must be greater than 0")


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
