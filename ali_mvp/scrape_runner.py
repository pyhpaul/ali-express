from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from .browser import (
    _attach_listing_context,
    advance_listing_page,
    collect_listing_page_products,
    dedupe_listing_products,
    enrich_single_product_detail,
    open_listing_page,
)
from .extractor import normalize_products
from .filtering import FilterGroup, filter_products, load_filter_groups, prefilter_listing_products
from .output import REVIEW_FIELDS, read_csv_rows, write_dict_csv, write_filter_audit_csv, write_products_csv, write_rank_csv
from .proxy_pool import NoHealthyProxyError, ProxyPool
from .review import build_review_rows
from .run_state import RunManifest, RunState, RunStateStore
from .scoring import ProductRecord, aggregate_rank, parse_count, parse_float


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    accepted_count: int
    blocked: bool = False


def run_new_scrape(*, manifest: RunManifest, groups: list[FilterGroup], run_dir: Path) -> RunResult:
    store = RunStateStore(run_dir)
    store.save_manifest(manifest)
    try:
        proxy_pool = ProxyPool.from_manifest(manifest=manifest, run_dir=run_dir)
    except Exception as error:
        failed_state = RunState(status="failed", last_error=str(error))
        store.save_state(failed_state)
        store.save_summary(failed_state)
        _write_outputs(run_dir, [], [])
        return RunResult(exit_code=5, accepted_count=0)

    try:
        page = open_listing_page(
            manifest.url,
            user_data_dir=manifest.user_data_dir,
            port=manifest.port,
            browser_hardening=manifest.browser_hardening,
            proxy=proxy_pool.current(),
            user_agent=manifest.user_agent,
            accept_language=manifest.accept_language,
        )
        return _run_scrape_from_state(
            manifest=manifest,
            groups=groups,
            run_dir=run_dir,
            store=store,
            proxy_pool=proxy_pool,
            page=page,
            state=RunState(status="running"),
            start_page=1,
        )
    finally:
        proxy_pool.close()


def resume_scrape(
    run_dir: Path,
    *,
    details_only: bool = False,
    proxy_override: str = "",
    proxy_file_override: str = "",
    user_agent_override: str = "",
    accept_language_override: str = "",
) -> RunResult:
    store = RunStateStore(run_dir)
    manifest = store.load_manifest()
    state = store.load_state()

    if details_only and not state.pending_detail_queue and state.status == "completed":
        store.save_state(state)
        store.save_summary(state)
        _write_outputs(run_dir, state.accepted_products, state.audit_rows)
        return RunResult(
            exit_code=_completed_exit_code(state.accepted_count),
            accepted_count=state.accepted_count,
            blocked=False,
        )

    if details_only and not state.pending_detail_queue and state.status != "completed":
        failed_details_only_state = replace(
            state,
            last_error="details_only_requested_without_pending_details",
        )
        store.save_state(failed_details_only_state)
        store.save_summary(failed_details_only_state)
        _write_outputs(run_dir, failed_details_only_state.accepted_products, failed_details_only_state.audit_rows)
        return RunResult(
            exit_code=4,
            accepted_count=failed_details_only_state.accepted_count,
            blocked=False,
        )

    effective_proxy = proxy_override or manifest.proxy
    effective_proxy_file = proxy_file_override or manifest.proxy_file
    effective_user_agent = user_agent_override or manifest.user_agent
    effective_accept_language = accept_language_override or manifest.accept_language
    groups = load_filter_groups(manifest.blacklist_file, manifest.reject_keyword)
    proxy_manifest = manifest
    if (
        effective_proxy != manifest.proxy
        or effective_proxy_file != manifest.proxy_file
        or effective_user_agent != manifest.user_agent
        or effective_accept_language != manifest.accept_language
    ):
        proxy_manifest = replace(
            manifest,
            proxy=effective_proxy,
            proxy_file=effective_proxy_file,
            user_agent=effective_user_agent,
            accept_language=effective_accept_language,
        )

    try:
        proxy_pool = ProxyPool.from_manifest(manifest=proxy_manifest, run_dir=run_dir)
    except Exception as error:
        failed_state = replace(state, status="failed", last_error=str(error))
        store.save_state(failed_state)
        store.save_summary(failed_state)
        _write_outputs(run_dir, failed_state.accepted_products, failed_state.audit_rows)
        return RunResult(exit_code=5, accepted_count=failed_state.accepted_count, blocked=False)

    proxy_pool.restore_selection(
        current_key=state.current_proxy_key,
        current_index=state.current_proxy_index,
        block_events=state.block_events_on_current_proxy,
    )

    try:
        page = open_listing_page(
            manifest.url,
            user_data_dir=manifest.user_data_dir,
            port=manifest.port,
            browser_hardening=manifest.browser_hardening,
            proxy=proxy_pool.current(),
            user_agent=effective_user_agent,
            accept_language=effective_accept_language,
        )

        resumed_state = state
        review_context_rows = _load_existing_review_context_rows(run_dir)
        pending_queue = list(state.pending_detail_queue)
        if pending_queue:
            resumed_state, blocked, review_context_rows = _resume_pending_details(
                state=resumed_state,
                pending_queue=pending_queue,
                page=page,
                manifest=manifest,
                groups=groups,
                review_context_rows=review_context_rows,
            )
            resumed_state = _with_proxy_state(resumed_state, proxy_pool)
            store.save_state(resumed_state)
            store.save_summary(resumed_state)
            _write_outputs(
                run_dir,
                resumed_state.accepted_products,
                resumed_state.audit_rows,
                review_context_rows=review_context_rows,
            )
            if blocked:
                return RunResult(
                    exit_code=3,
                    accepted_count=resumed_state.accepted_count,
                    blocked=True,
                )

        if details_only:
            completed_state = _with_proxy_state(replace(resumed_state, status="completed"), proxy_pool)
            store.save_state(completed_state)
            store.save_summary(completed_state)
            _write_outputs(
                run_dir,
                completed_state.accepted_products,
                completed_state.audit_rows,
                review_context_rows=review_context_rows,
            )
            return RunResult(
                exit_code=_completed_exit_code(completed_state.accepted_count),
                accepted_count=completed_state.accepted_count,
                blocked=False,
            )

        return _run_scrape_from_state(
            manifest=manifest,
            groups=groups,
            run_dir=run_dir,
            store=store,
            proxy_pool=proxy_pool,
            page=page,
            state=resumed_state,
            start_page=max(1, resumed_state.current_listing_page + 1),
        )
    finally:
        proxy_pool.close()


def _resume_pending_details(
    *,
    state: RunState,
    pending_queue: list[dict[str, Any]],
    page: object,
    manifest: RunManifest,
    groups: list[FilterGroup],
    review_context_rows: list[dict[str, Any]],
) -> tuple[RunState, bool, list[dict[str, Any]]]:
    accepted_products = list(state.accepted_products)
    audit_rows = list(state.audit_rows)
    normalized_count = state.normalized_count
    completed_products: list[dict[str, Any]] = []
    updated_review_context_rows = list(review_context_rows)

    for index, pending_product in enumerate(pending_queue):
        raw_product = dict(pending_product)
        status = str(raw_product.get("detailStatus") or "")
        if status != "detail_enriched":
            status = enrich_single_product_detail(page, raw_product)
        if status == "captcha_blocked":
            accepted_products, audit_rows, normalized_delta, normalized_rows = _finalize_pending_products(
                manifest=manifest,
                groups=groups,
                accepted_products=accepted_products,
                audit_rows=audit_rows,
                raw_products=completed_products,
            )
            updated_review_context_rows = _merge_review_context_rows(updated_review_context_rows, normalized_rows)
            blocked_queue = [raw_product]
            blocked_queue.extend(dict(item) for item in pending_queue[index + 1 :])
            blocked_state = replace(
                state,
                status="blocked",
                normalized_count=normalized_count + normalized_delta,
                accepted_count=len(accepted_products),
                accepted_products=accepted_products,
                audit_rows=audit_rows,
                pending_detail_queue=blocked_queue,
                last_block_reason="captcha_blocked",
                last_blocked_url=_product_url(raw_product),
            )
            return blocked_state, True, updated_review_context_rows
        completed_products.append(raw_product)

    accepted_products, audit_rows, normalized_delta, normalized_rows = _finalize_pending_products(
        manifest=manifest,
        groups=groups,
        accepted_products=accepted_products,
        audit_rows=audit_rows,
        raw_products=completed_products,
    )
    updated_review_context_rows = _merge_review_context_rows(updated_review_context_rows, normalized_rows)
    resumed_state = replace(
        state,
        status="running",
        normalized_count=normalized_count + normalized_delta,
        accepted_products=accepted_products,
        accepted_count=len(accepted_products),
        audit_rows=audit_rows,
        pending_detail_queue=[],
        last_block_reason="",
        last_blocked_url="",
    )
    return resumed_state, False, updated_review_context_rows


def _rebuild_accepted_products(
    products: list[ProductRecord],
    products_by_url: dict[str, ProductRecord],
) -> list[ProductRecord]:
    return [products_by_url.get(product.product_url, product) for product in products]


def _merge_detail_into_record(record: ProductRecord, product: dict[str, object], status: str) -> ProductRecord:
    return replace(
        record,
        promo_channel=str(product.get("promoChannel", record.promo_channel) or record.promo_channel),
        promotion_text=str(product.get("promotionText", record.promotion_text) or record.promotion_text),
        shop_name=str(product.get("shopName", record.shop_name) or record.shop_name),
        shipping_text=str(product.get("shippingText", record.shipping_text) or record.shipping_text),
        detail_rating=parse_float(str(product.get("detailRatingText") or product.get("detailRating") or record.detail_rating)),
        detail_review_count=parse_count(
            str(product.get("detailReviewText") or product.get("detailReviewCount") or record.detail_review_count)
        ),
        breadcrumb=str(product.get("breadcrumb", record.breadcrumb) or record.breadcrumb),
        attributes_text=str(product.get("attributesText", record.attributes_text) or record.attributes_text),
        description_text=str(product.get("descriptionText", record.description_text) or record.description_text),
        detail_status=str(product.get("detailStatus", status) or status),
    )


def _merge_detail_context_into_records(
    records: list[ProductRecord],
    raw_products: list[dict[str, Any]],
) -> list[ProductRecord]:
    if not records or not raw_products:
        return list(records)

    raw_by_url = {
        product_url: dict(product)
        for product in raw_products
        if (product_url := _product_url(product))
    }
    merged: list[ProductRecord] = []
    for record in records:
        raw_product = raw_by_url.get(record.product_url)
        if raw_product is None:
            merged.append(record)
            continue
        merged.append(_merge_detail_into_record(record, raw_product, record.detail_status))
    return merged


def _run_scrape_from_state(
    *,
    manifest: RunManifest,
    groups: list[FilterGroup],
    run_dir: Path,
    store: RunStateStore,
    proxy_pool: ProxyPool,
    page: object,
    state: RunState,
    start_page: int,
) -> RunResult:
    accepted_products = list(state.accepted_products)
    audit_rows = list(state.audit_rows)
    review_context_rows = _load_existing_review_context_rows(run_dir)
    seen_key_order = list(state.seen_product_keys)
    seen_key_order_index = set(seen_key_order)
    seen_keys = set(seen_key_order)
    raw_products_count = state.raw_products_count
    normalized_count = state.normalized_count
    current_page = max(1, start_page)

    if current_page > 1 and not _move_to_listing_page(page, current_page):
        failed_state = replace(
            state,
            status="failed",
            last_block_reason="listing_page_unreachable",
            last_blocked_url=str(getattr(page, "url", "") or manifest.url),
        )
        store.save_state(failed_state)
        store.save_summary(failed_state)
        _write_outputs(run_dir, failed_state.accepted_products, failed_state.audit_rows)
        return RunResult(exit_code=4, accepted_count=failed_state.accepted_count)

    while len(accepted_products) < manifest.max_items:
        page_products = dedupe_listing_products(collect_listing_page_products(page), seen_keys)
        for product in page_products:
            key = _product_url(product)
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
        pending_detail_queue: list[dict[str, Any]] = []
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
            ready_to_normalize, pending_detail_queue, last_block_reason, last_blocked_url = _enrich_listing_survivors(
                page=page,
                listing_survivors=listing_survivors,
            )
            blocked = bool(pending_detail_queue)

        normalized = normalize_products(
            ready_to_normalize,
            source_type=manifest.source_type,
            source_value=manifest.source_value,
            scraped_at=manifest.created_at,
        )
        normalized = _merge_detail_context_into_records(normalized, ready_to_normalize)
        review_context_rows = _merge_review_context_rows(
            review_context_rows,
            [asdict(product) for product in normalized],
        )
        normalized_count += len(normalized)
        accepted_products, audit_rows = _apply_filtered_products(
            manifest=manifest,
            groups=groups,
            accepted_products=accepted_products,
            audit_rows=audit_rows,
            normalized=normalized,
        )

        checkpoint_state = RunState(
            status="blocked" if blocked else "running",
            current_listing_page=current_page,
            raw_products_count=raw_products_count,
            normalized_count=normalized_count,
            accepted_count=len(accepted_products),
            seen_product_keys=list(seen_key_order),
            accepted_products=list(accepted_products),
            audit_rows=list(audit_rows),
            pending_detail_queue=pending_detail_queue,
            current_proxy_index=proxy_pool.current_index,
            current_proxy_key=proxy_pool.current_key(),
            block_events_on_current_proxy=proxy_pool.block_events_on_current,
            last_block_reason=last_block_reason,
            last_blocked_url=last_blocked_url,
        )
        if blocked:
            proxy_pool.mark_blocked()
            checkpoint_state = replace(
                checkpoint_state,
                current_proxy_index=proxy_pool.current_index,
                current_proxy_key=proxy_pool.current_key(),
                block_events_on_current_proxy=proxy_pool.block_events_on_current,
            )
        store.save_state(checkpoint_state)
        store.save_summary(checkpoint_state)

        if blocked:
            _write_outputs(
                run_dir,
                accepted_products,
                audit_rows,
                review_context_rows=review_context_rows,
            )
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
        pending_detail_queue=[],
        current_proxy_index=proxy_pool.current_index,
        current_proxy_key=proxy_pool.current_key(),
        block_events_on_current_proxy=proxy_pool.block_events_on_current,
        last_block_reason="",
        last_blocked_url="",
    )
    store.save_state(final_state)
    store.save_summary(final_state)
    _write_outputs(
        run_dir,
        accepted_products,
        audit_rows,
        review_context_rows=review_context_rows,
    )
    return RunResult(
        exit_code=_completed_exit_code(len(accepted_products)),
        accepted_count=len(accepted_products),
    )


def _enrich_listing_survivors(
    *,
    page: object,
    listing_survivors: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str]:
    enriched_survivors: list[dict[str, Any]] = []
    for index, product in enumerate(listing_survivors):
        status = enrich_single_product_detail(page, product)
        if status == "captcha_blocked":
            return (
                enriched_survivors,
                [dict(item) for item in listing_survivors[index:]],
                "captcha_blocked",
                _product_url(product),
            )
        enriched_survivors.append(product)
    return enriched_survivors, [], "", ""


def _apply_filtered_products(
    *,
    manifest: RunManifest,
    groups: list[FilterGroup],
    accepted_products: list[ProductRecord],
    audit_rows: list[dict[str, str]],
    normalized: list[ProductRecord],
) -> tuple[list[ProductRecord], list[dict[str, str]]]:
    updated_products = list(accepted_products)
    updated_audit = list(audit_rows)
    page_accepted, page_audit = filter_products(normalized, groups)
    remaining = manifest.max_items - len(updated_products)
    updated_products.extend(page_accepted[:remaining])

    accepted_audit_count = 0
    for row in page_audit:
        if row["filter_decision"] == "accepted":
            if accepted_audit_count >= remaining:
                continue
            accepted_audit_count += 1
        updated_audit.append(row)
    return updated_products, updated_audit


def _finalize_pending_products(
    *,
    manifest: RunManifest,
    groups: list[FilterGroup],
    accepted_products: list[ProductRecord],
    audit_rows: list[dict[str, str]],
    raw_products: list[dict[str, Any]],
) -> tuple[list[ProductRecord], list[dict[str, str]], int, list[dict[str, Any]]]:
    if not raw_products:
        return list(accepted_products), list(audit_rows), 0, []
    normalized = normalize_products(
        raw_products,
        source_type=manifest.source_type,
        source_value=manifest.source_value,
        scraped_at=manifest.created_at,
    )
    normalized = _merge_detail_context_into_records(normalized, raw_products)
    updated_products, updated_audit = _apply_filtered_products(
        manifest=manifest,
        groups=groups,
        accepted_products=accepted_products,
        audit_rows=audit_rows,
        normalized=normalized,
    )
    return updated_products, updated_audit, len(normalized), [asdict(product) for product in normalized]


def _move_to_listing_page(page: object, target_page: int) -> bool:
    if target_page <= 1:
        return True
    for page_number in range(2, target_page + 1):
        if not advance_listing_page(page, page_number):
            return False
    return True


def _product_url(product: dict[str, object]) -> str:
    return str(product.get("resolvedProductUrl") or product.get("url") or "")


def _with_proxy_state(state: RunState, proxy_pool: ProxyPool) -> RunState:
    return replace(
        state,
        current_proxy_index=proxy_pool.current_index,
        current_proxy_key=proxy_pool.current_key(),
        block_events_on_current_proxy=proxy_pool.block_events_on_current,
    )


def _write_outputs(
    run_dir: Path,
    accepted_products: list[ProductRecord],
    audit_rows: list[dict[str, str]],
    *,
    review_context_rows: list[dict[str, Any]] | None = None,
) -> None:
    merged_review_context_rows = _merge_review_context_rows(
        _load_existing_review_context_rows(run_dir),
        review_context_rows if review_context_rows is not None else [asdict(product) for product in accepted_products],
    )
    write_products_csv(run_dir / "products.csv", accepted_products)
    write_filter_audit_csv(run_dir / "products_filter_audit.csv", audit_rows)
    review_rows = build_review_rows(merged_review_context_rows, audit_rows)
    write_dict_csv(run_dir / "products_review.csv", REVIEW_FIELDS, review_rows)
    write_rank_csv(run_dir / "category_rank.csv", aggregate_rank(accepted_products))


def _completed_exit_code(accepted_count: int) -> int:
    return 0 if accepted_count > 0 else 2


def _load_existing_review_context_rows(run_dir: Path) -> list[dict[str, str]]:
    review_path = run_dir / "products_review.csv"
    if not review_path.exists():
        return []
    return read_csv_rows(review_path)


def _merge_review_context_rows(
    existing_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged_by_url: dict[str, dict[str, Any]] = {}
    for row in existing_rows:
        product_url = str(row.get("product_url", "") or "")
        if product_url:
            merged_by_url[product_url] = dict(row)
    for row in new_rows:
        product_url = str(row.get("product_url", "") or "")
        if product_url:
            merged_by_url[product_url] = dict(row)
    return list(merged_by_url.values())
