import pytest

from ali_mvp.output import read_csv_rows
from ali_mvp.postprocess import _build_audit_zh_rows, run_postprocess_for_dir

def test_build_audit_zh_rows_raises_when_lengths_mismatch():
    audit_rows = [
        {
            "source_type": "keyword",
            "source_value": "home appliance accessories",
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
        }
    ]

    with pytest.raises(ValueError, match="audit_rows and review_rows_zh length mismatch: 1 != 0"):
        _build_audit_zh_rows(audit_rows, [])


def test_run_postprocess_for_dir_writes_translated_rows(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "products.csv").write_text(
        "source_type,source_value,title,price,sold_count,rating,review_count,product_url,search_card_url,image_url,entry_type,is_promoted,promo_channel,promotion_text,promo_landing_url,shop_name,shipping_text,detail_rating,detail_review_count,breadcrumb,attributes_text,description_text,detail_status,scraped_at\n"
        "keyword,home appliance accessories,Shock pad,$1,0,0,0,https://example.test/item/1,https://example.test/card/1,https://example.test/img.jpg,item_card,False,promo,3 pcs free shipping,https://example.test/promo/1,Store A,Free shipping,0,0,,\"{\"\"Type\"\":\"\"Pad\"\"}\",Accessory,ok,2026-05-11T00:00:00Z\n",
        encoding="utf-8-sig",
    )
    (run_dir / "products_filter_audit.csv").write_text(
        "source_type,source_value,title,product_url,filter_decision,filter_stage,reject_groups,reject_terms,reject_fields,warning_groups,warning_terms,warning_fields\n"
        "keyword,home appliance accessories,Shock pad,https://example.test/item/1,accepted,accepted,,,,,,\n",
        encoding="utf-8-sig",
    )

    translations = {
        "Shock pad": "减震垫",
        "Store A": "店铺A",
        "3 pcs free shipping": "3件包邮",
        "Type: Pad": "类型：减震垫",
    }

    run_postprocess_for_dir(run_dir, translator=lambda text: translations.get(text, f"ZH::{text}"))

    products_zh = read_csv_rows(run_dir / "products_zh.csv")
    audit_zh = read_csv_rows(run_dir / "products_filter_audit_zh.csv")
    review_only = read_csv_rows(run_dir / "review_only.csv")
    report_html = (run_dir / "products_report.html").read_text(encoding="utf-8")

    assert products_zh[0]["title_zh"] == "减震垫"
    assert products_zh[0]["shop_name_zh"] == "店铺A"
    assert products_zh[0]["promotion_text_zh"] == "3件包邮"
    assert products_zh[0]["attributes_summary"] == "Type: Pad"
    assert products_zh[0]["attributes_summary_zh"] == "类型：减震垫"
    assert products_zh[0]["decision_label"] == "建议入库"
    assert products_zh[0]["stage_label"] == "已通过"
    assert products_zh[0]["review_note"] == "可入库候选"
    assert audit_zh[0]["filter_decision_zh"] == "通过"
    assert audit_zh[0]["decision_label"] == "建议入库"
    assert audit_zh[0]["stage_label"] == "已通过"
    assert audit_zh[0]["review_note"] == "可入库候选"
    assert review_only[0]["title"] == "Shock pad"
    assert review_only[0]["title_zh"] == "减震垫"
    assert review_only[0]["decision_label"] == "建议入库"
    assert review_only[0]["stage_label"] == "已通过"
    assert review_only[0]["review_note"] == "可入库候选"
    assert "翻译来源" in report_html
    assert "default" in report_html


def test_run_postprocess_for_dir_writes_rejected_review_labels(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "products.csv").write_text(
        "source_type,source_value,title,price,sold_count,rating,review_count,product_url,search_card_url,image_url,entry_type,is_promoted,promo_channel,promotion_text,promo_landing_url,shop_name,shipping_text,detail_rating,detail_review_count,breadcrumb,attributes_text,description_text,detail_status,scraped_at\n",
        encoding="utf-8-sig",
    )
    (run_dir / "products_filter_audit.csv").write_text(
        "source_type,source_value,title,product_url,filter_decision,filter_stage,reject_groups,reject_terms,reject_fields,warning_groups,warning_terms,warning_fields\n"
        "keyword,home appliance accessories,Battery charger,https://example.test/item/2,rejected,listing_title,electrical_power,battery,title,,,\n",
        encoding="utf-8-sig",
    )

    run_postprocess_for_dir(run_dir, translator=lambda text: {"Battery charger": "电池充电器"}.get(text, text))

    audit_zh = read_csv_rows(run_dir / "products_filter_audit_zh.csv")
    review_only = read_csv_rows(run_dir / "review_only.csv")

    assert audit_zh[0]["filter_decision_zh"] == "拒绝"
    assert audit_zh[0]["decision_label"] == "拒绝入库"
    assert audit_zh[0]["stage_label"] == "标题命中"
    assert audit_zh[0]["review_note"] == "拒绝原因: 带电供电类"
    assert review_only[0]["title"] == "Battery charger"
    assert review_only[0]["title_zh"] == "电池充电器"
    assert review_only[0]["decision_label"] == "拒绝入库"
    assert review_only[0]["stage_label"] == "标题命中"
    assert review_only[0]["review_note"] == "拒绝原因: 带电供电类"


def test_run_postprocess_for_dir_ignores_identity_cache_when_namespace_changes(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "products.csv").write_text(
        "source_type,source_value,title,price,sold_count,rating,review_count,product_url,search_card_url,image_url,entry_type,is_promoted,promo_channel,promotion_text,promo_landing_url,shop_name,shipping_text,detail_rating,detail_review_count,breadcrumb,attributes_text,description_text,detail_status,scraped_at\n"
        "keyword,home appliance accessories,Shock pad,$1,0,0,0,https://example.test/item/1,https://example.test/card/1,https://example.test/img.jpg,item_card,False,,,,Store A,Free shipping,0,0,,\"{\"\"Type\"\":\"\"Pad\"\"}\",Accessory,ok,2026-05-11T00:00:00Z\n",
        encoding="utf-8-sig",
    )
    (run_dir / "products_filter_audit.csv").write_text(
        "source_type,source_value,title,product_url,filter_decision,filter_stage,reject_groups,reject_terms,reject_fields,warning_groups,warning_terms,warning_fields\n"
        "keyword,home appliance accessories,Shock pad,https://example.test/item/1,accepted,accepted,,,,,,\n",
        encoding="utf-8-sig",
    )
    (run_dir / "translation_cache.json").write_text(
        '{"Shock pad":"Shock pad"}',
        encoding="utf-8",
    )

    run_postprocess_for_dir(
        run_dir,
        translator=lambda text: "减震垫" if text == "Shock pad" else text,
        translation_cache_namespace="mymemory",
    )

    products_zh = read_csv_rows(run_dir / "products_zh.csv")

    assert products_zh[0]["title_zh"] == "减震垫"


def test_review_only_rows_are_sorted_for_manual_review():
    rows = [
        {
            "source_type": "keyword",
            "source_value": "home appliance accessories",
            "title": "Shock pad",
            "title_zh": "减震垫",
            "product_url": "https://example.test/item/1",
            "image_url": "",
            "price": "$1",
            "entry_type": "item_card",
            "shop_name": "",
            "shop_name_zh": "",
            "promotion_text": "",
            "promotion_text_zh": "",
            "attributes_text": "",
            "attributes_summary": "",
            "attributes_summary_zh": "",
            "filter_decision": "accepted",
            "filter_stage": "accepted",
            "reason_zh": "未命中中文规则说明",
        },
        {
            "source_type": "keyword",
            "source_value": "home appliance accessories",
            "title": "Battery charger",
            "title_zh": "电池充电器",
            "product_url": "https://example.test/item/2",
            "image_url": "",
            "price": "$3",
            "entry_type": "item_card",
            "shop_name": "",
            "shop_name_zh": "",
            "promotion_text": "",
            "promotion_text_zh": "",
            "attributes_text": "",
            "attributes_summary": "",
            "attributes_summary_zh": "",
            "filter_decision": "rejected",
            "filter_stage": "listing_title",
            "reason_zh": "带电供电类",
        },
        {
            "source_type": "keyword",
            "source_value": "home appliance accessories",
            "title": "Pulse igniter",
            "title_zh": "脉冲点火器",
            "product_url": "https://example.test/item/3",
            "image_url": "",
            "price": "$2",
            "entry_type": "item_card",
            "shop_name": "",
            "shop_name_zh": "",
            "promotion_text": "",
            "promotion_text_zh": "",
            "attributes_text": "",
            "attributes_summary": "",
            "attributes_summary_zh": "",
            "filter_decision": "rejected",
            "filter_stage": "detail_post_enrich",
            "reason_zh": "点火控制类",
        },
        {
            "source_type": "keyword",
            "source_value": "home appliance accessories",
            "title": "Remote control A",
            "title_zh": "遥控器A",
            "product_url": "https://example.test/item/4",
            "image_url": "",
            "price": "$4",
            "entry_type": "item_card",
            "shop_name": "",
            "shop_name_zh": "",
            "promotion_text": "",
            "promotion_text_zh": "",
            "attributes_text": "",
            "attributes_summary": "",
            "attributes_summary_zh": "",
            "filter_decision": "rejected",
            "filter_stage": "listing_title",
            "reason_zh": "遥控控制类",
        },
        {
            "source_type": "keyword",
            "source_value": "home appliance accessories",
            "title": "Remote control B",
            "title_zh": "遥控器B",
            "product_url": "https://example.test/item/5",
            "image_url": "",
            "price": "$5",
            "entry_type": "item_card",
            "shop_name": "",
            "shop_name_zh": "",
            "promotion_text": "",
            "promotion_text_zh": "",
            "attributes_text": "",
            "attributes_summary": "",
            "attributes_summary_zh": "",
            "filter_decision": "rejected",
            "filter_stage": "detail_post_enrich",
            "reason_zh": "遥控控制类",
        },
    ]

    from ali_mvp.postprocess import _build_review_only_rows

    review_only = _build_review_only_rows(rows)

    assert [row["title"] for row in review_only] == [
        "Battery charger",
        "Pulse igniter",
        "Remote control B",
        "Remote control A",
        "Shock pad",
    ]
