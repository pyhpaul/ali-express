import csv

import pytest

from ali_mvp.output import (
    FILTER_AUDIT_FIELDS,
    FILTER_AUDIT_ZH_FIELDS,
    LLM_REVIEW_FIELDS,
    PRODUCT_ZH_FIELDS,
    REVIEW_FIELDS,
    REVIEW_ONLY_FIELDS,
    read_csv_rows,
    write_dict_csv,
    write_filter_audit_csv,
    write_llm_review_csv,
    write_products_csv,
    write_rank_csv,
)
from ali_mvp.scoring import ProductRecord, RankRecord


def test_read_csv_rows_round_trips_written_audit(tmp_path):
    path = tmp_path / "products_filter_audit.csv"
    rows = [{"source_type": "keyword", "source_value": "x", "title": "A", "product_url": "u"}]

    write_dict_csv(path, ["source_type", "source_value", "title", "product_url"], rows)
    loaded = read_csv_rows(path)

    assert loaded == [{"source_type": "keyword", "source_value": "x", "title": "A", "product_url": "u"}]


def test_review_fields_match_expected_columns_and_order():
    assert REVIEW_FIELDS == [
        "source_type",
        "source_value",
        "title",
        "product_url",
        "image_url",
        "price",
        "search_card_url",
        "entry_type",
        "is_promoted",
        "promo_channel",
        "promotion_text",
        "shop_name",
        "shipping_text",
        "attributes_text",
        "description_text",
        "detail_status",
        "filter_decision",
        "filter_stage",
        "reject_groups",
        "reject_terms",
        "reject_fields",
        "warning_groups",
        "warning_terms",
        "warning_fields",
    ]


def test_llm_review_fields_match_expected_columns_and_order():
    assert LLM_REVIEW_FIELDS == [
        "source_type",
        "source_value",
        "title",
        "product_url",
        "image_url",
        "price",
        "entry_type",
        "promotion_text",
        "shop_name",
        "attributes_text",
        "description_text",
        "detail_status",
        "filter_decision",
        "filter_stage",
        "reject_groups",
        "reject_terms",
        "warning_groups",
        "warning_terms",
        "llm_decision",
        "llm_reason",
        "llm_risk_tags",
        "llm_confidence",
        "llm_summary_zh",
        "llm_model",
        "llm_provider",
        "llm_base_url",
        "llm_prompt_version",
        "llm_input_hash",
        "llm_reviewed_at",
        "llm_error",
    ]


def test_product_zh_fields_match_expected_columns_and_order():
    assert PRODUCT_ZH_FIELDS == [
        "source_type",
        "source_value",
        "title",
        "price",
        "sold_count",
        "rating",
        "review_count",
        "product_url",
        "search_card_url",
        "image_url",
        "entry_type",
        "is_promoted",
        "promo_channel",
        "promotion_text",
        "promo_landing_url",
        "shop_name",
        "shipping_text",
        "detail_rating",
        "detail_review_count",
        "breadcrumb",
        "attributes_text",
        "description_text",
        "detail_status",
        "scraped_at",
        "title_zh",
        "shop_name_zh",
        "promotion_text_zh",
        "attributes_summary",
        "attributes_summary_zh",
        "decision_label",
        "stage_label",
        "review_note",
    ]


def test_filter_audit_zh_fields_match_expected_columns_and_order():
    assert FILTER_AUDIT_ZH_FIELDS == [
        "source_type",
        "source_value",
        "title",
        "product_url",
        "filter_decision",
        "filter_stage",
        "reject_groups",
        "reject_terms",
        "reject_fields",
        "warning_groups",
        "warning_terms",
        "warning_fields",
        "filter_decision_zh",
        "filter_stage_zh",
        "reject_groups_zh",
        "reject_terms_zh",
        "warning_groups_zh",
        "warning_terms_zh",
        "reason_zh",
        "decision_label",
        "stage_label",
        "review_note",
    ]


def test_review_only_fields_match_expected_columns_and_order():
    assert REVIEW_ONLY_FIELDS == [
        "source_type",
        "source_value",
        "title",
        "title_zh",
        "product_url",
        "image_url",
        "price",
        "entry_type",
        "shop_name",
        "shop_name_zh",
        "promotion_text",
        "promotion_text_zh",
        "attributes_summary",
        "attributes_summary_zh",
        "decision_label",
        "stage_label",
        "review_note",
    ]


def test_write_dict_csv_rejects_extra_keys(tmp_path):
    path = tmp_path / "audit.csv"

    with pytest.raises(ValueError, match="unexpected CSV columns: extra"):
        write_dict_csv(path, ["source_type"], [{"source_type": "keyword", "extra": "boom"}])


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
            detail_status="",
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
            detail_status="captcha_blocked",
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
    assert rows[0]["detail_status"] == "captcha_blocked"


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
        }
    ]

    write_filter_audit_csv(path, rows)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        written_rows = list(csv.DictReader(handle))

    assert written_rows[0]["source_type"] == "keyword"
    assert written_rows[0]["source_value"] == "home appliance accessories"
    for field in FILTER_AUDIT_FIELDS:
        if field not in {"source_type", "source_value"}:
            assert written_rows[0][field] == ""


def test_write_llm_review_csv_writes_expected_columns_and_rows(tmp_path):
    path = tmp_path / "products_llm_review.csv"
    rows = [
        {
            "source_type": "keyword",
            "source_value": "home appliance accessories",
            "title": "Shock pad",
            "product_url": "https://example.test/item/1",
            "image_url": "https://example.test/item/1.jpg",
            "price": "$1",
            "entry_type": "item_card",
            "promotion_text": "Free shipping",
            "shop_name": "Store A",
            "attributes_text": '{"Type":"Pad"}',
            "description_text": "Accessory",
            "detail_status": "ok",
            "filter_decision": "accepted",
            "filter_stage": "accepted",
            "reject_groups": "",
            "reject_terms": "",
            "warning_groups": "fragile",
            "warning_terms": "battery",
            "llm_decision": "review",
            "llm_reason": "needs manual verification",
            "llm_risk_tags": "battery",
            "llm_confidence": "0.42",
            "llm_summary_zh": "需要人工复核",
            "llm_model": "gpt-test",
            "llm_provider": "local",
            "llm_base_url": "http://localhost:11434/v1",
            "llm_prompt_version": "v1",
            "llm_input_hash": "abc123",
            "llm_reviewed_at": "2026-05-13T00:00:00Z",
            "llm_error": "",
        }
    ]

    write_llm_review_csv(path, rows)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == LLM_REVIEW_FIELDS
        written_rows = list(reader)

    assert written_rows == rows
