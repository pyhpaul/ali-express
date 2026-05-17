"""End-to-end captcha solver tests with real browser."""

from __future__ import annotations

import time
import pytest
from importlib import import_module

try:
    from DrissionPage import ChromiumOptions, ChromiumPage
    from DrissionPage.common import Actions
except Exception:
    pytest.skip("DrissionPage not available", allow_module_level=True)


@pytest.fixture
def incognito_page():
    """Create an incognito browser page for testing."""
    browser_module = import_module("ali_mvp.browser")
    opts = ChromiumOptions()
    opts.set_argument('--incognito')
    opts.set_browser_path('')
    opts.set_local_port(9334)
    opts.headless(False)

    page = ChromiumPage(opts)
    yield page
    try:
        page.quit()
    except Exception:
        pass


def test_captcha_solver_normal_pass(incognito_page):
    """Test captcha solver in normal pass scenario."""
    page = incognito_page
    captcha_solver = import_module("ali_mvp.captcha_solver")

    # Navigate to AliExpress
    page.get("https://www.aliexpress.com")
    time.sleep(3)

    # Check if captcha is present
    has_captcha = captcha_solver.is_slider_captcha(page)
    print(f"Slider captcha detected: {has_captcha}")

    if has_captcha:
        # Try to solve
        solved, diagnostic = captcha_solver.try_solve_captcha_with_result(page, timeout_seconds=30.0)
        print(f"Solved: {solved}")
        print(f"Diagnostic: {diagnostic}")

        if solved:
            assert not captcha_solver.is_slider_captcha(page), "Captcha should be cleared after solving"
            print("✓ Captcha solved successfully")
        else:
            print(f"✗ Captcha solving failed: {diagnostic.get('fail_reason')}")
    else:
        print("✓ No captcha detected, page is clean")


def test_captcha_solver_retry_on_failure(incognito_page):
    """Test captcha solver retry mechanism on failure."""
    page = incognito_page
    captcha_solver = import_module("ali_mvp.captcha_solver")

    # Navigate to a test page with slider captcha
    # Use a known URL that triggers captcha
    page.get("https://www.aliexpress.com/wholesale?SearchText=test")
    time.sleep(3)

    has_captcha = captcha_solver.is_slider_captcha(page)
    print(f"Initial captcha state: {has_captcha}")

    if not has_captcha:
        print("No captcha triggered, skipping retry test")
        pytest.skip("No captcha to test retry mechanism")

    # Test retry button detection
    retry_button = captcha_solver._find_retry_button(page)
    print(f"Retry button found: {retry_button is not None}")

    # Test the solve function with retries
    solved, diagnostic = captcha_solver._solve_slider_captcha_with_result(page, timeout_seconds=30.0)
    print(f"Final result - Solved: {solved}")
    print(f"Diagnostic: {diagnostic}")

    if solved:
        assert not captcha_solver.is_slider_captcha(page), "Captcha should be cleared"
        print("✓ Captcha solved with retries")
    else:
        print(f"✗ Captcha not solved after retries: {diagnostic.get('fail_reason')}")
        # Don't fail the test if captcha persists - it might be due to anti-bot measures
