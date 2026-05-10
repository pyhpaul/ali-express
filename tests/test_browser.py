import json

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
        lambda url, user_data_dir=None, port=None: calls.__setitem__("open", calls["open"] + 1) or FakePage(),
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
            if url.endswith("/1.html"):
                self.url = "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1"
                self.title = "验证码拦截"
            else:
                self.url = url
                self.title = "normal item"

            def run_js(self, script):
                return {
                    "shopName": "Should not be used after captcha",
                    "attributesText": '{"Type":"Mixer Parts"}',
                    "descriptionText": "Should not leak into blocked item",
                }

    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        browser,
        "_open_detail_from_listing_context",
        lambda page, product: setattr(page, "url", "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1")
        or setattr(page, "title", "验证码拦截")
        or True,
    )
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)
    monkeypatch.setattr(browser, "_wait_for_captcha_resolution", lambda page, timeout_seconds=60.0, interval_seconds=1.0: False)

    products = [
        {"url": "https://www.aliexpress.com/item/1.html", "title": "blocked first"},
        {"url": "https://www.aliexpress.com/item/2.html", "title": "must not continue"},
    ]

    page = FakePage()
    browser._enrich_product_details(page, products)

    assert page.calls == ["https://www.aliexpress.com/w/wholesale-home-appliance-accessories.html"]
    assert products[0]["detailStatus"] == "captcha_blocked"
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
        return True

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
    assert products[0].get("detailStatus", "") == ""
    assert products[1]["shopName"] == "Example Store"
    assert products[1].get("detailStatus", "") == ""


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
    assert products[0].get("detailStatus", "") == ""
    assert products[1].get("detailStatus", "") == ""


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
    assert products[0].get("detailStatus", "") == ""
    assert products[1].get("detailStatus", "") == ""


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
