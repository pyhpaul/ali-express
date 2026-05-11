from __future__ import annotations

from collections import Counter
from html import escape


FILTER_DECISION_ZH = {
    "accepted": "建议入库",
    "rejected": "拒绝入库",
}

FILTER_STAGE_ZH = {
    "accepted": "已通过",
    "listing_title": "标题命中",
    "detail_post_enrich": "详情补充后命中",
}


def render_report_html(
    review_rows: list[dict[str, str]],
    *,
    source_label: str,
    translation_provider: str = "default",
) -> str:
    rejected = [row for row in review_rows if row.get("filter_decision") == "rejected"]
    accepted = [row for row in review_rows if row.get("filter_decision") != "rejected"]
    reject_reasons = Counter(_reason_label(row) for row in rejected if _reason_label(row))
    reason_options = _collect_reason_options(review_rows)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{escape(source_label)} report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
    h1, h2 {{ margin-bottom: 12px; }}
    .meta, .summary-grid {{ margin-bottom: 16px; }}
    .summary-grid p {{ margin: 6px 0; }}
    .card {{ border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; margin: 12px 0; }}
    .card.rejected {{ border-color: #dc2626; background: #fef2f2; }}
    .card.accepted {{ border-color: #16a34a; background: #f0fdf4; }}
    .title-zh {{ color: #374151; font-weight: 600; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; }}
    .badge.rejected {{ background: #fee2e2; color: #991b1b; }}
    .badge.accepted {{ background: #dcfce7; color: #166534; }}
    .muted {{ color: #6b7280; }}
    .filters {{ display: flex; gap: 16px; margin: 16px 0; flex-wrap: wrap; }}
    .filters label {{ font-weight: 600; }}
  </style>
</head>
<body>
  <h1>{escape(source_label)}</h1>
  <section id="summary">
    <h2>Summary</h2>
    <div class="meta">
      <p>翻译来源: {escape(translation_provider)}</p>
    </div>
    <div class="summary-grid">
      <p>Total: {len(review_rows)}</p>
      <p>Rejected: {len(rejected)}</p>
      <p>Accepted: {len(accepted)}</p>
    </div>
    {_render_reject_reason_summary(reject_reasons)}
    {_render_filters(reason_options)}
  </section>
  <section id="rejected">
    <h2>拒绝入库</h2>
    {''.join(_render_card(row) for row in rejected)}
  </section>
  <section id="accepted">
    <h2>建议入库</h2>
    {''.join(_render_card(row) for row in accepted)}
  </section>
  <script>
    function applyFilters() {{
      const decision = document.getElementById('decision-filter').value;
      const reason = document.getElementById('reason-filter').value;
      const cards = document.querySelectorAll('article.card');
      for (const card of cards) {{
        const cardDecision = card.dataset.decision || '';
        const cardReason = card.dataset.reason || '';
        const decisionMatch = decision === 'all' || cardDecision === decision;
        const reasonMatch = reason === 'all' || cardReason === reason;
        card.style.display = decisionMatch && reasonMatch ? '' : 'none';
      }}
    }}
  </script>
</body>
</html>"""


def _render_reject_reason_summary(reject_reasons: Counter[str]) -> str:
    if not reject_reasons:
        return ""

    items = "".join(
        f"<li>{escape(reason)}: {count}</li>" for reason, count in reject_reasons.most_common()
    )
    return f"<ul id=\"reject-reasons\">{items}</ul>"


def _render_card(row: dict[str, str]) -> str:
    decision = row.get("filter_decision", "")
    decision_zh = row.get("filter_decision_zh", FILTER_DECISION_ZH.get(decision, decision))
    filter_stage = row.get("filter_stage", "")
    filter_stage_zh = row.get("filter_stage_zh", FILTER_STAGE_ZH.get(filter_stage, filter_stage))
    reason_zh = row.get("reason_zh", "")
    card_reason = _card_reason_value(row)

    parts = [
        (
            f"<article class=\"card {escape(decision)}\" "
            f"data-decision=\"{escape(decision)}\" "
            f"data-reason=\"{escape(card_reason)}\">"
        ),
        f"<p><span class=\"badge {escape(decision)}\">{escape(decision_zh)}</span></p>",
        f"<h3>{escape(row.get('title', ''))}</h3>",
    ]

    title_zh = row.get("title_zh", "")
    if title_zh:
        parts.append(f"<p class=\"title-zh\">{escape(title_zh)}</p>")

    if row.get("price", ""):
        parts.append(f"<p class=\"price\">价格: {escape(row.get('price', ''))}</p>")
    if filter_stage_zh:
        parts.append(f"<p class=\"stage\">命中阶段: {escape(filter_stage_zh)}</p>")
    if decision == "rejected" and reason_zh:
        parts.append(f"<p class=\"reason\">拒绝原因: {escape(reason_zh)}</p>")
    elif decision != "rejected":
        parts.append("<p class=\"reason\">判定说明: 可入库候选</p>")

    detail_status = row.get("detail_status", "")
    if detail_status:
        parts.append(f"<p class=\"detail-status muted\">detail_status: {escape(detail_status)}</p>")

    parts.append("</article>")
    return "".join(parts)


def _reason_label(row: dict[str, str]) -> str:
    reason_zh = str(row.get("reason_zh", "")).strip()
    if reason_zh:
        return reason_zh
    reject_groups = str(row.get("reject_groups_zh", "") or row.get("reject_groups", "")).strip()
    if reject_groups:
        return reject_groups.split(" | ")[0].strip()
    return ""


def _card_reason_value(row: dict[str, str]) -> str:
    if row.get("filter_decision") == "rejected":
        return _reason_label(row)
    return ""


def _collect_reason_options(review_rows: list[dict[str, str]]) -> list[str]:
    seen: set[str] = set()
    options: list[str] = []
    for row in review_rows:
        reason = _card_reason_value(row)
        if not reason or reason in seen:
            continue
        seen.add(reason)
        options.append(reason)
    return sorted(options)


def _render_filters(reason_options: list[str]) -> str:
    reason_items = ['<option value="all">全部</option>']
    for reason in reason_options:
        reason_items.append(f'<option value="{escape(reason)}">{escape(reason)}</option>')
    return (
        '<div class="filters">'
        '<label>入库判定 '
        '<select id="decision-filter" onchange="applyFilters()">'
        '<option value="all">全部</option>'
        '<option value="rejected">只看拒绝入库</option>'
        '<option value="accepted">只看建议入库</option>'
        "</select>"
        "</label>"
        '<label>拒绝原因 '
        f'<select id="reason-filter" onchange="applyFilters()">{"".join(reason_items)}</select>'
        "</label>"
        "</div>"
    )
