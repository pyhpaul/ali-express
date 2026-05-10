from __future__ import annotations

from typing import Iterable


PRODUCT_CONTEXT_FIELDS = (
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
)


def build_review_rows(products: Iterable[dict[str, str]], audit_rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Join audit rows with product context by product_url; duplicate product_url values raise ValueError."""

    product_index: dict[str, dict[str, str]] = {}
    for row in products:
        product_url = row.get("product_url", "")
        if not product_url:
            continue
        if product_url in product_index:
            raise ValueError(f"duplicate product_url: {product_url}")
        product_index[product_url] = row

    result: list[dict[str, str]] = []
    for audit in audit_rows:
        merged = dict(audit)
        product = product_index.get(audit.get("product_url", ""), {})
        for field in PRODUCT_CONTEXT_FIELDS:
            merged[field] = str(product.get(field, ""))
        result.append(merged)
    return result


def enrich_review_rows_with_zh(
    review_rows: list[dict[str, str]],
    *,
    translations: dict[str, str],
    reason_builder,
    attributes_summary_builder,
) -> list[dict[str, str]]:
    enriched: list[dict[str, str]] = []
    for row in review_rows:
        summary = attributes_summary_builder(row.get("attributes_text", ""))
        copied = dict(row)
        copied["title_zh"] = translations.get(row.get("title", ""), row.get("title", ""))
        copied["shop_name_zh"] = translations.get(row.get("shop_name", ""), row.get("shop_name", ""))
        copied["promotion_text_zh"] = translations.get(row.get("promotion_text", ""), row.get("promotion_text", ""))
        copied["attributes_summary"] = summary
        copied["attributes_summary_zh"] = translations.get(summary, summary)
        copied["reason_zh"] = reason_builder(row)
        enriched.append(copied)
    return enriched
