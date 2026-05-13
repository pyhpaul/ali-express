from ali_mvp.llm_reporting import render_llm_report_html


def test_render_llm_report_html_groups_keep_drop_and_error_rows():
    rows = [
        {
            "title": "Keep title",
            "llm_summary_zh": "疑似芯片控制类",
            "llm_risk_tags": "chip|controller",
            "filter_decision": "accepted",
            "price": "$1",
            "product_url": "https://example.test/item/1",
            "image_url": "https://example.test/item/1.jpg",
            "detail_status": "ok",
            "llm_decision": "keep",
            "llm_error": "",
        },
        {
            "title": "Drop title",
            "llm_summary_zh": "营销套装",
            "llm_risk_tags": "promo_bundle",
            "filter_decision": "rejected",
            "price": "$2",
            "product_url": "https://example.test/item/2",
            "image_url": "https://example.test/item/2.jpg",
            "detail_status": "ok",
            "llm_decision": "drop",
            "llm_error": "",
        },
        {
            "title": "Error title",
            "llm_summary_zh": "",
            "llm_risk_tags": "",
            "filter_decision": "accepted",
            "price": "$3",
            "product_url": "https://example.test/item/3",
            "image_url": "https://example.test/item/3.jpg",
            "detail_status": "detail_failed",
            "llm_decision": "",
            "llm_error": "json parse failed",
        },
    ]

    html = render_llm_report_html(
        rows,
        source_label="home appliance accessories",
        model_label="gpt-test",
        prompt_version="v1",
    )

    assert '<section id="llm-keep">' in html
    assert '<section id="llm-drop">' in html
    assert '<section id="llm-error">' in html
    assert "Keep: 1" in html
    assert "Drop: 1" in html
    assert "Error: 1" in html
    assert "疑似芯片控制类" in html
    assert "json parse failed" in html


def test_render_llm_report_html_escapes_user_content():
    rows = [
        {
            "title": '<script>alert("x")</script>',
            "llm_summary_zh": "<b>summary</b>",
            "llm_risk_tags": "chip&controller",
            "filter_decision": 'accepted" onclick="x',
            "price": "$1",
            "product_url": "https://example.test/item/1?a=1&b=2",
            "image_url": "https://example.test/item/1.jpg?x=<y>",
            "detail_status": "ok",
            "llm_decision": "keep",
            "llm_error": "",
        }
    ]

    html = render_llm_report_html(
        rows,
        source_label="source <unsafe>",
        model_label='gpt-"test"',
        prompt_version="v1<script>",
    )

    assert "<script>alert" not in html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert "&lt;b&gt;summary&lt;/b&gt;" in html
    assert "source &lt;unsafe&gt;" in html
    assert 'gpt-&quot;test&quot;' in html
    assert "v1&lt;script&gt;" in html


def test_render_llm_report_html_treats_decision_with_error_as_error():
    rows = [
        {
            "title": "Conflicted row",
            "llm_summary_zh": "should be error",
            "llm_risk_tags": "chip",
            "filter_decision": "accepted",
            "price": "$1",
            "product_url": "https://example.test/item/1",
            "image_url": "https://example.test/item/1.jpg",
            "detail_status": "ok",
            "llm_decision": "keep",
            "llm_error": "boom",
        }
    ]

    html = render_llm_report_html(
        rows,
        source_label="source",
        model_label="gpt-test",
        prompt_version="v1",
    )

    assert "Keep: 0" in html
    assert "Error: 1" in html
    assert "<h2>LLM Keep</h2>\n    <div class=\"cards keep\"></div>" in html
    assert "llm_error:</span> boom" in html
