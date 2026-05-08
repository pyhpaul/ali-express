from ali_mvp.browser import PRODUCT_SCRIPT


def test_product_script_returns_iife_result_to_python():
    assert PRODUCT_SCRIPT.lstrip().startswith("return ")
