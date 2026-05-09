from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from DrissionPage import ChromiumOptions, ChromiumPage


PRODUCT_SCRIPT = r"""
return (() => {
  function isPromoHref(href) {
    return /\/ssr\/.*BundleDeals2/i.test(String(href || ''));
  }

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

  const cards = Array.from(document.querySelectorAll('a[href*="/item/"], a[href*="item/"], a[href*="BundleDeals2"]'));
  const results = [];
  const seen = new Set();
  for (const link of cards) {
    const url = link.href || link.getAttribute('href') || '';
    if (!url || seen.has(url)) continue;
    if (!url.includes('/item/') && !isPromoHref(url)) continue;
    seen.add(url);
    const card = link.closest('[class*="product"], [class*="item"], [data-product-id], li, div, section') || link;
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
      cardUrl: url,
      entryType: isPromoHref(url) ? 'promo_card' : 'item_card',
      resolvedProductUrl: '',
      image: img ? (img.src || img.getAttribute('data-src') || '') : ''
    });
  }
  return results;
})()
"""

NEXT_PAGE_SCRIPT = r"""
return (() => {
  const targetPage = __TARGET_PAGE__;

  function isVisible(el) {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function classText(el) {
    return String(el && el.className || '');
  }

  function elementText(el) {
    return String((el && (el.innerText || el.textContent)) || '');
  }

  function setInputValue(input, value) {
    const ownSetter = Object.getOwnPropertyDescriptor(input, 'value')?.set;
    const prototypeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    if (prototypeSetter && ownSetter !== prototypeSetter) {
      prototypeSetter.call(input, value);
    } else {
      input.value = value;
    }
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
  }

  function findQuickJumperInput() {
    const explicit = document.querySelector('input[aria-label="Page"]');
    if (explicit) return explicit;
    const inputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type])'));
    return inputs.find((input) => {
      const scope = input.closest('[class*="pagination"]') || input.parentElement;
      const text = elementText(scope);
      return scope && /pagination/i.test(classText(scope)) && /go to page|confirm|\/\s*\d+/i.test(text);
    });
  }

  function findConfirmButton(input) {
    const scope = input.closest('[class*="pagination"]') || input.parentElement || document;
    const buttons = Array.from(scope.querySelectorAll('button'));
    return buttons.find((button) => {
      if (button.disabled || button.getAttribute('aria-disabled') === 'true') return false;
      return /confirm|确定|go/i.test(elementText(button).trim());
    });
  }

  function jumpToTargetPage() {
    const input = findQuickJumperInput();
    if (!input || !isVisible(input)) return '';
    input.scrollIntoView({block: 'center'});
    input.focus();
    setInputValue(input, String(targetPage));
    const confirm = findConfirmButton(input);
    if (confirm && isVisible(confirm)) {
      confirm.click();
      return 'quick-jumper';
    }
    input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', bubbles: true}));
    input.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', code: 'Enter', bubbles: true}));
    return 'quick-jumper-enter';
  }

  function clickPaginationNext() {
    const nextContainers = Array.from(document.querySelectorAll('li, button, a, div'))
      .filter(el => classText(el).includes('comet-pagination-next') || classText(el).includes('pagination-next'));
    for (const container of nextContainers) {
      if (container.getAttribute('aria-disabled') === 'true') continue;
      const clickable = container.matches('button,a') ? container : container.querySelector('button,a') || container;
      if (!clickable || !isVisible(clickable)) continue;
      clickable.scrollIntoView({block: 'center'});
      clickable.click();
      return 'next-button';
    }
    return '';
  }

  return jumpToTargetPage() || clickPaginationNext() || '';
})()
"""

PAGINATION_READY_SCRIPT = r"""
return (() => {
  function isVisible(el) {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }
  const quickJumper = document.querySelector('input[aria-label="Page"]');
  if (quickJumper && isVisible(quickJumper)) return true;
  return Array.from(document.querySelectorAll('li, button, a, div'))
    .some(el => String(el.className || '').includes('pagination-next') && isVisible(el));
})()
"""


def collect_raw_products(
    url: str,
    max_items: int,
    scroll_rounds: int = 8,
    user_data_dir: str | None = None,
    port: int | None = None,
    enrich_detail: bool = False,
    pages: int | None = None,
) -> list[dict[str, object]]:
    page = open_listing_page(url, user_data_dir=user_data_dir, port=port)
    all_products: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    current_page = 1

    while True:
        current_products = collect_listing_page_products(page, scroll_rounds=scroll_rounds)
        all_products.extend(dedupe_listing_products(current_products, seen_urls))
        if len(all_products) >= max_items:
            break
        if pages is not None and current_page >= pages:
            break
        next_page = current_page + 1
        if not advance_listing_page(page, next_page):
            break
        current_page = next_page

    return _finalize_products(
        page,
        all_products,
        max_items=max_items,
        enrich_detail=enrich_detail,
    )


def open_listing_page(
    url: str,
    *,
    user_data_dir: str | None = None,
    port: int | None = None,
) -> ChromiumPage:
    page = ChromiumPage(_build_options(user_data_dir=user_data_dir, port=port))
    page.get(url)
    time.sleep(3)
    return page


def collect_listing_page_products(page: ChromiumPage, *, scroll_rounds: int = 8) -> list[dict[str, object]]:
    return _collect_current_page(page, scroll_rounds=scroll_rounds)


def dedupe_listing_products(
    products: list[dict[str, object]],
    seen_keys: set[str],
) -> list[dict[str, object]]:
    unique: list[dict[str, object]] = []
    for product in products:
        product_key = _product_key(product)
        if product_key and product_key not in seen_keys:
            seen_keys.add(product_key)
            unique.append(product)
    return unique


def advance_listing_page(page: ChromiumPage, target_page: int) -> bool:
    return _go_to_next_page(page, target_page)


def enrich_listing_products(page: ChromiumPage, products: list[dict[str, object]]) -> None:
    _enrich_product_details(page, products)


def _collect_current_page(page: ChromiumPage, *, scroll_rounds: int) -> list[dict[str, object]]:
    best: list[dict[str, object]] = []
    for _ in range(scroll_rounds):
        page.run_js("window.scrollBy(0, Math.max(900, window.innerHeight || 900));")
        time.sleep(1)
        raw = page.run_js(PRODUCT_SCRIPT)
        if isinstance(raw, list) and len(raw) >= len(best):
            best = _prepare_listing_products(raw)
    raw = page.run_js(PRODUCT_SCRIPT)
    if isinstance(raw, list) and len(raw) >= len(best):
        return _prepare_listing_products(raw)
    return best


def _go_to_next_page(page: ChromiumPage, target_page: int) -> bool:
    if not _scroll_to_pagination(page):
        return False
    old_signature = _page_signature(page)
    clicked = page.run_js(NEXT_PAGE_SCRIPT.replace("__TARGET_PAGE__", str(target_page)))
    if not clicked:
        return False
    if not _wait_for_listing_change(page, old_signature):
        return False
    page.run_js("window.scrollTo(0, 0);")
    time.sleep(1)
    return True


def _scroll_to_pagination(page: ChromiumPage, rounds: int = 12) -> bool:
    last_height = -1
    stable_rounds = 0
    for _ in range(rounds):
        if page.run_js(PAGINATION_READY_SCRIPT):
            return True
        height = page.run_js(
            "return Math.max(document.body.scrollHeight || 0, document.documentElement.scrollHeight || 0);"
        )
        page.run_js("window.scrollTo(0, Math.max(document.body.scrollHeight || 0, document.documentElement.scrollHeight || 0));")
        time.sleep(1)
        if page.run_js(PAGINATION_READY_SCRIPT):
            return True
        if height == last_height:
            stable_rounds += 1
        else:
            stable_rounds = 0
            last_height = height
        if stable_rounds >= 3:
            break
    return bool(page.run_js(PAGINATION_READY_SCRIPT))


def _wait_for_listing_change(
    page: ChromiumPage,
    old_signature: tuple[str, ...],
    *,
    timeout_seconds: float = 15,
    interval_seconds: float = 1,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(interval_seconds)
        signature = _page_signature(page)
        if not signature:
            continue
        if not old_signature or signature != old_signature:
            return True
    return False


def _page_signature(page: ChromiumPage) -> tuple[str, ...]:
    raw = page.run_js(PRODUCT_SCRIPT)
    if not isinstance(raw, list):
        return ()
    return _product_signature(raw)


def _product_signature(products: list[dict[str, object]], limit: int = 20) -> tuple[str, ...]:
    keys: list[str] = []
    for product in products:
        key = _product_key(product)
        if key and key not in keys:
            keys.append(key)
        if len(keys) >= limit:
            break
    return tuple(keys)


def _product_key(product: dict[str, object]) -> str:
    product_url = str(product.get("resolvedProductUrl") or product.get("url") or "")
    marker = "/item/"
    if marker in product_url:
        tail = product_url.split(marker, 1)[1]
        item_id = tail.split(".", 1)[0].split("/", 1)[0]
        if item_id:
            return item_id
    if _is_promo_url(product_url):
        resolved = _resolve_promo_product_url(product_url)
        if resolved:
            return _product_key({"url": resolved})
    return str(product.get("cardUrl") or product_url)


def _finalize_products(
    page: ChromiumPage,
    raw: list[dict[str, object]],
    *,
    max_items: int,
    enrich_detail: bool,
) -> list[dict[str, object]]:
    products = raw[:max_items]
    if enrich_detail:
        enrich_listing_products(page, products)
    return products


DETAIL_FIELDS_SCRIPT = r"""
return (() => {
  function textOf(node) {
    return node ? String(node.innerText || node.textContent || '').trim() : '';
  }

  function cleanText(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function breadcrumbText() {
    const nodes = Array.from(document.querySelectorAll('nav a, [class*="breadcrumb"] a, [class*="breadcrumb"] span'))
      .map(node => cleanText(textOf(node)))
      .filter(Boolean);
    return nodes.join(' > ');
  }

  function frameText(frame) {
    try {
      const doc = frame && frame.contentDocument;
      return cleanText(doc && doc.body && (doc.body.innerText || doc.body.textContent));
    } catch (error) {
      return '';
    }
  }

  function attributesJson() {
    const pairs = {};
    const rows = Array.from(document.querySelectorAll('li, tr, [class*="sku"] [class*="item"], [class*="property"] [class*="item"]'));
    for (const row of rows) {
      const text = cleanText(textOf(row));
      if (!text || !text.includes(':')) continue;
      const [key, ...rest] = text.split(':');
      const value = cleanText(rest.join(':'));
      if (key && value && !pairs[key]) {
        pairs[key] = value;
      }
    }
    return JSON.stringify(pairs);
  }

  const storeNodes = Array.from(document.querySelectorAll('a[href*="store"], [class*="store"] a, [class*="shop"] a'))
    .map(node => cleanText(textOf(node)))
    .filter(Boolean);
  const breadcrumbNodes = Array.from(document.querySelectorAll('nav a, [class*="breadcrumb"] a, [class*="breadcrumb"] span'))
    .map(node => cleanText(textOf(node)))
    .filter(Boolean);
  const descriptionFrames = Array.from(document.querySelectorAll('#nav-description iframe, [class*="description"] iframe'))
    .map(frame => frameText(frame))
    .filter(Boolean);
  const reviewerText = cleanText(textOf(document.querySelector('[class*="reviewer"]')));

  return {
    shopName: storeNodes[0] || '',
    shopNameCandidates: storeNodes,
    shippingText: cleanText(textOf(document.querySelector('[class*="shipping"], [data-pl="shipping"]'))),
    detailRatingText: cleanText(textOf(document.querySelector('[class*="rating"], [aria-label*="rating"]'))),
    detailReviewText: cleanText(textOf(document.querySelector('[class*="review"], a[href*="reviews"]'))),
    breadcrumb: breadcrumbText(),
    breadcrumbCandidates: breadcrumbNodes,
    attributesText: attributesJson(),
    descriptionText: cleanText(textOf(document.querySelector('[class*="description"], [data-pl="description"], #product-description'))),
    descriptionFrameText: descriptionFrames[0] || '',
    reviewerText: reviewerText
  };
})()
"""


PROMO_FIELDS_SCRIPT = r"""
return (() => {
  function cleanText(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  const body = cleanText(document.body && (document.body.innerText || document.body.textContent));
  const signals = [];
  if (/Free shipping on 3 items/i.test(body)) signals.push('Free shipping on 3 items');
  if (/Free returns/i.test(body)) signals.push('Free returns');
  if (/Buy more,save more/i.test(body)) signals.push('Buy more,save more');

  return {
    promoChannel: /Dollar Express/i.test(body) ? 'Dollar Express' : '',
    promotionText: signals.join(' | ')
  };
})()
"""


def _enrich_product_details(page: ChromiumPage, products: list[dict[str, object]]) -> None:
    listing_url = page.url
    for product in products:
        _prepare_listing_product(product)
        detail_url = str(product.get("resolvedProductUrl") or product.get("url") or "")
        if not detail_url:
            continue
        try:
            if str(product.get("entryType") or "") == "promo_card":
                promo_url = str(product.get("promoLandingUrl") or product.get("cardUrl") or "")
                if promo_url:
                    page.get(promo_url)
                    time.sleep(2)
                    promo = page.run_js(PROMO_FIELDS_SCRIPT)
                    if isinstance(promo, dict):
                        product.update(promo)
            page.get(detail_url)
            time.sleep(2)
            detail = page.run_js(DETAIL_FIELDS_SCRIPT)
        except Exception:
            detail = {}
        if isinstance(detail, dict):
            detail = _normalize_detail_fields(detail)
            product.update(detail)
        if detail_url:
            product["url"] = detail_url
    if listing_url:
        page.get(listing_url)


def _prepare_listing_products(raw: list[object]) -> list[dict[str, object]]:
    products: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        product = dict(item)
        _prepare_listing_product(product)
        products.append(product)
    return products


def _prepare_listing_product(product: dict[str, object]) -> None:
    card_url = str(product.get("cardUrl") or product.get("url") or "")
    resolved_url = str(product.get("resolvedProductUrl") or "")
    entry_type = str(product.get("entryType") or "")
    is_promoted = bool(product.get("isPromoted"))

    if _is_promo_url(card_url):
        entry_type = "promo_card"
        is_promoted = True
        resolved_url = resolved_url or _resolve_promo_product_url(card_url)
        product["promoLandingUrl"] = card_url
    else:
        entry_type = entry_type or "item_card"
        resolved_url = resolved_url or card_url
        product.setdefault("promoLandingUrl", "")

    product["entryType"] = entry_type
    product["cardUrl"] = card_url
    product["resolvedProductUrl"] = resolved_url
    product["isPromoted"] = is_promoted
    if resolved_url:
        product["url"] = resolved_url


def _is_promo_url(url: str) -> bool:
    return "/ssr/" in url and "BundleDeals2" in url


def _resolve_promo_product_url(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    candidates = [
        _resolve_item_id_from_utparam(query.get("utparam-url", [""])[0]),
        _resolve_item_id_from_product_ids(query.get("productIds", [""])[0]),
    ]
    for item_id in candidates:
        if item_id:
            return f"https://www.aliexpress.com/item/{item_id}.html"
    return ""


def _resolve_item_id_from_product_ids(value: str) -> str:
    head = str(value or "").split(":", 1)[0].strip()
    return head if head.isdigit() else ""


def _resolve_item_id_from_utparam(value: str) -> str:
    match = re.search(r"x_object_id:([^|]+)", str(value or ""))
    item_id = match.group(1).strip() if match else ""
    return item_id if item_id.isdigit() else ""


def _normalize_detail_fields(detail: dict[str, object]) -> dict[str, object]:
    normalized = dict(detail)
    normalized["shopName"] = _pick_shop_name(
        _text_list(detail.get("shopNameCandidates")),
        _text(detail.get("shopName")),
    )
    normalized["breadcrumb"] = _normalize_breadcrumb(_text_list(detail.get("breadcrumbCandidates")), _text(detail.get("breadcrumb")))
    normalized["descriptionText"] = _normalize_description_text(
        _text(detail.get("descriptionFrameText")),
        _text(detail.get("descriptionText")),
    )
    normalized["detailReviewText"] = _normalize_review_text(
        _text(detail.get("detailReviewText")),
        _text(detail.get("reviewerText")),
    )
    return normalized


def _pick_shop_name(candidates: list[str], fallback: str) -> str:
    preferred = []
    for candidate in candidates:
        text = candidate.strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in {"0 cart", "cart", "store", "message", "seller info"}:
            continue
        if lowered.startswith("sold by "):
            text = text[8:].strip()
        text = re.sub(r"\s*\((?:trader|seller)\)\s*$", "", text, flags=re.IGNORECASE).strip()
        preferred.append(text)
    if preferred:
        return preferred[-1]
    return fallback


def _normalize_breadcrumb(candidates: list[str], fallback: str) -> str:
    unique: list[str] = []
    for text in candidates:
        for part in _breadcrumb_parts(text):
            if part not in unique:
                unique.append(part)
    if unique:
        return " > ".join(unique)
    return " > ".join(_breadcrumb_parts(fallback))


def _breadcrumb_parts(text: str) -> list[str]:
    cleaned = _text(text)
    if not cleaned:
        return []
    cleaned = re.sub(r"^this product belongs to\s*", "", cleaned, flags=re.IGNORECASE)
    marker = re.search(r"\band you can find similar products at\b", cleaned, flags=re.IGNORECASE)
    if marker:
        segments = [
            cleaned[: marker.start()],
            cleaned[marker.end() :],
        ]
    else:
        segments = [cleaned]

    parts: list[str] = []
    for segment in segments:
        for raw in re.split(r"\s*>\s*|\s*,\s*", segment):
            part = raw.strip(" ,>.")
            if not part:
                continue
            if part.lower() == "all categories":
                continue
            if part not in parts:
                parts.append(part)
    return parts


def _normalize_description_text(frame_text: str, fallback: str) -> str:
    if frame_text:
        return frame_text
    bad_prefixes = (
        "description report this item or seller",
        "top brand on aliexpress",
        "highly rated",
    )
    lowered = fallback.lower()
    if not fallback or any(lowered.startswith(prefix) for prefix in bad_prefixes):
        return ""
    return fallback


def _normalize_review_text(primary: str, reviewer_text: str) -> str:
    if primary and "reviews" in primary.lower():
        return primary
    match = re.search(r"(\d+(?:[,.]\d+)*)\s+reviews", reviewer_text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)} Reviews"
    return primary


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _build_options(user_data_dir: str | None, port: int | None) -> ChromiumOptions:
    options = ChromiumOptions()
    if port is not None:
        options.set_local_port(port)
    if user_data_dir:
        options.set_user_data_path(str(Path(user_data_dir).resolve()))
    return options
