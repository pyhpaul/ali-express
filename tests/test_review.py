from ali_mvp.review import build_review_rows


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

    assert review_rows[0]["shop_name"] == "Store A"
    assert review_rows[0]["filter_decision"] == "accepted"


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
    assert review_rows[0]["image_url"] == ""
