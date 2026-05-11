from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .browser import (
    _attach_listing_context,
    advance_listing_page,
    collect_listing_page_products,
    dedupe_listing_products,
    enrich_single_product_detail,
    open_listing_page,
)
from .extractor import normalize_products
from .filtering import FilterGroup, filter_products, prefilter_listing_products
from .output import REVIEW_FIELDS, write_dict_csv, write_filter_audit_csv, write_products_csv, write_rank_csv
from .review import build_review_rows
from .run_state import RunManifest, RunState, RunStateStore
from .scoring import ProductRecord, aggregate_rank


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    accepted_count: int
    blocked: bool = False


def run_new_scrape(*, manifest: RunManifest, groups: list[FilterGroup], run_dir: Path) -> RunResult:
    store = RunStateStore(run_dir)
    store.save_manifest(manifest)

    page = open_listing_page(
        manifest.url,
        user_data_dir=manifest.user_data_dir,
        port=manifest.port,
        browser_hardening=manifest.browser_hardening,
    )

    accepted_products: list[ProductRecord] = []
    audit_rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    seen_key_order: list[str] = []
    seen_key_order_index: set[str] = set()
    current_page = 1
    raw_products_count = 0
    normalized_count = 0

    while len(accepted_products) < manifest.max_items:
        page_products = dedupe_listing_products(collect_listing_page_products(page), seen_keys)
        for product in page_products:
            key = str(product.get("resolvedProductUrl") or product.get("url") or "")
            if key and key not in seen_key_order_index:
                seen_key_order.append(key)
                seen_key_order_index.add(key)
        raw_products_count += len(page_products)
        listing_survivors, listing_audit = prefilter_listing_products(
            page_products,
            groups,
            source_type=manifest.source_type,
            source_value=manifest.source_value,
        )
        audit_rows.extend(listing_audit)

        blocked = False
        pending_detail_queue: list[str] = []
        last_block_reason = ""
        last_blocked_url = ""
        ready_to_normalize = listing_survivors

        if manifest.enrich_detail and listing_survivors:
            _attach_listing_context(
                listing_survivors,
                base_url=manifest.url,
                page_url=str(getattr(page, "url", "") or manifest.url),
                page_number=current_page,
            )
            enriched_survivors: list[dict[str, object]] = []
            blocked_index: int | None = None
            for index, product in enumerate(listing_survivors):
                status = enrich_single_product_detail(page, product)
                if status == "captcha_blocked":
                    blocked = True
                    blocked_index = index
                    last_block_reason = status
                    last_blocked_url = str(product.get("resolvedProductUrl") or product.get("url") or "")
                    if last_blocked_url:
                        pending_detail_queue.append(last_blocked_url)
                    pending_detail_queue.extend(
                        str(item.get("resolvedProductUrl") or item.get("url") or "")
                        for item in listing_survivors[index + 1 :]
                        if str(item.get("resolvedProductUrl") or item.get("url") or "")
                    )
                    break
                enriched_survivors.append(product)
            ready_to_normalize = enriched_survivors

        normalized = normalize_products(
            ready_to_normalize,
            source_type=manifest.source_type,
            source_value=manifest.source_value,
            scraped_at=manifest.created_at,
        )
        normalized_count += len(normalized)
        page_accepted, page_audit = filter_products(normalized, groups)

        remaining = manifest.max_items - len(accepted_products)
        accepted_products.extend(page_accepted[:remaining])

        accepted_audit_count = 0
        for row in page_audit:
            if row["filter_decision"] == "accepted":
                if accepted_audit_count >= remaining:
                    continue
                accepted_audit_count += 1
            audit_rows.append(row)

        state = RunState(
            status="blocked" if blocked else "running",
            current_listing_page=current_page,
            raw_products_count=raw_products_count,
            normalized_count=normalized_count,
            accepted_count=len(accepted_products),
            seen_product_keys=list(seen_key_order),
            accepted_products=list(accepted_products),
            audit_rows=list(audit_rows),
            pending_detail_queue=pending_detail_queue,
            last_block_reason=last_block_reason,
            last_blocked_url=last_blocked_url,
        )
        store.save_state(state)
        store.save_summary(state)

        if blocked:
            _write_outputs(run_dir, accepted_products, audit_rows)
            return RunResult(exit_code=3, accepted_count=len(accepted_products), blocked=True)

        if len(accepted_products) >= manifest.max_items:
            break
        if manifest.pages is not None and current_page >= manifest.pages:
            break
        next_page = current_page + 1
        if not advance_listing_page(page, next_page):
            break
        current_page = next_page

    final_state = RunState(
        status="completed",
        current_listing_page=current_page,
        raw_products_count=raw_products_count,
        normalized_count=normalized_count,
        accepted_count=len(accepted_products),
        seen_product_keys=list(seen_key_order),
        accepted_products=list(accepted_products),
        audit_rows=list(audit_rows),
    )
    store.save_state(final_state)
    store.save_summary(final_state)
    _write_outputs(run_dir, accepted_products, audit_rows)
    return RunResult(exit_code=0, accepted_count=len(accepted_products))


def _write_outputs(run_dir: Path, accepted_products: list[ProductRecord], audit_rows: list[dict[str, str]]) -> None:
    write_products_csv(run_dir / "products.csv", accepted_products)
    write_filter_audit_csv(run_dir / "products_filter_audit.csv", audit_rows)
    review_rows = build_review_rows([asdict(product) for product in accepted_products], audit_rows)
    write_dict_csv(run_dir / "products_review.csv", REVIEW_FIELDS, review_rows)
    write_rank_csv(run_dir / "category_rank.csv", aggregate_rank(accepted_products))
