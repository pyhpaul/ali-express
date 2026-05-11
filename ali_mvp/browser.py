from __future__ import annotations

import json
import random
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
    browser_hardening: str = "minimal",
) -> list[dict[str, object]]:
    page = open_listing_page(
        url,
        user_data_dir=user_data_dir,
        port=port,
        browser_hardening=browser_hardening,
    )
    all_products: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    current_page = 1

    while True:
        current_products = collect_listing_page_products(page, scroll_rounds=scroll_rounds)
        if enrich_detail:
            _attach_listing_context(
                current_products,
                base_url=url,
                page_url=str(getattr(page, "url", "") or url),
                page_number=current_page,
            )
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
    browser_hardening: str = "minimal",
) -> ChromiumPage:
    page = ChromiumPage(
        _build_options(
            user_data_dir=user_data_dir,
            port=port,
            browser_hardening=browser_hardening,
        )
    )
    page.get(url)
    if browser_hardening == "minimal":
        _init_page_stealth(page)
    _pause_after_navigation()
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
        _human_scroll_step(page)
        _sleep_jitter(0.8, 1.2)
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
    _sleep_jitter(0.2, 0.6)
    clicked = page.run_js(NEXT_PAGE_SCRIPT.replace("__TARGET_PAGE__", str(target_page)))
    if not clicked:
        return False
    if not _wait_for_listing_change(page, old_signature):
        return False
    page.run_js("window.scrollTo(0, 0);")
    _pause_after_navigation()
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
        _sleep_jitter(0.8, 1.2)
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
    for product in products:
        _strip_internal_product_fields(product)
    return products


DETAIL_FIELDS_SCRIPT = r"""
return (() => {
  function textOf(node) {
    return node ? String(node.innerText || node.textContent || '').trim() : '';
  }

  function cleanText(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function parseJson(value) {
    try {
      return JSON.parse(value);
    } catch (error) {
      return null;
    }
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

  function collectAttributePairs() {
    const pairs = [];
    const seen = new Set();

    function pushPair(key, value) {
      const cleanKey = cleanText(key);
      const cleanValue = cleanText(value);
      if (!cleanKey || !cleanValue) return;
      const marker = `${cleanKey}\u0000${cleanValue}`;
      if (seen.has(marker)) return;
      seen.add(marker);
      pairs.push({ key: cleanKey, value: cleanValue });
    }

    const specRows = Array.from(document.querySelectorAll(
      '#nav-specification li, [data-pl="product-specs"] li, [class*="pecification"] li'
    ));
    for (const row of specRows) {
      const keyNode = row.querySelector('[class*="title"], [class*="prop"] [class*="title"]');
      const valueNode = row.querySelector('[class*="desc"], [class*="value"]');
      if (keyNode && valueNode) {
        pushPair(textOf(keyNode), textOf(valueNode));
      }
    }

    const selectedSkuRows = Array.from(document.querySelectorAll(
      '[class*="ku--wrap"] [class*="property"], [class*="sku"] [class*="property"]'
    ));
    for (const row of selectedSkuRows) {
      const keyNode = row.querySelector('[class*="title"]');
      const valueNode = row.querySelector('[class*="selected"], [class*="text"], [class*="value"]');
      if (keyNode && valueNode) {
        pushPair(textOf(keyNode), textOf(valueNode));
        continue;
      }
      const text = cleanText(textOf(row));
      const match = text.match(/^([^:]+):\s*(.+)$/);
      if (match) {
        pushPair(match[1], match[2]);
      }
    }

    return pairs;
  }

  function jsonLdDescription() {
    const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
    for (const script of scripts) {
      const parsed = parseJson(script.textContent || '');
      const queue = Array.isArray(parsed) ? [...parsed] : [parsed];
      while (queue.length) {
        const current = queue.shift();
        if (!current || typeof current !== 'object') continue;
        const description = cleanText(current.description);
        if (description) return description;
        if (Array.isArray(current['@graph'])) {
          queue.push(...current['@graph']);
        }
      }
    }
    return '';
  }

  function metaDescription() {
    const nodes = Array.from(document.querySelectorAll(
      'meta[name="description"], meta[property="og:description"], meta[name="twitter:description"]'
    ));
    for (const node of nodes) {
      const value = cleanText(node.getAttribute('content') || '');
      if (value) return value;
    }
    return '';
  }

  function detailDescriptionText() {
    const selectors = [
      '#product-description',
      '[data-pl="product-description"]',
      '[data-pl="description"]',
      '#nav-description',
      '[class*="product-description"]',
      '[class*="detail-description"]',
      '[class*="description--"]',
      '[class*="description"]'
    ];
    for (const selector of selectors) {
      const nodes = Array.from(document.querySelectorAll(selector));
      for (const node of nodes) {
        const value = cleanText(textOf(node));
        if (value) return value;
      }
    }
    return '';
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
  const attributePairs = collectAttributePairs();
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
    attributePairs: attributePairs,
    descriptionText: detailDescriptionText(),
    descriptionFrameText: descriptionFrames[0] || '',
    jsonLdDescription: jsonLdDescription(),
    metaDescription: metaDescription(),
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
    current_listing_page: int | None = None
    listing_context_ready = False
    for index, product in enumerate(products):
        _prepare_listing_product(product)
        detail_url = str(product.get("resolvedProductUrl") or product.get("url") or "")
        if not detail_url:
            continue
        entry_type = str(product.get("entryType") or "")
        try:
            target_listing_page = _listing_page_number(product)
            has_listing_context = _has_listing_context(product)
            if has_listing_context and (not listing_context_ready or current_listing_page != target_listing_page):
                if not _restore_listing_context(page, product, str(listing_url or "")):
                    product["detailStatus"] = "listing_context_failed"
                    listing_context_ready = False
                    continue
                current_listing_page = target_listing_page
                listing_context_ready = True
            if entry_type == "promo_card":
                promo_url = str(product.get("promoLandingUrl") or product.get("cardUrl") or "")
                if promo_url:
                    page.get(promo_url)
                    time.sleep(2)
                    promo = page.run_js(PROMO_FIELDS_SCRIPT)
                    if isinstance(promo, dict):
                        product.update(promo)
                    listing_context_ready = False
                    if has_listing_context:
                        if not _restore_listing_context(page, product, str(listing_url or "")):
                            product["detailStatus"] = "listing_context_failed"
                            continue
                        current_listing_page = target_listing_page
                        listing_context_ready = True
            opened = _open_detail_from_listing_context(page, product)
            if not opened:
                product["detailStatus"] = "detail_open_failed"
                if has_listing_context:
                    _restore_listing_context(page, product, str(listing_url or ""))
                elif listing_url:
                    page.get(str(listing_url))
                    _wait_for_page_ready(page)
                listing_context_ready = False
                continue
            detail_page = _resolve_detail_page_context(page, product)
            if _is_captcha_page(str(detail_page.url), str(getattr(detail_page, "title", ""))):
                if not _wait_for_captcha_resolution(detail_page):
                    product["detailStatus"] = "captcha_blocked"
                    _mark_detail_status(products[index + 1 :], "detail_skipped_after_captcha")
                    break
            detail = detail_page.run_js(DETAIL_FIELDS_SCRIPT)
        except Exception:
            detail = {}
            if has_listing_context:
                try:
                    _restore_listing_context(page, product, str(listing_url or ""))
                except Exception:
                    pass
            elif listing_url:
                try:
                    page.get(str(listing_url))
                    _wait_for_page_ready(page)
                except Exception:
                    pass
            listing_context_ready = False
        if isinstance(detail, dict):
            detail = _normalize_detail_fields(detail)
            product.update(detail)
        if detail_url:
            product["url"] = detail_url
        try:
            if product.get("_detailUsedNewTab"):
                detail_tab_id = str(product.get("_detailTabId") or "")
                if detail_tab_id:
                    page.close_tabs(detail_tab_id)
                page.activate_tab(str(product.get("_listingTabId") or page.tab_id))
                _wait_for_page_ready(page)
            else:
                page.back()
                _wait_for_page_ready(page)
        except Exception:
            if listing_url:
                page.get(listing_url)
                _wait_for_page_ready(page)
            listing_context_ready = False
            continue
        listing_context_ready = entry_type != "promo_card"
    if listing_url:
        page.get(listing_url)


def _wait_for_captcha_resolution(
    page: ChromiumPage,
    timeout_seconds: float = 60.0,
    interval_seconds: float = 1.0,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _is_captcha_page(str(getattr(page, "url", "")), str(getattr(page, "title", ""))):
            return True
        time.sleep(interval_seconds)
        _wait_for_page_ready(page)
    return not _is_captcha_page(str(getattr(page, "url", "")), str(getattr(page, "title", "")))


def _mark_detail_status(products: list[dict[str, object]], status: str) -> None:
    for product in products:
        if not product.get("detailStatus"):
            product["detailStatus"] = status


def _restore_listing_context(page: ChromiumPage, product: dict[str, object], default_listing_url: str) -> bool:
    target_page = _listing_page_number(product)
    base_url = str(product.get("_listingBaseUrl") or default_listing_url or "")
    page_url = str(product.get("_listingPageUrl") or base_url)
    target_url = page_url or base_url
    if target_page <= 1:
        if not target_url:
            return False
        page.get(target_url)
        _wait_for_page_ready(page)
        return True
    if not base_url:
        return False
    page.get(base_url)
    _wait_for_page_ready(page)
    return advance_listing_page(page, target_page)


def _open_detail_from_listing_context(page: ChromiumPage, product: dict[str, object]) -> bool:
    before_url = str(getattr(page, "url", "") or "")
    before_tabs = list(getattr(page, "tab_ids", []) or [])
    before_tab_id = str(getattr(page, "tab_id", "") or "")
    script = _detail_click_script(product)
    clicked = page.run_js(script)
    if clicked in {"clicked", "navigated"}:
        _wait_for_page_ready(page)
        after_url = str(getattr(page, "url", "") or "")
        if after_url and after_url != before_url and "/item/" in after_url:
            product["_detailUsedNewTab"] = False
            product["_detailTabId"] = before_tab_id
            product["_listingTabId"] = before_tab_id
            return True

        after_tabs = list(getattr(page, "tab_ids", []) or [])
        new_tabs = [tab_id for tab_id in after_tabs if tab_id not in before_tabs]
        if new_tabs:
            detail_tab_id = str(getattr(page, "latest_tab", "") or new_tabs[-1])
            detail_page = page.get_tab(detail_tab_id)
            _wait_for_page_ready(detail_page)
            detail_url = str(getattr(detail_page, "url", "") or "")
            if detail_url and "/item/" in detail_url:
                product["_detailUsedNewTab"] = True
                product["_detailTabId"] = detail_tab_id
                product["_listingTabId"] = before_tab_id
                return True

    direct_url = _direct_detail_open_url(product)
    if not direct_url:
        return False
    page.get(direct_url)
    _wait_for_page_ready(page)
    after_url = str(getattr(page, "url", "") or "")
    if not after_url or "/item/" not in after_url:
        return False
    product["_detailUsedNewTab"] = False
    product["_detailTabId"] = before_tab_id
    product["_listingTabId"] = before_tab_id
    return True


def _resolve_detail_page_context(page: ChromiumPage, product: dict[str, object]) -> ChromiumPage:
    detail_tab_id = str(product.get("_detailTabId") or "")
    if product.get("_detailUsedNewTab") and detail_tab_id:
        return page.get_tab(detail_tab_id)
    return page


def _wait_for_page_ready(page: ChromiumPage, timeout_seconds: float = 8.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            ready = page.run_js("return document.readyState;")
        except Exception:
            time.sleep(0.2)
            continue
        if str(ready or "").lower() == "complete":
            return
        time.sleep(0.2)


def _detail_click_script(product: dict[str, object]) -> str:
    card_url = json.dumps(str(product.get("cardUrl") or ""))
    detail_url = json.dumps(str(product.get("resolvedProductUrl") or product.get("url") or ""))
    return f"""
return (() => {{
  window.__ALI_MVP_DETAIL_CLICK__ = true;
  const cardUrl = {card_url};
  const detailUrl = {detail_url};
  const anchors = Array.from(document.querySelectorAll('a[href]'));
  const marker = detailUrl ? '/item/' + detailUrl.split('/item/').pop().split(/[?#]/)[0] : '';
  const anchor = anchors.find((node) => {{
    const href = node.href || node.getAttribute('href') || '';
    if (!href) return false;
    return href === cardUrl || href === detailUrl || (marker && href.includes(marker));
  }});
  if (!anchor) return 'missing';
  anchor.scrollIntoView({{ block: 'center' }});
  anchor.target = '_self';
  anchor.click();
  return 'clicked';
}})()
"""


def _direct_detail_open_url(product: dict[str, object]) -> str:
    entry_type = str(product.get("entryType") or "")
    candidates: list[str]
    if entry_type == "promo_card":
        candidates = [
            str(product.get("resolvedProductUrl") or ""),
            str(product.get("url") or ""),
            str(product.get("cardUrl") or ""),
        ]
    else:
        candidates = [
            str(product.get("cardUrl") or ""),
            str(product.get("resolvedProductUrl") or ""),
            str(product.get("url") or ""),
        ]
    for candidate in candidates:
        if "/item/" in candidate:
            return candidate
    return ""


def _is_captcha_page(url: str, title: str) -> bool:
    lowered_url = str(url or "").lower()
    lowered_title = str(title or "").lower()
    if "/_____tmd_____/punish" in lowered_url:
        return True
    if "验证码拦截" in str(title or ""):
        return True
    return "captcha" in lowered_title and "intercept" in lowered_title


def _attach_listing_context(
    products: list[dict[str, object]],
    *,
    base_url: str,
    page_url: str,
    page_number: int,
) -> None:
    for product in products:
        product["_listingBaseUrl"] = base_url
        product["_listingPageUrl"] = page_url or base_url
        product["_listingPageNumber"] = page_number


def _has_listing_context(product: dict[str, object]) -> bool:
    return any(key in product for key in ("_listingBaseUrl", "_listingPageUrl", "_listingPageNumber"))


def _listing_page_number(product: dict[str, object]) -> int:
    try:
        return max(1, int(product.get("_listingPageNumber") or 1))
    except (TypeError, ValueError):
        return 1


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
    normalized["attributesText"] = _normalize_attributes_text(
        _text(detail.get("attributesText")),
        detail.get("attributePairs"),
    )
    normalized["descriptionText"] = _normalize_description_text(
        _text(detail.get("descriptionFrameText")),
        _text(detail.get("descriptionText")),
        _text(detail.get("jsonLdDescription")),
        _text(detail.get("metaDescription")),
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


def _normalize_attributes_text(raw_text: str, pairs: object) -> str:
    merged: dict[str, str] = {}
    parsed = _parse_attributes_json(raw_text)
    if isinstance(parsed, dict):
        for key, value in parsed.items():
            clean_key = _text(key)
            clean_value = _text(value)
            if clean_key and clean_value and clean_key not in merged:
                merged[clean_key] = clean_value
    if isinstance(pairs, list):
        for item in pairs:
            if not isinstance(item, dict):
                continue
            clean_key = _text(item.get("key"))
            clean_value = _text(item.get("value"))
            if clean_key and clean_value and clean_key not in merged:
                merged[clean_key] = clean_value
    return json.dumps(merged, ensure_ascii=True, separators=(",", ":")) if merged else raw_text


def _parse_attributes_json(raw_text: str) -> dict[str, object] | None:
    if not raw_text:
        return None
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_description_text(frame_text: str, fallback: str, jsonld_text: str, meta_text: str) -> str:
    if frame_text:
        return frame_text
    bad_prefixes = (
        "description report this item or seller",
        "top brand on aliexpress",
        "highly rated",
    )
    lowered = fallback.lower()
    if not fallback or any(lowered.startswith(prefix) for prefix in bad_prefixes):
        return jsonld_text or meta_text
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


def _strip_internal_product_fields(product: dict[str, object]) -> None:
    for key in [name for name in product if str(name).startswith("_")]:
        product.pop(key, None)


def _sleep_jitter(min_s: float, max_s: float) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _human_scroll_step(page: ChromiumPage) -> None:
    distance = random.randint(700, 1100)
    page.run_js(f"window.scrollBy(0, {distance});")


def _pause_after_navigation() -> None:
    _sleep_jitter(0.8, 1.6)


def _init_page_stealth(page: ChromiumPage) -> None:
    if not hasattr(page, "run_js"):
        return
    page.run_js(
        """
return (() => {
  try {
    const define = (target, key, value) => {
      try {
        Object.defineProperty(target, key, {
          configurable: true,
          get: () => value,
        });
      } catch (error) {}
    };
    define(Navigator.prototype, 'webdriver', undefined);
    define(Navigator.prototype, 'language', navigator.language || 'en-US');
    define(Navigator.prototype, 'languages', navigator.languages || ['en-US', 'en']);
    const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
    if (originalQuery) {
      window.navigator.permissions.query = (parameters) => {
        if (parameters && parameters.name === 'notifications') {
          return Promise.resolve({ state: Notification.permission });
        }
        return originalQuery.call(window.navigator.permissions, parameters);
      };
    }
  } catch (error) {}
  return true;
})()
"""
    )


def _build_options(
    user_data_dir: str | None,
    port: int | None,
    browser_hardening: str = "minimal",
) -> ChromiumOptions:
    options = ChromiumOptions()
    if port is not None:
        options.set_local_port(port)
    if user_data_dir:
        options.set_user_data_path(str(Path(user_data_dir).resolve()))
    return options
