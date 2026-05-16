import json

from DrissionPage.errors import ContextLostError

from ali_mvp import browser
from ali_mvp.browser import NEXT_PAGE_SCRIPT, PRODUCT_SCRIPT


def test_product_script_returns_iife_result_to_python():
    assert PRODUCT_SCRIPT.lstrip().startswith("return ")


def test_product_script_has_listing_rating_helper():
    assert "function findRatingLine(lines)" in PRODUCT_SCRIPT
    assert "ratingText: findRatingLine(lines)" in PRODUCT_SCRIPT


def test_product_script_collects_bundle_deals_promo_cards():
    assert '"/item/"' in PRODUCT_SCRIPT
    assert "BundleDeals2" in PRODUCT_SCRIPT
    assert "entryType" in PRODUCT_SCRIPT
    assert "resolvedProductUrl" in PRODUCT_SCRIPT


def test_detail_fields_script_targets_product_specs_and_jsonld_fallbacks():
    assert 'data-pl="product-specs"' in browser.DETAIL_FIELDS_SCRIPT
    assert '[class*="ku--wrap"]' in browser.DETAIL_FIELDS_SCRIPT
    assert 'application/ld+json' in browser.DETAIL_FIELDS_SCRIPT
    assert "jsonLdDescription" in browser.DETAIL_FIELDS_SCRIPT
    assert "metaDescription" in browser.DETAIL_FIELDS_SCRIPT


def test_collect_raw_products_uses_finalize_path_for_detail_enrichment():
    from pathlib import Path

    source = Path("ali_mvp/browser.py").read_text(encoding="utf-8")

    assert "def _finalize_products(" in source
    collect_body = source.split("def collect_raw_products(", 1)[1].split("def _collect_current_page(", 1)[0]
    assert "return _finalize_products(" in collect_body
    assert "return raw[:max_items]" not in collect_body


def test_next_page_script_uses_dom_next_button_not_page_url_guess():
    assert "comet-pagination-next" in NEXT_PAGE_SCRIPT
    assert ".click()" in NEXT_PAGE_SCRIPT
    assert "page=" not in NEXT_PAGE_SCRIPT
    assert "quick-jumper" in NEXT_PAGE_SCRIPT


def test_next_page_script_prefers_quick_jumper_and_sets_react_input_value():
    compact = "".join(NEXT_PAGE_SCRIPT.split())

    assert "HTMLInputElement.prototype" in NEXT_PAGE_SCRIPT
    assert "returnjumpToTargetPage()||clickPaginationNext()||'';" in compact


def test_collect_raw_products_accepts_pages_parameter():
    from pathlib import Path

    source = Path("ali_mvp/browser.py").read_text(encoding="utf-8")

    assert "pages: int | None = None" in source
    assert "while True" in source


def test_collect_raw_products_deduplicates_by_item_id():
    from pathlib import Path

    source = Path("ali_mvp/browser.py").read_text(encoding="utf-8")

    assert "def _product_key(" in source
    assert 'marker = "/item/"' in source


def test_dedupe_listing_products_keeps_first_unique_product_key():
    seen_keys: set[str] = set()
    products = [
        {"url": "https://www.aliexpress.com/item/1001.html"},
        {"url": "https://www.aliexpress.com/item/1001.html"},
        {"url": "https://www.aliexpress.com/item/1002.html"},
    ]

    unique = browser.dedupe_listing_products(products, seen_keys)

    assert [item["url"] for item in unique] == [
        "https://www.aliexpress.com/item/1001.html",
        "https://www.aliexpress.com/item/1002.html",
    ]


def test_collect_listing_page_products_wraps_current_page_collection(monkeypatch):
    class FakePage:
        pass

    monkeypatch.setattr(
        browser,
        "_collect_current_page",
        lambda page, scroll_rounds=8: [{"url": "https://www.aliexpress.com/item/1001.html"}],
    )

    products = browser.collect_listing_page_products(FakePage(), scroll_rounds=3)

    assert products == [{"url": "https://www.aliexpress.com/item/1001.html"}]


def test_collect_raw_products_uses_public_browser_helpers(monkeypatch):
    calls = {"open": 0, "collect": 0, "advance": 0, "enrich": 0}

    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress"

    monkeypatch.setattr(
        browser,
        "open_listing_page",
        lambda url, user_data_dir=None, port=None, browser_hardening="minimal": (
            calls.__setitem__("open", calls["open"] + 1) or FakePage()
        ),
    )
    monkeypatch.setattr(
        browser,
        "collect_listing_page_products",
        lambda page, scroll_rounds=8: calls.__setitem__("collect", calls["collect"] + 1)
        or [{"url": "https://www.aliexpress.com/item/1001.html"}],
    )
    monkeypatch.setattr(browser, "dedupe_listing_products", lambda products, seen_keys: products)
    monkeypatch.setattr(
        browser,
        "advance_listing_page",
        lambda page, target_page: calls.__setitem__("advance", calls["advance"] + 1) or False,
    )
    monkeypatch.setattr(
        browser,
        "enrich_listing_products",
        lambda page, products: calls.__setitem__("enrich", calls["enrich"] + 1),
    )

    products = browser.collect_raw_products(
        "https://www.aliexpress.com/wholesale?SearchText=women+dress",
        max_items=1,
        enrich_detail=True,
        pages=1,
    )

    assert products == [{"url": "https://www.aliexpress.com/item/1001.html"}]
    assert calls == {"open": 1, "collect": 1, "advance": 0, "enrich": 1}


def test_collect_raw_products_passes_browser_hardening_to_open_listing_page(monkeypatch):
    seen: dict[str, object] = {}

    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress"

    monkeypatch.setattr(
        browser,
        "open_listing_page",
        lambda url, **kwargs: (
            seen.setdefault("browser_hardening", kwargs.get("browser_hardening", "minimal")) or FakePage()
        ),
    )
    monkeypatch.setattr(
        browser,
        "collect_listing_page_products",
        lambda page, scroll_rounds=8: [{"url": "https://www.aliexpress.com/item/1001.html"}],
    )
    monkeypatch.setattr(browser, "dedupe_listing_products", lambda products, seen_keys: products)

    products = browser.collect_raw_products(
        "https://www.aliexpress.com/wholesale?SearchText=women+dress",
        max_items=1,
        browser_hardening="off",
    )

    assert products == [{"url": "https://www.aliexpress.com/item/1001.html"}]
    assert seen["browser_hardening"] == "off"


def test_open_listing_page_applies_minimal_stealth_and_pause(monkeypatch):
    calls: list[tuple[str, object]] = []

    class FakePage:
        def __init__(self, options):
            calls.append(("page_init", options))

        def get(self, url):
            calls.append(("get", url))

    monkeypatch.setattr(browser, "ChromiumPage", FakePage)
    monkeypatch.setattr(browser, "_build_options", lambda **kwargs: calls.append(("build_options", kwargs)) or object())
    monkeypatch.setattr(browser, "_init_page_stealth", lambda page: calls.append(("stealth", page)))
    monkeypatch.setattr(browser, "_pause_after_navigation", lambda: calls.append(("pause", None)))

    page = browser.open_listing_page(
        "https://example.test/listing",
        user_data_dir=".browser-profile",
        port=9333,
        browser_hardening="minimal",
    )

    assert isinstance(page, FakePage)
    assert (
        "build_options",
        {
            "user_data_dir": ".browser-profile",
            "port": 9333,
            "browser_hardening": "minimal",
            "proxy": "",
            "user_agent": "",
            "accept_language": "",
        },
    ) in calls
    assert any(name == "stealth" for name, _ in calls)
    assert any(name == "pause" for name, _ in calls)


def test_open_listing_page_skips_stealth_when_hardening_off(monkeypatch):
    calls: list[tuple[str, object]] = []

    class FakePage:
        def __init__(self, options):
            calls.append(("page_init", options))

        def get(self, url):
            calls.append(("get", url))

    monkeypatch.setattr(browser, "ChromiumPage", FakePage)
    monkeypatch.setattr(browser, "_build_options", lambda **kwargs: object())
    monkeypatch.setattr(browser, "_init_page_stealth", lambda page: calls.append(("stealth", page)))
    monkeypatch.setattr(browser, "_pause_after_navigation", lambda: calls.append(("pause", None)))

    browser.open_listing_page("https://example.test/listing", browser_hardening="off")

    assert not any(name == "stealth" for name, _ in calls)
    assert any(name == "pause" for name, _ in calls)


def test_build_options_applies_proxy_user_agent_and_language(monkeypatch):
    calls: list[tuple[str, object]] = []

    class FakeOptions:
        def set_local_port(self, value):
            calls.append(("set_local_port", value))

        def set_user_data_path(self, value):
            calls.append(("set_user_data_path", value))

        def set_proxy(self, value):
            calls.append(("set_proxy", value))

        def set_user_agent(self, value):
            calls.append(("set_user_agent", value))

        def set_argument(self, arg, value=None):
            calls.append(("set_argument", (arg, value)))

    monkeypatch.setattr(browser, "ChromiumOptions", FakeOptions)

    browser._build_options(
        user_data_dir=".browser-profile",
        port=9333,
        browser_hardening="minimal",
        proxy="http://127.0.0.1:8080",
        user_agent="ua-fixed",
        accept_language="en-US,en;q=0.9",
    )

    assert ("set_local_port", 9333) in calls
    assert any(name == "set_user_data_path" and str(value).endswith(".browser-profile") for name, value in calls)
    assert ("set_proxy", "http://127.0.0.1:8080") in calls
    assert ("set_user_agent", "ua-fixed") in calls
    assert ("set_argument", ("--lang", "en-US")) in calls


def test_prepare_listing_product_resolves_bundle_deals_entry_product():
    product = {
        "title": "shock pad",
        "url": "https://www.aliexpress.com/ssr/300000512/BundleDeals2?productIds=1005007009946538:12000057714698736&pha_manifest=ssr&_immersiveMode=true&disableNav=YES&sourceName=SEARCHProduct&utparam-url=scene:search|query_from:|x_object_id:1005007009946538|_p_origin_prod:1005008778696174",
    }

    browser._prepare_listing_product(product)

    assert product["entryType"] == "promo_card"
    assert product["cardUrl"] == product["promoLandingUrl"]
    assert product["resolvedProductUrl"] == "https://www.aliexpress.com/item/1005007009946538.html"
    assert product["isPromoted"] is True


def test_go_to_next_page_requires_product_signature_change(monkeypatch):
    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress"

        def run_js(self, script):
            if script == PRODUCT_SCRIPT:
                return [{"url": "https://www.aliexpress.com/item/100500001.html"}]
            if "const targetPage = 2;" in script:
                return "quick-jumper"
            return None

    monkeypatch.setattr(browser, "_scroll_to_pagination", lambda page: True)
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)

    assert browser._go_to_next_page(FakePage(), 2) is False


def test_scroll_to_pagination_retries_after_context_lost(monkeypatch):
    class FakePage:
        def __init__(self):
            self.ready_calls = 0

        def run_js(self, script):
            if script == browser.PAGINATION_READY_SCRIPT:
                self.ready_calls += 1
                if self.ready_calls == 1:
                    raise ContextLostError()
                if self.ready_calls == 2:
                    return False
                return True
            if script.startswith("return Math.max("):
                return 1200
            if script.startswith("window.scrollTo(0, Math.max("):
                return None
            raise AssertionError(script)

    monkeypatch.setattr(browser, "_sleep_jitter", lambda min_s, max_s: None)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)

    assert browser._scroll_to_pagination(FakePage(), rounds=2) is True


def test_wait_for_listing_change_retries_after_context_lost(monkeypatch):
    class FakePage:
        def __init__(self):
            self.calls = 0

        def run_js(self, script):
            assert script == PRODUCT_SCRIPT
            self.calls += 1
            if self.calls == 1:
                raise ContextLostError()
            return [{"url": f"https://www.aliexpress.com/item/{1000 + self.calls}.html"}]

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)

    assert browser._wait_for_listing_change(
        FakePage(),
        ("1001",),
        timeout_seconds=0.05,
        interval_seconds=0,
    ) is True


def test_collect_current_page_returns_all_products_without_max_items_cap(monkeypatch):
    class FakePage:
        def run_js(self, script):
            if script == PRODUCT_SCRIPT:
                return [
                    {"url": "https://www.aliexpress.com/item/1.html"},
                    {"url": "https://www.aliexpress.com/item/2.html"},
                    {"url": "https://www.aliexpress.com/item/3.html"},
                ]
            return None

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)

    products = browser._collect_current_page(FakePage(), scroll_rounds=1)

    assert [product["url"] for product in products] == [
        "https://www.aliexpress.com/item/1.html",
        "https://www.aliexpress.com/item/2.html",
        "https://www.aliexpress.com/item/3.html",
    ]


def test_collect_current_page_retries_after_context_lost(monkeypatch):
    class FakePage:
        def __init__(self):
            self.product_calls = 0

        def run_js(self, script):
            if script == PRODUCT_SCRIPT:
                self.product_calls += 1
                if self.product_calls == 1:
                    raise ContextLostError()
                return [{"url": "https://www.aliexpress.com/item/1.html"}]
            if script.startswith("window.scrollBy(0, "):
                return None
            return None

    monkeypatch.setattr(browser, "_sleep_jitter", lambda min_s, max_s: None)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)

    products = browser._collect_current_page(FakePage(), scroll_rounds=1)

    assert [product["url"] for product in products] == [
        "https://www.aliexpress.com/item/1.html",
    ]


def test_go_to_next_page_succeeds_when_click_triggers_context_lost(monkeypatch):
    class FakePage:
        url = "https://www.aliexpress.com/wholesale?SearchText=women+dress"

        def __init__(self):
            self.after_click = False

        def run_js(self, script):
            if script == PRODUCT_SCRIPT:
                if self.after_click:
                    return [{"url": "https://www.aliexpress.com/item/100500002.html"}]
                return [{"url": "https://www.aliexpress.com/item/100500001.html"}]
            if "const targetPage = 2;" in script:
                self.after_click = True
                raise ContextLostError()
            if script == "window.scrollTo(0, 0);":
                return None
            raise AssertionError(script)

    monkeypatch.setattr(browser, "_scroll_to_pagination", lambda page: True)
    monkeypatch.setattr(browser, "_sleep_jitter", lambda min_s, max_s: None)
    monkeypatch.setattr(browser, "_pause_after_navigation", lambda: None)
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)

    assert browser._go_to_next_page(FakePage(), 2) is True


def test_finalize_products_applies_total_cap_once():
    class FakePage:
        url = "https://www.aliexpress.com/w/wholesale-women-dress.html"

    raw = [
        {"url": "https://www.aliexpress.com/item/1.html"},
        {"url": "https://www.aliexpress.com/item/2.html"},
        {"url": "https://www.aliexpress.com/item/3.html"},
    ]

    products = browser._finalize_products(
        FakePage(),
        raw,
        max_items=2,
        enrich_detail=False,
    )

    assert [product["url"] for product in products] == [
        "https://www.aliexpress.com/item/1.html",
        "https://www.aliexpress.com/item/2.html",
    ]


def test_finalize_products_enriches_every_final_product_when_enabled(monkeypatch):
    class FakePage:
        url = "https://www.aliexpress.com/w/wholesale-women-dress.html"

    raw = [
        {"url": "https://www.aliexpress.com/item/1.html"},
        {"url": "https://www.aliexpress.com/item/2.html"},
        {"url": "https://www.aliexpress.com/item/3.html"},
    ]
    enriched_urls: list[str] = []

    def fake_enrich(page, products):
        for product in products:
            enriched_urls.append(product["url"])
            product["shopName"] = "Example Store"

    monkeypatch.setattr(browser, "_enrich_product_details", fake_enrich)

    products = browser._finalize_products(
        FakePage(),
        raw,
        max_items=2,
        enrich_detail=True,
    )

    assert enriched_urls == [
        "https://www.aliexpress.com/item/1.html",
        "https://www.aliexpress.com/item/2.html",
    ]
    assert products[0]["shopName"] == "Example Store"


def test_enrich_single_product_detail_marks_captcha_blocked(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"
            self.calls: list[str] = []

        def get(self, url):
            self.calls.append(url)
            self.url = url

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        browser,
        "_open_detail_from_listing_context",
        lambda page, product: setattr(page, "url", "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1")
        or setattr(page, "title", "验证码拦截")
        or True,
    )
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)
    monkeypatch.setattr(
        browser,
        "_wait_for_captcha_resolution",
        lambda page, timeout_seconds=60.0, interval_seconds=1.0: (
            False,
            {
                "stage": "detail",
                "page_url": "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1",
                "result": "failed",
                "fail_reason": "gate_not_cleared",
            },
        ),
    )

    product = {"url": "https://www.aliexpress.com/item/1.html", "title": "blocked first"}

    status = browser.enrich_single_product_detail(FakePage(), product)

    assert status == "captcha_blocked"
    assert product["detailStatus"] == "captcha_blocked"
    assert product["_captchaDiagnostic"] == {
        "stage": "detail",
        "page_url": "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1",
        "result": "failed",
        "fail_reason": "gate_not_cleared",
    }
    assert product.get("attributesText", "") == ""
    assert product.get("descriptionText", "") == ""


def test_enrich_single_product_detail_overwrites_captcha_diagnostic_on_success(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"

        def get(self, url):
            self.url = url

        def back(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"

        def run_js(self, script):
            if script == browser.DETAIL_FIELDS_SCRIPT:
                return {
                    "shopName": "Example Store",
                    "shopNameCandidates": ["Example Store"],
                    "attributesText": '{"Type":"Accessory"}',
                    "attributePairs": [],
                    "descriptionText": "detail text",
                    "descriptionFrameText": "",
                    "jsonLdDescription": "",
                    "metaDescription": "",
                    "breadcrumb": "",
                    "breadcrumbCandidates": [],
                    "detailReviewText": "",
                    "reviewerText": "",
                }
            return {}

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        browser,
        "_open_detail_from_listing_context",
        lambda page, product: setattr(page, "url", "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1")
        or setattr(page, "title", "验证码拦截")
        or True,
    )
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)
    monkeypatch.setattr(
        browser,
        "_wait_for_captcha_resolution",
        lambda page, timeout_seconds=60.0, interval_seconds=1.0: (
            True,
            {
                "stage": "detail",
                "page_url": "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1",
                "result": "solved",
                "fail_reason": "",
            },
        ),
    )

    product = {
        "url": "https://www.aliexpress.com/item/1.html",
        "title": "resolved first",
        "_captchaDiagnostic": {"stage": "old", "page_url": "old", "result": "failed", "fail_reason": "old"},
    }

    status = browser.enrich_single_product_detail(FakePage(), product)

    assert status == "detail_enriched"
    assert product["detailStatus"] == "detail_enriched"
    assert product["_captchaDiagnostic"] == {
        "stage": "detail",
        "page_url": "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1",
        "result": "solved",
        "fail_reason": "",
    }
    assert product["shopName"] == "Example Store"


def test_enrich_single_product_detail_marks_missing_url_status():
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"

    product = {"title": "missing url"}

    status = browser.enrich_single_product_detail(FakePage(), product)

    assert status == "detail_missing_url"
    assert product["detailStatus"] == "detail_missing_url"


def test_enrich_single_product_detail_writes_detail_fields_on_success(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"

        def get(self, url):
            self.url = url

        def back(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"

        def run_js(self, script):
            if script == browser.DETAIL_FIELDS_SCRIPT:
                return {
                    "shopName": "Example Store",
                    "shopNameCandidates": ["Example Store"],
                    "attributesText": '{"Type":"Accessory"}',
                    "attributePairs": [],
                    "descriptionText": "detail text",
                    "descriptionFrameText": "",
                    "jsonLdDescription": "",
                    "metaDescription": "",
                    "breadcrumb": "",
                    "breadcrumbCandidates": [],
                    "detailReviewText": "",
                    "reviewerText": "",
                }
            return {}

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        browser,
        "_open_detail_from_listing_context",
        lambda page, product: setattr(page, "url", product["url"]) or setattr(page, "title", "detail") or True,
    )
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)

    product = {"url": "https://www.aliexpress.com/item/1.html", "title": "normal item"}

    status = browser.enrich_single_product_detail(FakePage(), product)

    assert status == "detail_enriched"
    assert product["detailStatus"] == "detail_enriched"
    assert product["shopName"] == "Example Store"
    assert product["attributesText"] == '{"Type":"Accessory"}'
    assert product["descriptionText"] == "detail text"


def test_enrich_single_product_detail_keeps_listing_page_when_listing_context_restore_fails(monkeypatch):
    listing_url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"

    class FakePage:
        def __init__(self):
            self.url = listing_url
            self.title = "listing"
            self.back_calls = 0

        def back(self):
            self.back_calls += 1
            self.url = "https://www.aliexpress.com/unexpected-history-target.html"
            self.title = "wrong"

    monkeypatch.setattr(browser, "_restore_listing_context", lambda page, product, default_listing_url: False)

    product = {
        "url": "https://www.aliexpress.com/item/1.html",
        "_listingBaseUrl": listing_url,
        "_listingPageUrl": listing_url,
        "_listingPageNumber": 2,
    }

    page = FakePage()
    status = browser.enrich_single_product_detail(page, product)

    assert status == "listing_context_failed"
    assert product["detailStatus"] == "listing_context_failed"
    assert page.url == listing_url
    assert page.back_calls == 0


def test_enrich_single_product_detail_sets_status_on_exception(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"

    monkeypatch.setattr(browser, "_open_detail_from_listing_context", lambda page, product: (_ for _ in ()).throw(RuntimeError("boom")))

    product = {"url": "https://www.aliexpress.com/item/1.html", "title": "raises on open"}

    status = browser.enrich_single_product_detail(FakePage(), product)

    assert status == "detail_open_failed"
    assert product["detailStatus"] == "detail_open_failed"


def test_enrich_product_details_continues_after_single_product_failure(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-women-dress.html"
            self.title = "listing"

        def get(self, url):
            self.url = url

        def run_js(self, script):
            return {
                "shopName": "Example Store",
                "shippingText": "Free shipping",
                "detailRatingText": "4.9",
                "detailReviewText": "20 reviews",
                "breadcrumb": "Home > Dresses",
                "attributesText": '{"Material":"Cotton"}',
                "descriptionText": "Long sleeve dress",
            }

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    open_calls = {"count": 0}

    def fake_open(page, product):
        open_calls["count"] += 1
        if product["url"].endswith("/2.html"):
            raise RuntimeError("boom")
        page.url = product["url"]
        page.title = "detail"
        return True

    monkeypatch.setattr(browser, "_open_detail_from_listing_context", fake_open)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)

    products = [
        {"url": "https://www.aliexpress.com/item/1.html"},
        {"url": "https://www.aliexpress.com/item/2.html"},
        {"url": "https://www.aliexpress.com/item/3.html"},
    ]

    browser._enrich_product_details(FakePage(), products)

    assert products[0]["shopName"] == "Example Store"
    assert products[1].get("shopName", "") == ""
    assert products[2]["shopName"] == "Example Store"
    assert open_calls["count"] == 3


def test_enrich_product_details_restores_default_listing_after_open_failure(monkeypatch):
    listing_url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"

    class FakePage:
        def __init__(self):
            self.url = listing_url
            self.title = "listing"
            self.mode = "listing"
            self.calls: list[str] = []

        def get(self, url):
            self.calls.append(url)
            self.url = url
            if url == listing_url:
                self.mode = "listing"
                self.title = "listing"
            elif "/item/" in url:
                self.mode = "detail"
                self.title = "detail"
            else:
                self.mode = "promo"
                self.title = "promo"

        def back(self):
            self.url = listing_url
            self.mode = "listing"
            self.title = "listing"

        def run_js(self, script):
            if script == browser.DETAIL_FIELDS_SCRIPT:
                return {
                    "shopName": "Example Store",
                    "attributesText": '{"Type":"Accessory"}',
                    "descriptionText": "detail text",
                }
            return {}

    open_modes: list[tuple[str, str]] = []

    def fake_open(page, product):
        open_modes.append((product["url"], page.mode))
        if product["url"].endswith("/1.html"):
            page.url = "https://www.aliexpress.com/ssr/300000512/BundleDeals2"
            page.mode = "promo"
            page.title = "promo"
            return False
        if page.mode != "listing":
            return False
        page.url = product["url"]
        page.mode = "detail"
        page.title = "detail"
        return True

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_open_detail_from_listing_context", fake_open)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)

    products = [
        {"url": "https://www.aliexpress.com/item/1.html"},
        {"url": "https://www.aliexpress.com/item/2.html"},
    ]

    page = FakePage()
    browser._enrich_product_details(page, products)

    assert open_modes == [
        ("https://www.aliexpress.com/item/1.html", "listing"),
        ("https://www.aliexpress.com/item/2.html", "listing"),
    ]
    assert products[0]["detailStatus"] == "detail_open_failed"
    assert products[1]["shopName"] == "Example Store"
    assert page.calls[0] == listing_url


def test_enrich_product_details_stops_after_captcha_and_marks_status(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"
            self.calls: list[str] = []

        def get(self, url):
            self.calls.append(url)
            self.url = url

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        browser,
        "_open_detail_from_listing_context",
        lambda page, product: setattr(page, "url", "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1")
        or setattr(page, "title", "验证码拦截")
        or True,
    )
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)
    monkeypatch.setattr(
        browser,
        "_wait_for_captcha_resolution",
        lambda page, timeout_seconds=60.0, interval_seconds=1.0: (
            False,
            {
                "stage": "detail",
                "page_url": "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1",
                "result": "failed",
                "fail_reason": "gate_not_cleared",
            },
        ),
    )

    products = [
        {"url": "https://www.aliexpress.com/item/1.html", "title": "blocked first"},
        {"url": "https://www.aliexpress.com/item/2.html", "title": "must not continue"},
    ]

    page = FakePage()
    browser.enrich_listing_products(page, products)

    assert page.calls == ["https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"]
    assert products[0]["detailStatus"] == "captcha_blocked"
    assert products[0]["_captchaDiagnostic"]["stage"] == "detail"
    assert products[0].get("attributesText", "") == ""
    assert products[0].get("descriptionText", "") == ""
    assert products[1]["detailStatus"] == "detail_skipped_after_captcha"
    assert products[1].get("shopName", "") == ""


def test_enrich_product_details_resumes_when_captcha_is_cleared(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"
            self.current_url = ""

        def get(self, url):
            self.url = url

        def back(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"

        def run_js(self, script):
            if script == browser.DETAIL_FIELDS_SCRIPT:
                return {
                    "shopName": "Example Store",
                    "attributesText": '{"Type":"Accessory"}',
                    "descriptionText": f"detail for {self.current_url}",
                }
            return {}

    open_calls = {"count": 0}

    def fake_open(page, product):
        open_calls["count"] += 1
        page.current_url = product["url"]
        if open_calls["count"] == 1:
            page.url = "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1"
            page.title = "验证码拦截"
            return True
        page.url = product["url"]
        page.title = "detail"
        return True

    def fake_wait_for_captcha(page, timeout_seconds=60.0, interval_seconds=1.0):
        page.url = page.current_url
        page.title = "detail"
        return True, None

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_open_detail_from_listing_context", fake_open)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)
    monkeypatch.setattr(browser, "_wait_for_captcha_resolution", fake_wait_for_captcha)

    products = [
        {"url": "https://www.aliexpress.com/item/1.html", "title": "captcha then cleared"},
        {"url": "https://www.aliexpress.com/item/2.html", "title": "normal next"},
    ]

    browser._enrich_product_details(FakePage(), products)

    assert products[0]["shopName"] == "Example Store"
    assert products[0]["detailStatus"] == "detail_enriched"
    assert products[1]["shopName"] == "Example Store"
    assert products[1]["detailStatus"] == "detail_enriched"


def test_enrich_product_details_resolves_promo_entry_and_keeps_promotion_text(monkeypatch):
    promo_url = (
        "https://www.aliexpress.com/ssr/300000512/BundleDeals2?"
        "productIds=1005007009946538:12000057714698736&pha_manifest=ssr&_immersiveMode=true"
        "&disableNav=YES&sourceName=SEARCHProduct&utparam-url=scene:search|query_from:|x_object_id:1005007009946538|_p_origin_prod:1005008778696174"
    )
    resolved_url = "https://www.aliexpress.com/item/1005007009946538.html"

    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"
            self.calls: list[str] = []

        def get(self, url):
            self.calls.append(url)
            self.url = url

        def run_js(self, script):
            if script == browser.PROMO_FIELDS_SCRIPT:
                return {
                    "promoChannel": "Dollar Express",
                    "promotionText": "Free shipping on 3 items | Free returns | Buy more,save more",
                }
            if script == browser.DETAIL_FIELDS_SCRIPT:
                return {
                    "shopName": "Example Store",
                    "shippingText": "Free shipping",
                    "detailRatingText": "4.9",
                    "detailReviewText": "20 reviews",
                    "breadcrumb": "Home > Appliances",
                    "attributesText": '{"Material":"Cotton"}',
                    "descriptionText": "Shock pad detail",
                }
                return {}

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        browser,
        "_open_detail_from_listing_context",
        lambda page, product: setattr(page, "url", resolved_url) or setattr(page, "title", "detail") or True,
    )
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)

    products = [
        {
            "title": "shock pad",
            "url": promo_url,
        }
    ]

    browser._prepare_listing_product(products[0])
    page = FakePage()
    browser._enrich_product_details(page, products)

    assert page.calls[0] == promo_url
    assert page.calls[-1] == "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
    assert products[0]["promoChannel"] == "Dollar Express"
    assert products[0]["promotionText"] == "Free shipping on 3 items | Free returns | Buy more,save more"
    assert products[0]["shopName"] == "Example Store"
    assert products[0]["url"] == resolved_url


def test_enrich_product_details_restores_listing_context_for_products_from_multiple_pages(monkeypatch):
    listing_page_1 = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
    listing_page_2 = f"{listing_page_1}?page=2"

    class FakePage:
        def __init__(self):
            self.url = listing_page_2
            self.title = "listing"
            self.current_listing_page = 2

        def get(self, url):
            self.url = url
            if url == listing_page_2:
                self.current_listing_page = 2
                self.title = "listing"
            elif url == listing_page_1:
                self.current_listing_page = 1
                self.title = "listing"
            elif "/item/" in url:
                self.title = "detail"

        def back(self):
            if self.current_listing_page == 2:
                self.url = listing_page_2
            else:
                self.url = listing_page_1
            self.title = "listing"

        def run_js(self, script):
            if script == browser.DETAIL_FIELDS_SCRIPT:
                return {
                    "shopName": f"Store p{self.current_listing_page}",
                    "attributesText": '{"Type":"Accessory"}',
                    "descriptionText": f"detail page {self.current_listing_page}",
                }
            return {}

    open_attempts: list[tuple[str, int]] = []
    advance_calls: list[int] = []

    def fake_open(page, product):
        open_attempts.append((product["url"], page.current_listing_page))
        if page.title != "listing" or page.current_listing_page != product["_listingPageNumber"]:
            return False
        page.url = product["url"]
        page.title = "detail"
        return True

    def fake_advance(page, target_page):
        advance_calls.append(target_page)
        page.url = listing_page_2
        page.current_listing_page = target_page
        page.title = "listing"
        return True

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_open_detail_from_listing_context", fake_open)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)
    monkeypatch.setattr(browser, "advance_listing_page", fake_advance)

    products = [
        {
            "url": "https://www.aliexpress.com/item/1.html",
            "_listingBaseUrl": listing_page_1,
            "_listingPageUrl": listing_page_1,
            "_listingPageNumber": 1,
        },
        {
            "url": "https://www.aliexpress.com/item/2.html",
            "_listingBaseUrl": listing_page_1,
            "_listingPageUrl": listing_page_2,
            "_listingPageNumber": 2,
        },
    ]

    page = FakePage()
    browser._enrich_product_details(page, products)

    assert open_attempts == [
        ("https://www.aliexpress.com/item/1.html", 1),
        ("https://www.aliexpress.com/item/2.html", 2),
    ]
    assert advance_calls == [2]
    assert products[0]["shopName"] == "Store p1"
    assert products[1]["shopName"] == "Store p2"
    assert products[0]["detailStatus"] == "detail_enriched"
    assert products[1]["detailStatus"] == "detail_enriched"


def test_enrich_product_details_restores_listing_context_after_promo_capture(monkeypatch):
    listing_page = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
    promo_url = (
        "https://www.aliexpress.com/ssr/300000512/BundleDeals2?"
        "productIds=1005007009946538:12000057714698736&pha_manifest=ssr&_immersiveMode=true"
    )
    resolved_url = "https://www.aliexpress.com/item/1005007009946538.html"
    normal_url = "https://www.aliexpress.com/item/2000000000000000.html"

    class FakePage:
        def __init__(self):
            self.url = listing_page
            self.title = "listing"
            self.mode = "listing"
            self.current_listing_page = 1

        def get(self, url):
            self.url = url
            if url == promo_url:
                self.mode = "promo"
                self.title = "promo"
            elif "/item/" in url:
                self.mode = "detail"
                self.title = "detail"
            else:
                self.mode = "listing"
                self.title = "listing"

        def back(self):
            self.url = listing_page
            self.mode = "listing"
            self.title = "listing"

        def run_js(self, script):
            if script == browser.PROMO_FIELDS_SCRIPT:
                return {
                    "promoChannel": "Dollar Express",
                    "promotionText": "Free shipping on 3 items | Free returns | Buy more,save more",
                }
            if script == browser.DETAIL_FIELDS_SCRIPT:
                return {
                    "shopName": "Example Store",
                    "attributesText": '{"Type":"Accessory"}',
                    "descriptionText": "detail text",
                }
            return {}

    open_modes: list[str] = []

    def fake_open(page, product):
        open_modes.append(page.mode)
        if page.mode != "listing":
            return False
        page.url = str(product.get("resolvedProductUrl") or product.get("url") or "")
        page.mode = "detail"
        page.title = "detail"
        return True

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_open_detail_from_listing_context", fake_open)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)

    products = [
        {
            "url": promo_url,
            "_listingBaseUrl": listing_page,
            "_listingPageUrl": listing_page,
            "_listingPageNumber": 1,
        },
        {
            "url": normal_url,
            "_listingBaseUrl": listing_page,
            "_listingPageUrl": listing_page,
            "_listingPageNumber": 1,
        },
    ]

    page = FakePage()
    browser._enrich_product_details(page, products)

    assert open_modes == ["listing", "listing"]
    assert products[0]["promoChannel"] == "Dollar Express"
    assert products[0]["shopName"] == "Example Store"
    assert products[1]["shopName"] == "Example Store"
    assert products[0]["detailStatus"] == "detail_enriched"
    assert products[1]["detailStatus"] == "detail_enriched"


def test_open_detail_from_listing_context_clicks_card_and_waits_for_navigation(monkeypatch):
    calls: list[str] = []

    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"

        def run_js(self, script):
            calls.append(script)
            if "window.__ALI_MVP_DETAIL_CLICK__" in script:
                self.url = "https://www.aliexpress.com/item/1001.html"
                self.title = "detail"
                return "clicked"
            return None

    wait_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page: wait_calls.append((page.url, page.title)))

    product = {
        "cardUrl": "https://www.aliexpress.com/item/1001.html?from=search",
        "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
    }

    page = FakePage()
    opened = browser._open_detail_from_listing_context(page, product)

    assert opened is True
    assert page.url == "https://www.aliexpress.com/item/1001.html"
    assert wait_calls == [("https://www.aliexpress.com/item/1001.html", "detail")]
    assert any('window.__ALI_MVP_DETAIL_CLICK__' in script for script in calls)


def test_open_detail_from_listing_context_handles_context_lost_after_navigation(monkeypatch):
    wait_calls: list[tuple[str, str]] = []

    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"
            self.tab_id = "listing-tab"
            self.tab_ids = ["listing-tab"]
            self.latest_tab = "listing-tab"

        def run_js(self, script):
            if "window.__ALI_MVP_DETAIL_CLICK__" in script:
                self.url = "https://www.aliexpress.com/item/1001.html"
                self.title = "detail"
                raise ContextLostError()
            if script == "return document.readyState;":
                return "complete"
            return None

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page: wait_calls.append((page.url, page.title)))

    product = {
        "cardUrl": "https://www.aliexpress.com/item/1001.html?from=search",
        "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
    }

    page = FakePage()
    opened = browser._open_detail_from_listing_context(page, product)

    assert opened is True
    assert page.url == "https://www.aliexpress.com/item/1001.html"
    assert product["_detailUsedNewTab"] is False
    assert wait_calls == [("https://www.aliexpress.com/item/1001.html", "detail")]


def test_open_detail_from_listing_context_requires_leaving_listing_page(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"

        def run_js(self, script):
            return "clicked"

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)

    product = {
        "cardUrl": "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html",
        "resolvedProductUrl": "",
    }

    page = FakePage()
    opened = browser._open_detail_from_listing_context(page, product)

    assert opened is False


def test_open_detail_from_listing_context_switches_to_new_tab_when_card_opens_blank(monkeypatch):
    calls: list[str] = []

    class FakeDetailTab:
        def __init__(self):
            self.url = "https://www.aliexpress.com/item/1001.html"
            self.title = "detail"
            self.tab_id = "detail-tab"

        def run_js(self, script):
            calls.append(("detail", script))
            if script == "return document.readyState;":
                return "complete"
            return None

    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"
            self.tab_id = "listing-tab"
            self.tab_ids = ["listing-tab"]
            self.latest_tab = "listing-tab"
            self.detail_tab = FakeDetailTab()

        def run_js(self, script):
            calls.append(("listing", script))
            if script == "return document.readyState;":
                return "complete"
            self.tab_ids = ["listing-tab", "detail-tab"]
            self.latest_tab = "detail-tab"
            return "clicked"

        def get_tab(self, id_or_num=None, title=None, url=None, tab_type="page", as_id=False):
            assert id_or_num == "detail-tab"
            return self.detail_tab

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)

    product = {
        "cardUrl": "https://www.aliexpress.com/item/1001.html?from=search",
        "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
    }

    page = FakePage()
    opened = browser._open_detail_from_listing_context(page, product)

    assert opened is True
    assert product["_detailTabId"] == "detail-tab"
    assert product["_detailUsedNewTab"] is True


def test_open_detail_from_listing_context_falls_back_to_direct_navigation_when_card_missing(monkeypatch):
    wait_calls: list[tuple[str, str]] = []

    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"
            self.title = "listing"
            self.calls: list[str] = []

        def run_js(self, script):
            self.calls.append(script)
            if "window.__ALI_MVP_DETAIL_CLICK__" in script:
                return "missing"
            return None

        def get(self, url):
            self.url = url
            self.title = "detail"

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page: wait_calls.append((page.url, page.title)))

    product = {
        "entryType": "item_card",
        "cardUrl": "https://www.aliexpress.com/item/1001.html?from=search",
        "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
    }

    page = FakePage()
    opened = browser._open_detail_from_listing_context(page, product)

    assert opened is True
    assert page.url == "https://www.aliexpress.com/item/1001.html?from=search"
    assert wait_calls == [("https://www.aliexpress.com/item/1001.html?from=search", "detail")]


def test_is_captcha_page_detects_punish_url_and_title():
    assert browser._is_captcha_page("https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1", "normal") is True
    assert browser._is_captcha_page("https://www.aliexpress.com/item/1.html", "验证码拦截") is True
    assert browser._is_captcha_page("https://www.aliexpress.com/item/1.html", "Thermomix - AliExpress 6") is False


def test_wait_for_captcha_resolution_tries_solver_once_and_returns_true_on_success(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1"
            self.title = "验证码拦截"

    page = FakePage()
    calls = {"solve": 0, "ready": 0}

    def fake_solve(target, timeout_seconds=30.0):
        calls["solve"] += 1
        target.url = "https://www.aliexpress.com/item/1.html"
        target.title = "detail"
        return True, {
            "result": "solved",
            "fail_reason": "",
        }

    monkeypatch.setattr(
        browser,
        "try_solve_captcha",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("old API should not be used")),
        raising=False,
    )
    monkeypatch.setattr(browser, "try_solve_captcha_with_result", fake_solve, raising=False)
    monkeypatch.setattr(
        browser,
        "_wait_for_page_ready",
        lambda page, timeout_seconds=8.0: calls.__setitem__("ready", calls["ready"] + 1),
    )
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)

    solved, diagnostic = browser._wait_for_captcha_resolution(page, timeout_seconds=2.0, interval_seconds=0.1)

    assert solved is True
    assert diagnostic["stage"] == "detail"
    assert diagnostic["page_url"] == "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1"
    assert calls["solve"] == 1
    assert calls["ready"] == 1


def test_wait_for_captcha_resolution_keeps_existing_timeout_path_when_solver_fails(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1"
            self.title = "验证码拦截"

    page = FakePage()
    calls = {"solve": 0, "sleep": 0, "ready": 0}
    moments = iter([0.0, 0.2, 0.6, 1.2])

    monkeypatch.setattr(
        browser,
        "try_solve_captcha",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("old API should not be used")),
        raising=False,
    )
    monkeypatch.setattr(
        browser,
        "try_solve_captcha_with_result",
        lambda target, timeout_seconds=30.0: (
            calls.__setitem__("solve", calls["solve"] + 1) or False,
            {
                "result": "failed",
                "fail_reason": "gate_not_cleared",
            },
        ),
        raising=False,
    )
    monkeypatch.setattr(
        browser,
        "_wait_for_page_ready",
        lambda page, timeout_seconds=8.0: calls.__setitem__("ready", calls["ready"] + 1),
    )
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: calls.__setitem__("sleep", calls["sleep"] + 1))
    monkeypatch.setattr(browser.time, "monotonic", lambda: next(moments))

    solved, diagnostic = browser._wait_for_captcha_resolution(page, timeout_seconds=1.0, interval_seconds=0.1)

    assert solved is False
    assert diagnostic["stage"] == "detail"
    assert diagnostic["page_url"] == "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1"
    assert diagnostic["result"] == "failed"
    assert diagnostic["fail_reason"] == "gate_not_cleared"
    assert calls["solve"] == 1
    assert calls["sleep"] == 1
    assert calls["ready"] == 1


def test_wait_for_captcha_resolution_does_not_extra_wait_after_solver_consumes_budget(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1"
            self.title = "验证码拦截"

    page = FakePage()
    calls = {"solve": 0, "sleep": 0, "ready": 0}
    moments = iter([0.0, 0.2, 1.2])

    monkeypatch.setattr(
        browser,
        "try_solve_captcha",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("old API should not be used")),
        raising=False,
    )
    monkeypatch.setattr(
        browser,
        "try_solve_captcha_with_result",
        lambda target, timeout_seconds=30.0: (
            calls.__setitem__("solve", calls["solve"] + 1) or False,
            {
                "result": "failed",
                "fail_reason": "gate_not_cleared",
            },
        ),
        raising=False,
    )
    monkeypatch.setattr(
        browser,
        "_wait_for_page_ready",
        lambda page, timeout_seconds=8.0: calls.__setitem__("ready", calls["ready"] + 1),
    )
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: calls.__setitem__("sleep", calls["sleep"] + 1))
    monkeypatch.setattr(browser.time, "monotonic", lambda: next(moments))

    solved, diagnostic = browser._wait_for_captcha_resolution(page, timeout_seconds=1.0, interval_seconds=0.1)

    assert solved is False
    assert diagnostic["stage"] == "detail"
    assert calls["solve"] == 1
    assert calls["sleep"] == 0
    assert calls["ready"] == 0


def test_normalize_detail_fields_prefers_real_store_name_and_cleans_breadcrumb_and_description():
    detail = {
        "shopName": "0 Cart",
        "shopNameCandidates": [
            "0 Cart",
            "Store",
            "Sold By BroKun Store (Trader)",
            "BroKun Store",
            "Message",
        ],
        "breadcrumb": "This product belongs to Home > Home",
        "breadcrumbCandidates": [
            "This product belongs to Home",
            "Home",
        ],
        "descriptionText": "Top Brand on AliExpress: Highly Rated 2,000+ people rated this brand highly.",
        "descriptionFrameText": "",
        "detailReviewText": "",
        "reviewerText": "4.9 353 Reviews ౹ This seller: 800+ sales | Total sales: 1,000+",
    }

    normalized = browser._normalize_detail_fields(detail)

    assert normalized["shopName"] == "BroKun Store"
    assert normalized["breadcrumb"] == "Home"
    assert normalized["descriptionText"] == ""
    assert normalized["detailReviewText"] == "353 Reviews"


def test_normalize_detail_fields_prefers_iframe_description_when_available():
    detail = {
        "shopName": "Example Store",
        "shopNameCandidates": ["Example Store"],
        "breadcrumb": "",
        "breadcrumbCandidates": [],
        "descriptionText": "Description Report this item or seller",
        "descriptionFrameText": "Actual product details for size and material.",
        "detailReviewText": "197 Reviews",
        "reviewerText": "4.5 197 Reviews ౹ 1,000+ sold",
    }

    normalized = browser._normalize_detail_fields(detail)

    assert normalized["descriptionText"] == "Actual product details for size and material."


def test_normalize_detail_fields_merges_spec_pairs_and_jsonld_description_fallback():
    detail = {
        "shopName": "Example Store",
        "shopNameCandidates": ["Example Store"],
        "breadcrumb": "",
        "breadcrumbCandidates": [],
        "attributesText": '{"Color":"110V"}',
        "attributePairs": [
            {"key": "Electric", "value": "No"},
            {"key": "Brand Name", "value": "FULANG,OLOEY"},
            {"key": "Color", "value": "220V"},
        ],
        "descriptionText": "Description Report this item or seller",
        "descriptionFrameText": "",
        "jsonLdDescription": "Buy Home Wireless Chest Enhanced Vibration Massage Machine USB Device Massager 2026 at AliExpress.",
        "detailReviewText": "",
        "reviewerText": "",
    }

    normalized = browser._normalize_detail_fields(detail)

    assert json.loads(normalized["attributesText"]) == {
        "Color": "110V",
        "Electric": "No",
        "Brand Name": "FULANG,OLOEY",
    }
    assert normalized["descriptionText"] == "Buy Home Wireless Chest Enhanced Vibration Massage Machine USB Device Massager 2026 at AliExpress."


def test_normalize_detail_fields_uses_meta_description_fallback_when_other_description_sources_are_empty():
    detail = {
        "shopName": "Example Store",
        "shopNameCandidates": ["Example Store"],
        "breadcrumb": "",
        "breadcrumbCandidates": [],
        "descriptionText": "Description Report this item or seller",
        "descriptionFrameText": "",
        "jsonLdDescription": "",
        "metaDescription": "Replacement Parts 6 Point Fusion 4980 Blade Cutter Assembly Compatible with Oster Osterizer Blender.",
        "detailReviewText": "",
        "reviewerText": "",
    }

    normalized = browser._normalize_detail_fields(detail)

    assert normalized["descriptionText"] == (
        "Replacement Parts 6 Point Fusion 4980 Blade Cutter Assembly Compatible with Oster Osterizer Blender."
    )


def test_normalize_detail_fields_cleans_polluted_breadcrumb_fallback():
    detail = {
        "shopName": "",
        "shopNameCandidates": [],
        "breadcrumb": "Home > , and you can find similar products at All Categories, > All Categories > , > Consumer Electronics > Home Electronic Accessories > Remote Controls > .",
        "breadcrumbCandidates": [],
        "descriptionText": "",
        "descriptionFrameText": "",
        "detailReviewText": "",
        "reviewerText": "",
    }

    normalized = browser._normalize_detail_fields(detail)

    assert normalized["breadcrumb"] == "Home > Consumer Electronics > Home Electronic Accessories > Remote Controls"


def test_normalize_detail_fields_cleans_polluted_breadcrumb_candidates():
    detail = {
        "shopName": "",
        "shopNameCandidates": [],
        "breadcrumb": "",
        "breadcrumbCandidates": [
            "This product belongs to Home, and you can find similar products at All Categories, Consumer Electronics, Home Electronic Accessories, Remote Controls.",
            "Home, and you can find similar products at All Categories, Consumer Electronics, Home Electronic Accessories, Remote Controls.",
        ],
        "descriptionText": "",
        "descriptionFrameText": "",
        "detailReviewText": "",
        "reviewerText": "",
    }

    normalized = browser._normalize_detail_fields(detail)

    assert normalized["breadcrumb"] == "Home > Consumer Electronics > Home Electronic Accessories > Remote Controls"


def test_collect_raw_products_auto_advances_until_total_target(monkeypatch):
    class FakePage:
        def __init__(self, *args, **kwargs):
            self.url = "https://www.aliexpress.com/w/wholesale-women-dress.html"

        def get(self, url):
            self.url = url

    page_results = iter(
        [
            [
                {"url": "https://www.aliexpress.com/item/1.html"},
                {"url": "https://www.aliexpress.com/item/2.html"},
            ],
            [
                {"url": "https://www.aliexpress.com/item/3.html"},
                {"url": "https://www.aliexpress.com/item/4.html"},
            ],
        ]
    )
    next_calls: list[int] = []

    monkeypatch.setattr(browser, "ChromiumPage", FakePage)
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_build_options", lambda **kwargs: object())
    monkeypatch.setattr(browser, "_collect_current_page", lambda page, scroll_rounds: next(page_results))
    monkeypatch.setattr(browser, "_go_to_next_page", lambda page, target_page: next_calls.append(target_page) or True)

    products = browser.collect_raw_products("https://example.test", max_items=3, pages=None)

    assert [product["url"] for product in products] == [
        "https://www.aliexpress.com/item/1.html",
        "https://www.aliexpress.com/item/2.html",
        "https://www.aliexpress.com/item/3.html",
    ]
    assert next_calls == [2]


def test_collect_raw_products_stops_at_explicit_page_limit(monkeypatch):
    class FakePage:
        def __init__(self, *args, **kwargs):
            self.url = "https://www.aliexpress.com/w/wholesale-women-dress.html"

        def get(self, url):
            self.url = url

    page_results = [
        [
            {"url": "https://www.aliexpress.com/item/1.html"},
            {"url": "https://www.aliexpress.com/item/2.html"},
        ],
        [
            {"url": "https://www.aliexpress.com/item/3.html"},
            {"url": "https://www.aliexpress.com/item/4.html"},
        ],
    ]
    index = {"value": 0}
    next_calls: list[int] = []

    def fake_collect(page, scroll_rounds):
        result = page_results[index["value"]]
        index["value"] += 1
        return result

    monkeypatch.setattr(browser, "ChromiumPage", FakePage)
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser, "_build_options", lambda **kwargs: object())
    monkeypatch.setattr(browser, "_collect_current_page", fake_collect)
    monkeypatch.setattr(browser, "_go_to_next_page", lambda page, target_page: next_calls.append(target_page) or True)

    products = browser.collect_raw_products("https://example.test", max_items=10, pages=1)

    assert [product["url"] for product in products] == [
        "https://www.aliexpress.com/item/1.html",
        "https://www.aliexpress.com/item/2.html",
    ]
    assert next_calls == []
