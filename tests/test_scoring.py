from ali_mvp.scoring import ProductRecord, aggregate_rank, parse_count, parse_float


def test_parse_count_handles_plain_commas_and_suffixes():
    assert parse_count("1,234 sold") == 1234
    assert parse_count("2.5K+ sold") == 2500
    assert parse_count("1.2M sold") == 1200000
    assert parse_count("") == 0
    assert parse_count(None) == 0


def test_parse_float_extracts_first_decimal_number():
    assert parse_float("4.8 stars") == 4.8
    assert parse_float("Rating: 5") == 5.0
    assert parse_float("") == 0.0
    assert parse_float(None) == 0.0


def test_aggregate_rank_groups_by_source_and_scores_heat():
    products = [
        ProductRecord(
            source_type="keyword",
            source_value="women dress",
            title="A",
            price="12.50",
            sold_count=100,
            rating=4.8,
            review_count=20,
            product_url="https://example.test/a",
            search_card_url="https://example.test/a",
            image_url="https://example.test/a.jpg",
            entry_type="item_card",
            is_promoted=False,
            promo_channel="",
            promotion_text="",
            promo_landing_url="",
            shop_name="",
            shipping_text="",
            detail_rating=0.0,
            detail_review_count=0,
            breadcrumb="",
            attributes_text="",
            description_text="",
            scraped_at="2026-05-08T00:00:00Z",
        ),
        ProductRecord(
            source_type="keyword",
            source_value="women dress",
            title="B",
            price="15.00",
            sold_count=200,
            rating=4.6,
            review_count=40,
            product_url="https://example.test/b",
            search_card_url="https://example.test/b",
            image_url="https://example.test/b.jpg",
            entry_type="item_card",
            is_promoted=False,
            promo_channel="",
            promotion_text="",
            promo_landing_url="",
            shop_name="",
            shipping_text="",
            detail_rating=0.0,
            detail_review_count=0,
            breadcrumb="",
            attributes_text="",
            description_text="",
            scraped_at="2026-05-08T00:00:00Z",
        ),
    ]

    rows = aggregate_rank(products)

    assert len(rows) == 1
    row = rows[0]
    assert row.source_value == "women dress"
    assert row.product_count == 2
    assert row.total_sold_count == 300
    assert row.avg_rating == 4.7
    assert row.avg_review_count == 30.0
    assert row.heat_score == 427.0
