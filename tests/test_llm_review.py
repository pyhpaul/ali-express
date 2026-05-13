from pathlib import Path

from ali_mvp.llm_client import LlmConfig
from ali_mvp.output import LLM_REVIEW_FIELDS, REVIEW_FIELDS, read_csv_rows, write_dict_csv, write_llm_review_csv
from ali_mvp.llm_review import (
    LLM_PROMPT_VERSION,
    compute_llm_input_hash,
    run_llm_review_for_dir,
)


def _config() -> LlmConfig:
    return LlmConfig(
        base_url="http://localhost:11434/v1",
        api_key="secret",
        model="gpt-test",
        provider="openai-compatible",
    )


def _review_row(
    *,
    product_url: str,
    title: str,
    promotion_text: str = "",
    attributes_text: str = "",
    description_text: str = "",
    entry_type: str = "item_card",
    detail_status: str = "ok",
    filter_decision: str = "accepted",
    filter_stage: str = "accepted",
    reject_groups: str = "",
    reject_terms: str = "",
    warning_groups: str = "",
    warning_terms: str = "",
) -> dict[str, str]:
    return {
        "source_type": "keyword",
        "source_value": "home appliance accessories",
        "title": title,
        "product_url": product_url,
        "image_url": f"{product_url}.jpg" if product_url else "",
        "price": "$1",
        "search_card_url": product_url,
        "entry_type": entry_type,
        "is_promoted": "False",
        "promo_channel": "",
        "promotion_text": promotion_text,
        "shop_name": "Store A",
        "shipping_text": "",
        "attributes_text": attributes_text,
        "description_text": description_text,
        "detail_status": detail_status,
        "filter_decision": filter_decision,
        "filter_stage": filter_stage,
        "reject_groups": reject_groups,
        "reject_terms": reject_terms,
        "reject_fields": "",
        "warning_groups": warning_groups,
        "warning_terms": warning_terms,
        "warning_fields": "",
    }


def _write_products_review_csv(run_dir: Path, rows: list[dict[str, str]]) -> None:
    write_dict_csv(run_dir / "products_review.csv", REVIEW_FIELDS, rows)


def _llm_row(base_row: dict[str, str], *, config: LlmConfig, decision: str = "keep") -> dict[str, str]:
    return {
        "source_type": base_row["source_type"],
        "source_value": base_row["source_value"],
        "title": base_row["title"],
        "product_url": base_row["product_url"],
        "image_url": base_row["image_url"],
        "price": base_row["price"],
        "entry_type": base_row["entry_type"],
        "promotion_text": base_row["promotion_text"],
        "shop_name": base_row["shop_name"],
        "attributes_text": base_row["attributes_text"],
        "description_text": base_row["description_text"],
        "detail_status": base_row["detail_status"],
        "filter_decision": base_row["filter_decision"],
        "filter_stage": base_row["filter_stage"],
        "reject_groups": base_row["reject_groups"],
        "reject_terms": base_row["reject_terms"],
        "warning_groups": base_row["warning_groups"],
        "warning_terms": base_row["warning_terms"],
        "llm_decision": decision,
        "llm_reason": f"{decision} reason",
        "llm_risk_tags": "battery",
        "llm_confidence": "high",
        "llm_summary_zh": f"{decision} summary",
        "llm_model": config.model,
        "llm_provider": config.provider,
        "llm_prompt_version": LLM_PROMPT_VERSION,
        "llm_input_hash": compute_llm_input_hash(base_row),
        "llm_reviewed_at": "2026-05-13T00:00:00Z",
        "llm_error": "",
    }


def test_run_llm_review_for_dir_reuses_existing_rows_when_hash_prompt_and_model_match(tmp_path):
    run_dir = tmp_path
    config = _config()
    review_row = _review_row(product_url="https://example.test/item/1", title="Adapter shell")
    _write_products_review_csv(run_dir, [review_row])
    write_llm_review_csv(run_dir / "products_llm_review.csv", [_llm_row(review_row, config=config, decision="keep")])

    def reviewer(_row, _config):
        raise AssertionError("reviewer should not be called")

    result = run_llm_review_for_dir(run_dir, config=config, reviewer=reviewer)

    rows = read_csv_rows(run_dir / "products_llm_review.csv")
    assert result.reviewed_count == 0
    assert result.skipped_count == 1
    assert result.failed_count == 0
    assert result.keep_count == 1
    assert rows[0]["llm_decision"] == "keep"


def test_run_llm_review_for_dir_continues_when_single_row_fails(tmp_path):
    run_dir = tmp_path
    config = _config()
    row1 = _review_row(product_url="https://example.test/item/1", title="Unknown item")
    row2 = _review_row(product_url="https://example.test/item/2", title="Vacuum brush")
    _write_products_review_csv(run_dir, [row1, row2])

    def reviewer(row, _config):
        if row["product_url"] == row1["product_url"]:
            raise RuntimeError("network boom")
        return {
            "decision": "keep",
            "reason": "looks like an accessory",
            "risk_tags": ["battery", "unknown_tag"],
            "confidence": "high",
            "summary_zh": "看起来是配件",
        }

    result = run_llm_review_for_dir(run_dir, config=config, reviewer=reviewer)

    rows = read_csv_rows(run_dir / "products_llm_review.csv")
    first, second = rows
    assert result.failed_count == 1
    assert result.reviewed_count == 1
    assert first["llm_decision"] == ""
    assert first["llm_error"] == "network boom"
    assert second["llm_decision"] == "keep"
    assert second["llm_risk_tags"] == "battery"


def test_run_llm_review_for_dir_force_true_reruns_even_when_existing_row_reusable(tmp_path):
    run_dir = tmp_path
    config = _config()
    review_row = _review_row(product_url="https://example.test/item/1", title="Adapter shell")
    _write_products_review_csv(run_dir, [review_row])
    write_llm_review_csv(run_dir / "products_llm_review.csv", [_llm_row(review_row, config=config, decision="drop")])
    calls = []

    def reviewer(row, _config):
        calls.append(row["product_url"])
        return {
            "decision": "keep",
            "reason": "rerun",
            "risk_tags": [],
            "confidence": "medium",
            "summary_zh": "重跑",
        }

    result = run_llm_review_for_dir(run_dir, config=config, reviewer=reviewer, force=True)

    rows = read_csv_rows(run_dir / "products_llm_review.csv")
    assert calls == [review_row["product_url"]]
    assert result.reviewed_count == 1
    assert result.skipped_count == 0
    assert rows[0]["llm_decision"] == "keep"


def test_run_llm_review_for_dir_reruns_when_existing_provider_differs(tmp_path):
    run_dir = tmp_path
    config = _config()
    review_row = _review_row(product_url="https://example.test/item/1", title="Adapter shell")
    _write_products_review_csv(run_dir, [review_row])
    existing_config = LlmConfig(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
        provider="other-provider",
    )
    write_llm_review_csv(run_dir / "products_llm_review.csv", [_llm_row(review_row, config=existing_config, decision="drop")])
    calls = []

    def reviewer(row, _config):
        calls.append(row["product_url"])
        return {
            "decision": "keep",
            "reason": "provider changed",
            "risk_tags": [],
            "confidence": "medium",
            "summary_zh": "provider changed",
        }

    result = run_llm_review_for_dir(run_dir, config=config, reviewer=reviewer)

    rows = read_csv_rows(run_dir / "products_llm_review.csv")
    assert calls == [review_row["product_url"]]
    assert result.reviewed_count == 1
    assert result.skipped_count == 0
    assert rows[0]["llm_provider"] == config.provider
    assert rows[0]["llm_decision"] == "keep"


def test_run_llm_review_for_dir_respects_max_items(tmp_path):
    run_dir = tmp_path
    config = _config()
    row1 = _review_row(product_url="https://example.test/item/1", title="Item 1")
    row2 = _review_row(product_url="https://example.test/item/2", title="Item 2")
    _write_products_review_csv(run_dir, [row1, row2])
    seen = []

    def reviewer(row, _config):
        seen.append(row["product_url"])
        return {
            "decision": "keep",
            "reason": "ok",
            "risk_tags": [],
            "confidence": "high",
            "summary_zh": "ok",
        }

    result = run_llm_review_for_dir(run_dir, config=config, reviewer=reviewer, max_items=1)

    rows = read_csv_rows(run_dir / "products_llm_review.csv")
    assert seen == [row1["product_url"]]
    assert result.total_rows == 1
    assert len(rows) == 1


def test_run_llm_review_for_dir_returns_non_zero_exit_code_when_all_rows_fail(tmp_path):
    run_dir = tmp_path
    config = _config()
    row1 = _review_row(product_url="https://example.test/item/1", title="Item 1")
    row2 = _review_row(product_url="https://example.test/item/2", title="Item 2")
    _write_products_review_csv(run_dir, [row1, row2])

    def reviewer(_row, _config):
        raise RuntimeError("always fails")

    result = run_llm_review_for_dir(run_dir, config=config, reviewer=reviewer)

    assert result.exit_code != 0
    assert result.failed_count == 2
    assert result.reviewed_count == 0
    assert result.skipped_count == 0


def test_run_llm_review_for_dir_writes_final_keep_and_drop_csv_with_full_fields(tmp_path):
    run_dir = tmp_path
    config = _config()
    row1 = _review_row(product_url="https://example.test/item/1", title="Keep item")
    row2 = _review_row(product_url="https://example.test/item/2", title="Drop item")
    _write_products_review_csv(run_dir, [row1, row2])

    def reviewer(row, _config):
        decision = "keep" if row["product_url"] == row1["product_url"] else "drop"
        return {
            "decision": decision,
            "reason": f"{decision} reason",
            "risk_tags": ["promo_bundle"] if decision == "drop" else [],
            "confidence": "high",
            "summary_zh": f"{decision} summary",
        }

    run_llm_review_for_dir(run_dir, config=config, reviewer=reviewer)

    keep_rows = read_csv_rows(run_dir / "products_final_keep.csv")
    drop_rows = read_csv_rows(run_dir / "products_final_drop.csv")

    assert list(keep_rows[0].keys()) == LLM_REVIEW_FIELDS
    assert list(drop_rows[0].keys()) == LLM_REVIEW_FIELDS
    assert keep_rows[0]["llm_decision"] == "keep"
    assert drop_rows[0]["llm_decision"] == "drop"
