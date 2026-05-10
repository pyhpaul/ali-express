from __future__ import annotations

from pathlib import Path

from .output import (
    FILTER_AUDIT_ZH_FIELDS,
    PRODUCT_ZH_FIELDS,
    REVIEW_FIELDS,
    read_csv_rows,
    write_dict_csv,
)
from .reporting import render_report_html
from .review import build_review_rows, enrich_review_rows_with_zh
from .translation import build_reason_zh, summarize_attributes_text, translate_texts


FILTER_DECISION_ZH = {
    "accepted": "通过",
    "rejected": "拒绝",
}

FILTER_STAGE_ZH = {
    "accepted": "已通过",
    "listing_title": "标题命中",
    "detail_post_enrich": "详情补充后命中",
}

GROUP_ZH = {
    "electrical_power": "带电供电类",
    "relay_switch_sensor": "电子元件或控制器类",
    "chip_pcb": "电子控制或芯片类",
    "remote_control_device": "遥控控制类",
    "ignition_control": "点火控制类",
    "medical_therapy": "治疗理疗设备类",
    "steam_cleaner_device": "整机清洁设备类",
    "beauty_device": "美容仪器设备类",
    "appliance_timer_switch": "定时控制类",
}


def run_postprocess_for_dir(run_dir: Path, *, translator) -> None:
    products = read_csv_rows(run_dir / "products.csv")
    audit_rows = read_csv_rows(run_dir / "products_filter_audit.csv")
    review_rows = build_review_rows(products, audit_rows)
    write_dict_csv(run_dir / "products_review.csv", REVIEW_FIELDS, review_rows)

    texts = _collect_translation_texts(review_rows)
    translations = translate_texts(texts, cache_path=run_dir / "translation_cache.json", translator=translator)
    review_rows_zh = enrich_review_rows_with_zh(
        review_rows,
        translations=translations,
        reason_builder=build_reason_zh,
        attributes_summary_builder=summarize_attributes_text,
    )

    write_dict_csv(run_dir / "products_zh.csv", PRODUCT_ZH_FIELDS, _build_products_zh_rows(products, review_rows_zh))
    write_dict_csv(
        run_dir / "products_filter_audit_zh.csv",
        FILTER_AUDIT_ZH_FIELDS,
        _build_audit_zh_rows(audit_rows, review_rows_zh),
    )
    (run_dir / "products_report.html").write_text(
        render_report_html(review_rows_zh, source_label=_source_label(review_rows_zh)),
        encoding="utf-8",
    )


def _collect_translation_texts(review_rows: list[dict[str, str]]) -> list[str]:
    texts: list[str] = []
    seen: set[str] = set()
    for row in review_rows:
        summary = summarize_attributes_text(row.get("attributes_text", ""))
        for text in (
            row.get("title", ""),
            row.get("shop_name", ""),
            row.get("promotion_text", ""),
            summary,
        ):
            if text and text not in seen:
                seen.add(text)
                texts.append(text)
    return texts


def _build_products_zh_rows(
    products: list[dict[str, str]],
    review_rows_zh: list[dict[str, str]],
) -> list[dict[str, str]]:
    review_by_product_url = {
        row.get("product_url", ""): row
        for row in review_rows_zh
        if row.get("product_url", "")
    }

    rows: list[dict[str, str]] = []
    for product in products:
        product_url = product.get("product_url", "")
        review_row = review_by_product_url.get(product_url, {})
        summary = review_row.get("attributes_summary", summarize_attributes_text(product.get("attributes_text", "")))
        rows.append(
            {
                **product,
                "title_zh": review_row.get("title_zh", product.get("title", "")),
                "shop_name_zh": review_row.get("shop_name_zh", product.get("shop_name", "")),
                "promotion_text_zh": review_row.get("promotion_text_zh", product.get("promotion_text", "")),
                "attributes_summary": summary,
                "attributes_summary_zh": review_row.get("attributes_summary_zh", summary),
            }
        )
    return rows


def _build_audit_zh_rows(
    audit_rows: list[dict[str, str]],
    review_rows_zh: list[dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for audit_row, review_row in zip(audit_rows, review_rows_zh):
        rows.append(
            {
                **audit_row,
                "filter_decision_zh": FILTER_DECISION_ZH.get(audit_row.get("filter_decision", ""), audit_row.get("filter_decision", "")),
                "filter_stage_zh": FILTER_STAGE_ZH.get(audit_row.get("filter_stage", ""), audit_row.get("filter_stage", "")),
                "reject_groups_zh": _translate_joined_tokens(audit_row.get("reject_groups", ""), GROUP_ZH),
                "reject_terms_zh": audit_row.get("reject_terms", ""),
                "warning_groups_zh": _translate_joined_tokens(audit_row.get("warning_groups", ""), GROUP_ZH),
                "warning_terms_zh": audit_row.get("warning_terms", ""),
                "reason_zh": review_row.get("reason_zh", ""),
            }
        )
    return rows


def _translate_joined_tokens(raw_value: str, mapping: dict[str, str]) -> str:
    if not raw_value:
        return ""
    translated: list[str] = []
    for token in raw_value.split("|"):
        normalized = token.strip()
        if not normalized:
            continue
        translated.append(mapping.get(normalized, normalized))
    return " | ".join(translated)


def _source_label(review_rows_zh: list[dict[str, str]]) -> str:
    for row in review_rows_zh:
        label = row.get("source_value", "").strip()
        if label:
            return label
    return "run"
