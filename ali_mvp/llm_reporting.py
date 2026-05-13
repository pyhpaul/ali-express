from __future__ import annotations

from html import escape

from .llm_review import classify_llm_row


def render_llm_report_html(
    review_rows: list[dict[str, str]],
    *,
    source_label: str,
    model_label: str,
    prompt_version: str,
) -> str:
    keep_rows = [row for row in review_rows if classify_llm_row(row) == "keep"]
    drop_rows = [row for row in review_rows if classify_llm_row(row) == "drop"]
    error_rows = [row for row in review_rows if classify_llm_row(row) == "error"]

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{escape(source_label)} llm report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
    h1, h2 {{ margin-bottom: 12px; }}
    .summary p {{ margin: 6px 0; }}
    section {{ margin-top: 24px; }}
    .cards {{ display: grid; gap: 12px; }}
    .card {{ border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; background: #fff; }}
    .keep .card {{ border-color: #16a34a; background: #f0fdf4; }}
    .drop .card {{ border-color: #dc2626; background: #fef2f2; }}
    .error .card {{ border-color: #d97706; background: #fffbeb; }}
    p {{ margin: 4px 0; word-break: break-word; }}
    .label {{ font-weight: 600; }}
  </style>
</head>
<body>
  <h1>{escape(source_label)}</h1>
  <section id="summary" class="summary">
    <h2>Summary</h2>
    <p>Keep: {len(keep_rows)}</p>
    <p>Drop: {len(drop_rows)}</p>
    <p>Error: {len(error_rows)}</p>
    <p>Model: {escape(model_label)}</p>
    <p>Prompt: {escape(prompt_version)}</p>
  </section>
  <section id="llm-keep">
    <h2>LLM Keep</h2>
    <div class="cards keep">{''.join(_render_card(row, include_error=False) for row in keep_rows)}</div>
  </section>
  <section id="llm-drop">
    <h2>LLM Drop</h2>
    <div class="cards drop">{''.join(_render_card(row, include_error=False) for row in drop_rows)}</div>
  </section>
  <section id="llm-error">
    <h2>LLM Error</h2>
    <div class="cards error">{''.join(_render_card(row, include_error=True) for row in error_rows)}</div>
  </section>
</body>
</html>"""


def _render_card(row: dict[str, str], *, include_error: bool) -> str:
    parts = [
        '<article class="card">',
        _field("title", row.get("title", "")),
        _field("llm_summary_zh", row.get("llm_summary_zh", "")),
        _field("llm_risk_tags", row.get("llm_risk_tags", "")),
        _field("filter_decision", row.get("filter_decision", "")),
        _field("price", row.get("price", "")),
        _field("product_url", row.get("product_url", "")),
        _field("image_url", row.get("image_url", "")),
        _field("detail_status", row.get("detail_status", "")),
    ]
    if include_error:
        parts.append(_field("llm_error", row.get("llm_error", "")))
    parts.append("</article>")
    return "".join(parts)


def _field(label: str, value: str) -> str:
    return f'<p><span class="label">{escape(label)}:</span> {escape(value)}</p>'
