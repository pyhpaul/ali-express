from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .browser import (
    _attach_listing_context,
    advance_listing_page,
    collect_browser_identity,
    collect_listing_page_products,
    dedupe_listing_products,
    enrich_single_product_detail,
    open_listing_page,
)
from .browser_identity import BrowserIdentityWarning, validate_browser_identity
from .extractor import normalize_products
from .filtering import FilterGroup, filter_products, load_filter_groups, prefilter_listing_products
from .output import (
    REVIEW_FIELDS,
    read_csv_rows,
    write_dict_csv,
    write_filter_audit_csv,
    write_page_probe_summary_csv,
    write_products_csv,
    write_rank_csv,
)
from .proxy_pool import NoHealthyProxyError, ProxyPool
from .review import build_review_rows
from .run_state import RunManifest, RunState, RunStateStore
from .scoring import ProductRecord, aggregate_rank, parse_count, parse_float
from .session_guard import SessionPreflightResult
from .session_guard import run_session_preflight


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    accepted_count: int
    blocked: bool = False
    blocked_proxy_key: str = field(default="", compare=False)


@dataclass(frozen=True)
class PageProbePageSummary:
    listing_page: int
    raw_seen: int
    raw_sampled: int
    normalized: int
    accepted: int
    blocked_reason: str = ""
    blocked_url: str = ""


def run_new_scrape(*, manifest: RunManifest, groups: list[FilterGroup], run_dir: Path) -> RunResult:
    store = RunStateStore(run_dir)
    store.save_manifest(manifest)
    existing_state = store.load_state()
    session_seed_state = RunState(
        status="running",
        session_risk_level=existing_state.session_risk_level,
        last_session_preflight_status=existing_state.last_session_preflight_status,
        consecutive_captcha_count=existing_state.consecutive_captcha_count,
        last_session_ok_at=existing_state.last_session_ok_at,
        cooldown_until=existing_state.cooldown_until,
    )

    if _is_session_cooldown_active(cooldown_until=existing_state.cooldown_until, now_iso=manifest.created_at):
        failed_state = replace(
            session_seed_state,
            status="failed",
            last_error="session_cooldown_active",
            last_block_reason="session_cooldown_active",
            last_blocked_url=manifest.url,
        )
        _save_failed_state(store, failed_state)
        _write_outputs(run_dir, failed_state.accepted_products, failed_state.audit_rows)
        return RunResult(exit_code=6, accepted_count=0, blocked=False)

    try:
        proxy_pool = ProxyPool.from_manifest(manifest=manifest, run_dir=run_dir)
    except Exception as error:
        failed_state = replace(session_seed_state, status="failed", last_error=str(error), identity_warning={})
        _save_failed_state(store, failed_state)
        _write_outputs(run_dir, [], [])
        return RunResult(exit_code=5, accepted_count=0)

    try:
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
        except Exception as error:
            failed_state = replace(session_seed_state, status="failed", last_error=str(error), identity_warning={})
            _save_failed_state(store, failed_state)
            _write_outputs(run_dir, failed_state.accepted_products, failed_state.audit_rows)
            return RunResult(exit_code=5, accepted_count=0, blocked=False)
        identity_warning = _collect_identity_warning(manifest=manifest, page=page)
        session_seed_state = _with_identity_warning(session_seed_state, identity_warning)
        preflight = _resolve_session_preflight(manifest=manifest, page=page)
        if preflight is None:
            running_state = replace(session_seed_state, status="running", last_session_preflight_status="skipped")
        else:
            running_state = _next_session_state(
                existing=session_seed_state,
                preflight_status=preflight.status,
                risk_level=preflight.risk_level,
                now_iso=manifest.created_at,
            )
        if preflight is not None and preflight.status != "ready":
            failed_state = replace(
                running_state,
                status="failed",
                last_error=preflight.status,
                last_block_reason=preflight.status,
                last_blocked_url=str(getattr(page, "url", "") or manifest.url),
            )
            _save_failed_state(store, failed_state)
            _write_outputs(run_dir, failed_state.accepted_products, failed_state.audit_rows)
            return RunResult(exit_code=6, accepted_count=failed_state.accepted_count, blocked=False)
        store.save_state(running_state)
        store.save_summary(running_state)
        result = _run_scrape_from_state(
            manifest=manifest,
            groups=groups,
            run_dir=run_dir,
            store=store,
            proxy_pool=proxy_pool,
            page=page,
            state=running_state,
            start_page=1,
        )
        _record_proxy_health(
            proxy_pool=proxy_pool,
            state=store.load_state(),
            blocked=result.blocked,
            proxy_key=result.blocked_proxy_key,
        )
        return result
    finally:
        proxy_pool.close()


def run_page_probe(
    *,
    source_type: str,
    source_value: str,
    url: str,
    pages: int,
    per_page_raw_limit: int,
    run_dir: Path,
    user_data_dir: str,
    port: int,
    enrich_detail: bool,
    groups: list[FilterGroup],
    browser_hardening: str,
    blacklist_file: str | None,
    reject_keyword: list[str],
    user_agent: str,
    accept_language: str,
    session_preflight: str,
) -> RunResult:
    page = open_listing_page(
        url,
        user_data_dir=user_data_dir,
        port=port,
        browser_hardening=browser_hardening,
        user_agent=user_agent,
        accept_language=accept_language,
    )
    accepted_products: list[ProductRecord] = []
    audit_rows: list[dict[str, str]] = []
    review_context_rows: list[dict[str, Any]] = []
    page_summaries: list[PageProbePageSummary] = []
    seen_keys: set[str] = set()
    blocked = False
    scraped_at = _utc_now_iso()
    unlimited_manifest = RunManifest(
        source_type=source_type,
        source_value=source_value,
        url=url,
        max_items=10**9,
        pages=pages,
        output_dir=str(run_dir),
        user_data_dir=user_data_dir,
        port=port,
        enrich_detail=enrich_detail,
        blacklist_file=blacklist_file,
        reject_keyword=list(reject_keyword),
        browser_hardening=browser_hardening,
        user_agent=user_agent,
        accept_language=accept_language,
        session_preflight=session_preflight,
        created_at=scraped_at,
    )

    for current_page in range(1, pages + 1):
        page_products = dedupe_listing_products(collect_listing_page_products(page), seen_keys)
        raw_seen = len(page_products)
        sampled_products = [dict(item) for item in page_products[:per_page_raw_limit]]
        listing_survivors, listing_audit = prefilter_listing_products(
            sampled_products,
            groups,
            source_type=source_type,
            source_value=source_value,
        )
        audit_rows.extend(listing_audit)

        blocked_reason = ""
        blocked_url = ""
        ready_to_normalize = listing_survivors
        if enrich_detail and listing_survivors:
            _attach_listing_context(
                listing_survivors,
                base_url=url,
                page_url=str(getattr(page, "url", "") or url),
                page_number=current_page,
            )
            ready_to_normalize, pending_detail_queue, blocked_reason, blocked_url = _enrich_listing_survivors(
                page=page,
                listing_survivors=listing_survivors,
            )
            blocked = bool(pending_detail_queue)

        normalized = normalize_products(
            ready_to_normalize,
            source_type=source_type,
            source_value=source_value,
            scraped_at=scraped_at,
        )
        normalized = _merge_detail_context_into_records(normalized, ready_to_normalize)
        review_context_rows = _merge_review_context_rows(
            review_context_rows,
            [asdict(product) for product in normalized],
        )
        accepted_before = len(accepted_products)
        accepted_products, audit_rows = _apply_filtered_products(
            manifest=unlimited_manifest,
            groups=groups,
            accepted_products=accepted_products,
            audit_rows=audit_rows,
            normalized=normalized,
        )
        page_summaries.append(
            PageProbePageSummary(
                listing_page=current_page,
                raw_seen=raw_seen,
                raw_sampled=len(sampled_products),
                normalized=len(normalized),
                accepted=len(accepted_products) - accepted_before,
                blocked_reason=blocked_reason,
                blocked_url=blocked_url,
            )
        )
        if blocked:
            break
        if current_page >= pages:
            break
        if not advance_listing_page(page, current_page + 1):
            break

    _write_outputs(
        run_dir,
        accepted_products,
        audit_rows,
        review_context_rows=review_context_rows,
    )
    write_page_probe_summary_csv(
        run_dir / "page_probe_summary.csv",
        [
            {
                "listing_page": row.listing_page,
                "raw_seen": row.raw_seen,
                "raw_sampled": row.raw_sampled,
                "normalized": row.normalized,
                "accepted": row.accepted,
                "blocked_reason": row.blocked_reason,
                "blocked_url": row.blocked_url,
            }
            for row in page_summaries
        ],
    )
    return RunResult(
        exit_code=3 if blocked else _completed_exit_code(len(accepted_products)),
        accepted_count=len(accepted_products),
        blocked=blocked,
    )


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
        failed_state = replace(state, status="failed", last_error=str(error), identity_warning={})
        _save_failed_state(store, failed_state)
        _write_outputs(run_dir, failed_state.accepted_products, failed_state.audit_rows)
        return RunResult(exit_code=5, accepted_count=failed_state.accepted_count, blocked=False)

    proxy_pool.restore_selection(
        current_key=state.current_proxy_key,
        current_index=state.current_proxy_index,
        block_events=state.block_events_on_current_proxy,
    )

    try:
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
        except Exception as error:
            failed_state = replace(state, status="failed", last_error=str(error), identity_warning={})
            _save_failed_state(store, failed_state)
            _write_outputs(run_dir, failed_state.accepted_products, failed_state.audit_rows)
            return RunResult(exit_code=5, accepted_count=failed_state.accepted_count, blocked=False)
        identity_warning = _collect_identity_warning(manifest=proxy_manifest, page=page)

        resumed_state = _with_identity_warning(state, identity_warning)
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
                _record_proxy_health(
                    proxy_pool=proxy_pool,
                    state=resumed_state,
                    blocked=True,
                    proxy_key=proxy_pool.current_key(),
                )
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
            _record_proxy_health(proxy_pool=proxy_pool, state=completed_state, blocked=False)
            return RunResult(
                exit_code=_completed_exit_code(completed_state.accepted_count),
                accepted_count=completed_state.accepted_count,
                blocked=False,
            )

        result = _run_scrape_from_state(
            manifest=manifest,
            groups=groups,
            run_dir=run_dir,
            store=store,
            proxy_pool=proxy_pool,
            page=page,
            state=resumed_state,
            start_page=max(1, resumed_state.current_listing_page + 1),
        )
        _record_proxy_health(
            proxy_pool=proxy_pool,
            state=store.load_state(),
            blocked=result.blocked,
            proxy_key=result.blocked_proxy_key,
        )
        return result
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
                _with_session_fields(state, state),
                status="blocked",
                normalized_count=normalized_count + normalized_delta,
                accepted_count=len(accepted_products),
                accepted_products=accepted_products,
                audit_rows=audit_rows,
                pending_detail_queue=blocked_queue,
                last_block_reason="captcha_blocked",
                last_blocked_url=_product_url(raw_product),
                captcha_diagnostic=_blocked_captcha_diagnostic(
                    existing=state.captcha_diagnostic,
                    blocked_product=raw_product,
                ),
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
        _with_session_fields(state, state),
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
            _with_session_fields(state, state),
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

        checkpoint_state = _with_session_fields(
            state,
            RunState(
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
                captcha_diagnostic=_blocked_captcha_diagnostic(
                    existing=state.captcha_diagnostic,
                    blocked_product=pending_detail_queue[0] if pending_detail_queue else None,
                ),
            ),
        )
        if blocked:
            blocked_proxy_key = proxy_pool.current_key()
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
            return RunResult(
                exit_code=3,
                accepted_count=len(accepted_products),
                blocked=True,
                blocked_proxy_key=blocked_proxy_key,
            )

        if len(accepted_products) >= manifest.max_items:
            break
        if manifest.pages is not None and current_page >= manifest.pages:
            break
        next_page = current_page + 1
        if not advance_listing_page(page, next_page):
            break
        current_page = next_page

    final_state = _with_session_fields(
        state,
        RunState(
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
        ),
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


def _save_failed_state(store: RunStateStore, state: RunState) -> None:
    store.save_state(state)
    store.save_summary(state)
    if not state.last_error:
        return
    summary = store.load_summary()
    summary["last_error"] = state.last_error
    with store.summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)


def _next_session_state(*, existing: RunState, preflight_status: str, risk_level: str, now_iso: str) -> RunState:
    consecutive_captcha_count = existing.consecutive_captcha_count
    cooldown_until = existing.cooldown_until
    last_session_ok_at = existing.last_session_ok_at

    if preflight_status == "ready":
        consecutive_captcha_count = 0
        cooldown_until = ""
        last_session_ok_at = now_iso
    elif preflight_status == "captcha_blocked":
        consecutive_captcha_count += 1
        next_cooldown = _add_minutes(now_iso, 30 if consecutive_captcha_count == 1 else 120)
        if next_cooldown:
            cooldown_until = next_cooldown

    return replace(
        existing,
        session_risk_level=risk_level,
        last_session_preflight_status=preflight_status,
        consecutive_captcha_count=consecutive_captcha_count,
        last_session_ok_at=last_session_ok_at,
        cooldown_until=cooldown_until,
    )


def _add_minutes(now_iso: str, minutes: int) -> str:
    if not now_iso:
        return ""
    current = _parse_iso_utc(now_iso)
    if current is None:
        return ""
    scheduled = current + timedelta(minutes=minutes)
    return scheduled.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_session_cooldown_active(*, cooldown_until: str, now_iso: str) -> bool:
    if not cooldown_until or not now_iso:
        return False
    cooldown_at = _parse_iso_utc(cooldown_until)
    now_at = _parse_iso_utc(now_iso)
    if cooldown_at is None or now_at is None:
        return False
    return cooldown_at > now_at


def _parse_iso_utc(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _with_session_fields(existing: RunState, updated: RunState) -> RunState:
    return replace(
        updated,
        session_risk_level=existing.session_risk_level,
        last_session_preflight_status=existing.last_session_preflight_status,
        consecutive_captcha_count=existing.consecutive_captcha_count,
        last_session_ok_at=existing.last_session_ok_at,
        cooldown_until=existing.cooldown_until,
        identity_warning=dict(existing.identity_warning),
        captcha_diagnostic=dict(existing.captcha_diagnostic),
    )


def _blocked_captcha_diagnostic(*, existing: dict[str, Any], blocked_product: dict[str, Any] | None) -> dict[str, Any]:
    if blocked_product is not None:
        diagnostic = blocked_product.get("_captchaDiagnostic")
        if isinstance(diagnostic, dict):
            return dict(diagnostic)
    return dict(existing)


def _collect_identity_warning(*, manifest: RunManifest, page: object) -> BrowserIdentityWarning | None:
    identity = collect_browser_identity(page)
    return validate_browser_identity(
        configured_user_agent=manifest.user_agent,
        configured_accept_language=manifest.accept_language,
        effective_user_agent=str(identity.get("user_agent") or ""),
        effective_language=str(identity.get("language") or ""),
        effective_languages=[str(item) for item in identity.get("languages", [])] if isinstance(identity.get("languages"), list) else [],
    )


def _with_identity_warning(state: RunState, warning: BrowserIdentityWarning | None) -> RunState:
    if warning is None:
        return replace(state, identity_warning={})
    return replace(
        state,
        identity_warning={
            "code": warning.code,
            "configured": dict(warning.configured),
            "effective": dict(warning.effective),
        },
    )


def _resolve_session_preflight(*, manifest: RunManifest, page: object) -> SessionPreflightResult | None:
    if manifest.session_preflight != "on":
        return None
    return run_session_preflight(page, search_url=manifest.url, warm_up=True)


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


def _record_proxy_health(*, proxy_pool: ProxyPool, state: RunState, blocked: bool, proxy_key: str = "") -> None:
    record_event = getattr(proxy_pool, "record_event", None)
    if record_event is None:
        return
    event = _proxy_health_event_for_state(state=state, blocked=blocked, blocked_proxy_key=proxy_key)
    if not event:
        return
    now_iso = _utc_now_iso()
    record_event(event, now_iso=now_iso, proxy_key=proxy_key)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _proxy_health_event_for_state(*, state: RunState, blocked: bool, blocked_proxy_key: str) -> str:
    if blocked and blocked_proxy_key:
        return "captcha"
    if state.status == "completed":
        return "success"
    if not state.last_error:
        return ""

    last_error = state.last_error.lower()
    timeout_markers = (
        "timeout",
        "timed out",
        "proxy disconnected",
        "connection reset",
        "connection refused",
        "socket",
    )
    if any(marker in last_error for marker in timeout_markers):
        return "timeout"
    return ""


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
