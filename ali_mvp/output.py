from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

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
    "detail_status",
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

FILTER_AUDIT_FIELDS = [
    "source_type",
    "source_value",
    "title",
    "product_url",
    "filter_decision",
    "filter_stage",
    "reject_groups",
    "reject_terms",
    "reject_fields",
    "warning_groups",
    "warning_terms",
    "warning_fields",
]

REVIEW_FIELDS = [
    "source_type",
    "source_value",
    "title",
    "product_url",
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
    "filter_decision",
    "filter_stage",
    "reject_groups",
    "reject_terms",
    "reject_fields",
    "warning_groups",
    "warning_terms",
    "warning_fields",
]

REVIEW_ONLY_FIELDS = [
    "source_type",
    "source_value",
    "title",
    "title_zh",
    "product_url",
    "image_url",
    "price",
    "entry_type",
    "shop_name",
    "shop_name_zh",
    "promotion_text",
    "promotion_text_zh",
    "attributes_summary",
    "attributes_summary_zh",
    "decision_label",
    "stage_label",
    "review_note",
]

PRODUCT_ZH_FIELDS = PRODUCT_FIELDS + [
    "title_zh",
    "shop_name_zh",
    "promotion_text_zh",
    "attributes_summary",
    "attributes_summary_zh",
    "decision_label",
    "stage_label",
    "review_note",
]

FILTER_AUDIT_ZH_FIELDS = FILTER_AUDIT_FIELDS + [
    "filter_decision_zh",
    "filter_stage_zh",
    "reject_groups_zh",
    "reject_terms_zh",
    "warning_groups_zh",
    "warning_terms_zh",
    "reason_zh",
    "decision_label",
    "stage_label",
    "review_note",
]


def write_products_csv(path: Path, products: Iterable[ProductRecord]) -> None:
    _write_dataclass_csv(path, PRODUCT_FIELDS, products)


def write_rank_csv(path: Path, rows: Iterable[RankRecord]) -> None:
    _write_dataclass_csv(path, RANK_FIELDS, rows)


def write_filter_audit_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    write_dict_csv(path, FILTER_AUDIT_FIELDS, rows)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_dict_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            extra_fields = sorted(set(row) - set(fieldnames))
            if extra_fields:
                raise ValueError(f"unexpected CSV columns: {', '.join(extra_fields)}")
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _write_dataclass_csv(path: Path, fieldnames: list[str], rows: Iterable[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
