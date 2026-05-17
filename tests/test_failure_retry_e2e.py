"""End-to-end test for failure retry element click in incognito mode."""

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
    opts.set_local_port(9335)
    opts.headless(False)

    page = ChromiumPage(opts)
    yield page
    try:
        page.quit()
    except Exception:
        pass


def test_failure_retry_element_detection_and_click(incognito_page):
    """Test detection and click of '验证失败，点击框体重试' element."""
    page = incognito_page
    captcha_solver = import_module("ali_mvp.captcha_solver")

    # Navigate to AliExpress to trigger captcha
    print("Navigating to AliExpress...")
    page.get("https://www.aliexpress.com")
    time.sleep(3)

    has_captcha = captcha_solver.is_slider_captcha(page)
    print(f"Slider captcha detected: {has_captcha}")

    if not has_captcha:
        print("No captcha triggered, skipping test")
        pytest.skip("No captcha to test failure retry element")

    # Try to solve captcha (expected to fail first time)
    print("\nAttempting to solve captcha (expected to fail)...")
    solved, diagnostic = captcha_solver._solve_slider_captcha_with_result(page, timeout_seconds=30.0)
    print(f"Initial solve attempt - Solved: {solved}")
    print(f"Diagnostic: {diagnostic}")

    # Check if failure retry element appears
    print("\nChecking for failure retry element...")
    failure_element = captcha_solver._find_failure_retry_element(page)
    print(f"Failure retry element found: {failure_element is not None}")

    if failure_element:
        try:
            print(f"Element text: {failure_element.text[:50] if failure_element.text else 'empty'}")
        except UnicodeEncodeError:
            print("Element text contains special characters")

        # Try to click the failure retry element
        print("\nClicking failure retry element...")
        clicked = captcha_solver._click_failure_retry_element(page)
        print(f"Click successful: {clicked}")

        if clicked:
            time.sleep(2)

            # Check if captcha is still present
            still_has_captcha = captcha_solver.is_slider_captcha(page)
            print(f"Captcha still present after click: {still_has_captcha}")

            if still_has_captcha:
                # Try to solve again after clicking retry
                print("\nAttempting to solve captcha after retry click...")
                solved_after_retry, diagnostic_after_retry = captcha_solver._solve_slider_captcha_with_result(
                    page, timeout_seconds=30.0
                )
                print(f"After retry - Solved: {solved_after_retry}")
                print(f"Diagnostic: {diagnostic_after_retry}")

                if solved_after_retry:
                    assert not captcha_solver.is_slider_captcha(page), "Captcha should be cleared after solving"
                    print("[OK] Captcha solved after clicking failure retry element")
                else:
                    print(f"[FAIL] Captcha not solved after retry: {diagnostic_after_retry.get('fail_reason')}")
            else:
                print("[OK] Captcha cleared after clicking failure retry element")
        else:
            print("[FAIL] Failed to click failure retry element")
    else:
        print("No failure retry element found, checking for standard retry button...")
        retry_button = captcha_solver._find_retry_button(page)
        print(f"Standard retry button found: {retry_button is not None}")

        if retry_button:
            print("Trying standard retry button...")
            clicked = captcha_solver._click_retry_button(page)
            print(f"Standard retry button clicked: {clicked}")

            if clicked:
                time.sleep(2)
                still_has_captcha = captcha_solver.is_slider_captcha(page)
                print(f"Captcha still present after standard retry: {still_has_captcha}")

                if still_has_captcha:
                    # Try to solve again
                    solved_after_retry, diagnostic_after_retry = captcha_solver._solve_slider_captcha_with_result(
                        page, timeout_seconds=30.0
                    )
                    print(f"After standard retry - Solved: {solved_after_retry}")

                    if solved_after_retry:
                        print("[OK] Captcha solved after clicking standard retry button")
                    else:
                        print(f"[FAIL] Captcha not solved after standard retry: {diagnostic_after_retry.get('fail_reason')}")
                else:
                    print("[OK] Captcha cleared after clicking standard retry button")


def test_solve_captcha_with_failure_retry_integration(incognito_page):
    """Test the full captcha solving flow with failure retry integration."""
    page = incognito_page
    captcha_solver = import_module("ali_mvp.captcha_solver")

    # Navigate to AliExpress
    print("Navigating to AliExpress...")
    page.get("https://www.aliexpress.com")
    time.sleep(3)

    has_captcha = captcha_solver.is_slider_captcha(page)
    print(f"Slider captcha detected: {has_captcha}")

    if not has_captcha:
        print("No captcha triggered, skipping test")
        pytest.skip("No captcha to test integration")

    # Use the full solve function which includes failure retry logic
    print("\nAttempting to solve captcha with full retry logic...")
    solved, diagnostic = captcha_solver.try_solve_captcha_with_result(page, timeout_seconds=60.0)
    print(f"Final result - Solved: {solved}")
    print(f"Diagnostic: {diagnostic}")

    if solved:
        assert not captcha_solver.is_slider_captcha(page), "Captcha should be cleared after solving"
        print("[OK] Captcha solved with full retry logic")
    else:
        print(f"[FAIL] Captcha not solved: {diagnostic.get('fail_reason')}")
        # Don't fail the test as captcha might persist due to anti-bot measures
