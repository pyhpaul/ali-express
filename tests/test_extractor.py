from ali_mvp.extractor import normalize_products


def test_normalize_products_deduplicates_urls_and_parses_numbers():
    raw = [
        {
            "title": " Dress ",
            "price": "$12.50",
            "soldText": "1.2K sold",
            "ratingText": "4.8",
            "reviewText": "32 reviews",
            "url": "//www.aliexpress.com/item/100500.html",
            "cardUrl": "//www.aliexpress.com/item/100500.html",
            "image": "//ae01.alicdn.com/item.jpg",
            "entryType": "item_card",
            "isPromoted": False,
            "shopName": " Example Store ",
            "shippingText": " Free shipping ",
            "detailRatingText": "4.9",
            "detailReviewText": "40 reviews",
            "breadcrumb": "Home > Dresses",
            "attributesText": '{"Material":"Cotton"}',
            "descriptionText": " Long sleeve dress ",
            "promoChannel": "",
            "promotionText": "",
            "promoLandingUrl": "",
        },
        {
            "title": "Duplicate",
            "price": "$13.00",
            "soldText": "10 sold",
            "ratingText": "4.5",
            "reviewText": "5 reviews",
            "url": "https://www.aliexpress.com/item/100500.html",
            "cardUrl": "https://www.aliexpress.com/item/100500.html",
            "image": "",
        },
    ]

    products = normalize_products(
        raw,
        source_type="keyword",
        source_value="women dress",
        scraped_at="2026-05-08T00:00:00Z",
    )

    assert len(products) == 1
    product = products[0]
    assert product.title == "Dress"
    assert product.sold_count == 1200
    assert product.rating == 4.8
    assert product.review_count == 32
    assert product.product_url == "https://www.aliexpress.com/item/100500.html"
    assert product.search_card_url == "https://www.aliexpress.com/item/100500.html"
    assert product.image_url == "https://ae01.alicdn.com/item.jpg"
    assert product.entry_type == "item_card"
    assert product.is_promoted is False
    assert product.shop_name == "Example Store"
    assert product.shipping_text == "Free shipping"
    assert product.detail_rating == 4.9
    assert product.detail_review_count == 40
    assert product.breadcrumb == "Home > Dresses"
    assert product.attributes_text == '{"Material":"Cotton"}'
    assert product.description_text == "Long sleeve dress"


def test_normalize_products_uses_resolved_promo_item_url_and_keeps_promo_metadata():
    raw = [
        {
            "title": "shock pad",
            "price": "$1.13",
            "soldText": "3,000+ sold",
            "ratingText": "4.9",
            "reviewText": "",
            "url": "https://www.aliexpress.com/ssr/300000512/BundleDeals2?productIds=1005007009946538:12000057714698736",
            "resolvedProductUrl": "https://www.aliexpress.com/item/1005007009946538.html",
            "cardUrl": "https://www.aliexpress.com/ssr/300000512/BundleDeals2?productIds=1005007009946538:12000057714698736",
            "image": "//ae01.alicdn.com/item.jpg",
            "entryType": "promo_card",
            "isPromoted": True,
            "promoChannel": "Dollar Express",
            "promotionText": "Free shipping on 3 items | Free returns | Buy more,save more",
            "promoLandingUrl": "https://www.aliexpress.com/ssr/300000512/BundleDeals2?productIds=1005007009946538:12000057714698736",
        }
    ]

    products = normalize_products(
        raw,
        source_type="keyword",
        source_value="home appliance accessories",
        scraped_at="2026-05-09T00:00:00Z",
    )

    assert len(products) == 1
    product = products[0]
    assert product.product_url == "https://www.aliexpress.com/item/1005007009946538.html"
    assert product.search_card_url == "https://www.aliexpress.com/ssr/300000512/BundleDeals2?productIds=1005007009946538:12000057714698736"
    assert product.entry_type == "promo_card"
    assert product.is_promoted is True
    assert product.promo_channel == "Dollar Express"
    assert product.promotion_text == "Free shipping on 3 items | Free returns | Buy more,save more"
    assert product.promo_landing_url == "https://www.aliexpress.com/ssr/300000512/BundleDeals2?productIds=1005007009946538:12000057714698736"
