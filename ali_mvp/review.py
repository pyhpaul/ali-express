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
