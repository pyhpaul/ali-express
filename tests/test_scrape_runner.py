from __future__ import annotations

import json
from dataclasses import asdict, replace
from importlib import import_module

import pytest

from ali_mvp.filtering import FilterGroup
from ali_mvp.output import read_csv_rows
from ali_mvp.run_state import RunManifest
from ali_mvp.scoring import ProductRecord
from ali_mvp.session_guard import SessionPreflightResult


def _manifest(tmp_path, *, pages: int | None = 1, enrich_detail: bool = True) -> RunManifest:
    return RunManifest(
        source_type="keyword",
        source_value="women dress",
        url="https://www.aliexpress.com/wholesale?SearchText=women+dress",
        max_items=20,
        pages=pages,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=enrich_detail,
        blacklist_file=None,
        reject_keyword=[],
        browser_hardening="minimal",
        created_at="2026-05-11T08:00:00Z",
    )


def _product_record(*, product_url: str, title: str, scraped_at: str = "2026-05-11T08:00:00Z") -> ProductRecord:
    return ProductRecord(
        source_type="keyword",
        source_value="women dress",
        title=title,
        price="$12.50",
        sold_count=100,
        rating=4.8,
        review_count=20,
        product_url=product_url,
        search_card_url=product_url,
        image_url=f"{product_url}.jpg",
        entry_type="item_card",
        is_promoted=False,
        promo_channel="",
        promotion_text="",
        promo_landing_url="",
        shop_name="Example Store",
        shipping_text="Free shipping",
        detail_rating=4.9,
        detail_review_count=25,
        breadcrumb="Home > Dresses",
        attributes_text='{"Material":"Cotton"}',
        description_text="Long sleeve dress",
        scraped_at=scraped_at,
        detail_status="detail_enriched",
    )


@pytest.fixture(autouse=True)
def _default_ready_session_preflight(monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    monkeypatch.setattr(
        scrape_runner,
        "run_session_preflight",
        lambda page, search_url, warm_up: SessionPreflightResult(
            status="ready",
            risk_level="low",
            page_type="search",
            reasons=[],
            warmed_up=bool(warm_up),
        ),
    )


def test_run_new_scrape_marks_blocked_run_and_writes_outputs(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    manifest = _manifest(tmp_path, pages=1, enrich_detail=True)

    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress"

    raw_product = {
        "title": "Dress A",
        "url": "https://www.aliexpress.com/item/1001.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
    }

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", lambda page: [dict(raw_product)])
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", lambda products, seen_keys: products)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )

    def fake_detail(page, product):
        product["detailStatus"] = "captcha_blocked"
        return "captcha_blocked"

    monkeypatch.setattr(scrape_runner, "enrich_single_product_detail", fake_detail)
    monkeypatch.setattr(scrape_runner, "advance_listing_page", lambda page, target_page: False)

    result = scrape_runner.run_new_scrape(
        manifest=manifest,
        groups=[FilterGroup(name="cli_extra")],
        run_dir=tmp_path,
    )

    assert result == scrape_runner.RunResult(exit_code=3, accepted_count=0, blocked=True)

    state = json.loads((tmp_path / "run_state.json").read_text(encoding="utf-8"))
    summary = json.loads((tmp_path / "run_summary.json").read_text(encoding="utf-8"))

    assert state["status"] == "blocked"
    assert state["last_block_reason"] == "captcha_blocked"
    assert state["last_blocked_url"] == "https://www.aliexpress.com/item/1001.html"
    assert state["pending_detail_queue"] == [
        {
            "title": "Dress A",
            "url": "https://www.aliexpress.com/item/1001.html",
            "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
            "detailStatus": "captcha_blocked",
            "_listingBaseUrl": manifest.url,
            "_listingPageUrl": "https://www.aliexpress.com/wholesale?SearchText=women+dress",
            "_listingPageNumber": 1,
        }
    ]
    assert summary["resume_recommended"] is True

    assert (tmp_path / "products.csv").exists()
    assert (tmp_path / "products_filter_audit.csv").exists()
    assert (tmp_path / "products_review.csv").exists()
    assert (tmp_path / "category_rank.csv").exists()


def test_run_new_scrape_stops_when_session_preflight_reports_phone_verification(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")

    class FakePage:
        url = "https://login.aliexpress.com/phone"

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(
        scrape_runner,
        "run_session_preflight",
        lambda page, search_url, warm_up: SessionPreflightResult(
            status="phone_verification_required",
            risk_level="high",
            page_type="verify",
            reasons=["phone_verification_required"],
            warmed_up=False,
        ),
    )

    result = scrape_runner.run_new_scrape(
        manifest=_manifest(tmp_path, pages=1, enrich_detail=False),
        groups=[],
        run_dir=tmp_path,
    )

    assert result == scrape_runner.RunResult(exit_code=6, accepted_count=0, blocked=False)
    state = json.loads((tmp_path / "run_state.json").read_text(encoding="utf-8"))
    summary = json.loads((tmp_path / "run_summary.json").read_text(encoding="utf-8"))

    assert state["status"] == "failed"
    assert state["last_error"] == "phone_verification_required"
    assert state["last_block_reason"] == "phone_verification_required"
    assert state["last_blocked_url"] == "https://login.aliexpress.com/phone"
    assert summary["status"] == "failed"
    assert summary["last_error"] == "phone_verification_required"
    assert summary["last_block_reason"] == "phone_verification_required"
    assert summary["last_blocked_url"] == "https://login.aliexpress.com/phone"
    assert (tmp_path / "products.csv").exists()
    assert (tmp_path / "products_filter_audit.csv").exists()
    assert (tmp_path / "products_review.csv").exists()
    assert (tmp_path / "category_rank.csv").exists()


def test_run_new_scrape_updates_captcha_cooldown_after_preflight_block(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    class FakePage:
        url = "https://www.aliexpress.com/verify"

    store = RunStateStore(tmp_path)
    store.save_state(
        RunState(
            status="failed",
            session_risk_level="high",
            last_session_preflight_status="captcha_blocked",
            consecutive_captcha_count=1,
            last_session_ok_at="2026-05-11T07:00:00Z",
            cooldown_until="2026-05-11T07:30:00Z",
        )
    )

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(
        scrape_runner,
        "run_session_preflight",
        lambda page, search_url, warm_up: SessionPreflightResult(
            status="captcha_blocked",
            risk_level="high",
            page_type="verify",
            reasons=["captcha"],
            warmed_up=False,
        ),
    )

    scrape_runner.run_new_scrape(
        manifest=_manifest(tmp_path, pages=1, enrich_detail=False),
        groups=[],
        run_dir=tmp_path,
    )

    state = scrape_runner.RunStateStore(tmp_path).load_state()
    assert state.session_risk_level == "high"
    assert state.last_session_preflight_status == "captcha_blocked"
    assert state.consecutive_captcha_count == 2
    assert state.cooldown_until == "2026-05-11T10:00:00Z"


def test_run_new_scrape_fails_fast_when_session_cooldown_is_active(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = _manifest(tmp_path, pages=1, enrich_detail=False)
    store = RunStateStore(tmp_path)
    store.save_state(
        RunState(
            status="failed",
            session_risk_level="high",
            last_session_preflight_status="captcha_blocked",
            consecutive_captcha_count=1,
            cooldown_until="2026-05-11T08:30:00Z",
            identity_warning={
                "code": "user_agent_major_mismatch",
                "configured": {"user_agent_major": 124},
                "effective": {"user_agent_major": 126},
            },
        )
    )

    opened = {"value": False}

    def fake_open_listing_page(*args, **kwargs):
        opened["value"] = True
        return object()

    monkeypatch.setattr(scrape_runner, "open_listing_page", fake_open_listing_page)

    result = scrape_runner.run_new_scrape(
        manifest=manifest,
        groups=[],
        run_dir=tmp_path,
    )

    state = store.load_state()

    assert result == scrape_runner.RunResult(exit_code=6, accepted_count=0, blocked=False)
    assert opened["value"] is False
    assert state.status == "failed"
    assert state.last_error == "session_cooldown_active"
    assert state.last_block_reason == "session_cooldown_active"
    assert state.last_blocked_url == manifest.url
    assert state.consecutive_captcha_count == 1
    assert state.cooldown_until == "2026-05-11T08:30:00Z"
    assert state.last_session_preflight_status == "captcha_blocked"
    assert state.identity_warning == {}


def test_run_new_scrape_skips_session_preflight_when_manifest_turns_it_off(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = replace(_manifest(tmp_path, pages=1, enrich_detail=False), session_preflight="off")
    store = RunStateStore(tmp_path)
    store.save_state(
        RunState(
            status="failed",
            session_risk_level="high",
            last_session_preflight_status="captcha_blocked",
            consecutive_captcha_count=2,
            last_session_ok_at="2026-05-11T07:00:00Z",
            cooldown_until="2026-05-11T07:30:00Z",
        )
    )

    class FakePage:
        url = manifest.url

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(
        scrape_runner,
        "run_session_preflight",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    monkeypatch.setattr(
        scrape_runner,
        "_run_scrape_from_state",
        lambda **kwargs: scrape_runner.RunResult(exit_code=0, accepted_count=0, blocked=False),
    )

    result = scrape_runner.run_new_scrape(
        manifest=manifest,
        groups=[],
        run_dir=tmp_path,
    )

    state = store.load_state()

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=0, blocked=False)
    assert state.last_session_preflight_status == "skipped"
    assert state.consecutive_captcha_count == 2
    assert state.cooldown_until == "2026-05-11T07:30:00Z"
    assert state.session_risk_level == "high"


def test_run_new_scrape_persists_identity_warning_without_reusing_last_error(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.browser_identity import BrowserIdentityWarning
    from ali_mvp.run_state import RunStateStore

    manifest = _manifest(tmp_path, pages=1, enrich_detail=False)

    class FakePage:
        url = manifest.url

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(
        scrape_runner,
        "collect_browser_identity",
        lambda page: {
            "user_agent": "effective-ua",
            "language": "en-US",
            "languages": ["en-US", "en"],
        },
    )
    monkeypatch.setattr(
        scrape_runner,
        "validate_browser_identity",
        lambda **kwargs: BrowserIdentityWarning(
            code="user_agent_major_mismatch",
            configured={"user_agent_major": 124},
            effective={"user_agent_major": 126},
        ),
    )
    monkeypatch.setattr(
        scrape_runner,
        "_run_scrape_from_state",
        lambda **kwargs: scrape_runner.RunResult(exit_code=0, accepted_count=0, blocked=False),
    )

    result = scrape_runner.run_new_scrape(
        manifest=manifest,
        groups=[],
        run_dir=tmp_path,
    )

    store = RunStateStore(tmp_path)
    state = store.load_state()
    summary = store.load_summary()

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=0, blocked=False)
    assert state.last_error == ""
    assert summary.get("last_error", "") == ""
    assert state.identity_warning == {
        "code": "user_agent_major_mismatch",
        "configured": {"user_agent_major": 124},
        "effective": {"user_agent_major": 126},
    }
    assert summary["identity_warning"] == {
        "code": "user_agent_major_mismatch",
        "configured": {"user_agent_major": 124},
        "effective": {"user_agent_major": 126},
    }


def test_run_new_scrape_keeps_existing_cooldown_when_created_at_is_invalid_for_captcha(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = replace(_manifest(tmp_path, pages=1, enrich_detail=False), created_at="not-a-timestamp")

    class FakePage:
        url = "https://www.aliexpress.com/verify"

    store = RunStateStore(tmp_path)
    store.save_state(
        RunState(
            status="failed",
            session_risk_level="high",
            last_session_preflight_status="captcha_blocked",
            consecutive_captcha_count=1,
            cooldown_until="2026-05-11T09:00:00Z",
        )
    )

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(
        scrape_runner,
        "run_session_preflight",
        lambda page, search_url, warm_up: SessionPreflightResult(
            status="captcha_blocked",
            risk_level="high",
            page_type="verify",
            reasons=["captcha"],
            warmed_up=False,
        ),
    )

    result = scrape_runner.run_new_scrape(
        manifest=manifest,
        groups=[],
        run_dir=tmp_path,
    )

    state = store.load_state()

    assert result == scrape_runner.RunResult(exit_code=6, accepted_count=0, blocked=False)
    assert state.consecutive_captcha_count == 2
    assert state.cooldown_until == "2026-05-11T09:00:00Z"


def test_run_new_scrape_completed_state_preserves_session_ready_fields(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunStateStore

    manifest = _manifest(tmp_path, pages=1, enrich_detail=False)

    class FakePage:
        url = manifest.url

    raw_product = {
        "title": "Dress Session",
        "url": "https://www.aliexpress.com/item/1012.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/1012.html",
    }

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", lambda page: [dict(raw_product)])
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", lambda products, seen_keys: products)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )
    monkeypatch.setattr(
        scrape_runner,
        "normalize_products",
        lambda products, *, source_type, source_value, scraped_at: [
            _product_record(
                product_url=str(product["resolvedProductUrl"]),
                title=str(product["title"]),
                scraped_at=scraped_at,
            )
            for product in products
        ],
    )
    monkeypatch.setattr(
        scrape_runner,
        "filter_products",
        lambda products, groups: (
            list(products),
            [
                {
                    "source_type": product.source_type,
                    "source_value": product.source_value,
                    "title": product.title,
                    "product_url": product.product_url,
                    "filter_decision": "accepted",
                    "filter_stage": "accepted",
                    "reject_groups": "",
                    "reject_terms": "",
                    "reject_fields": "",
                    "warning_groups": "",
                    "warning_terms": "",
                    "warning_fields": "",
                }
                for product in products
            ],
        ),
    )

    result = scrape_runner.run_new_scrape(
        manifest=manifest,
        groups=[],
        run_dir=tmp_path,
    )

    state = RunStateStore(tmp_path).load_state()

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=1, blocked=False)
    assert state.status == "completed"
    assert state.last_session_preflight_status == "ready"
    assert state.last_session_ok_at == manifest.created_at


def test_run_new_scrape_fails_when_v2rayn_provider_has_no_healthy_proxy(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.proxy_pool import NoHealthyProxyError
    from ali_mvp.run_state import RunStateStore

    manifest = RunManifest(
        source_type="keyword",
        source_value="pump part",
        url="https://www.aliexpress.com/wholesale?SearchText=pump+part",
        max_items=20,
        pages=None,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        blacklist_file=None,
        proxy_provider="v2rayn",
        v2rayn_dir="C:/Users/test/v2rayN",
    )
    monkeypatch.setattr(
        "ali_mvp.scrape_runner.ProxyPool.from_manifest",
        lambda **kwargs: (_ for _ in ()).throw(NoHealthyProxyError("no healthy proxy")),
    )

    result = scrape_runner.run_new_scrape(manifest=manifest, groups=[], run_dir=tmp_path)
    state = RunStateStore(tmp_path).load_state()

    assert result.exit_code == 5
    assert state.status == "failed"
    assert state.last_error == "no healthy proxy"


def test_run_new_scrape_fails_when_provider_bootstrap_raises_generic_error(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = RunManifest(
        source_type="keyword",
        source_value="pump part",
        url="https://www.aliexpress.com/wholesale?SearchText=pump+part",
        max_items=20,
        pages=None,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        blacklist_file=None,
        proxy_provider="v2rayn",
        v2rayn_dir="C:/Users/test/v2rayN",
    )
    store = RunStateStore(tmp_path)
    store.save_state(
        RunState(
            status="failed",
            session_risk_level="high",
            last_session_preflight_status="captcha_blocked",
            consecutive_captcha_count=2,
            cooldown_until="2026-05-11T10:00:00Z",
            identity_warning={
                "code": "user_agent_major_mismatch",
                "configured": {"user_agent_major": 124},
                "effective": {"user_agent_major": 126},
            },
        )
    )
    monkeypatch.setattr(
        "ali_mvp.scrape_runner.ProxyPool.from_manifest",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing xray.exe")),
    )

    result = scrape_runner.run_new_scrape(manifest=manifest, groups=[], run_dir=tmp_path)
    state = store.load_state()

    assert result.exit_code == 5
    assert state.status == "failed"
    assert state.last_error == "missing xray.exe"
    assert state.last_session_preflight_status == "captcha_blocked"
    assert state.consecutive_captcha_count == 2
    assert state.cooldown_until == "2026-05-11T10:00:00Z"
    assert state.identity_warning == {}


def test_run_new_scrape_persists_failed_state_when_browser_open_fails_and_clears_warning(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = _manifest(tmp_path, pages=1, enrich_detail=False)
    store = RunStateStore(tmp_path)
    store.save_state(
        RunState(
            status="failed",
            identity_warning={
                "code": "user_agent_major_mismatch",
                "configured": {"user_agent_major": 124},
                "effective": {"user_agent_major": 126},
            },
        )
    )

    monkeypatch.setattr(
        scrape_runner,
        "open_listing_page",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("browser failed to start")),
    )

    result = scrape_runner.run_new_scrape(
        manifest=manifest,
        groups=[],
        run_dir=tmp_path,
    )

    state = store.load_state()
    summary = store.load_summary()

    assert result == scrape_runner.RunResult(exit_code=5, accepted_count=0, blocked=False)
    assert state.status == "failed"
    assert state.last_error == "browser failed to start"
    assert state.identity_warning == {}
    assert summary["status"] == "failed"
    assert summary["last_error"] == "browser failed to start"
    assert "identity_warning" not in summary


def test_resume_scrape_restores_saved_proxy_selection_without_live_hot_swap(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    store = RunStateStore(tmp_path)
    manifest = RunManifest(
        source_type="keyword",
        source_value="pump part",
        url="https://www.aliexpress.com/wholesale?SearchText=pump+part",
        max_items=20,
        pages=None,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        blacklist_file=None,
        proxy_provider="v2rayn",
        v2rayn_dir="C:/Users/test/v2rayN",
    )
    store.save_manifest(manifest)
    store.save_state(
        RunState(
            status="blocked",
            current_proxy_index=1,
            current_proxy_key="node-b",
            pending_detail_queue=[
                {
                    "title": "Dress Pending",
                    "url": "https://www.aliexpress.com/item/1999.html",
                    "cardUrl": "https://www.aliexpress.com/item/1999.html",
                    "resolvedProductUrl": "https://www.aliexpress.com/item/1999.html",
                    "_listingBaseUrl": manifest.url,
                    "_listingPageUrl": manifest.url,
                    "_listingPageNumber": 1,
                }
            ],
        )
    )

    seen = {"restore": None, "closed": False, "open_calls": 0, "opened_proxy": "", "mark_blocked_calls": 0}

    class FakePage:
        url = manifest.url

    class FakePool:
        def __init__(self):
            self.proxies = ["socks5://127.0.0.1:11081", "socks5://127.0.0.1:11082"]
            self.keys = ["node-a", "node-b"]
            self.current_index = 0
            self.block_events_on_current = 0

        def restore_selection(self, *, current_key, current_index, block_events):
            seen["restore"] = (current_key, current_index, block_events)
            if current_key in self.keys:
                self.current_index = self.keys.index(current_key)
            else:
                self.current_index = current_index
            self.block_events_on_current = block_events

        def current(self):
            return self.proxies[self.current_index]

        def current_key(self):
            return self.keys[self.current_index]

        def close(self):
            seen["closed"] = True

        def mark_blocked(self):
            seen["mark_blocked_calls"] += 1
            return self.current()

    monkeypatch.setattr("ali_mvp.scrape_runner.ProxyPool.from_manifest", lambda **kwargs: FakePool())
    def fake_open_listing_page(*args, **kwargs):
        seen["open_calls"] += 1
        seen["opened_proxy"] = str(kwargs.get("proxy") or "")
        return FakePage()

    monkeypatch.setattr(scrape_runner, "open_listing_page", fake_open_listing_page)
    monkeypatch.setattr(
        scrape_runner,
        "enrich_single_product_detail",
        lambda page, product: product.__setitem__("detailStatus", "detail_enriched") or "detail_enriched",
    )

    result = scrape_runner.resume_scrape(tmp_path, details_only=True)
    resumed_state = store.load_state()

    assert result.exit_code == 0
    assert seen["restore"] == ("node-b", 1, 0)
    assert seen["open_calls"] == 1
    assert seen["opened_proxy"] == "socks5://127.0.0.1:11082"
    assert resumed_state.current_proxy_index == 1
    assert resumed_state.current_proxy_key == "node-b"
    assert resumed_state.block_events_on_current_proxy == 0
    assert seen["mark_blocked_calls"] == 0
    assert seen["closed"] is True


def test_resume_scrape_fails_when_v2rayn_provider_has_no_healthy_proxy(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.proxy_pool import NoHealthyProxyError
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = RunManifest(
        source_type="keyword",
        source_value="pump part",
        url="https://www.aliexpress.com/wholesale?SearchText=pump+part",
        max_items=20,
        pages=None,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        blacklist_file=None,
        proxy_provider="v2rayn",
        v2rayn_dir="C:/Users/test/v2rayN",
    )
    existing_product = _product_record(
        product_url="https://www.aliexpress.com/item/2401.html",
        title="Dress Resume",
        scraped_at="2026-05-11T08:00:00Z",
    )
    state = RunState(
        status="blocked",
        current_listing_page=1,
        raw_products_count=1,
        normalized_count=1,
        accepted_count=1,
        seen_product_keys=[existing_product.product_url],
        accepted_products=[existing_product],
        audit_rows=[],
        pending_detail_queue=[],
        current_proxy_index=1,
        current_proxy_key="node-b",
        block_events_on_current_proxy=1,
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    monkeypatch.setattr(
        "ali_mvp.scrape_runner.ProxyPool.from_manifest",
        lambda **kwargs: (_ for _ in ()).throw(NoHealthyProxyError("no healthy proxy")),
    )

    result = scrape_runner.resume_scrape(tmp_path, details_only=False)
    failed_state = store.load_state()

    assert result == scrape_runner.RunResult(exit_code=5, accepted_count=1, blocked=False)
    assert failed_state.status == "failed"
    assert failed_state.last_error == "no healthy proxy"
    assert failed_state.accepted_count == 1
    assert failed_state.accepted_products == [existing_product]


def test_resume_scrape_fails_when_provider_bootstrap_raises_generic_error(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = RunManifest(
        source_type="keyword",
        source_value="pump part",
        url="https://www.aliexpress.com/wholesale?SearchText=pump+part",
        max_items=20,
        pages=None,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        blacklist_file=None,
        proxy_provider="v2rayn",
        v2rayn_dir="C:/Users/test/v2rayN",
    )
    existing_product = _product_record(
        product_url="https://www.aliexpress.com/item/2405.html",
        title="Dress Resume Generic Error",
        scraped_at="2026-05-11T08:00:00Z",
    )
    existing_audit = [
        {
            "source_type": manifest.source_type,
            "source_value": manifest.source_value,
            "title": existing_product.title,
            "product_url": existing_product.product_url,
            "filter_decision": "accepted",
            "filter_stage": "detail",
            "reject_groups": "",
            "reject_terms": "",
            "reject_fields": "",
            "warning_groups": "",
            "warning_terms": "",
            "warning_fields": "",
        }
    ]
    state = RunState(
        status="blocked",
        current_listing_page=1,
        raw_products_count=1,
        normalized_count=1,
        accepted_count=1,
        seen_product_keys=[existing_product.product_url],
        accepted_products=[existing_product],
        audit_rows=existing_audit,
        pending_detail_queue=[],
        current_proxy_index=1,
        current_proxy_key="node-b",
        block_events_on_current_proxy=1,
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    monkeypatch.setattr(
        "ali_mvp.scrape_runner.ProxyPool.from_manifest",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing xray.exe")),
    )

    result = scrape_runner.resume_scrape(tmp_path, details_only=False)
    failed_state = store.load_state()

    assert result == scrape_runner.RunResult(exit_code=5, accepted_count=1, blocked=False)
    assert failed_state.status == "failed"
    assert failed_state.last_error == "missing xray.exe"
    assert failed_state.accepted_count == 1
    assert failed_state.accepted_products == [existing_product]
    assert failed_state.audit_rows == existing_audit


def test_resume_scrape_details_only_completed_short_circuits_before_provider(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = _manifest(tmp_path, pages=2, enrich_detail=True)
    existing_product = _product_record(
        product_url="https://www.aliexpress.com/item/2402.html",
        title="Dress Done",
        scraped_at=manifest.created_at,
    )
    state = RunState(
        status="completed",
        current_listing_page=2,
        raw_products_count=1,
        normalized_count=1,
        accepted_count=1,
        seen_product_keys=[existing_product.product_url],
        accepted_products=[existing_product],
        audit_rows=[],
        pending_detail_queue=[],
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    monkeypatch.setattr(
        "ali_mvp.scrape_runner.ProxyPool.from_manifest",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("provider should not be created")),
    )

    result = scrape_runner.resume_scrape(tmp_path, details_only=True)

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=1, blocked=False)


def test_resume_scrape_persists_restored_proxy_state_after_pending_details(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = RunManifest(
        source_type="keyword",
        source_value="pump part",
        url="https://www.aliexpress.com/wholesale?SearchText=pump+part",
        max_items=20,
        pages=None,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=True,
        blacklist_file=None,
        proxy_provider="v2rayn",
        v2rayn_dir="C:/Users/test/v2rayN",
        created_at="2026-05-11T08:00:00Z",
    )
    pending_product = {
        "title": "Dress Pending",
        "url": "https://www.aliexpress.com/item/2403.html",
        "cardUrl": "https://www.aliexpress.com/item/2403.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/2403.html",
        "_listingBaseUrl": manifest.url,
        "_listingPageUrl": manifest.url,
        "_listingPageNumber": 1,
    }
    state = RunState(
        status="blocked",
        current_listing_page=1,
        raw_products_count=1,
        normalized_count=0,
        accepted_count=0,
        seen_product_keys=[pending_product["resolvedProductUrl"]],
        accepted_products=[],
        audit_rows=[],
        pending_detail_queue=[dict(pending_product)],
        current_proxy_index=0,
        current_proxy_key="node-a",
        block_events_on_current_proxy=0,
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    class FakePage:
        url = manifest.url

    class FakePool:
        def __init__(self):
            self.current_index = 1
            self.block_events_on_current = 0

        def restore_selection(self, *, current_key, current_index, block_events):
            self.current_index = 1
            self.block_events_on_current = 0

        def current(self):
            return "socks5://127.0.0.1:11082"

        def current_key(self):
            return "node-b"

        def close(self):
            return None

    def fake_detail(page, product):
        product["detailStatus"] = "detail_enriched"
        return "detail_enriched"

    monkeypatch.setattr("ali_mvp.scrape_runner.ProxyPool.from_manifest", lambda **kwargs: FakePool())
    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "enrich_single_product_detail", fake_detail)

    result = scrape_runner.resume_scrape(tmp_path, details_only=True)
    resumed_state = store.load_state()

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=1, blocked=False)
    assert resumed_state.current_proxy_index == 1
    assert resumed_state.current_proxy_key == "node-b"
    assert resumed_state.block_events_on_current_proxy == 0


def test_run_new_scrape_persists_proxy_progress_and_browser_identity_on_block(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    proxy_file = tmp_path / "proxies.txt"
    proxy_file.write_text("http://proxy-a:8080\nhttp://proxy-b:8080\n", encoding="utf-8")
    manifest = replace(
        _manifest(tmp_path, pages=1, enrich_detail=True),
        proxy_file=str(proxy_file),
        max_blocks_per_proxy=1,
        user_agent="ua-fixed",
        accept_language="en-US,en;q=0.9",
    )

    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress"

    open_kwargs: list[dict[str, object]] = []
    raw_product = {
        "title": "Dress Proxy",
        "url": "https://www.aliexpress.com/item/1011.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/1011.html",
    }

    def fake_open_listing_page(url, **kwargs):
        open_kwargs.append({"url": url, **kwargs})
        return FakePage()

    def fake_detail(page, product):
        product["detailStatus"] = "captcha_blocked"
        return "captcha_blocked"

    monkeypatch.setattr(scrape_runner, "open_listing_page", fake_open_listing_page)
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", lambda page: [dict(raw_product)])
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", lambda products, seen_keys: products)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )
    monkeypatch.setattr(scrape_runner, "enrich_single_product_detail", fake_detail)

    result = scrape_runner.run_new_scrape(
        manifest=manifest,
        groups=[],
        run_dir=tmp_path,
    )

    state = json.loads((tmp_path / "run_state.json").read_text(encoding="utf-8"))

    assert result == scrape_runner.RunResult(exit_code=3, accepted_count=0, blocked=True)
    assert open_kwargs == [
        {
            "url": manifest.url,
            "user_data_dir": manifest.user_data_dir,
            "port": manifest.port,
            "browser_hardening": manifest.browser_hardening,
            "proxy": "http://proxy-a:8080",
            "user_agent": "ua-fixed",
            "accept_language": "en-US,en;q=0.9",
        }
    ]
    assert state["current_proxy_index"] == 1
    assert state["block_events_on_current_proxy"] == 0


def test_run_new_scrape_checkpoints_across_multiple_pages(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")

    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress"

    pages = {
        1: [
            {
                "title": "Dress A",
                "url": "https://www.aliexpress.com/item/1001.html",
                "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
            }
        ],
        2: [
            {
                "title": "Dress B",
                "url": "https://www.aliexpress.com/item/1002.html",
                "resolvedProductUrl": "https://www.aliexpress.com/item/1002.html",
            }
        ],
    }
    current_page = {"value": 1}

    def fake_collect(page):
        return [dict(item) for item in pages[current_page["value"]]]

    def fake_dedupe(products, seen_keys):
        unique = []
        for product in products:
            key = product["resolvedProductUrl"]
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(product)
        return unique

    def fake_advance(page, target_page):
        if target_page > 2:
            return False
        current_page["value"] = target_page
        return True

    def fake_normalize(products, *, source_type, source_value, scraped_at):
        return [
            _product_record(
                product_url=str(product["resolvedProductUrl"]),
                title=str(product["title"]),
                scraped_at=scraped_at,
            )
            for product in products
        ]

    def fake_filter(products, groups):
        return (
            list(products),
            [
                {
                    "source_type": product.source_type,
                    "source_value": product.source_value,
                    "title": product.title,
                    "product_url": product.product_url,
                    "filter_decision": "accepted",
                    "filter_stage": "accepted",
                    "reject_groups": "",
                    "reject_terms": "",
                    "reject_fields": "",
                    "warning_groups": "",
                    "warning_terms": "",
                    "warning_fields": "",
                }
                for product in products
            ],
        )

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", fake_collect)
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", fake_dedupe)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )
    monkeypatch.setattr(scrape_runner, "normalize_products", fake_normalize)
    monkeypatch.setattr(scrape_runner, "filter_products", fake_filter)
    monkeypatch.setattr(scrape_runner, "advance_listing_page", fake_advance)

    result = scrape_runner.run_new_scrape(
        manifest=_manifest(tmp_path, pages=2, enrich_detail=False),
        groups=[],
        run_dir=tmp_path,
    )

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=2, blocked=False)

    state = json.loads((tmp_path / "run_state.json").read_text(encoding="utf-8"))
    summary = json.loads((tmp_path / "run_summary.json").read_text(encoding="utf-8"))

    assert state["status"] == "completed"
    assert state["current_listing_page"] == 2
    assert state["accepted_count"] == 2
    assert state["seen_product_keys"] == [
        "https://www.aliexpress.com/item/1001.html",
        "https://www.aliexpress.com/item/1002.html",
    ]
    assert len(state["audit_rows"]) == 2
    assert len(state["accepted_products"]) == 2
    assert state["accepted_products"][0] == asdict(_product_record(product_url="https://www.aliexpress.com/item/1001.html", title="Dress A"))
    assert summary["status"] == "completed"
    assert summary["resume_recommended"] is False


def test_run_page_probe_samples_each_page_and_continues_until_page_limit(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")

    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress"

    pages = {
        1: [
            {"title": "Dress A1", "url": "https://www.aliexpress.com/item/1001.html", "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html"},
            {"title": "Dress A2", "url": "https://www.aliexpress.com/item/1002.html", "resolvedProductUrl": "https://www.aliexpress.com/item/1002.html"},
            {"title": "Dress A3", "url": "https://www.aliexpress.com/item/1003.html", "resolvedProductUrl": "https://www.aliexpress.com/item/1003.html"},
        ],
        2: [
            {"title": "Dress B1", "url": "https://www.aliexpress.com/item/2001.html", "resolvedProductUrl": "https://www.aliexpress.com/item/2001.html"},
            {"title": "Dress B2", "url": "https://www.aliexpress.com/item/2002.html", "resolvedProductUrl": "https://www.aliexpress.com/item/2002.html"},
            {"title": "Dress B3", "url": "https://www.aliexpress.com/item/2003.html", "resolvedProductUrl": "https://www.aliexpress.com/item/2003.html"},
        ],
    }
    current_page = {"value": 1}
    advanced: list[int] = []

    def fake_collect(page):
        return [dict(item) for item in pages[current_page["value"]]]

    def fake_advance(page, target_page):
        advanced.append(target_page)
        current_page["value"] = target_page
        return True

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", fake_collect)
    monkeypatch.setattr(scrape_runner, "advance_listing_page", fake_advance)
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", lambda products, seen_keys: products)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )
    monkeypatch.setattr(scrape_runner, "normalize_products", lambda raw_products, *, source_type, source_value, scraped_at: [])
    monkeypatch.setattr(scrape_runner, "filter_products", lambda normalized, groups: ([], []))

    result = scrape_runner.run_page_probe(
        source_type="keyword",
        source_value="home appliance accessories",
        url="https://example.test",
        pages=2,
        per_page_raw_limit=2,
        run_dir=tmp_path,
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        groups=[],
        browser_hardening="minimal",
        blacklist_file=None,
        reject_keyword=[],
        user_agent="",
        accept_language="en-US,en;q=0.9",
        session_preflight="off",
    )

    assert result == scrape_runner.RunResult(exit_code=2, accepted_count=0, blocked=False)
    assert advanced == [2]

    rows = read_csv_rows(tmp_path / "page_probe_summary.csv")
    assert rows == [
        {
            "listing_page": "1",
            "raw_seen": "3",
            "raw_sampled": "2",
            "normalized": "0",
            "accepted": "0",
            "blocked_reason": "",
            "blocked_url": "",
        },
        {
            "listing_page": "2",
            "raw_seen": "3",
            "raw_sampled": "2",
            "normalized": "0",
            "accepted": "0",
            "blocked_reason": "",
            "blocked_url": "",
        },
    ]


def test_run_new_scrape_attaches_listing_context_before_detail_enrich(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")

    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress&page=2"

    raw_product = {
        "title": "Dress A",
        "url": "https://www.aliexpress.com/item/1001.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
    }
    seen_contexts: list[dict[str, object]] = []

    def fake_enrich(page, product):
        seen_contexts.append(
            {
                "_listingBaseUrl": product.get("_listingBaseUrl"),
                "_listingPageUrl": product.get("_listingPageUrl"),
                "_listingPageNumber": product.get("_listingPageNumber"),
            }
        )
        return "detail_enriched"

    def fake_attach(products, *, base_url, page_url, page_number):
        for product in products:
            product["_listingBaseUrl"] = base_url
            product["_listingPageUrl"] = page_url
            product["_listingPageNumber"] = page_number

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", lambda page: [dict(raw_product)])
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", lambda products, seen_keys: products)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )
    monkeypatch.setattr(scrape_runner, "_attach_listing_context", fake_attach)
    monkeypatch.setattr(scrape_runner, "enrich_single_product_detail", fake_enrich)
    monkeypatch.setattr(
        scrape_runner,
        "normalize_products",
        lambda products, *, source_type, source_value, scraped_at: [
            _product_record(product_url=str(product["resolvedProductUrl"]), title=str(product["title"]), scraped_at=scraped_at)
            for product in products
        ],
    )
    monkeypatch.setattr(
        scrape_runner,
        "filter_products",
        lambda products, groups: (
            list(products),
            [
                {
                    "source_type": product.source_type,
                    "source_value": product.source_value,
                    "title": product.title,
                    "product_url": product.product_url,
                    "filter_decision": "accepted",
                    "filter_stage": "accepted",
                    "reject_groups": "",
                    "reject_terms": "",
                    "reject_fields": "",
                    "warning_groups": "",
                    "warning_terms": "",
                    "warning_fields": "",
                }
                for product in products
            ],
        ),
    )
    monkeypatch.setattr(scrape_runner, "advance_listing_page", lambda page, target_page: False)

    manifest = _manifest(tmp_path, pages=2, enrich_detail=True)
    result = scrape_runner.run_new_scrape(
        manifest=manifest,
        groups=[],
        run_dir=tmp_path,
    )

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=1, blocked=False)
    assert seen_contexts == [
        {
            "_listingBaseUrl": manifest.url,
            "_listingPageUrl": "https://www.aliexpress.com/wholesale?SearchText=women+dress&page=2",
            "_listingPageNumber": 1,
        }
    ]


def test_run_new_scrape_returns_exit_code_2_when_no_products_are_accepted(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")

    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress"

    raw_product = {
        "title": "Dress Reject",
        "url": "https://www.aliexpress.com/item/1009.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/1009.html",
    }

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", lambda page: [dict(raw_product)])
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", lambda products, seen_keys: products)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )
    monkeypatch.setattr(
        scrape_runner,
        "normalize_products",
        lambda products, *, source_type, source_value, scraped_at: [
            _product_record(product_url=str(product["resolvedProductUrl"]), title=str(product["title"]), scraped_at=scraped_at)
            for product in products
        ],
    )
    monkeypatch.setattr(
        scrape_runner,
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
                    "filter_stage": "detail_post_enrich",
                    "reject_groups": "manual_blacklist",
                    "reject_terms": "dress",
                    "reject_fields": "title",
                    "warning_groups": "",
                    "warning_terms": "",
                    "warning_fields": "",
                }
                for product in products
            ],
        ),
    )
    monkeypatch.setattr(scrape_runner, "advance_listing_page", lambda page, target_page: False)

    result = scrape_runner.run_new_scrape(
        manifest=_manifest(tmp_path, pages=1, enrich_detail=False),
        groups=[],
        run_dir=tmp_path,
    )

    summary = json.loads((tmp_path / "run_summary.json").read_text(encoding="utf-8"))

    assert result == scrape_runner.RunResult(exit_code=2, accepted_count=0, blocked=False)
    assert summary["status"] == "completed"
    assert summary["accepted_count"] == 0


def test_run_new_scrape_writes_review_context_for_detail_rejections(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    manifest = _manifest(tmp_path, pages=1, enrich_detail=True)

    class FakePage:
        url = manifest.url

    raw_product = {
        "title": "Dress Reject",
        "url": "https://www.aliexpress.com/item/1010.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/1010.html",
    }

    def fake_detail(page, product):
        product["detailStatus"] = "detail_enriched"
        product["attributesText"] = '{"Material":"Silk"}'
        product["descriptionText"] = "Rejected detail context"
        return "detail_enriched"

    def fake_normalize(products, *, source_type, source_value, scraped_at):
        return [
            _product_record(
                product_url=str(product["resolvedProductUrl"]),
                title=str(product["title"]),
                scraped_at=scraped_at,
            )
            for product in products
        ]

    def fake_filter(products, groups):
        assert len(products) == 1
        product = products[0]
        rejected = replace(
            product,
            attributes_text='{"Material":"Silk"}',
            description_text="Rejected detail context",
            detail_status="detail_enriched",
        )
        return (
            [],
            [
                {
                    "source_type": rejected.source_type,
                    "source_value": rejected.source_value,
                    "title": rejected.title,
                    "product_url": rejected.product_url,
                    "filter_decision": "rejected",
                    "filter_stage": "detail_post_enrich",
                    "reject_groups": "manual_blacklist",
                    "reject_terms": "silk",
                    "reject_fields": "attributes_text",
                    "warning_groups": "",
                    "warning_terms": "",
                    "warning_fields": "",
                }
            ],
        )

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", lambda page: [dict(raw_product)])
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", lambda products, seen_keys: products)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )
    monkeypatch.setattr(scrape_runner, "enrich_single_product_detail", fake_detail)
    monkeypatch.setattr(scrape_runner, "normalize_products", fake_normalize)
    monkeypatch.setattr(scrape_runner, "filter_products", fake_filter)
    monkeypatch.setattr(scrape_runner, "advance_listing_page", lambda page, target_page: False)

    result = scrape_runner.run_new_scrape(
        manifest=manifest,
        groups=[],
        run_dir=tmp_path,
    )

    review_rows = read_csv_rows(tmp_path / "products_review.csv")

    assert result == scrape_runner.RunResult(exit_code=2, accepted_count=0, blocked=False)
    assert review_rows == [
        {
            "source_type": "keyword",
            "source_value": "women dress",
            "title": "Dress Reject",
            "product_url": "https://www.aliexpress.com/item/1010.html",
            "image_url": "https://www.aliexpress.com/item/1010.html.jpg",
            "price": "$12.50",
            "search_card_url": "https://www.aliexpress.com/item/1010.html",
            "entry_type": "item_card",
            "is_promoted": "False",
            "promo_channel": "",
            "promotion_text": "",
            "shop_name": "Example Store",
            "shipping_text": "Free shipping",
            "attributes_text": '{"Material":"Silk"}',
            "description_text": "Rejected detail context",
            "detail_status": "detail_enriched",
            "filter_decision": "rejected",
            "filter_stage": "detail_post_enrich",
            "reject_groups": "manual_blacklist",
            "reject_terms": "silk",
            "reject_fields": "attributes_text",
            "warning_groups": "",
            "warning_terms": "",
            "warning_fields": "",
        }
    ]


def test_run_new_scrape_preserves_seen_product_key_order_with_multiple_new_items_on_one_page(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")

    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress"

    page_products = [
        {
            "title": "Dress B",
            "url": "https://www.aliexpress.com/item/1002.html",
            "resolvedProductUrl": "https://www.aliexpress.com/item/1002.html",
        },
        {
            "title": "Dress A",
            "url": "https://www.aliexpress.com/item/1001.html",
            "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
        },
        {
            "title": "Dress C",
            "url": "https://www.aliexpress.com/item/1003.html",
            "resolvedProductUrl": "https://www.aliexpress.com/item/1003.html",
        },
    ]

    def fake_dedupe(products, seen_keys):
        unique = []
        for product in products:
            key = str(product["resolvedProductUrl"])
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(product)
        return unique

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", lambda page: [dict(item) for item in page_products])
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", fake_dedupe)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )
    monkeypatch.setattr(
        scrape_runner,
        "normalize_products",
        lambda products, *, source_type, source_value, scraped_at: [
            _product_record(product_url=str(product["resolvedProductUrl"]), title=str(product["title"]), scraped_at=scraped_at)
            for product in products
        ],
    )
    monkeypatch.setattr(
        scrape_runner,
        "filter_products",
        lambda products, groups: (
            list(products),
            [
                {
                    "source_type": product.source_type,
                    "source_value": product.source_value,
                    "title": product.title,
                    "product_url": product.product_url,
                    "filter_decision": "accepted",
                    "filter_stage": "accepted",
                    "reject_groups": "",
                    "reject_terms": "",
                    "reject_fields": "",
                    "warning_groups": "",
                    "warning_terms": "",
                    "warning_fields": "",
                }
                for product in products
            ],
        ),
    )
    monkeypatch.setattr(scrape_runner, "advance_listing_page", lambda page, target_page: False)

    scrape_runner.run_new_scrape(
        manifest=_manifest(tmp_path, pages=1, enrich_detail=False),
        groups=[],
        run_dir=tmp_path,
    )

    state = json.loads((tmp_path / "run_state.json").read_text(encoding="utf-8"))

    assert state["seen_product_keys"] == [
        "https://www.aliexpress.com/item/1002.html",
        "https://www.aliexpress.com/item/1001.html",
        "https://www.aliexpress.com/item/1003.html",
    ]


def test_resume_scrape_continues_after_current_listing_page_without_restarting_page_one(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = _manifest(tmp_path, pages=3, enrich_detail=False)
    existing_product = _product_record(
        product_url="https://www.aliexpress.com/item/2001.html",
        title="Dress A",
        scraped_at=manifest.created_at,
    )
    state = RunState(
        status="blocked",
        current_listing_page=2,
        raw_products_count=1,
        normalized_count=1,
        accepted_count=1,
        seen_product_keys=[existing_product.product_url],
        accepted_products=[existing_product],
        audit_rows=[
            {
                "source_type": existing_product.source_type,
                "source_value": existing_product.source_value,
                "title": existing_product.title,
                "product_url": existing_product.product_url,
                "filter_decision": "accepted",
                "filter_stage": "accepted",
                "reject_groups": "",
                "reject_terms": "",
                "reject_fields": "",
                "warning_groups": "",
                "warning_terms": "",
                "warning_fields": "",
            }
        ],
        pending_detail_queue=[],
        last_block_reason="manual_resume",
        last_blocked_url="",
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    class FakePage:
        url = manifest.url
        current_page = 1

    collect_calls: list[int] = []
    advance_calls: list[int] = []
    page_three_product = {
        "title": "Dress C",
        "url": "https://www.aliexpress.com/item/2003.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/2003.html",
    }

    def fake_collect(page):
        collect_calls.append(page.current_page)
        if page.current_page != 3:
            raise AssertionError(f"resume should collect page 3 only, got page {page.current_page}")
        return [dict(page_three_product)]

    def fake_advance(page, target_page):
        advance_calls.append(target_page)
        page.current_page = target_page
        return target_page <= 3

    def fake_dedupe(products, seen_keys):
        unique = []
        for product in products:
            key = str(product["resolvedProductUrl"])
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(product)
        return unique

    def fake_normalize(products, *, source_type, source_value, scraped_at):
        return [
            _product_record(
                product_url=str(product["resolvedProductUrl"]),
                title=str(product["title"]),
                scraped_at=scraped_at,
            )
            for product in products
        ]

    def fake_filter(products, groups):
        return (
            list(products),
            [
                {
                    "source_type": product.source_type,
                    "source_value": product.source_value,
                    "title": product.title,
                    "product_url": product.product_url,
                    "filter_decision": "accepted",
                    "filter_stage": "accepted",
                    "reject_groups": "",
                    "reject_terms": "",
                    "reject_fields": "",
                    "warning_groups": "",
                    "warning_terms": "",
                    "warning_fields": "",
                }
                for product in products
            ],
        )

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "collect_listing_page_products", fake_collect)
    monkeypatch.setattr(scrape_runner, "advance_listing_page", fake_advance)
    monkeypatch.setattr(scrape_runner, "dedupe_listing_products", fake_dedupe)
    monkeypatch.setattr(
        scrape_runner,
        "prefilter_listing_products",
        lambda raw_products, groups, source_type, source_value: (raw_products, []),
    )
    monkeypatch.setattr(scrape_runner, "normalize_products", fake_normalize)
    monkeypatch.setattr(scrape_runner, "filter_products", fake_filter)

    result = scrape_runner.resume_scrape(tmp_path, details_only=False)

    resumed_state = store.load_state()

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=2, blocked=False)
    assert collect_calls == [3]
    assert 1 not in collect_calls
    assert advance_calls[-1] == 3
    assert resumed_state.pending_detail_queue == []
    assert resumed_state.current_listing_page == 3
    assert resumed_state.accepted_count == 2
    assert [product.product_url for product in resumed_state.accepted_products] == [
        existing_product.product_url,
        page_three_product["resolvedProductUrl"],
    ]


def test_resume_scrape_marks_failed_when_target_listing_page_cannot_be_reached(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = _manifest(tmp_path, pages=3, enrich_detail=False)
    existing_product = _product_record(
        product_url="https://www.aliexpress.com/item/2101.html",
        title="Dress Resume",
        scraped_at=manifest.created_at,
    )
    state = RunState(
        status="blocked",
        current_listing_page=2,
        raw_products_count=1,
        normalized_count=1,
        accepted_count=1,
        seen_product_keys=[existing_product.product_url],
        accepted_products=[existing_product],
        audit_rows=[],
        pending_detail_queue=[],
        last_block_reason="captcha_blocked",
        last_blocked_url=existing_product.product_url,
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    class FakePage:
        url = manifest.url

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "advance_listing_page", lambda page, target_page: False)

    result = scrape_runner.resume_scrape(tmp_path, details_only=False)

    resumed_state = store.load_state()
    summary = store.load_summary()

    assert result == scrape_runner.RunResult(exit_code=4, accepted_count=1, blocked=False)
    assert resumed_state.status == "failed"
    assert resumed_state.current_listing_page == 2
    assert resumed_state.last_block_reason == "listing_page_unreachable"
    assert resumed_state.last_blocked_url == manifest.url
    assert summary["status"] == "failed"
    assert summary["resume_recommended"] is True


def test_resume_scrape_details_only_keeps_incomplete_run_blocked_when_no_pending_queue(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = _manifest(tmp_path, pages=3, enrich_detail=True)
    existing_product = _product_record(
        product_url="https://www.aliexpress.com/item/2201.html",
        title="Dress Resume",
        scraped_at=manifest.created_at,
    )
    state = RunState(
        status="blocked",
        current_listing_page=2,
        raw_products_count=1,
        normalized_count=1,
        accepted_count=1,
        seen_product_keys=[existing_product.product_url],
        accepted_products=[existing_product],
        audit_rows=[],
        pending_detail_queue=[],
        last_block_reason="captcha_blocked",
        last_blocked_url=existing_product.product_url,
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    opened = {"value": False}

    def fake_open_listing_page(*args, **kwargs):
        opened["value"] = True
        return object()

    monkeypatch.setattr(scrape_runner, "open_listing_page", fake_open_listing_page)

    result = scrape_runner.resume_scrape(tmp_path, details_only=True)

    resumed_state = store.load_state()
    summary = store.load_summary()

    assert result == scrape_runner.RunResult(exit_code=4, accepted_count=1, blocked=False)
    assert opened["value"] is False
    assert resumed_state.status == "blocked"
    assert resumed_state.pending_detail_queue == []
    assert resumed_state.accepted_count == 1
    assert resumed_state.last_error == "details_only_requested_without_pending_details"
    assert summary["status"] == "blocked"
    assert summary["resume_recommended"] is True


def test_resume_scrape_details_only_short_circuits_completed_run_without_browser(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = _manifest(tmp_path, pages=2, enrich_detail=True)
    existing_product = _product_record(
        product_url="https://www.aliexpress.com/item/2202.html",
        title="Dress Done",
        scraped_at=manifest.created_at,
    )
    state = RunState(
        status="completed",
        current_listing_page=2,
        raw_products_count=1,
        normalized_count=1,
        accepted_count=1,
        seen_product_keys=[existing_product.product_url],
        accepted_products=[existing_product],
        audit_rows=[],
        pending_detail_queue=[],
        last_block_reason="",
        last_blocked_url="",
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    opened = {"value": False}

    def fake_open_listing_page(*args, **kwargs):
        opened["value"] = True
        return object()

    monkeypatch.setattr(scrape_runner, "open_listing_page", fake_open_listing_page)

    result = scrape_runner.resume_scrape(tmp_path, details_only=True)

    resumed_state = store.load_state()
    summary = store.load_summary()

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=1, blocked=False)
    assert opened["value"] is False
    assert resumed_state.status == "completed"
    assert resumed_state.pending_detail_queue == []
    assert resumed_state.accepted_count == 1
    assert summary["status"] == "completed"
    assert summary["resume_recommended"] is False


def test_resume_scrape_details_only_short_circuits_completed_zero_accept_run_without_browser(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = _manifest(tmp_path, pages=2, enrich_detail=True)
    state = RunState(
        status="completed",
        current_listing_page=2,
        raw_products_count=1,
        normalized_count=1,
        accepted_count=0,
        seen_product_keys=["https://www.aliexpress.com/item/2203.html"],
        accepted_products=[],
        audit_rows=[
            {
                "source_type": "keyword",
                "source_value": "women dress",
                "title": "Dress Reject",
                "product_url": "https://www.aliexpress.com/item/2203.html",
                "filter_decision": "rejected",
                "filter_stage": "detail_post_enrich",
                "reject_groups": "manual_blacklist",
                "reject_terms": "wool",
                "reject_fields": "attributes_text",
                "warning_groups": "",
                "warning_terms": "",
                "warning_fields": "",
            }
        ],
        pending_detail_queue=[],
        last_block_reason="",
        last_blocked_url="",
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    opened = {"value": False}

    def fake_open_listing_page(*args, **kwargs):
        opened["value"] = True
        return object()

    monkeypatch.setattr(scrape_runner, "open_listing_page", fake_open_listing_page)

    result = scrape_runner.resume_scrape(tmp_path, details_only=True)

    resumed_state = store.load_state()
    summary = store.load_summary()

    assert result == scrape_runner.RunResult(exit_code=2, accepted_count=0, blocked=False)
    assert opened["value"] is False
    assert resumed_state.status == "completed"
    assert resumed_state.pending_detail_queue == []
    assert resumed_state.accepted_count == 0
    assert summary["status"] == "completed"
    assert summary["resume_recommended"] is False


def test_resume_scrape_applies_proxy_and_identity_overrides_to_browser_open(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = replace(
        _manifest(tmp_path, pages=1, enrich_detail=True),
        proxy="http://manifest-proxy:8080",
        proxy_file="",
        user_agent="ua-manifest",
        accept_language="en-US,en;q=0.9",
    )
    pending_product = {
        "title": "Dress Override",
        "url": "https://www.aliexpress.com/item/2301.html",
        "cardUrl": "https://www.aliexpress.com/item/2301.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/2301.html",
        "_listingBaseUrl": manifest.url,
        "_listingPageUrl": manifest.url,
        "_listingPageNumber": 1,
    }
    state = RunState(
        status="blocked",
        current_listing_page=1,
        raw_products_count=1,
        normalized_count=0,
        accepted_count=0,
        seen_product_keys=[pending_product["resolvedProductUrl"]],
        accepted_products=[],
        audit_rows=[],
        pending_detail_queue=[dict(pending_product)],
        last_block_reason="captcha_blocked",
        last_blocked_url=pending_product["resolvedProductUrl"],
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    class FakePage:
        url = manifest.url

    open_kwargs: list[dict[str, object]] = []

    def fake_open_listing_page(url, **kwargs):
        open_kwargs.append({"url": url, **kwargs})
        return FakePage()

    def fake_detail(page, product):
        product["detailStatus"] = "detail_enriched"
        return "detail_enriched"

    monkeypatch.setattr(scrape_runner, "open_listing_page", fake_open_listing_page)
    monkeypatch.setattr(scrape_runner, "enrich_single_product_detail", fake_detail)

    result = scrape_runner.resume_scrape(
        tmp_path,
        details_only=True,
        proxy_override="http://override-proxy:9090",
        proxy_file_override="",
        user_agent_override="ua-override",
        accept_language_override="fr-FR,fr;q=0.9",
    )

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=1, blocked=False)
    assert open_kwargs == [
        {
            "url": manifest.url,
            "user_data_dir": manifest.user_data_dir,
            "port": manifest.port,
            "browser_hardening": manifest.browser_hardening,
            "proxy": "http://override-proxy:9090",
            "user_agent": "ua-override",
            "accept_language": "fr-FR,fr;q=0.9",
        }
    ]


def test_resume_scrape_details_only_normalizes_filters_and_persists_pending_raw_products(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = _manifest(tmp_path, pages=1, enrich_detail=True)
    pending_product = {
        "title": "Dress B",
        "url": "https://www.aliexpress.com/item/2002.html",
        "cardUrl": "https://www.aliexpress.com/item/2002.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/2002.html",
        "_listingBaseUrl": manifest.url,
        "_listingPageUrl": manifest.url,
        "_listingPageNumber": 1,
    }
    state = scrape_runner.RunState(
        status="blocked",
        current_listing_page=1,
        raw_products_count=1,
        normalized_count=0,
        accepted_count=0,
        seen_product_keys=[pending_product["resolvedProductUrl"]],
        accepted_products=[],
        audit_rows=[],
        pending_detail_queue=[dict(pending_product)],
        last_block_reason="captcha_blocked",
        last_blocked_url=pending_product["resolvedProductUrl"],
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    class FakePage:
        url = manifest.url

    detail_calls: list[str] = []

    def fake_detail(page, product):
        detail_calls.append(str(product["resolvedProductUrl"]))
        product["detailStatus"] = "detail_enriched"
        product["attributesText"] = '{"Material":"Silk"}'
        product["descriptionText"] = "Recovered detail"
        return "detail_enriched"

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "enrich_single_product_detail", fake_detail)

    result = scrape_runner.resume_scrape(tmp_path, details_only=True)

    resumed_state = store.load_state()
    summary = store.load_summary()

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=1, blocked=False)
    assert detail_calls == [pending_product["resolvedProductUrl"]]
    assert resumed_state.status == "completed"
    assert resumed_state.pending_detail_queue == []
    assert resumed_state.normalized_count == 1
    assert resumed_state.accepted_count == 1
    assert resumed_state.accepted_products[0].product_url == pending_product["resolvedProductUrl"]
    assert resumed_state.accepted_products[0].detail_status == "detail_enriched"
    assert resumed_state.accepted_products[0].attributes_text == '{"Material":"Silk"}'
    assert resumed_state.accepted_products[0].description_text == "Recovered detail"
    assert resumed_state.audit_rows == [
        {
            "source_type": "keyword",
            "source_value": "women dress",
            "title": "Dress B",
            "product_url": "https://www.aliexpress.com/item/2002.html",
            "filter_decision": "accepted",
            "filter_stage": "accepted",
            "reject_groups": "",
            "reject_terms": "",
            "reject_fields": "",
            "warning_groups": "",
            "warning_terms": "",
            "warning_fields": "",
        }
    ]
    assert summary["status"] == "completed"
    assert summary["resume_recommended"] is False


def test_resume_scrape_details_only_preserves_rejected_pending_products_in_audit(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = _manifest(tmp_path, pages=1, enrich_detail=True)
    pending_product = {
        "title": "Dress Reject",
        "url": "https://www.aliexpress.com/item/2999.html",
        "cardUrl": "https://www.aliexpress.com/item/2999.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/2999.html",
        "_listingBaseUrl": manifest.url,
        "_listingPageUrl": manifest.url,
        "_listingPageNumber": 1,
    }
    state = scrape_runner.RunState(
        status="blocked",
        current_listing_page=1,
        raw_products_count=1,
        normalized_count=0,
        accepted_count=0,
        seen_product_keys=[pending_product["resolvedProductUrl"]],
        accepted_products=[],
        audit_rows=[],
        pending_detail_queue=[dict(pending_product)],
        last_block_reason="captcha_blocked",
        last_blocked_url=pending_product["resolvedProductUrl"],
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    class FakePage:
        url = manifest.url

    detail_calls: list[str] = []

    def fake_detail(page, product):
        detail_calls.append(str(product["resolvedProductUrl"]))
        product["detailStatus"] = "detail_enriched"
        product["attributesText"] = '{"Material":"Wool"}'
        return "detail_enriched"

    def fake_filter(products, groups):
        assert len(products) == 1
        product = products[0]
        return (
            [],
            [
                {
                    "source_type": product.source_type,
                    "source_value": product.source_value,
                    "title": product.title,
                    "product_url": product.product_url,
                    "filter_decision": "rejected",
                    "filter_stage": "detail_post_enrich",
                    "reject_groups": "manual_blacklist",
                    "reject_terms": "wool",
                    "reject_fields": "attributes_text",
                    "warning_groups": "",
                    "warning_terms": "",
                    "warning_fields": "",
                }
            ],
        )

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "enrich_single_product_detail", fake_detail)
    monkeypatch.setattr(scrape_runner, "filter_products", fake_filter)

    result = scrape_runner.resume_scrape(tmp_path, details_only=True)

    resumed_state = store.load_state()
    summary = store.load_summary()
    review_rows = read_csv_rows(tmp_path / "products_review.csv")

    assert detail_calls == [pending_product["resolvedProductUrl"]]
    assert result.exit_code == 2
    assert resumed_state.status == "completed"
    assert resumed_state.pending_detail_queue == []
    assert resumed_state.accepted_products == []
    assert resumed_state.accepted_count == 0
    assert resumed_state.audit_rows == [
        {
            "source_type": "keyword",
            "source_value": "women dress",
            "title": "Dress Reject",
            "product_url": "https://www.aliexpress.com/item/2999.html",
            "filter_decision": "rejected",
            "filter_stage": "detail_post_enrich",
            "reject_groups": "manual_blacklist",
            "reject_terms": "wool",
            "reject_fields": "attributes_text",
            "warning_groups": "",
            "warning_terms": "",
            "warning_fields": "",
        }
    ]
    assert review_rows[0]["attributes_text"] == '{"Material":"Wool"}'
    assert review_rows[0]["detail_status"] == "detail_enriched"
    assert summary["status"] == "completed"


def test_resume_scrape_stays_blocked_when_detail_queue_hits_captcha_again(tmp_path, monkeypatch):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunState, RunStateStore

    manifest = _manifest(tmp_path, pages=1, enrich_detail=True)
    first = {
        "title": "Dress C",
        "url": "https://www.aliexpress.com/item/3001.html",
        "cardUrl": "https://www.aliexpress.com/item/3001.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/3001.html",
        "_listingBaseUrl": manifest.url,
        "_listingPageUrl": manifest.url,
        "_listingPageNumber": 1,
    }
    second = {
        "title": "Dress D",
        "url": "https://www.aliexpress.com/item/3002.html",
        "cardUrl": "https://www.aliexpress.com/item/3002.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/3002.html",
        "_listingBaseUrl": manifest.url,
        "_listingPageUrl": manifest.url,
        "_listingPageNumber": 1,
    }
    state = scrape_runner.RunState(
        status="blocked",
        current_listing_page=1,
        raw_products_count=2,
        normalized_count=0,
        accepted_count=0,
        seen_product_keys=[first["resolvedProductUrl"], second["resolvedProductUrl"]],
        accepted_products=[],
        audit_rows=[],
        pending_detail_queue=[dict(first), dict(second)],
        last_block_reason="captcha_blocked",
        last_blocked_url=first["resolvedProductUrl"],
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    class FakePage:
        url = manifest.url

    detail_calls: list[str] = []

    def fake_detail(page, product):
        detail_calls.append(str(product["resolvedProductUrl"]))
        product["detailStatus"] = "captcha_blocked"
        return "captcha_blocked"

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "enrich_single_product_detail", fake_detail)

    result = scrape_runner.resume_scrape(tmp_path, details_only=True)

    resumed_state = store.load_state()
    summary = store.load_summary()

    assert result == scrape_runner.RunResult(exit_code=3, accepted_count=0, blocked=True)
    assert detail_calls == [first["resolvedProductUrl"]]
    assert resumed_state.status == "blocked"
    assert resumed_state.last_block_reason == "captcha_blocked"
    assert resumed_state.last_blocked_url == first["resolvedProductUrl"]
    assert resumed_state.pending_detail_queue == [dict(first, detailStatus="captcha_blocked"), second]
    assert resumed_state.accepted_products == []
    assert summary["resume_recommended"] is True
    assert "captcha_diagnostic" not in summary


def test_resume_scrape_details_only_preserves_existing_captcha_diagnostic_after_pending_detail_success(
    tmp_path, monkeypatch
):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunStateStore

    manifest = _manifest(tmp_path, pages=1, enrich_detail=True)
    existing_diagnostic = {
        "stage": "preflight",
        "page_url": manifest.url,
        "solver": {"status": "solved"},
    }
    pending_product = {
        "title": "Dress Resume Success",
        "url": "https://www.aliexpress.com/item/3101.html",
        "cardUrl": "https://www.aliexpress.com/item/3101.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/3101.html",
        "_listingBaseUrl": manifest.url,
        "_listingPageUrl": manifest.url,
        "_listingPageNumber": 1,
    }
    state = scrape_runner.RunState(
        status="blocked",
        current_listing_page=1,
        raw_products_count=1,
        normalized_count=0,
        accepted_count=0,
        seen_product_keys=[pending_product["resolvedProductUrl"]],
        accepted_products=[],
        audit_rows=[],
        pending_detail_queue=[dict(pending_product)],
        last_block_reason="captcha_blocked",
        last_blocked_url=pending_product["resolvedProductUrl"],
        captcha_diagnostic=dict(existing_diagnostic),
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    class FakePage:
        url = manifest.url

    def fake_detail(page, product):
        product["detailStatus"] = "detail_enriched"
        return "detail_enriched"

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "enrich_single_product_detail", fake_detail)

    result = scrape_runner.resume_scrape(tmp_path, details_only=True)

    resumed_state = store.load_state()
    summary = store.load_summary()

    assert result == scrape_runner.RunResult(exit_code=0, accepted_count=1, blocked=False)
    assert resumed_state.status == "completed"
    assert resumed_state.captcha_diagnostic == existing_diagnostic
    assert summary["captcha_diagnostic"] == existing_diagnostic


def test_resume_scrape_details_only_persists_latest_captcha_diagnostic_when_detail_queue_hits_captcha_again(
    tmp_path, monkeypatch
):
    scrape_runner = import_module("ali_mvp.scrape_runner")
    from ali_mvp.run_state import RunStateStore

    manifest = _manifest(tmp_path, pages=1, enrich_detail=True)
    existing_diagnostic = {
        "stage": "preflight",
        "page_url": manifest.url,
        "solver": {"status": "solved"},
    }
    latest_diagnostic = {
        "stage": "detail",
        "page_url": "https://www.aliexpress.com/item/3201.html",
        "solver": {"status": "blocked"},
    }
    first = {
        "title": "Dress Resume Blocked",
        "url": "https://www.aliexpress.com/item/3201.html",
        "cardUrl": "https://www.aliexpress.com/item/3201.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/3201.html",
        "_listingBaseUrl": manifest.url,
        "_listingPageUrl": manifest.url,
        "_listingPageNumber": 1,
    }
    second = {
        "title": "Dress Resume Later",
        "url": "https://www.aliexpress.com/item/3202.html",
        "cardUrl": "https://www.aliexpress.com/item/3202.html",
        "resolvedProductUrl": "https://www.aliexpress.com/item/3202.html",
        "_listingBaseUrl": manifest.url,
        "_listingPageUrl": manifest.url,
        "_listingPageNumber": 1,
    }
    state = scrape_runner.RunState(
        status="blocked",
        current_listing_page=1,
        raw_products_count=2,
        normalized_count=0,
        accepted_count=0,
        seen_product_keys=[first["resolvedProductUrl"], second["resolvedProductUrl"]],
        accepted_products=[],
        audit_rows=[],
        pending_detail_queue=[dict(first), dict(second)],
        last_block_reason="captcha_blocked",
        last_blocked_url=first["resolvedProductUrl"],
        captcha_diagnostic=dict(existing_diagnostic),
    )
    store = RunStateStore(tmp_path)
    store.save_manifest(manifest)
    store.save_state(state)
    store.save_summary(state)

    class FakePage:
        url = manifest.url

    def fake_detail(page, product):
        product["_captchaDiagnostic"] = dict(latest_diagnostic)
        product["detailStatus"] = "captcha_blocked"
        return "captcha_blocked"

    monkeypatch.setattr(scrape_runner, "open_listing_page", lambda *args, **kwargs: FakePage())
    monkeypatch.setattr(scrape_runner, "enrich_single_product_detail", fake_detail)

    result = scrape_runner.resume_scrape(tmp_path, details_only=True)

    resumed_state = store.load_state()
    summary = store.load_summary()

    assert result == scrape_runner.RunResult(exit_code=3, accepted_count=0, blocked=True)
    assert resumed_state.status == "blocked"
    assert resumed_state.captcha_diagnostic == latest_diagnostic
    assert summary["captcha_diagnostic"] == latest_diagnostic
