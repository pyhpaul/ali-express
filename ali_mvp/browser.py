from __future__ import annotations

import time
from pathlib import Path

from DrissionPage import ChromiumOptions, ChromiumPage


PRODUCT_SCRIPT = r"""
(() => {
  const cards = Array.from(document.querySelectorAll('a[href*="/item/"], a[href*="item/"]'));
  const results = [];
  const seen = new Set();
  for (const link of cards) {
    const url = link.href || link.getAttribute('href') || '';
    if (!url || seen.has(url)) continue;
    seen.add(url);
    const card = link.closest('[class*="product"], [class*="item"], [data-product-id], li, div') || link;
    const text = (card.innerText || link.innerText || '').trim();
    const lines = text.split('\n').map(line => line.trim()).filter(Boolean);
    const img = card.querySelector('img') || link.querySelector('img');
    const priceLine = lines.find(line => /[$€£¥]|US\s*\$|\d+[,.]\d{2}/i.test(line)) || '';
    const soldLine = lines.find(line => /sold|orders|已售|售出/i.test(line)) || '';
    const ratingLine = lines.find(line => /\b[1-5](?:\.\d)?\b/.test(line) && /star|rating|reviews?|评价|评星/i.test(line)) || '';
    const reviewLine = lines.find(line => /reviews?|评价/i.test(line)) || '';
    const title = (img && (img.alt || img.title)) || lines.find(line => line.length > 12) || link.textContent || '';
    results.push({
      title,
      price: priceLine,
      soldText: soldLine,
      ratingText: ratingLine,
      reviewText: reviewLine,
      url,
      image: img ? (img.src || img.getAttribute('data-src') || '') : ''
    });
  }
  return results;
})()
"""


def collect_raw_products(
    url: str,
    max_items: int,
    scroll_rounds: int = 8,
    user_data_dir: str | None = None,
    port: int | None = None,
) -> list[dict[str, object]]:
    page = ChromiumPage(_build_options(user_data_dir=user_data_dir, port=port))
    page.get(url)
    time.sleep(3)
    for _ in range(scroll_rounds):
        page.run_js("window.scrollBy(0, Math.max(900, window.innerHeight || 900));")
        time.sleep(1)
        raw = page.run_js(PRODUCT_SCRIPT)
        if isinstance(raw, list) and len(raw) >= max_items:
            return raw[:max_items]
    raw = page.run_js(PRODUCT_SCRIPT)
    if not isinstance(raw, list):
        return []
    return raw[:max_items]


def _build_options(user_data_dir: str | None, port: int | None) -> ChromiumOptions:
    options = ChromiumOptions()
    if port is not None:
        options.set_local_port(port)
    if user_data_dir:
        options.set_user_data_path(str(Path(user_data_dir).resolve()))
    return options
