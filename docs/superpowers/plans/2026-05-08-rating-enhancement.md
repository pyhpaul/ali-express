# AliExpress Rating Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve AliExpress rating extraction so listing-page rating numbers are captured and optional detail-page enrichment is available.

**Architecture:** Keep the primary fix in browser-side extraction because the rating signal is already present in listing card text. Keep detail enrichment optional and bounded through CLI parameters to avoid unnecessary page visits.

**Tech Stack:** Python 3.13, DrissionPage, pytest, stdlib argparse.

---

## Task 1: Document Evidence and Scope

**Files:**
- Create: `docs/superpowers/specs/2026-05-08-rating-enhancement-design.md`
- Create: `docs/superpowers/plans/2026-05-08-rating-enhancement.md`

- [ ] Record live evidence showing rating appears as an independent numeric line before the sold line.
- [ ] Define listing-first extraction and optional detail enrichment.

## Task 2: Listing Rating Extraction

**Files:**
- Modify: `ali_mvp/browser.py`
- Test: `tests/test_browser.py`

- [ ] Write a failing test that asserts `PRODUCT_SCRIPT` includes a `findRatingLine` helper.
- [ ] Add `findRatingLine(lines)` in the browser script.
- [ ] Use `findRatingLine(lines)` to populate `ratingText`.
- [ ] Run `python -m pytest tests/test_browser.py -v`.

## Task 3: Detail Enrichment CLI Surface

**Files:**
- Modify: `ali_mvp/cli.py`
- Modify: `ali_mvp/browser.py`
- Test: `tests/test_cli.py`

- [ ] Write a failing test for `--enrich-detail-rating` and `--detail-limit`.
- [ ] Add parser options.
- [ ] Add optional browser function parameters without changing the default behavior.
- [ ] Run `python -m pytest tests/test_cli.py -v`.

## Task 4: Verification

**Files:**
- No required source changes unless verification finds defects.

- [ ] Run `python -m pytest -v`.
- [ ] Run `python -m compileall ali_mvp tests`.
- [ ] Run live scrape with `python -m ali_mvp scrape --keyword "women dress" --max-items 20 --port 9333 --user-data-dir .browser-profile`.
- [ ] Confirm `data/products.csv` has non-zero `rating` values.
- [ ] Commit the enhancement.

