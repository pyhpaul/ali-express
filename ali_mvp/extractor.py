from __future__ import annotations

from collections.abc import Mapping

from .scoring import ProductRecord, parse_count, parse_float


def normalize_products(
    raw_products: list[Mapping[str, object]],
    *,
    source_type: str,
    source_value: str,
    scraped_at: str,
) -> list[ProductRecord]:
    products: list[ProductRecord] = []
    seen_urls: set[str] = set()

    for raw in raw_products:
        title = _clean_text(raw.get("title"))
        url = _normalize_url(_clean_text(raw.get("url")))
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        products.append(
            ProductRecord(
                source_type=source_type,
                source_value=source_value,
                title=title,
                price=_clean_text(raw.get("price")),
                sold_count=parse_count(_clean_text(raw.get("soldText"))),
                rating=parse_float(_clean_text(raw.get("ratingText"))),
                review_count=parse_count(_clean_text(raw.get("reviewText"))),
                product_url=url,
                image_url=_normalize_url(_clean_text(raw.get("image"))),
                scraped_at=scraped_at,
            )
        )

    return products


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _normalize_url(value: str) -> str:
    if value.startswith("//"):
        return f"https:{value}"
    return value
