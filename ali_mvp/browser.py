from __future__ import annotations

import time
from pathlib import Path

from DrissionPage import ChromiumOptions, ChromiumPage


PRODUCT_SCRIPT = r"""
return (() => {
  function isPriceLine(line) {
    return /[$€£¥]|US\s*\$|\d+[,.]\d{2}/i.test(line);
  }

  function isSoldLine(line) {
    return /sold|orders|已售|售出/i.test(line);
  }

  function findRatingLine(lines) {
    const soldIndex = lines.findIndex(line => isSoldLine(line));
    const end = soldIndex >= 0 ? soldIndex : lines.length;
    const candidates = lines.slice(0, end).filter((line) => {
      if (isPriceLine(line) || /%|off|save|shipping|interest/i.test(line)) return false;
      return /^[1-5](?:\.\d)?$/.test(line);
    });
    return candidates.length ? candidates[candidates.length - 1] : '';
  }

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
    const priceLine = lines.find(line => isPriceLine(line)) || '';
    const soldLine = lines.find(line => isSoldLine(line)) || '';
    const reviewLine = lines.find(line => /reviews?|评价/i.test(line)) || '';
    const title = (img && (img.alt || img.title)) || lines.find(line => line.length > 12) || link.textContent || '';
    results.push({
      title,
      price: priceLine,
      soldText: soldLine,
      ratingText: findRatingLine(lines),
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
    enrich_detail_rating: bool = False,
    detail_limit: int = 5,
) -> list[dict[str, object]]:
    page = ChromiumPage(_build_options(user_data_dir=user_data_dir, port=port))
    page.get(url)
    time.sleep(3)
    for _ in range(scroll_rounds):
        page.run_js("window.scrollBy(0, Math.max(900, window.innerHeight || 900));")
        time.sleep(1)
        raw = page.run_js(PRODUCT_SCRIPT)
        if isinstance(raw, list) and len(raw) >= max_items:
            return _finalize_products(
                page,
                raw,
                max_items=max_items,
                enrich_detail_rating=enrich_detail_rating,
                detail_limit=detail_limit,
            )
    raw = page.run_js(PRODUCT_SCRIPT)
    if not isinstance(raw, list):
        return []
    return _finalize_products(
        page,
        raw,
        max_items=max_items,
        enrich_detail_rating=enrich_detail_rating,
        detail_limit=detail_limit,
    )


def _finalize_products(
    page: ChromiumPage,
    raw: list[dict[str, object]],
    *,
    max_items: int,
    enrich_detail_rating: bool,
    detail_limit: int,
) -> list[dict[str, object]]:
    products = raw[:max_items]
    if enrich_detail_rating:
        _enrich_detail_ratings(page, products, detail_limit)
    return products


DETAIL_RATING_SCRIPT = r"""
return (() => {
  const text = document.body ? document.body.innerText : '';
  const match = text.match(/\b([1-5](?:\.\d)?)\s*(?:stars?|out of 5|rating|评价|评星)\b/i);
  if (match) return match[1];
  const ratingNode = document.querySelector('[class*="rating"], [class*="star"], [aria-label*="star"], [aria-label*="rating"]');
  return ratingNode ? (ratingNode.innerText || ratingNode.getAttribute('aria-label') || '') : '';
})()
"""


def _enrich_detail_ratings(page: ChromiumPage, products: list[dict[str, object]], detail_limit: int) -> None:
    enriched = 0
    listing_url = page.url
    for product in products:
        if enriched >= detail_limit:
            break
        if product.get("ratingText"):
            continue
        url = str(product.get("url") or "")
        if not url:
            continue
        try:
            page.get(url)
            time.sleep(2)
            rating = page.run_js(DETAIL_RATING_SCRIPT)
        except Exception:
            rating = ""
        if rating:
            product["ratingText"] = rating
        enriched += 1
    if listing_url:
        page.get(listing_url)


def _build_options(user_data_dir: str | None, port: int | None) -> ChromiumOptions:
    options = ChromiumOptions()
    if port is not None:
        options.set_local_port(port)
    if user_data_dir:
        options.set_user_data_path(str(Path(user_data_dir).resolve()))
    return options
