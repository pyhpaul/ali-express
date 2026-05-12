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
            "filter_stage": "listing_title",
            "reject_groups": "electrical_power",
            "reason_zh": "带电供电类",
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
            "filter_stage": "accepted",
            "reject_groups": "",
            "reason_zh": "未命中中文规则说明",
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

    html = render_report_html(
        review_rows,
        source_label="home appliance accessories",
        translation_provider="mymemory",
    )

    assert '<section id="rejected">' in html
    assert '<section id="accepted">' in html
    assert html.index('<section id="rejected">') < html.index('<section id="accepted">')
    assert '<section id="summary">' in html
    assert "Total: 2" in html
    assert "Rejected: 1" in html
    assert "Accepted: 1" in html
    assert "翻译来源" in html
    assert "mymemory" in html
    assert "拒绝入库" in html
    assert "建议入库" in html

    rejected_section = _extract_section(html, "rejected")
    accepted_section = _extract_section(html, "accepted")

    assert "Battery charger" in rejected_section
    assert "电池充电器" in rejected_section
    assert "Shock pad" not in rejected_section
    assert "Shock pad" in accepted_section
    assert "减震垫" in accepted_section
    assert "Battery charger" not in accepted_section
    assert "带电供电类: 1" in html
    assert "标题命中" in rejected_section
    assert "带电供电类" in rejected_section
    assert "判定说明: 可入库候选" in accepted_section
    assert "拒绝原因: 未命中中文规则说明" not in accepted_section
    assert '<ul id="reject-reasons">' in html
    assert 'id="decision-filter"' in html
    assert 'id="reason-filter"' in html
    assert '<option value="all">全部</option>' in html
    assert '<option value="rejected">只看拒绝入库</option>' in html
    assert '<option value="accepted">只看建议入库</option>' in html
    assert '<option value="带电供电类">带电供电类</option>' in html
    assert 'data-decision="rejected"' in rejected_section
    assert 'data-reason="带电供电类"' in rejected_section
    assert 'data-decision="accepted"' in accepted_section
    assert 'data-reason=""' in accepted_section
    assert "applyFilters()" in html


def test_render_report_html_handles_all_rejected_rows():
    html = render_report_html(
        [
            {
                "title": "Battery charger",
                "title_zh": "电池充电器",
                "filter_decision": "rejected",
                "filter_stage": "listing_title",
                "reject_groups": "electrical_power",
                "reason_zh": "带电供电类",
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
        translation_provider="identity",
    )

    assert "Rejected: 1" in html
    assert "Accepted: 0" in html
    assert "identity" in html


def test_render_report_html_escapes_html_sensitive_content():
    html = render_report_html(
        [
            {
                "title": '<b>Battery charger</b>',
                "title_zh": "电池充电器",
                "filter_decision": "rejected",
                "filter_stage": "listing_title",
                "reject_groups": 'electrical_power<script>',
                "reason_zh": '带电供电类<script>',
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
        source_label='<script>alert("x")</script>',
        translation_provider='<script>mymemory</script>',
    )

    assert '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;' in html
    assert '&lt;b&gt;Battery charger&lt;/b&gt;' in html
    assert '带电供电类&lt;script&gt;: 1' in html
    assert '&lt;script&gt;mymemory&lt;/script&gt;' in html
    assert '<script>alert("x")</script>' not in html
    assert '<b>Battery charger</b>' not in html
    assert 'electrical_power<script>' not in html
