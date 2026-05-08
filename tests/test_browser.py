from ali_mvp.browser import PRODUCT_SCRIPT


def test_product_script_returns_iife_result_to_python():
    assert PRODUCT_SCRIPT.lstrip().startswith("return ")


def test_product_script_has_listing_rating_helper():
    assert "function findRatingLine(lines)" in PRODUCT_SCRIPT
    assert "ratingText: findRatingLine(lines)" in PRODUCT_SCRIPT


def test_collect_raw_products_uses_finalize_path_for_detail_enrichment():
    from pathlib import Path

    source = Path("ali_mvp/browser.py").read_text(encoding="utf-8")

    assert "def _finalize_products(" in source
    assert "return raw[:max_items]" not in source
