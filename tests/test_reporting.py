from ali_mvp.reporting import render_report_html


def _extract_section(html: str, section_id: str) -> str:
    start_marker = f'<section id="{section_id}">'
    end_marker = "</section>"
    start = html.index(start_marker)
    end = html.index(end_marker, start)
    return html[start:end]


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

    assert '<section id="rejected">' in html
    assert '<section id="accepted">' in html
    assert "Total: 2" in html
    assert "Rejected: 1" in html
    assert "Accepted: 1" in html

    rejected_section = _extract_section(html, "rejected")
    accepted_section = _extract_section(html, "accepted")

    assert "Battery charger" in rejected_section
    assert "Shock pad" not in rejected_section
    assert "Shock pad" in accepted_section
    assert "Battery charger" not in accepted_section


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
