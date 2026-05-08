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
            "image": "//ae01.alicdn.com/item.jpg",
        },
        {
            "title": "Duplicate",
            "price": "$13.00",
            "soldText": "10 sold",
            "ratingText": "4.5",
            "reviewText": "5 reviews",
            "url": "https://www.aliexpress.com/item/100500.html",
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
    assert product.image_url == "https://ae01.alicdn.com/item.jpg"
