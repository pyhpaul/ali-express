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

        def get(self, url):
            if url.endswith("/2.html"):
                raise RuntimeError("boom")
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

    products = [
        {"url": "https://www.aliexpress.com/item/1.html"},
        {"url": "https://www.aliexpress.com/item/2.html"},
        {"url": "https://www.aliexpress.com/item/3.html"},
    ]

    browser._enrich_product_details(FakePage(), products)

    assert products[0]["shopName"] == "Example Store"
    assert products[1].get("shopName", "") == ""
    assert products[2]["shopName"] == "Example Store"


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

    products = [
        {
            "title": "shock pad",
            "url": promo_url,
        }
    ]

    browser._prepare_listing_product(products[0])
    page = FakePage()
    browser._enrich_product_details(page, products)

    assert page.calls[:2] == [promo_url, resolved_url]
    assert products[0]["promoChannel"] == "Dollar Express"
    assert products[0]["promotionText"] == "Free shipping on 3 items | Free returns | Buy more,save more"
    assert products[0]["shopName"] == "Example Store"
    assert products[0]["url"] == resolved_url


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
