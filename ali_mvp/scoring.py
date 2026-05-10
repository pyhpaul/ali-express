from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


COUNT_RE = re.compile(r"(\d+(?:[,.]\d+)*)\s*([kKmM])?")
FLOAT_RE = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True)
class ProductRecord:
    source_type: str
    source_value: str
    title: str
    price: str
    sold_count: int
    rating: float
    review_count: int
    product_url: str
    search_card_url: str
    image_url: str
    entry_type: str
    is_promoted: bool
    promo_channel: str
    promotion_text: str
    promo_landing_url: str
    shop_name: str
    shipping_text: str
    detail_rating: float
    detail_review_count: int
    breadcrumb: str
    attributes_text: str
    description_text: str
    scraped_at: str
    detail_status: str = ""


@dataclass(frozen=True)
class RankRecord:
    source_value: str
    product_count: int
    total_sold_count: int
    avg_rating: float
    avg_review_count: float
    heat_score: float


def parse_count(value: str | None) -> int:
    if not value:
        return 0
    match = COUNT_RE.search(value)
    if not match:
        return 0
    number_text, suffix = match.groups()
    multiplier = 1
    if suffix and suffix.lower() == "k":
        multiplier = 1_000
    elif suffix and suffix.lower() == "m":
        multiplier = 1_000_000
    normalized = number_text.replace(",", "")
    return int(float(normalized) * multiplier)


def parse_float(value: str | None) -> float:
    if not value:
        return 0.0
    match = FLOAT_RE.search(value)
    if not match:
        return 0.0
    return float(match.group(0))


def aggregate_rank(products: Iterable[ProductRecord]) -> list[RankRecord]:
    grouped: dict[str, list[ProductRecord]] = {}
    for product in products:
        grouped.setdefault(product.source_value, []).append(product)

    rows = [_build_rank(source_value, items) for source_value, items in grouped.items()]
    return sorted(rows, key=lambda row: row.heat_score, reverse=True)


def _build_rank(source_value: str, products: list[ProductRecord]) -> RankRecord:
    product_count = len(products)
    total_sold = sum(product.sold_count for product in products)
    total_reviews = sum(product.review_count for product in products)
    avg_rating = round(sum(product.rating for product in products) / product_count, 2)
    avg_reviews = round(total_reviews / product_count, 2)
    heat_score = round(total_sold + total_reviews + product_count * 10 + avg_rating * 10, 2)
    return RankRecord(
        source_value=source_value,
        product_count=product_count,
        total_sold_count=total_sold,
        avg_rating=avg_rating,
        avg_review_count=avg_reviews,
        heat_score=heat_score,
    )
