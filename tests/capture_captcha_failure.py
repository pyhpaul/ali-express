"""Capture captcha failure scenario for manual inspection."""

from __future__ import annotations

import sys
import time
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from DrissionPage import ChromiumOptions, ChromiumPage


def capture_captcha_state(output_dir: str = "data/captcha_debug"):
    """Capture current captcha state for debugging."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    opts = ChromiumOptions()
    opts.set_argument('--incognito')
    opts.set_browser_path('')
    opts.set_local_port(9339)
    opts.headless(False)

    print("Opening browser in incognito mode...")
    page = ChromiumPage(opts)

    try:
        # Navigate to trigger captcha
        print("Navigating to AliExpress...")
        page.get('https://www.aliexpress.com')
        time.sleep(3)

        from ali_mvp.captcha_solver import (
            is_slider_captcha,
            _SLIDER_BUTTON_ID,
            _SLIDER_TRACK_ID,
            _SLIDER_WRAPPER_ID,
            _CAPTCHA_CONTAINER_ID,
            _get_slider_distance,
            _generate_slider_trajectory,
            _perform_slider_drag,
        )

        has_captcha = is_slider_captcha(page)
        print(f"Slider captcha detected: {has_captcha}")

        if not has_captcha:
            print("No captcha triggered, try again or check network")
            return

        # Capture initial state
        print("Capturing initial state...")
        page.get_screenshot(path=str(output_path / "01_initial.png"))

        # Get slider info
        distance = _get_slider_distance(page)
        print(f"Slider distance (with overshoot): {distance}")

        # Capture DOM info
        dom_info = {
            "url": page.url,
            "title": page.title,
            "slider_distance": distance,
            "has_slider_button": page.ele(f"#{_SLIDER_BUTTON_ID}") is not None,
            "has_slider_track": page.ele(f"#{_SLIDER_TRACK_ID}") is not None,
            "has_slider_wrapper": page.ele(f"#{_SLIDER_WRAPPER_ID}") is not None,
            "has_captcha_container": page.ele(f"#{_CAPTCHA_CONTAINER_ID}") is not None,
        }

        # Try to find retry button candidates
        retry_selectors = [
            "#nc_1_refresh1",
            ".nc-lang-cnt .btn_refresh",
            "[class*='btn_refresh']",
            "[class*='refresh']",
            ".nc_iconfont.btn_refresh",
            ".nc-lang-cnt",
            "#nc_1_wrapper",
            f"#{_CAPTCHA_CONTAINER_ID}",
        ]

        found_elements = {}
        for selector in retry_selectors:
            try:
                elem = page.ele(selector)
                if elem:
                    found_elements[selector] = {
                        "tag": elem.tag,
                        "text": elem.text[:100] if elem.text else "",
                        "html": elem.html[:500] if elem.html else "",
                    }
            except Exception:
                pass

        dom_info["found_elements"] = found_elements

        # Save DOM info
        with open(output_path / "dom_info.json", "w", encoding="utf-8") as f:
            json.dump(dom_info, f, ensure_ascii=False, indent=2)

        print(f"DOM info saved to {output_path / 'dom_info.json'}")

        # Now perform a drag that will likely fail
        print("\nAttempting drag (expected to fail)...")
        button = page.ele(f"#{_SLIDER_BUTTON_ID}")
        if button and distance > 0:
            trajectory = _generate_slider_trajectory(distance)
            try:
                _perform_slider_drag(page, button, trajectory)
                print("Drag completed")
            except Exception as e:
                print(f"Drag error (expected): {e}")

            time.sleep(2)

            # Capture post-drag state
            print("Capturing post-drag state...")
            page.get_screenshot(path=str(output_path / "02_after_drag.png"))

            # Check if still has captcha
            still_has_captcha = is_slider_captcha(page)
            print(f"Still has captcha: {still_has_captcha}")

            if still_has_captcha:
                print("\nCapturing failure state...")

                # Get updated DOM
                failure_info = {
                    "still_has_captcha": still_has_captcha,
                    "current_url": page.url,
                }

                # Check for retry buttons again
                retry_candidates = {}
                for selector in retry_selectors + [
                    "*[class*='refresh']",
                    "*[class*='retry']",
                    "*[class*='again']",
                    "*[id*='refresh']",
                    "*[id*='retry']",
                ]:
                    try:
                        elems = page.eles(selector)
                        for i, elem in enumerate(elems):
                            key = f"{selector}[{i}]"
                            retry_candidates[key] = {
                                "tag": elem.tag,
                                "text": elem.text[:100] if elem.text else "",
                                "classes": elem.attr("class") or "",
                                "id": elem.attr("id") or "",
                            }
                    except Exception:
                        pass

                failure_info["retry_candidates"] = retry_candidates

                with open(output_path / "failure_state.json", "w", encoding="utf-8") as f:
                    json.dump(failure_info, f, ensure_ascii=False, indent=2)

                print(f"Failure state saved to {output_path / 'failure_state.json'}")
                print(f"\nScreenshots saved to {output_path}/")
                print("Please check the screenshots and failure_state.json to identify retry button")
            else:
                print("SUCCESS: Captcha solved!")

    finally:
        page.quit()
        print("\nBrowser closed")


if __name__ == "__main__":
    capture_captcha_state()
