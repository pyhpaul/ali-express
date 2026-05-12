import pytest

from ali_mvp.review import PRODUCT_CONTEXT_FIELDS, build_review_rows, enrich_review_rows_with_zh


def test_build_review_rows_merges_product_context_into_audit_rows():
    products = [
        {
            "title": "Shock pad",
            "product_url": "https://example.test/item/1",
            "image_url": "https://example.test/img.jpg",
            "price": "$1.00",
            "search_card_url": "https://example.test/card/1",
            "entry_type": "item_card",
            "is_promoted": "False",
            "promo_channel": "",
            "promotion_text": "",
            "shop_name": "Store A",
            "shipping_text": "Free shipping",
            "attributes_text": "{\"Type\":\"Pad\"}",
            "description_text": "Accessory",
            "detail_status": "",
        }
    ]
    audit_rows = [
        {
            "title": "Shock pad",
            "product_url": "https://example.test/item/1",
            "filter_decision": "accepted",
            "filter_stage": "accepted",
            "reject_groups": "",
            "reject_terms": "",
            "reject_fields": "",
            "warning_groups": "",
            "warning_terms": "",
            "warning_fields": "",
            "source_type": "keyword",
            "source_value": "home appliance accessories",
        }
    ]

    review_rows = build_review_rows(products, audit_rows)

    assert [row["product_url"] for row in review_rows] == ["https://example.test/item/1"]
    assert review_rows[0]["shop_name"] == "Store A"
    assert review_rows[0]["filter_decision"] == "accepted"


def test_build_review_rows_preserves_audit_row_order():
    review_rows = build_review_rows(
        [
            {
                "title": "First",
                "product_url": "https://example.test/item/1",
                "shop_name": "Store A",
            },
            {
                "title": "Second",
                "product_url": "https://example.test/item/2",
                "shop_name": "Store B",
            },
        ],
        [
            {
                "title": "Second",
                "product_url": "https://example.test/item/2",
                "filter_decision": "accepted",
                "filter_stage": "accepted",
                "source_type": "keyword",
                "source_value": "home appliance accessories",
                "reject_groups": "",
                "reject_terms": "",
                "reject_fields": "",
                "warning_groups": "",
                "warning_terms": "",
                "warning_fields": "",
            },
            {
                "title": "First",
                "product_url": "https://example.test/item/1",
                "filter_decision": "accepted",
                "filter_stage": "accepted",
                "source_type": "keyword",
                "source_value": "home appliance accessories",
                "reject_groups": "",
                "reject_terms": "",
                "reject_fields": "",
                "warning_groups": "",
                "warning_terms": "",
                "warning_fields": "",
            },
        ],
    )

    assert [row["product_url"] for row in review_rows] == [
        "https://example.test/item/2",
        "https://example.test/item/1",
    ]


def test_build_review_rows_keeps_listing_prefilter_rejections_without_product_context():
    review_rows = build_review_rows(
        [],
        [
            {
                "title": "Battery charger board",
                "product_url": "https://example.test/item/2",
                "filter_decision": "rejected",
                "filter_stage": "listing_title",
                "source_type": "keyword",
                "source_value": "home appliance accessories",
                "reject_groups": "electrical_power",
                "reject_terms": "battery",
                "reject_fields": "title",
                "warning_groups": "",
                "warning_terms": "",
                "warning_fields": "",
            }
        ],
    )

    assert review_rows[0]["title"] == "Battery charger board"
    assert {field: review_rows[0][field] for field in PRODUCT_CONTEXT_FIELDS} == {
        "image_url": "",
        "price": "",
        "search_card_url": "",
        "entry_type": "",
        "is_promoted": "",
        "promo_channel": "",
        "promotion_text": "",
        "shop_name": "",
        "shipping_text": "",
        "attributes_text": "",
        "description_text": "",
        "detail_status": "",
    }


def test_build_review_rows_does_not_match_same_title_without_same_product_url():
    review_rows = build_review_rows(
        [
            {
                "title": "Shock pad",
                "product_url": "https://example.test/item/1",
                "shop_name": "Store A",
            }
        ],
        [
            {
                "title": "Shock pad",
                "product_url": "https://example.test/item/2",
                "filter_decision": "accepted",
                "filter_stage": "accepted",
                "source_type": "keyword",
                "source_value": "home appliance accessories",
                "reject_groups": "",
                "reject_terms": "",
                "reject_fields": "",
                "warning_groups": "",
                "warning_terms": "",
                "warning_fields": "",
            }
        ],
    )

    assert review_rows[0]["shop_name"] == ""


def test_build_review_rows_raises_on_duplicate_product_url():
    with pytest.raises(ValueError, match="duplicate product_url: https://example.test/item/1"):
        build_review_rows(
            [
                {
                    "title": "Shock pad",
                    "product_url": "https://example.test/item/1",
                    "shop_name": "Store A",
                },
                {
                    "title": "Shock pad duplicate",
                    "product_url": "https://example.test/item/1",
                    "shop_name": "Store B",
                },
            ],
            [],
        )


def test_enrich_review_rows_with_zh_adds_translated_context_and_reason():
    review_rows = [
        {
            "title": "Shock pad",
            "shop_name": "Store A",
            "promotion_text": "Hot deal",
            "attributes_text": "{\"Color\":\"Blue\",\"Type\":\"Pad\"}",
            "reject_terms": "battery | charger",
            "reject_groups": "electrical_power",
        }
    ]

    enriched = enrich_review_rows_with_zh(
        review_rows,
        translations={
            "Shock pad": "减震垫",
            "Store A": "A 店铺",
            "Hot deal": "热卖",
            "Color: Blue; Type: Pad": "颜色: 蓝色; 类型: 垫",
        },
        reason_builder=lambda row: "带电供电类",
        attributes_summary_builder=lambda raw_text: "Color: Blue; Type: Pad",
    )

    assert enriched[0]["title_zh"] == "减震垫"
    assert enriched[0]["shop_name_zh"] == "A 店铺"
    assert enriched[0]["promotion_text_zh"] == "热卖"
    assert enriched[0]["attributes_summary"] == "Color: Blue; Type: Pad"
    assert enriched[0]["attributes_summary_zh"] == "颜色: 蓝色; 类型: 垫"
    assert enriched[0]["reason_zh"] == "带电供电类"
