from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Mapping

from .llm_client import LlmConfig
from .output import read_csv_rows, write_llm_review_csv


LLM_PROMPT_VERSION = "v1"

LLM_RISK_TAGS = {
    "electrical",
    "battery",
    "chip",
    "controller",
    "motor",
    "heating",
    "wireless",
    "uncertain",
    "not_accessory",
    "promo_bundle",
}

LLM_INPUT_HASH_FIELDS = (
    "title",
    "promotion_text",
    "attributes_text",
    "description_text",
    "entry_type",
    "detail_status",
    "filter_decision",
    "filter_stage",
    "reject_groups",
    "reject_terms",
    "warning_groups",
    "warning_terms",
)


@dataclass(frozen=True)
class LlmReviewRunResult:
    exit_code: int
    total_rows: int
    reviewed_count: int
    skipped_count: int
    failed_count: int
    keep_count: int
    drop_count: int


def compute_llm_input_hash(row: Mapping[str, str]) -> str:
    payload = {field: row.get(field, "") for field in LLM_INPUT_HASH_FIELDS}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_llm_review_for_dir(
    run_dir: Path,
    *,
    config: LlmConfig,
    force: bool = False,
    max_items: int | None = None,
    reviewer: Callable[[dict[str, str], LlmConfig], Mapping[str, object]],
) -> LlmReviewRunResult:
    review_rows = read_csv_rows(run_dir / "products_review.csv")
    if max_items is not None:
        review_rows = review_rows[:max_items]

    existing_rows = _load_existing_llm_rows(run_dir / "products_llm_review.csv")
    output_rows: list[dict[str, str]] = []
    reviewed_count = 0
    skipped_count = 0
    failed_count = 0

    for row in review_rows:
        existing = existing_rows.get(row.get("product_url", ""))
        if _can_reuse_existing(existing, row=row, config=config, force=force):
            output_rows.append(dict(existing))
            skipped_count += 1
            continue

        try:
            result = reviewer(row, config)
            output_rows.append(_build_llm_review_row(row, config=config, result=result))
            reviewed_count += 1
        except Exception as exc:
            output_rows.append(_build_llm_review_row(row, config=config, error=str(exc)))
            failed_count += 1

    write_llm_review_csv(run_dir / "products_llm_review.csv", output_rows)
    write_llm_review_csv(
        run_dir / "products_final_keep.csv",
        [row for row in output_rows if row.get("llm_decision") == "keep"],
    )
    write_llm_review_csv(
        run_dir / "products_final_drop.csv",
        [row for row in output_rows if row.get("llm_decision") == "drop"],
    )
    return _build_run_result(
        total_rows=len(review_rows),
        reviewed_count=reviewed_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        rows=output_rows,
    )


def _load_existing_llm_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows = read_csv_rows(path)
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        product_url = row.get("product_url", "")
        if product_url:
            indexed[product_url] = row
    return indexed


def _can_reuse_existing(
    existing: dict[str, str] | None,
    *,
    row: Mapping[str, str],
    config: LlmConfig,
    force: bool,
) -> bool:
    if force or existing is None:
        return False
    product_url = row.get("product_url", "")
    if not product_url:
        return False
    return (
        existing.get("llm_input_hash", "") == compute_llm_input_hash(row)
        and existing.get("llm_prompt_version", "") == LLM_PROMPT_VERSION
        and existing.get("llm_model", "") == config.model
        and existing.get("llm_provider", "") == config.provider
        and bool(existing.get("llm_decision", "").strip())
    )


def _build_llm_review_row(
    row: Mapping[str, str],
    *,
    config: LlmConfig,
    result: Mapping[str, object] | None = None,
    error: str = "",
) -> dict[str, str]:
    risk_tags = _normalize_risk_tags(result.get("risk_tags", []) if result else [])
    decision = str(result.get("decision", "")) if result else ""
    reviewed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "source_type": row.get("source_type", ""),
        "source_value": row.get("source_value", ""),
        "title": row.get("title", ""),
        "product_url": row.get("product_url", ""),
        "image_url": row.get("image_url", ""),
        "price": row.get("price", ""),
        "entry_type": row.get("entry_type", ""),
        "promotion_text": row.get("promotion_text", ""),
        "shop_name": row.get("shop_name", ""),
        "attributes_text": row.get("attributes_text", ""),
        "description_text": row.get("description_text", ""),
        "detail_status": row.get("detail_status", ""),
        "filter_decision": row.get("filter_decision", ""),
        "filter_stage": row.get("filter_stage", ""),
        "reject_groups": row.get("reject_groups", ""),
        "reject_terms": row.get("reject_terms", ""),
        "warning_groups": row.get("warning_groups", ""),
        "warning_terms": row.get("warning_terms", ""),
        "llm_decision": decision if not error else "",
        "llm_reason": str(result.get("reason", "")) if result and not error else "",
        "llm_risk_tags": "|".join(risk_tags),
        "llm_confidence": str(result.get("confidence", "")) if result and not error else "",
        "llm_summary_zh": str(result.get("summary_zh", "")) if result and not error else "",
        "llm_model": config.model,
        "llm_provider": config.provider,
        "llm_prompt_version": LLM_PROMPT_VERSION,
        "llm_input_hash": compute_llm_input_hash(row),
        "llm_reviewed_at": reviewed_at,
        "llm_error": error,
    }


def _normalize_risk_tags(raw_tags: object) -> list[str]:
    if not isinstance(raw_tags, list):
        return []
    tags: list[str] = []
    for tag in raw_tags:
        normalized = str(tag).strip()
        if normalized in LLM_RISK_TAGS:
            tags.append(normalized)
    return tags


def _build_run_result(
    *,
    total_rows: int,
    reviewed_count: int,
    skipped_count: int,
    failed_count: int,
    rows: list[dict[str, str]],
) -> LlmReviewRunResult:
    keep_count = sum(1 for row in rows if row.get("llm_decision") == "keep")
    drop_count = sum(1 for row in rows if row.get("llm_decision") == "drop")
    exit_code = 0 if reviewed_count > 0 or skipped_count > 0 else 1
    return LlmReviewRunResult(
        exit_code=exit_code,
        total_rows=total_rows,
        reviewed_count=reviewed_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        keep_count=keep_count,
        drop_count=drop_count,
    )
