import csv

from ali_mvp.output import write_filter_audit_csv, write_products_csv, write_rank_csv
from ali_mvp.scoring import ProductRecord, RankRecord


def test_write_products_csv_writes_header_and_rows(tmp_path):
    path = tmp_path / "products.csv"
    products = [
        ProductRecord(
            source_type="keyword",
            source_value="women dress",
            title="Dress",
            price="$12.50",
            sold_count=100,
            rating=4.8,
            review_count=20,
            product_url="https://example.test/item",
            search_card_url="https://example.test/item",
            image_url="https://example.test/item.jpg",
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
        )
    ]

    write_products_csv(path, products)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["title"] == "Dress"
    assert rows[0]["sold_count"] == "100"


def test_write_products_csv_includes_detail_enrichment_fields(tmp_path):
    path = tmp_path / "products.csv"
    products = [
        ProductRecord(
            source_type="keyword",
            source_value="women dress",
            title="Dress",
            price="$12.50",
            sold_count=100,
            rating=4.8,
            review_count=20,
            product_url="https://example.test/item",
            search_card_url="https://example.test/promo",
            image_url="https://example.test/item.jpg",
            entry_type="promo_card",
            is_promoted=True,
            promo_channel="Dollar Express",
            promotion_text="Free shipping on 3 items | Free returns | Buy more,save more",
            promo_landing_url="https://example.test/promo",
            shop_name="Example Store",
            shipping_text="Free shipping",
            detail_rating=4.9,
            detail_review_count=25,
            breadcrumb="Home > Dresses",
            attributes_text='{"Material":"Cotton"}',
            description_text="Long sleeve dress",
            scraped_at="2026-05-08T00:00:00Z",
        )
    ]

    write_products_csv(path, products)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["entry_type"] == "promo_card"
    assert rows[0]["is_promoted"] == "True"
    assert rows[0]["promo_channel"] == "Dollar Express"
    assert rows[0]["promotion_text"] == "Free shipping on 3 items | Free returns | Buy more,save more"
    assert rows[0]["shop_name"] == "Example Store"
    assert rows[0]["attributes_text"] == '{"Material":"Cotton"}'
    assert rows[0]["description_text"] == "Long sleeve dress"


def test_write_rank_csv_writes_header_and_rows(tmp_path):
    path = tmp_path / "category_rank.csv"
    rows = [
        RankRecord(
            source_value="women dress",
            product_count=2,
            total_sold_count=300,
            avg_rating=4.7,
            avg_review_count=30.0,
            heat_score=427.0,
        )
    ]

    write_rank_csv(path, rows)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        loaded = list(csv.DictReader(handle))
    assert loaded[0]["source_value"] == "women dress"
    assert loaded[0]["heat_score"] == "427.0"


def test_write_filter_audit_csv_writes_expected_columns(tmp_path):
    path = tmp_path / "products_filter_audit.csv"
    rows = [
        {
            "source_type": "keyword",
            "source_value": "home appliance accessories",
            "title": "Battery charger board",
            "product_url": "https://example.test/item",
            "filter_decision": "rejected",
            "filter_stage": "listing_title",
            "reject_groups": "electrical_power",
            "reject_terms": "battery",
            "reject_fields": "title",
            "warning_groups": "",
            "warning_terms": "",
            "warning_fields": "",
        }
    ]

    write_filter_audit_csv(path, rows)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        written_rows = list(csv.DictReader(handle))

    assert written_rows[0]["filter_stage"] == "listing_title"
    assert written_rows[0]["filter_decision"] == "rejected"
