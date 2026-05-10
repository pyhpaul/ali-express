# AliExpress 中文后处理与浏览器最小加固 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有 AliExpress 抓取流程新增中文后处理产物、HTML 审核页、审核视图中间文件，并以最小侵入方式加入浏览器节奏与最小 stealth 加固。

**Architecture:** 保持 `scrape` 主链路职责不变，只在 `run_scrape()` 收敛点后追加可选后处理。后处理拆为 review 视图组装、翻译/缓存、HTML 报表三个独立模块。浏览器优化只落在 `browser.py` 的 options、页面初始化和 wait/pacing helper，不改抓取业务语义。

**Tech Stack:** Python 3, DrissionPage, argparse, csv/json/pathlib, pytest

---

## File Structure

### New files

- `ali_mvp/postprocess.py`
  - 后处理总编排，负责读取 run 目录数据、组装 review 行、驱动翻译与 HTML 输出
- `ali_mvp/review.py`
  - 定义 review row schema，并负责把 `products.csv` / `products_filter_audit.csv` 合并成 `products_review.csv`
- `ali_mvp/translation.py`
  - 文本翻译接口、缓存读写、失败回退、字段级批处理
- `ali_mvp/reporting.py`
  - 生成 `products_report.html`
- `tests/test_review.py`
  - 审核视图组装与 join 逻辑测试
- `tests/test_translation.py`
  - 缓存、失败回退、字段翻译测试
- `tests/test_reporting.py`
  - HTML 页面结构与 summary 统计测试
- `tests/fixtures/postprocess/*.csv`
  - 后处理和 review 组装测试夹具

### Modified files

- `ali_mvp/cli.py`
  - 增加 `postprocess` 子命令
  - 为 `scrape` 增加 `--browser-hardening`
  - 在 `run_scrape()` 写完原始 CSV 后可调用 review 产物生成
- `ali_mvp/output.py`
  - 增加 CSV 读写 helper
  - 增加 `products_review.csv` / 中文 CSV / HTML 文件落盘 helper
- `ali_mvp/browser.py`
  - 增加 browser hardening 配置透传
  - 增加最小 stealth 初始化 helper
  - 增加 jitter / pacing helper
- `README.md`
  - 增加 `postprocess` 用法、输出说明、`--browser-hardening` 说明
- `tests/test_cli.py`
  - 覆盖新子命令、新参数、`run_scrape()` 调用后处理 hook
- `tests/test_browser.py`
  - 覆盖 pacing helper、options hardening、初始化 hook
- `tests/test_output.py`
  - 覆盖新增 CSV reader/writer 和 HTML 输出 helper

## Task 1: 定义后处理 CLI 入口和参数边界

**Files:**
- Modify: `ali_mvp/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 写 parser 失败测试，锁定新 CLI 接口**

```python
def test_parser_accepts_postprocess_run_dir_and_default_browser_hardening():
    parser = build_parser()

    scrape_args = parser.parse_args(["scrape", "--keyword", "women dress"])
    post_args = parser.parse_args(["postprocess", "--run-dir", "data/run-1"])

    assert scrape_args.browser_hardening == "minimal"
    assert post_args.run_dir == "data/run-1"
```

- [ ] **Step 2: 运行单测确认失败**

Run: `python -m pytest tests/test_cli.py::test_parser_accepts_postprocess_run_dir_and_default_browser_hardening -q`
Expected: FAIL，提示 `browser_hardening` 或 `postprocess` 参数尚不存在

- [ ] **Step 3: 在 `ali_mvp/cli.py` 增加参数与命令**

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ali_mvp")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scrape = subparsers.add_parser("scrape", help="Scrape AliExpress product listings.")
    # ... existing source args ...
    scrape.add_argument(
        "--browser-hardening",
        choices=("off", "minimal"),
        default="minimal",
        help="Apply optional browser pacing/stealth hardening.",
    )
    scrape.set_defaults(func=run_scrape)

    postprocess = subparsers.add_parser("postprocess", help="Generate zh outputs and review report from an existing run.")
    postprocess.add_argument("--run-dir", required=True, help="Existing scrape run directory containing products.csv outputs.")
    postprocess.set_defaults(func=run_postprocess)
    return parser
```

- [ ] **Step 4: 运行 parser 测试确认通过**

Run: `python -m pytest tests/test_cli.py::test_parser_accepts_postprocess_run_dir_and_default_browser_hardening -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add ali_mvp/cli.py tests/test_cli.py
git commit -m "feat(cli): add postprocess command surface

Why:
- expose zh postprocess and browser hardening without changing scrape semantics

What:
- add postprocess subcommand
- add browser hardening flag to scrape parser

Test:
- python -m pytest tests/test_cli.py::test_parser_accepts_postprocess_run_dir_and_default_browser_hardening -q"
```

## Task 2: 增加 output 读写基础设施

**Files:**
- Modify: `ali_mvp/output.py`
- Test: `tests/test_output.py`

- [ ] **Step 1: 写失败测试，定义 CSV 读取和 review/zh 输出 helper**

```python
def test_read_csv_rows_round_trips_written_audit(tmp_path):
    path = tmp_path / "products_filter_audit.csv"
    rows = [{"source_type": "keyword", "source_value": "x", "title": "A", "product_url": "u"}]

    write_dict_csv(path, ["source_type", "source_value", "title", "product_url"], rows)
    loaded = read_csv_rows(path)

    assert loaded == [{"source_type": "keyword", "source_value": "x", "title": "A", "product_url": "u"}]
```

- [ ] **Step 2: 运行单测确认失败**

Run: `python -m pytest tests/test_output.py::test_read_csv_rows_round_trips_written_audit -q`
Expected: FAIL，提示 `write_dict_csv` 或 `read_csv_rows` 未定义

- [ ] **Step 3: 在 `ali_mvp/output.py` 增加通用读写 helper**

```python
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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_dict_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
```

- [ ] **Step 4: 把现有 audit writer 复用到通用 helper**

```python
def write_filter_audit_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    write_dict_csv(path, FILTER_AUDIT_FIELDS, rows)
```

- [ ] **Step 5: 运行 output 测试确认通过**

Run: `python -m pytest tests/test_output.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add ali_mvp/output.py tests/test_output.py
git commit -m "feat(output): add reusable csv io helpers

Why:
- postprocess needs stable csv readers and extra writers without duplicating io code

What:
- add generic csv dict read/write helpers
- prepare review output field definitions

Test:
- python -m pytest tests/test_output.py -q"
```

## Task 3: 定义 review row 组装逻辑

**Files:**
- Create: `ali_mvp/review.py`
- Test: `tests/test_review.py`
- Fixture: `tests/fixtures/postprocess/products.csv`
- Fixture: `tests/fixtures/postprocess/products_filter_audit.csv`

- [ ] **Step 1: 写失败测试，锁定 accepted/rejected 合并规则**

```python
def test_build_review_rows_merges_product_context_into_audit_rows():
    products = [
        {
            "title": "Shock pad",
            "product_url": "https://example.test/item/1",
            "image_url": "https://example.test/img.jpg",
            "price": "$1.00",
            "search_card_url": "https://example.test/card/1",
            "entry_type": "item_card",
            "is_promoted": "False",
            "promo_channel": "",
            "promotion_text": "",
            "shop_name": "Store A",
            "shipping_text": "Free shipping",
            "attributes_text": "{\"Type\":\"Pad\"}",
            "description_text": "Accessory",
            "detail_status": "",
        }
    ]
    audit_rows = [
        {
            "title": "Shock pad",
            "product_url": "https://example.test/item/1",
            "filter_decision": "accepted",
            "filter_stage": "accepted",
            "reject_groups": "",
            "reject_terms": "",
            "reject_fields": "",
            "warning_groups": "",
            "warning_terms": "",
            "warning_fields": "",
            "source_type": "keyword",
            "source_value": "home appliance accessories",
        }
    ]

    review_rows = build_review_rows(products, audit_rows)

    assert review_rows[0]["shop_name"] == "Store A"
    assert review_rows[0]["filter_decision"] == "accepted"
```

- [ ] **Step 2: 运行单测确认失败**

Run: `python -m pytest tests/test_review.py::test_build_review_rows_merges_product_context_into_audit_rows -q`
Expected: FAIL，提示 `build_review_rows` 模块不存在

- [ ] **Step 3: 在 `ali_mvp/review.py` 实现 review row schema 和 join**

```python
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
    product_index = {row.get("product_url", ""): row for row in products if row.get("product_url")}
    result: list[dict[str, str]] = []
    for audit in audit_rows:
        merged = dict(audit)
        product = product_index.get(audit.get("product_url", ""), {})
        for field in PRODUCT_CONTEXT_FIELDS:
            merged[field] = str(product.get(field, ""))
        result.append(merged)
    return result
```

- [ ] **Step 4: 增加 listing_title rejected 无产品上下文时的回退测试**

```python
def test_build_review_rows_keeps_listing_prefilter_rejections_without_product_context():
    review_rows = build_review_rows([], [{
        "title": "Battery charger board",
        "product_url": "https://example.test/item/2",
        "filter_decision": "rejected",
        "filter_stage": "listing_title",
        "source_type": "keyword",
        "source_value": "home appliance accessories",
        "reject_groups": "electrical_power",
        "reject_terms": "battery",
        "reject_fields": "title",
        "warning_groups": "",
        "warning_terms": "",
        "warning_fields": "",
    }])

    assert review_rows[0]["title"] == "Battery charger board"
    assert review_rows[0]["image_url"] == ""
```

- [ ] **Step 5: 运行 review 测试确认通过**

Run: `python -m pytest tests/test_review.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add ali_mvp/review.py tests/test_review.py tests/fixtures/postprocess
git commit -m "feat(review): add review row join model

Why:
- html and zh outputs need one unified accepted/rejected review view

What:
- add review row builder that merges audit rows with product context
- preserve listing prefilter rejections without product context

Test:
- python -m pytest tests/test_review.py -q"
```

## Task 4: 实现属性摘要和翻译缓存接口

**Files:**
- Create: `ali_mvp/translation.py`
- Test: `tests/test_translation.py`

- [ ] **Step 1: 写失败测试，定义属性摘要与缓存回退行为**

```python
def test_summarize_attributes_returns_first_pairs_from_json():
    text = "{\"Color\":\"Blue\",\"Type\":\"Pad\",\"Material\":\"Rubber\"}"

    summary = summarize_attributes_text(text, limit=2)

    assert summary == "Color: Blue; Type: Pad"


def test_translate_texts_falls_back_to_source_when_backend_raises(tmp_path):
    cache_path = tmp_path / "translation_cache.json"

    rows = translate_texts(["Shock pad"], cache_path=cache_path, translator=lambda text: (_ for _ in ()).throw(RuntimeError("boom")))

    assert rows == {"Shock pad": "Shock pad"}
```

- [ ] **Step 2: 运行单测确认失败**

Run: `python -m pytest tests/test_translation.py -q`
Expected: FAIL，提示模块或函数不存在

- [ ] **Step 3: 在 `ali_mvp/translation.py` 实现摘要与缓存**

```python
from __future__ import annotations

import json
from pathlib import Path


def summarize_attributes_text(raw_text: str, limit: int = 3) -> str:
    try:
        parsed = json.loads(raw_text) if raw_text else {}
    except json.JSONDecodeError:
        return ""
    if not isinstance(parsed, dict):
        return ""
    parts = []
    for key, value in list(parsed.items())[:limit]:
        if str(key).strip() and str(value).strip():
            parts.append(f"{key}: {value}")
    return "; ".join(parts)


def translate_texts(texts: list[str], *, cache_path: Path, translator) -> dict[str, str]:
    cache = load_translation_cache(cache_path)
    result: dict[str, str] = {}
    for text in texts:
        if not text:
            result[text] = ""
            continue
        if text in cache:
            result[text] = cache[text]
            continue
        try:
            translated = translator(text)
        except Exception:
            translated = text
        cache[text] = translated or text
        result[text] = cache[text]
    save_translation_cache(cache_path, cache)
    return result
```

- [ ] **Step 4: 增加缓存命中测试**

```python
def test_translate_texts_reuses_cache_without_reinvoking_backend(tmp_path):
    cache_path = tmp_path / "translation_cache.json"
    calls = {"count": 0}

    def fake_translator(text: str) -> str:
        calls["count"] += 1
        return "减震垫"

    first = translate_texts(["Shock pad"], cache_path=cache_path, translator=fake_translator)
    second = translate_texts(["Shock pad"], cache_path=cache_path, translator=fake_translator)

    assert first["Shock pad"] == "减震垫"
    assert second["Shock pad"] == "减震垫"
    assert calls["count"] == 1
```

- [ ] **Step 5: 运行 translation 测试确认通过**

Run: `python -m pytest tests/test_translation.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add ali_mvp/translation.py tests/test_translation.py
git commit -m "feat(translation): add attribute summaries and cache-backed fallback translation

Why:
- zh postprocess needs stable text summaries and best-effort translation without breaking runs

What:
- add attribute summary helper
- add cache-backed text translation with source fallback

Test:
- python -m pytest tests/test_translation.py -q"
```

## Task 5: 实现中文 reason 与 review 中文增强

**Files:**
- Modify: `ali_mvp/review.py`
- Modify: `ali_mvp/translation.py`
- Test: `tests/test_review.py`
- Test: `tests/test_translation.py`

- [ ] **Step 1: 写失败测试，锁定 blacklist 中文 reason 映射**

```python
def test_build_reason_zh_prefers_rule_mapping_over_raw_translation():
    row = {
        "reject_terms": "battery | charger",
        "reject_groups": "electrical_power",
        "warning_terms": "",
        "filter_decision": "rejected",
    }

    assert build_reason_zh(row) == "带电供电类"
```

- [ ] **Step 2: 运行单测确认失败**

Run: `python -m pytest tests/test_translation.py::test_build_reason_zh_prefers_rule_mapping_over_raw_translation -q`
Expected: FAIL，提示 `build_reason_zh` 未定义

- [ ] **Step 3: 在 `ali_mvp/translation.py` 增加 reason 映射**

```python
REASON_ZH_RULES = (
    ({"battery", "lithium", "charger", "power adapter"}, "带电供电类"),
    ({"remote control", "controller", "pcb", "chip", "pcba"}, "电子控制或芯片类"),
    ({"sensor", "ignition", "timer switch", "relay module"}, "电子元件或控制器类"),
)


def build_reason_zh(row: dict[str, str]) -> str:
    haystack = " | ".join(
        part for part in (
            row.get("reject_terms", ""),
            row.get("warning_terms", ""),
            row.get("reject_groups", ""),
        ) if part
    ).lower()
    for terms, label in REASON_ZH_RULES:
        if any(term in haystack for term in terms):
            return label
    return "未命中中文规则说明"
```

- [ ] **Step 4: 在 `ali_mvp/review.py` 增加中文增强 helper**

```python
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
```

- [ ] **Step 5: 运行 review/translation 相关测试确认通过**

Run: `python -m pytest tests/test_review.py tests/test_translation.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add ali_mvp/review.py ali_mvp/translation.py tests/test_review.py tests/test_translation.py
git commit -m "feat(review): add zh review enrichment helpers

Why:
- review outputs need deterministic chinese reason fields and summary translations

What:
- add blacklist reason zh mapping
- add review row zh enrichment helper

Test:
- python -m pytest tests/test_review.py tests/test_translation.py -q"
```

## Task 6: 实现 HTML 报表渲染

**Files:**
- Create: `ali_mvp/reporting.py`
- Test: `tests/test_reporting.py`

- [ ] **Step 1: 写失败测试，锁定 summary 与 accepted/rejected 两块**

```python
def test_render_report_html_includes_summary_and_rejected_first():
    review_rows = [
        {"title": "Battery charger", "title_zh": "电池充电器", "filter_decision": "rejected", "reject_groups": "electrical_power", "price": "$3", "image_url": "", "shop_name": "", "shop_name_zh": "", "promotion_text": "", "promotion_text_zh": "", "attributes_summary": "", "attributes_summary_zh": "", "detail_status": "listing_title"},
        {"title": "Shock pad", "title_zh": "减震垫", "filter_decision": "accepted", "reject_groups": "", "price": "$1", "image_url": "", "shop_name": "", "shop_name_zh": "", "promotion_text": "", "promotion_text_zh": "", "attributes_summary": "", "attributes_summary_zh": "", "detail_status": ""},
    ]

    html = render_report_html(review_rows, source_label="home appliance accessories")

    assert "Rejected" in html
    assert "Accepted" in html
    assert html.index("Battery charger") < html.index("Shock pad")
    assert "total" in html.lower()
```

- [ ] **Step 2: 运行单测确认失败**

Run: `python -m pytest tests/test_reporting.py::test_render_report_html_includes_summary_and_rejected_first -q`
Expected: FAIL，提示模块或函数不存在

- [ ] **Step 3: 在 `ali_mvp/reporting.py` 实现 HTML 渲染**

```python
from __future__ import annotations

from collections import Counter
from html import escape


def render_report_html(review_rows: list[dict[str, str]], *, source_label: str) -> str:
    rejected = [row for row in review_rows if row.get("filter_decision") == "rejected"]
    accepted = [row for row in review_rows if row.get("filter_decision") != "rejected"]
    reject_groups = Counter()
    for row in rejected:
        for group in row.get("reject_groups", "").split(" | "):
            if group:
                reject_groups[group] += 1
    return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{escape(source_label)} report</title></head>
<body>
  <h1>{escape(source_label)}</h1>
  <section id="summary">
    <p>Total: {len(review_rows)}</p>
    <p>Rejected: {len(rejected)}</p>
    <p>Accepted: {len(accepted)}</p>
  </section>
  <section id="rejected">{''.join(_render_card(row) for row in rejected)}</section>
  <section id="accepted">{''.join(_render_card(row) for row in accepted)}</section>
</body>
</html>"""
```

- [ ] **Step 4: 增加空 accepted / 全 rejected 场景测试**

```python
def test_render_report_html_handles_all_rejected_rows():
    html = render_report_html([{"title": "Battery charger", "title_zh": "电池充电器", "filter_decision": "rejected", "reject_groups": "electrical_power", "price": "$3", "image_url": "", "shop_name": "", "shop_name_zh": "", "promotion_text": "", "promotion_text_zh": "", "attributes_summary": "", "attributes_summary_zh": "", "detail_status": "listing_title"}], source_label="run")

    assert "Rejected: 1" in html
    assert "Accepted: 0" in html
```

- [ ] **Step 5: 运行 reporting 测试确认通过**

Run: `python -m pytest tests/test_reporting.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add ali_mvp/reporting.py tests/test_reporting.py
git commit -m "feat(reporting): render review html report

Why:
- staff need a visual accepted/rejected review page for blacklist auditing

What:
- add html report renderer with summary and rejected-first layout

Test:
- python -m pytest tests/test_reporting.py -q"
```

## Task 7: 实现 postprocess 编排并接入 CLI

**Files:**
- Create: `ali_mvp/postprocess.py`
- Modify: `ali_mvp/cli.py`
- Modify: `ali_mvp/output.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_output.py`

- [ ] **Step 1: 写失败测试，锁定 `run_postprocess()` 产物**

```python
def test_run_postprocess_writes_review_zh_and_html(monkeypatch, tmp_path):
    from ali_mvp import cli

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "products.csv").write_text("source_type,source_value,title,price,sold_count,rating,review_count,product_url,search_card_url,image_url,entry_type,is_promoted,promo_channel,promotion_text,promo_landing_url,shop_name,shipping_text,detail_rating,detail_review_count,breadcrumb,attributes_text,description_text,detail_status,scraped_at\nkeyword,home appliance accessories,Shock pad,$1,0,0,0,https://example.test/item/1,https://example.test/card/1,https://example.test/img.jpg,item_card,False,,, ,Store A,Free shipping,0,0,,\"{\"\"Type\"\":\"\"Pad\"\"}\",Accessory,,2026-05-11T00:00:00Z\n", encoding="utf-8-sig")
    (run_dir / "products_filter_audit.csv").write_text("source_type,source_value,title,product_url,filter_decision,filter_stage,reject_groups,reject_terms,reject_fields,warning_groups,warning_terms,warning_fields\nkeyword,home appliance accessories,Shock pad,https://example.test/item/1,accepted,accepted,,,,,,\n", encoding="utf-8-sig")

    args = argparse.Namespace(run_dir=str(run_dir))

    code = cli.run_postprocess(args)

    assert code == 0
    assert (run_dir / "products_review.csv").exists()
    assert (run_dir / "products_zh.csv").exists()
    assert (run_dir / "products_filter_audit_zh.csv").exists()
    assert (run_dir / "products_report.html").exists()
```

- [ ] **Step 2: 运行单测确认失败**

Run: `python -m pytest tests/test_cli.py::test_run_postprocess_writes_review_zh_and_html -q`
Expected: FAIL，提示 `run_postprocess` 未定义

- [ ] **Step 3: 在 `ali_mvp/postprocess.py` 实现编排函数**

```python
from __future__ import annotations

from pathlib import Path

from .output import FILTER_AUDIT_FIELDS, PRODUCT_FIELDS, REVIEW_FIELDS, read_csv_rows, write_dict_csv
from .reporting import render_report_html
from .review import build_review_rows, enrich_review_rows_with_zh
from .translation import build_reason_zh, summarize_attributes_text, translate_texts


def run_postprocess_for_dir(run_dir: Path, *, translator) -> None:
    products = read_csv_rows(run_dir / "products.csv")
    audit_rows = read_csv_rows(run_dir / "products_filter_audit.csv")
    review_rows = build_review_rows(products, audit_rows)
    write_dict_csv(run_dir / "products_review.csv", REVIEW_FIELDS, review_rows)

    texts = _collect_translation_texts(review_rows)
    cache_path = run_dir / "translation_cache.json"
    translations = translate_texts(texts, cache_path=cache_path, translator=translator)
    review_rows_zh = enrich_review_rows_with_zh(
        review_rows,
        translations=translations,
        reason_builder=build_reason_zh,
        attributes_summary_builder=summarize_attributes_text,
    )

    write_dict_csv(run_dir / "products_zh.csv", PRODUCT_FIELDS + ["title_zh", "shop_name_zh", "promotion_text_zh", "attributes_summary", "attributes_summary_zh"], _build_products_zh_rows(products, review_rows_zh))
    write_dict_csv(run_dir / "products_filter_audit_zh.csv", FILTER_AUDIT_FIELDS + ["filter_decision_zh", "filter_stage_zh", "reject_groups_zh", "reject_terms_zh", "warning_groups_zh", "warning_terms_zh", "reason_zh"], _build_audit_zh_rows(audit_rows, review_rows_zh))
    (run_dir / "products_report.html").write_text(render_report_html(review_rows_zh, source_label=_source_label(review_rows_zh)), encoding="utf-8")
```

- [ ] **Step 4: 在 `ali_mvp/cli.py` 中接入 `run_postprocess()`**

```python
def run_postprocess(args: argparse.Namespace) -> int:
    from .postprocess import run_postprocess_for_dir

    run_postprocess_for_dir(Path(args.run_dir), translator=lambda text: text)
    print(f"Wrote: {Path(args.run_dir) / 'products_review.csv'}")
    print(f"Wrote: {Path(args.run_dir) / 'products_zh.csv'}")
    print(f"Wrote: {Path(args.run_dir) / 'products_filter_audit_zh.csv'}")
    print(f"Wrote: {Path(args.run_dir) / 'products_report.html'}")
    return 0
```

- [ ] **Step 5: 在 `run_scrape()` 写完原始 CSV 后写 `products_review.csv`**

```python
review_rows = build_review_rows(
    [asdict(product) for product in accepted_products],
    audit_rows,
)
write_dict_csv(output_dir / "products_review.csv", REVIEW_FIELDS, review_rows)
```

- [ ] **Step 6: 运行 CLI/output 相关测试确认通过**

Run: `python -m pytest tests/test_cli.py tests/test_output.py tests/test_review.py tests/test_translation.py tests/test_reporting.py -q`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add ali_mvp/postprocess.py ali_mvp/cli.py ali_mvp/output.py tests/test_cli.py tests/test_output.py tests/test_review.py tests/test_translation.py tests/test_reporting.py
git commit -m "feat(postprocess): generate review, zh csv, and html outputs

Why:
- complete the approved postprocess flow without changing scrape’s raw output contract

What:
- add run-dir postprocess orchestration
- generate review csv, zh csv outputs, and html report
- emit review csv from scrape runs

Test:
- python -m pytest tests/test_cli.py tests/test_output.py tests/test_review.py tests/test_translation.py tests/test_reporting.py -q"
```

## Task 8: 实现 browser hardening 参数透传与 pacing helper

**Files:**
- Modify: `ali_mvp/browser.py`
- Modify: `ali_mvp/cli.py`
- Test: `tests/test_browser.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 写失败测试，锁定 hardening 参数透传**

```python
def test_run_scrape_passes_browser_hardening_to_collectors(monkeypatch, tmp_path):
    from ali_mvp import cli

    args = argparse.Namespace(
        keyword="women dress",
        url=None,
        category_url=None,
        max_items=1,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        pages=1,
        blacklist_file=None,
        reject_keyword=[],
        browser_hardening="minimal",
    )
    seen = {}

    monkeypatch.setattr(cli, "load_filter_groups", lambda path, keywords: [])
    monkeypatch.setattr(cli, "collect_raw_products", lambda *a, **k: seen.setdefault("hardening", k.get("browser_hardening")) or [])
    monkeypatch.setattr(cli, "normalize_products", lambda *a, **k: [])
    monkeypatch.setattr(cli, "filter_products", lambda products, groups: ([], []))
    monkeypatch.setattr(cli, "write_products_csv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "write_filter_audit_csv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "write_rank_csv", lambda *a, **k: None)

    cli.run_scrape(args)

    assert seen["hardening"] == "minimal"
```

- [ ] **Step 2: 运行单测确认失败**

Run: `python -m pytest tests/test_cli.py::test_run_scrape_passes_browser_hardening_to_collectors -q`
Expected: FAIL，提示 `browser_hardening` 未透传

- [ ] **Step 3: 在 `ali_mvp/browser.py` 增加 hardening 参数与 jitter helper**

```python
import random


def _sleep_jitter(min_s: float, max_s: float) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _human_scroll_step(page: ChromiumPage) -> None:
    distance = random.randint(700, 1100)
    page.run_js(f"window.scrollBy(0, {distance});")


def _pause_after_navigation() -> None:
    _sleep_jitter(0.8, 1.6)
```

- [ ] **Step 4: 把固定 sleep 改为 helper，并加最小 stealth 初始化 hook**

```python
def open_listing_page(
    url: str,
    *,
    user_data_dir: str | None = None,
    port: int | None = None,
    browser_hardening: str = "minimal",
) -> ChromiumPage:
    page = ChromiumPage(_build_options(user_data_dir=user_data_dir, port=port, browser_hardening=browser_hardening))
    page.get(url)
    if browser_hardening == "minimal":
        _init_page_stealth(page)
    _pause_after_navigation()
    return page
```

- [ ] **Step 5: 写并通过 browser 测试**

Run: `python -m pytest tests/test_browser.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add ali_mvp/browser.py ali_mvp/cli.py tests/test_browser.py tests/test_cli.py
git commit -m "fix(browser): add minimal pacing and hardening hooks

Why:
- reduce fixed automation rhythm without changing scrape behavior

What:
- add browser hardening parameter plumbing
- replace fixed sleeps with bounded jitter helpers
- add minimal page stealth initialization hook

Test:
- python -m pytest tests/test_browser.py tests/test_cli.py -q"
```

## Task 9: 文档化并做全量回归

**Files:**
- Modify: `README.md`
- Test: `tests/test_cli.py`
- Test: `tests/test_browser.py`
- Test: `tests/test_output.py`
- Test: `tests/test_review.py`
- Test: `tests/test_translation.py`
- Test: `tests/test_reporting.py`

- [ ] **Step 1: 更新 README 用法**

```markdown
Postprocess outputs:

```bash
python -m ali_mvp postprocess --run-dir data/home-appliance-accessories/20260511_120000
```

Additional outputs:

- `products_review.csv`
- `products_zh.csv`
- `products_filter_audit_zh.csv`
- `products_report.html`

Browser hardening:

- `--browser-hardening off|minimal`
- default: `minimal`
```

- [ ] **Step 2: 运行全量测试**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 3: 做一次代表性本地回归**

Run: `python -m ali_mvp scrape --keyword "Home appliance accessories" --max-items 5 --pages 1 --blacklist-file rules/product_blacklist.json`
Expected: 生成：
- `products.csv`
- `products_filter_audit.csv`
- `products_review.csv`
- `category_rank.csv`

- [ ] **Step 4: 对该 run 执行 postprocess**

Run: `python -m ali_mvp postprocess --run-dir data/home-appliance-accessories/<timestamp>`
Expected: 生成：
- `products_zh.csv`
- `products_filter_audit_zh.csv`
- `products_report.html`
- `translation_cache.json`

- [ ] **Step 5: 提交**

```bash
git add README.md
git commit -m "docs(readme): document zh postprocess and browser hardening

Why:
- make the new workflow and outputs discoverable

What:
- document postprocess usage, review outputs, and browser hardening flag

Test:
- python -m pytest -q
- python -m ali_mvp scrape --keyword \"Home appliance accessories\" --max-items 5 --pages 1 --blacklist-file rules/product_blacklist.json
- python -m ali_mvp postprocess --run-dir data/home-appliance-accessories/<timestamp>"
```

## Self-Review

### Spec coverage

- `postprocess` 子命令：Task 1, Task 7
- `products_review.csv`：Task 2, Task 3, Task 7
- `products_zh.csv` / `products_filter_audit_zh.csv`：Task 4, Task 5, Task 7
- `products_report.html`：Task 6, Task 7
- 翻译缓存与失败回退：Task 4
- 黑名单中文 reason 映射：Task 5
- `--browser-hardening off|minimal`：Task 1, Task 8
- pacing / stealth 最小加固：Task 8
- README 与回归验证：Task 9

无明显 spec 漏项。

### Placeholder scan

已检查本计划，无 `TODO`、`TBD`、`implement later`、`similar to task N` 等占位语句。

### Type consistency

- CLI 子命令：`run_postprocess`
- review 组装：`build_review_rows`
- 中文增强：`enrich_review_rows_with_zh`
- 翻译：`translate_texts`
- 属性摘要：`summarize_attributes_text`
- HTML 渲染：`render_report_html`

命名在各任务之间保持一致。
