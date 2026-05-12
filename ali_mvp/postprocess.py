from __future__ import annotations

from pathlib import Path

from .output import (
    FILTER_AUDIT_ZH_FIELDS,
    PRODUCT_ZH_FIELDS,
    REVIEW_FIELDS,
    REVIEW_ONLY_FIELDS,
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

DECISION_LABELS = {
    "accepted": "建议入库",
    "rejected": "拒绝入库",
}


def run_postprocess_for_dir(run_dir: Path, *, translator, translation_cache_namespace: str = "default") -> None:
    products = read_csv_rows(run_dir / "products.csv")
    audit_rows = read_csv_rows(run_dir / "products_filter_audit.csv")
    review_rows = _load_review_rows(run_dir, products=products, audit_rows=audit_rows)
    write_dict_csv(run_dir / "products_review.csv", REVIEW_FIELDS, review_rows)

    texts = _collect_translation_texts(review_rows)
    translations = translate_texts(
        texts,
        cache_path=run_dir / "translation_cache.json",
        translator=translator,
        cache_namespace=translation_cache_namespace,
    )
    review_rows_zh = enrich_review_rows_with_zh(
        review_rows,
        translations=translations,
        reason_builder=build_reason_zh,
        attributes_summary_builder=summarize_attributes_text,
    )

    write_dict_csv(run_dir / "products_zh.csv", PRODUCT_ZH_FIELDS, _build_products_zh_rows(products, review_rows_zh))
    write_dict_csv(run_dir / "review_only.csv", REVIEW_ONLY_FIELDS, _build_review_only_rows(review_rows_zh))
    write_dict_csv(
        run_dir / "products_filter_audit_zh.csv",
        FILTER_AUDIT_ZH_FIELDS,
        _build_audit_zh_rows(audit_rows, review_rows_zh),
    )
    (run_dir / "products_report.html").write_text(
        render_report_html(
            review_rows_zh,
            source_label=_source_label(review_rows_zh),
            translation_provider=translation_cache_namespace,
        ),
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


def _load_review_rows(
    run_dir: Path,
    *,
    products: list[dict[str, str]],
    audit_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    review_path = run_dir / "products_review.csv"
    if review_path.exists():
        existing_review_rows = read_csv_rows(review_path)
        if len(existing_review_rows) == len(audit_rows):
            return existing_review_rows
    return build_review_rows(products, audit_rows)


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
                "decision_label": _decision_label(review_row),
                "stage_label": _stage_label(review_row),
                "review_note": _review_note(review_row),
            }
        )
    return rows


def _build_audit_zh_rows(
    audit_rows: list[dict[str, str]],
    review_rows_zh: list[dict[str, str]],
) -> list[dict[str, str]]:
    if len(audit_rows) != len(review_rows_zh):
        raise ValueError(
            f"audit_rows and review_rows_zh length mismatch: {len(audit_rows)} != {len(review_rows_zh)}"
        )

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
                "decision_label": _decision_label(review_row),
                "stage_label": _stage_label(review_row),
                "review_note": _review_note(review_row),
            }
        )
    return rows


def _build_review_only_rows(review_rows_zh: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in review_rows_zh:
        summary = row.get("attributes_summary", summarize_attributes_text(row.get("attributes_text", "")))
        rows.append(
            {
                "source_type": row.get("source_type", ""),
                "source_value": row.get("source_value", ""),
                "title": row.get("title", ""),
                "title_zh": row.get("title_zh", row.get("title", "")),
                "product_url": row.get("product_url", ""),
                "image_url": row.get("image_url", ""),
                "price": row.get("price", ""),
                "entry_type": row.get("entry_type", ""),
                "shop_name": row.get("shop_name", ""),
                "shop_name_zh": row.get("shop_name_zh", row.get("shop_name", "")),
                "promotion_text": row.get("promotion_text", ""),
                "promotion_text_zh": row.get("promotion_text_zh", row.get("promotion_text", "")),
                "attributes_summary": summary,
                "attributes_summary_zh": row.get("attributes_summary_zh", summary),
                "decision_label": _decision_label(row),
                "stage_label": _stage_label(row),
                "review_note": _review_note(row),
            }
        )
    return sorted(rows, key=_review_only_sort_key)


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


def _decision_label(row: dict[str, str]) -> str:
    return DECISION_LABELS.get(row.get("filter_decision", ""), row.get("filter_decision", ""))


def _stage_label(row: dict[str, str]) -> str:
    return FILTER_STAGE_ZH.get(row.get("filter_stage", ""), row.get("filter_stage", ""))


def _review_note(row: dict[str, str]) -> str:
    if row.get("filter_decision") == "rejected":
        reason_zh = row.get("reason_zh", "").strip()
        if reason_zh:
            return f"拒绝原因: {reason_zh}"
        return "拒绝原因: 待人工复核"
    return "可入库候选"


def _review_only_sort_key(row: dict[str, str]) -> tuple[object, ...]:
    decision = row.get("decision_label", "")
    stage = row.get("stage_label", "")
    reason = row.get("review_note", "")
    title = row.get("title_zh", "") or row.get("title", "")
    decision_rank = 0 if decision == "拒绝入库" else 1
    stage_rank = 0 if stage == "详情补充后命中" else 1 if stage == "标题命中" else 2
    return (
        decision_rank,
        reason,
        stage_rank,
        title,
        row.get("product_url", ""),
    )
