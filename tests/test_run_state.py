import json

from ali_mvp.run_state import RunManifest, RunState, RunStateStore
from ali_mvp.scoring import ProductRecord


def _build_product_record() -> ProductRecord:
    return ProductRecord(
        source_type="keyword",
        source_value="women dress",
        title="Dress",
        price="$12.50",
        sold_count=100,
        rating=4.8,
        review_count=20,
        product_url="https://example.test/item/1.html",
        search_card_url="https://example.test/item/1.html",
        image_url="https://example.test/item-1.jpg",
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
        scraped_at="2026-05-11T08:00:00Z",
        detail_status="ok",
    )


def test_run_state_store_round_trip_json_files(tmp_path):
    store = RunStateStore(tmp_path)
    manifest = RunManifest(
        source_type="keyword",
        source_value="women dress",
        url="",
        max_items=20,
        pages=None,
        output_dir="data/women-dress/20260511_160000",
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=True,
        blacklist_file=None,
        reject_keyword=["battery", "sensor"],
        browser_hardening="minimal",
        proxy="http://proxy-1.test:8080",
        proxy_file="proxies.txt",
        max_blocks_per_proxy=2,
        user_agent="ua",
        accept_language="en-US,en;q=0.9",
        created_at="2026-05-11T08:00:00Z",
    )
    state = RunState(
        status="running",
        current_listing_page=2,
        raw_products_count=15,
        normalized_count=14,
        accepted_count=12,
        seen_product_keys=["sku-1", "sku-2"],
        accepted_products=[_build_product_record()],
        audit_rows=[{"filter_decision": "accepted"}],
        pending_detail_queue=[
            {
                "url": "https://example.test/item/2.html",
                "resolvedProductUrl": "https://example.test/item/2.html",
            }
        ],
        current_proxy_index=1,
        block_events_on_current_proxy=0,
        last_block_reason="",
        last_blocked_url="",
        last_error="",
    )
    store.save_manifest(manifest)
    store.save_state(state)

    assert store.manifest_path.name == "run_manifest.json"
    assert store.state_path.name == "run_state.json"
    assert store.summary_path.name == "run_summary.json"
    assert store.load_manifest() == manifest
    assert store.load_state() == state
    assert isinstance(store.load_state().accepted_products[0], ProductRecord)


def test_run_manifest_and_state_roundtrip_preserve_proxy_provider(tmp_path):
    store = RunStateStore(tmp_path)
    manifest = RunManifest(
        source_type="keyword",
        source_value="kettle parts",
        url="https://www.aliexpress.com/wholesale?SearchText=kettle+parts",
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
    state = RunState(current_proxy_index=1, current_proxy_key="node-b")

    store.save_manifest(manifest)
    store.save_state(state)

    assert store.load_manifest().proxy_provider == "v2rayn"
    assert store.load_manifest().v2rayn_dir == "C:/Users/test/v2rayN"
    assert store.load_state().current_proxy_key == "node-b"


def test_run_state_to_summary_marks_blocked_runs(tmp_path):
    store = RunStateStore(tmp_path)
    state = RunState(
        status="blocked",
        current_listing_page=1,
        raw_products_count=6,
        normalized_count=5,
        accepted_count=5,
        seen_product_keys=["sku-1"],
        accepted_products=[_build_product_record()],
        audit_rows=[],
        pending_detail_queue=[
            {
                "url": "https://example.test/item/9.html",
                "resolvedProductUrl": "https://example.test/item/9.html",
            }
        ],
        current_proxy_index=2,
        block_events_on_current_proxy=1,
        last_block_reason="captcha_blocked",
        last_blocked_url="https://www.aliexpress.com/item/9.html",
        last_error="Timed out waiting for manual unblock",
    )

    store.save_summary(state)

    assert store.load_summary() == {
        "status": "blocked",
        "current_listing_page": 1,
        "accepted_count": 5,
        "last_block_reason": "captcha_blocked",
        "last_blocked_url": "https://www.aliexpress.com/item/9.html",
        "resume_recommended": True,
    }


def test_load_state_returns_default_when_run_state_file_missing(tmp_path):
    store = RunStateStore(tmp_path)

    assert store.load_state() == RunState()


def test_load_manifest_defaults_browser_hardening_to_off(tmp_path):
    store = RunStateStore(tmp_path)
    payload = {
        "source_type": "keyword",
        "source_value": "women dress",
        "url": "",
        "max_items": 20,
        "pages": None,
        "output_dir": "data/women-dress/20260511_160000",
        "user_data_dir": ".browser-profile",
        "port": 9333,
        "enrich_detail": True,
        "blacklist_file": None,
        "reject_keyword": [],
        "proxy": "",
        "proxy_file": "",
        "max_blocks_per_proxy": 2,
        "user_agent": "ua",
        "accept_language": "en-US,en;q=0.9",
        "created_at": "2026-05-11T08:00:00Z",
    }
    store.manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.load_manifest().browser_hardening == "off"


def test_load_manifest_normalizes_missing_or_invalid_proxy_provider_to_manual(tmp_path):
    store = RunStateStore(tmp_path)
    payload = {
        "source_type": "keyword",
        "source_value": "women dress",
        "url": "",
        "max_items": 20,
        "pages": None,
        "output_dir": "data/women-dress/20260511_160000",
        "user_data_dir": ".browser-profile",
        "port": 9333,
        "enrich_detail": True,
        "blacklist_file": None,
        "reject_keyword": [],
        "browser_hardening": "minimal",
        "proxy_provider": "invalid-provider",
        "v2rayn_dir": "C:/Users/test/v2rayN",
        "proxy": "",
        "proxy_file": "",
        "max_blocks_per_proxy": 2,
        "user_agent": "ua",
        "accept_language": "en-US,en;q=0.9",
        "created_at": "2026-05-11T08:00:00Z",
    }
    store.manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    manifest = store.load_manifest()

    assert manifest.proxy_provider == "manual"

    payload.pop("proxy_provider")
    store.manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.load_manifest().proxy_provider == "manual"


def test_load_manifest_normalizes_invalid_session_preflight_to_on(tmp_path):
    store = RunStateStore(tmp_path)
    payload = {
        "source_type": "keyword",
        "source_value": "women dress",
        "url": "",
        "max_items": 20,
        "pages": None,
        "output_dir": "data/women-dress/20260511_160000",
        "user_data_dir": ".browser-profile",
        "port": 9333,
        "enrich_detail": True,
        "blacklist_file": None,
        "reject_keyword": [],
        "browser_hardening": "minimal",
        "proxy_provider": "manual",
        "session_preflight": "invalid",
        "proxy": "",
        "proxy_file": "",
        "max_blocks_per_proxy": 2,
        "user_agent": "ua",
        "accept_language": "en-US,en;q=0.9",
        "created_at": "2026-05-11T08:00:00Z",
    }
    store.manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.load_manifest().session_preflight == "on"

    payload["session_preflight"] = "off"
    store.manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.load_manifest().session_preflight == "off"


def test_load_state_upgrades_legacy_pending_detail_queue_urls_to_dicts(tmp_path):
    store = RunStateStore(tmp_path)
    payload = {
        "status": "blocked",
        "current_listing_page": 2,
        "pending_detail_queue": [
            "https://example.test/item/1.html",
            "https://example.test/item/2.html",
        ],
    }
    store.state_path.write_text(json.dumps(payload), encoding="utf-8")

    state = store.load_state()

    assert state.pending_detail_queue == [
        {
            "url": "https://example.test/item/1.html",
            "resolvedProductUrl": "https://example.test/item/1.html",
        },
        {
            "url": "https://example.test/item/2.html",
            "resolvedProductUrl": "https://example.test/item/2.html",
        },
    ]


def test_run_state_to_summary_marks_failed_runs_resume_recommended(tmp_path):
    store = RunStateStore(tmp_path)
    state = RunState(
        status="failed",
        current_listing_page=3,
        accepted_count=2,
        accepted_products=[_build_product_record()],
        last_block_reason="network_error",
        last_blocked_url="https://www.aliexpress.com/item/11.html",
        last_error="proxy disconnected",
    )

    store.save_summary(state)

    assert store.load_summary() == {
        "status": "failed",
        "current_listing_page": 3,
        "accepted_count": 2,
        "last_block_reason": "network_error",
        "last_blocked_url": "https://www.aliexpress.com/item/11.html",
        "resume_recommended": True,
    }


def test_run_state_round_trips_session_risk_fields():
    state = RunState(
        status="blocked",
        session_risk_level="high",
        last_session_preflight_status="captcha_blocked",
        consecutive_captcha_count=2,
        last_session_ok_at="2026-05-12T10:00:00Z",
        cooldown_until="2026-05-12T10:30:00Z",
    )

    payload = state.to_dict()
    restored = RunState.from_dict(payload)

    assert restored.session_risk_level == "high"
    assert restored.last_session_preflight_status == "captcha_blocked"
    assert restored.consecutive_captcha_count == 2
    assert restored.cooldown_until == "2026-05-12T10:30:00Z"


def test_run_state_round_trips_captcha_diagnostic():
    state = RunState(
        status="running",
        captcha_diagnostic={
            "stage": "preflight",
            "page_url": "https://www.aliexpress.com/wholesale?SearchText=women+dress",
            "attempts": 2,
        },
    )

    payload = state.to_dict()
    restored = RunState.from_dict(payload)

    assert restored.captcha_diagnostic == {
        "stage": "preflight",
        "page_url": "https://www.aliexpress.com/wholesale?SearchText=women+dress",
        "attempts": 2,
    }


def test_run_state_summary_includes_full_identity_warning_structure(tmp_path):
    store = RunStateStore(tmp_path)
    state = RunState(
        status="completed",
        accepted_count=1,
        identity_warning={
            "code": "accept_language_mismatch",
            "configured": {"accept_language_primary": "en-US"},
            "effective": {"navigator_language": "fr-FR"},
        },
    )

    store.save_summary(state)

    assert store.load_summary()["identity_warning"] == {
        "code": "accept_language_mismatch",
        "configured": {"accept_language_primary": "en-US"},
        "effective": {"navigator_language": "fr-FR"},
    }


def test_run_state_summary_includes_captcha_diagnostic(tmp_path):
    store = RunStateStore(tmp_path)
    state = RunState(
        status="blocked",
        accepted_count=1,
        last_block_reason="captcha_blocked",
        last_blocked_url="https://www.aliexpress.com/item/11.html",
        captcha_diagnostic={
            "stage": "detail",
            "page_url": "https://www.aliexpress.com/item/11.html",
            "solver": {"status": "solved"},
        },
    )

    store.save_summary(state)

    assert store.load_summary()["captcha_diagnostic"] == {
        "stage": "detail",
        "page_url": "https://www.aliexpress.com/item/11.html",
        "solver": {"status": "solved"},
    }


def test_run_state_from_dict_ignores_malformed_identity_warning_payload():
    state = RunState.from_dict(
        {
            "status": "failed",
            "identity_warning": {
                "code": "accept_language_mismatch",
                "configured": ["bad-configured-shape"],
                "effective": "bad-effective-shape",
            },
        }
    )

    assert state.identity_warning == {}
