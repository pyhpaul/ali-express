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
    pre_require_terms: tuple[str, ...] = ()
    post_require_terms: tuple[str, ...] = ()


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
            pre_require_terms = tuple(_normalize_terms(item.get("pre_require_terms", [])))
            post_source = item.get("post_reject_terms", item.get("terms", []))
            post_terms = tuple(_normalize_terms(post_source))
            post_require_terms = tuple(_normalize_terms(item.get("post_require_terms", [])))
            if name and (pre_terms or post_terms):
                groups.append(
                    FilterGroup(
                        name=name,
                        pre_reject_terms=pre_terms,
                        post_reject_terms=post_terms,
                        pre_require_terms=pre_require_terms,
                        post_require_terms=post_require_terms,
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
        reject_hits = _collect_group_hits(
            {"title": title},
            groups,
            reject_terms_attr="pre_reject_terms",
            require_terms_attr="pre_require_terms",
        )
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
            reject_terms_attr="post_reject_terms",
            require_terms_attr="post_require_terms",
        )
        warning_hits = _collect_product_hits(
            product,
            groups,
            fields=("breadcrumb", "description_text"),
            reject_terms_attr="post_reject_terms",
            require_terms_attr="post_require_terms",
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
    reject_terms_attr: str,
    require_terms_attr: str,
) -> list[dict[str, str]]:
    field_texts: dict[str, str] = {}
    for field in fields:
        haystack = getattr(product, field, "")
        if not haystack:
            continue
        field_texts[field] = haystack
    if not field_texts:
        return []
    return _collect_group_hits(
        field_texts,
        groups,
        reject_terms_attr=reject_terms_attr,
        require_terms_attr=require_terms_attr,
    )


def _collect_group_hits(
    field_texts: dict[str, str],
    groups: Iterable[FilterGroup],
    *,
    reject_terms_attr: str,
    require_terms_attr: str,
) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    normalized_fields = {field: haystack.lower() for field, haystack in field_texts.items() if haystack}
    combined_haystack = "\n".join(normalized_fields.values())
    for group in groups:
        group_hits: list[dict[str, str]] = []
        for field, haystack in normalized_fields.items():
            for term in getattr(group, reject_terms_attr):
                normalized = term.strip().lower()
                if _matches_term(haystack, normalized):
                    group_hits.append({"group": group.name, "term": term, "field": field})
        if not group_hits:
            continue
        require_terms = getattr(group, require_terms_attr)
        if require_terms and not any(_matches_term(combined_haystack, term.strip().lower()) for term in require_terms):
            continue
        hits.extend(group_hits)
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
