from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .scoring import ProductRecord, RankRecord


PRODUCT_FIELDS = [
    "source_type",
    "source_value",
    "title",
    "price",
    "sold_count",
    "rating",
    "review_count",
    "product_url",
    "search_card_url",
    "image_url",
    "entry_type",
    "is_promoted",
    "promo_channel",
    "promotion_text",
    "promo_landing_url",
    "shop_name",
    "shipping_text",
    "detail_rating",
    "detail_review_count",
    "breadcrumb",
    "attributes_text",
    "description_text",
    "scraped_at",
]

RANK_FIELDS = [
    "source_value",
    "product_count",
    "total_sold_count",
    "avg_rating",
    "avg_review_count",
    "heat_score",
]


def write_products_csv(path: Path, products: Iterable[ProductRecord]) -> None:
    _write_dataclass_csv(path, PRODUCT_FIELDS, products)


def write_rank_csv(path: Path, rows: Iterable[RankRecord]) -> None:
    _write_dataclass_csv(path, RANK_FIELDS, rows)


def _write_dataclass_csv(path: Path, fieldnames: list[str], rows: Iterable[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
