from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterable

from .scoring import ProductRecord


@dataclass(frozen=True)
class FilterGroup:
    name: str
    pre_reject_terms: tuple[str, ...] = ()
    post_reject_terms: tuple[str, ...] = ()


def load_filter_groups(
    blacklist_file: str | Path | None,
    reject_keywords: list[str],
) -> list[FilterGroup]:
    groups: list[FilterGroup] = []
    if blacklist_file:
        payload = json.loads(Path(blacklist_file).read_text(encoding="utf-8"))
        for item in payload.get("groups", []):
            name = str(item.get("name") or "").strip()
            pre_terms = tuple(_normalize_terms(item.get("pre_reject_terms", [])))
            post_source = item.get("post_reject_terms", item.get("terms", []))
            post_terms = tuple(_normalize_terms(post_source))
            if name and (pre_terms or post_terms):
                groups.append(
                    FilterGroup(
                        name=name,
                        pre_reject_terms=pre_terms,
                        post_reject_terms=post_terms,
                    )
                )
    cli_terms = tuple(_normalize_terms(reject_keywords))
    if cli_terms:
        groups.append(FilterGroup(name="cli_extra", pre_reject_terms=(), post_reject_terms=cli_terms))
    return groups


def prefilter_listing_products(
    raw_products: list[dict[str, object]],
    groups: list[FilterGroup],
    *,
    source_type: str,
    source_value: str,
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    survivors: list[dict[str, object]] = []
    audit_rows: list[dict[str, str]] = []

    for product in raw_products:
        title = " ".join(str(product.get("title") or "").split())
        product_url = str(product.get("resolvedProductUrl") or product.get("url") or "")
        reject_hits = _collect_text_hits(title, groups, terms_attr="pre_reject_terms", field="title")
        if reject_hits:
            audit_rows.append(
                {
                    "source_type": source_type,
                    "source_value": source_value,
                    "title": title,
                    "product_url": product_url,
                    "filter_decision": "rejected",
                    "filter_stage": "listing_title",
                    "reject_groups": _join_unique(hit["group"] for hit in reject_hits),
                    "reject_terms": _join_unique(hit["term"] for hit in reject_hits),
                    "reject_fields": "title",
                    "warning_groups": "",
                    "warning_terms": "",
                    "warning_fields": "",
                }
            )
            continue
        survivors.append(product)
    return survivors, audit_rows


def filter_products(
    products: list[ProductRecord],
    groups: list[FilterGroup],
) -> tuple[list[ProductRecord], list[dict[str, str]]]:
    accepted: list[ProductRecord] = []
    audit_rows: list[dict[str, str]] = []

    for product in products:
        reject_hits = _collect_product_hits(
            product,
            groups,
            fields=("title", "attributes_text"),
            terms_attr="post_reject_terms",
        )
        warning_hits = _collect_product_hits(
            product,
            groups,
            fields=("breadcrumb", "description_text"),
            terms_attr="post_reject_terms",
        )
        decision = "rejected" if reject_hits else "accepted"
        stage = "detail_post_enrich" if reject_hits else "accepted"
        if decision == "accepted":
            accepted.append(product)
        audit_rows.append(
            {
                "source_type": product.source_type,
                "source_value": product.source_value,
                "title": product.title,
                "product_url": product.product_url,
                "filter_decision": decision,
                "filter_stage": stage,
                "reject_groups": _join_unique(hit["group"] for hit in reject_hits),
                "reject_terms": _join_unique(hit["term"] for hit in reject_hits),
                "reject_fields": _join_unique(hit["field"] for hit in reject_hits),
                "warning_groups": _join_unique(hit["group"] for hit in warning_hits),
                "warning_terms": _join_unique(hit["term"] for hit in warning_hits),
                "warning_fields": _join_unique(hit["field"] for hit in warning_hits),
            }
        )
    return accepted, audit_rows


def _collect_product_hits(
    product: ProductRecord,
    groups: Iterable[FilterGroup],
    *,
    fields: tuple[str, ...],
    terms_attr: str,
) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for field in fields:
        haystack = getattr(product, field, "").lower()
        if not haystack:
            continue
        hits.extend(_collect_text_hits(haystack, groups, terms_attr=terms_attr, field=field))
    return hits


def _collect_text_hits(
    haystack: str,
    groups: Iterable[FilterGroup],
    *,
    terms_attr: str,
    field: str,
) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    normalized_haystack = haystack.lower()
    for group in groups:
        for term in getattr(group, terms_attr):
            normalized = term.strip().lower()
            if _matches_term(normalized_haystack, normalized):
                hits.append({"group": group.name, "term": term, "field": field})
    return hits


def _join_unique(values: Iterable[str]) -> str:
    ordered: list[str] = []
    for value in values:
        if value and value not in ordered:
            ordered.append(value)
    return " | ".join(ordered)


def _normalize_terms(values: Iterable[object]) -> list[str]:
    terms: list[str] = []
    for value in values:
        term = " ".join(str(value or "").split())
        if term and term not in terms:
            terms.append(term)
    return terms


def _matches_term(haystack: str, term: str) -> bool:
    if not term:
        return False
    if len(term) <= 2 and term.isalnum():
        return re.search(rf"\b{re.escape(term)}\b", haystack) is not None
    return term in haystack
