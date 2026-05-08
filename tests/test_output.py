import csv

from ali_mvp.output import write_products_csv, write_rank_csv
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
            image_url="https://example.test/item.jpg",
            scraped_at="2026-05-08T00:00:00Z",
        )
    ]

    write_products_csv(path, products)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["title"] == "Dress"
    assert rows[0]["sold_count"] == "100"


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
