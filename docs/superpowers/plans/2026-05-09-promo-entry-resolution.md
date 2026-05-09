# Promo Entry Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture promo search cards, resolve their entry product item URL, and preserve promo signals alongside normal product detail enrichment.

**Architecture:** Extend the listing extractor to emit both normal item cards and BundleDeals2 promo cards, resolve promo entry item URLs from the promo URL itself, then branch the detail enrichment pass so promo cards first collect promo text and then visit the resolved item detail page.

**Tech Stack:** Python 3.13, DrissionPage, argparse, pytest, csv, dataclasses

---

### Task 1: Add failing tests for promo-card recognition and resolution

**Files:**
- Modify: `tests/test_browser.py`
- Modify: `tests/test_extractor.py`
- Modify: `tests/test_output.py`
- Modify: `tests/test_scoring.py`

- [ ] Add failing tests for promo card detection in `PRODUCT_SCRIPT`.
- [ ] Add failing tests for resolving `BundleDeals2` URLs to real item URLs.
- [ ] Add failing tests for promo metadata flow into normalization and CSV output.

### Task 2: Extend browser extraction for promo cards

**Files:**
- Modify: `ali_mvp/browser.py`
- Test: `tests/test_browser.py`

- [ ] Update `PRODUCT_SCRIPT` to emit both `/item/` and `/ssr/.../BundleDeals2` cards.
- [ ] Add helper(s) to mark `entryType`, `searchCardUrl`, `promoLandingUrl`, and `resolvedProductUrl`.
- [ ] Update `_product_key()` so promo cards dedupe by resolved item id.

### Task 3: Branch detail enrichment for promo cards

**Files:**
- Modify: `ali_mvp/browser.py`
- Test: `tests/test_browser.py`

- [ ] Add promo metadata extraction script for `Dollar Express` signals.
- [ ] For `promo_card`, visit promo landing page first, then resolved item page.
- [ ] Merge promo metadata and detail metadata into the same raw product dict.

### Task 4: Flow promo fields into records and CSV

**Files:**
- Modify: `ali_mvp/scoring.py`
- Modify: `ali_mvp/extractor.py`
- Modify: `ali_mvp/output.py`
- Test: `tests/test_extractor.py`
- Test: `tests/test_output.py`
- Test: `tests/test_scoring.py`

- [ ] Add product fields for `entry_type`, `search_card_url`, `is_promoted`, `promo_channel`, `promotion_text`, and `promo_landing_url`.
- [ ] Normalize raw promo values into `ProductRecord`.
- [ ] Write the new fields to `products.csv`.

### Task 5: Update usage docs and verify

**Files:**
- Modify: `README.md`

- [ ] Document promo-card behavior and output semantics.
- [ ] Run focused pytest cases first, then full `python -m pytest -q`.
- [ ] Run one live scrape against `Home appliance accessories` and confirm promo rows carry both item URL and promotion text.
