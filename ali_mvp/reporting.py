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
<head>
  <meta charset="utf-8">
  <title>{escape(source_label)} report</title>
</head>
<body>
  <h1>{escape(source_label)}</h1>
  <section id="summary">
    <h2>Summary</h2>
    <p>Total: {len(review_rows)}</p>
    <p>Rejected: {len(rejected)}</p>
    <p>Accepted: {len(accepted)}</p>
    {_render_reject_group_summary(reject_groups)}
  </section>
  <section id="rejected">
    <h2>Rejected</h2>
    {''.join(_render_card(row) for row in rejected)}
  </section>
  <section id="accepted">
    <h2>Accepted</h2>
    {''.join(_render_card(row) for row in accepted)}
  </section>
</body>
</html>"""


def _render_reject_group_summary(reject_groups: Counter[str]) -> str:
    if not reject_groups:
        return ""

    items = "".join(
        f"<li>{escape(group)}: {count}</li>" for group, count in reject_groups.most_common()
    )
    return f"<ul id=\"reject-groups\">{items}</ul>"


def _render_card(row: dict[str, str]) -> str:
    title = escape(row.get("title", ""))
    title_zh = escape(row.get("title_zh", ""))
    price = escape(row.get("price", ""))
    decision = escape(row.get("filter_decision", ""))
    detail_status = escape(row.get("detail_status", ""))

    parts = [
        f"<article class=\"card {decision}\">",
        f"<h3>{title}</h3>",
    ]
    if title_zh:
        parts.append(f"<p class=\"title-zh\">{title_zh}</p>")
    if price:
        parts.append(f"<p class=\"price\">{price}</p>")
    if detail_status:
        parts.append(f"<p class=\"detail-status\">{detail_status}</p>")
    parts.append(f"<p class=\"decision\">{decision}</p>")
    parts.append("</article>")
    return "".join(parts)
