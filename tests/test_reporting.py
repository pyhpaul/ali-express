from ali_mvp.reporting import render_report_html


def test_render_report_html_includes_summary_and_rejected_first():
    review_rows = [
        {
            "title": "Battery charger",
            "title_zh": "电池充电器",
            "filter_decision": "rejected",
            "reject_groups": "electrical_power",
            "price": "$3",
            "image_url": "",
            "shop_name": "",
            "shop_name_zh": "",
            "promotion_text": "",
            "promotion_text_zh": "",
            "attributes_summary": "",
            "attributes_summary_zh": "",
            "detail_status": "listing_title",
        },
        {
            "title": "Shock pad",
            "title_zh": "减震垫",
            "filter_decision": "accepted",
            "reject_groups": "",
            "price": "$1",
            "image_url": "",
            "shop_name": "",
            "shop_name_zh": "",
            "promotion_text": "",
            "promotion_text_zh": "",
            "attributes_summary": "",
            "attributes_summary_zh": "",
            "detail_status": "",
        },
    ]

    html = render_report_html(review_rows, source_label="home appliance accessories")

    assert "Rejected" in html
    assert "Accepted" in html
    assert html.index("Battery charger") < html.index("Shock pad")
    assert "total" in html.lower()


def test_render_report_html_handles_all_rejected_rows():
    html = render_report_html(
        [
            {
                "title": "Battery charger",
                "title_zh": "电池充电器",
                "filter_decision": "rejected",
                "reject_groups": "electrical_power",
                "price": "$3",
                "image_url": "",
                "shop_name": "",
                "shop_name_zh": "",
                "promotion_text": "",
                "promotion_text_zh": "",
                "attributes_summary": "",
                "attributes_summary_zh": "",
                "detail_status": "listing_title",
            }
        ],
        source_label="run",
    )

    assert "Rejected: 1" in html
    assert "Accepted: 0" in html
