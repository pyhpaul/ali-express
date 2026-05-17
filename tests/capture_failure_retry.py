"""Capture failure retry element for debugging."""

from __future__ import annotations

import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from DrissionPage import ChromiumOptions, ChromiumPage


def capture_failure_retry_element(output_dir: str = "data/failure_retry_debug"):
    """Capture failure retry element state for debugging."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    opts = ChromiumOptions()
    opts.set_argument('--incognito')
    opts.set_browser_path('')
    opts.set_local_port(9336)
    opts.headless(False)

    print("Opening browser in incognito mode...")
    page = ChromiumPage(opts)

    try:
        print("Navigating to AliExpress...")
        page.get('https://www.aliexpress.com')
        time.sleep(3)

        from ali_mvp.captcha_solver import (
            is_slider_captcha,
            _SLIDER_BUTTON_ID,
            _SLIDER_TRACK_ID,
            _FAILURE_RETRY_TEXT,
            _get_slider_distance,
            _generate_slider_trajectory,
            _perform_slider_drag,
        )

        has_captcha = is_slider_captcha(page)
        print(f"Slider captcha detected: {has_captcha}")

        if not has_captcha:
            print("No captcha triggered, try again or check network")
            return

        print("Capturing initial state...")
        page.get_screenshot(path=str(output_path / "01_initial.png"))

        distance = _get_slider_distance(page)
        print(f"Slider distance: {distance}")

        button = page.ele(f"#{_SLIDER_BUTTON_ID}")
        if button and distance > 0:
            print("\nAttempting drag (expected to fail)...")
            trajectory = _generate_slider_trajectory(distance)
            try:
                _perform_slider_drag(page, button, trajectory)
                print("Drag completed")
            except Exception as e:
                print(f"Drag error: {e}")

            time.sleep(2)

            print("Capturing post-drag state...")
            page.get_screenshot(path=str(output_path / "02_after_drag.png"))

            still_has_captcha = is_slider_captcha(page)
            print(f"Still has captcha: {still_has_captcha}")

            if still_has_captcha:
                print("\nSearching for failure retry element...")

                search_results = {}

                print(f"Looking for text: '{_FAILURE_RETRY_TEXT}'")

                try:
                    elements = page.eles(f"text={_FAILURE_RETRY_TEXT}")
                    search_results["text_selector"] = {
                        "found": len(elements) > 0,
                        "count": len(elements),
                    }
                    if elements:
                        for i, elem in enumerate(elements[:3]):
                            search_results[f"text_selector_{i}"] = {
                                "tag": elem.tag,
                                "text": elem.text[:200] if elem.text else "",
                                "html": elem.html[:500] if elem.html else "",
                                "classes": elem.attr("class") or "",
                                "id": elem.attr("id") or "",
                            }
                except Exception as e:
                    search_results["text_selector"] = {"error": str(e)}

                xpath_patterns = [
                    f"//*[contains(text(), '{_FAILURE_RETRY_TEXT}')]",
                    f"//*[contains(., '{_FAILURE_RETRY_TEXT}')]",
                    f"//div[contains(text(), '{_FAILURE_RETRY_TEXT}')]",
                    f"//span[contains(text(), '{_FAILURE_RETRY_TEXT}')]",
                ]

                for i, xpath in enumerate(xpath_patterns):
                    try:
                        elements = page.eles(xpath)
                        search_results[f"xpath_{i}"] = {
                            "pattern": xpath,
                            "found": len(elements) > 0,
                            "count": len(elements),
                        }
                        if elements:
                            elem = elements[0]
                            search_results[f"xpath_{i}_detail"] = {
                                "tag": elem.tag,
                                "text": elem.text[:200] if elem.text else "",
                                "html": elem.html[:500] if elem.html else "",
                            }
                    except Exception as e:
                        search_results[f"xpath_{i}"] = {"error": str(e)}

                try:
                    js_result = page.run_js(r"""
return (() => {
    const results = [];
    const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT,
        null,
        false
    );
    const searchText = '""" + _FAILURE_RETRY_TEXT + r"""';
    while (walker.nextNode()) {
        const node = walker.currentNode;
        if (node.textContent && node.textContent.includes(searchText)) {
            results.push({
                text: node.textContent.substring(0, 200),
                parentTag: node.parentElement ? node.parentElement.tagName : 'unknown',
                parentClass: node.parentElement ? node.parentElement.className : '',
                parentId: node.parentElement ? node.parentElement.id : '',
                parentHtml: node.parentElement ? node.parentElement.outerHTML.substring(0, 500) : '',
            });
        }
    }
    return results;
})()
""")
                    search_results["js_text_search"] = {
                        "found": len(js_result) > 0 if js_result else False,
                        "results": js_result[:3] if js_result else [],
                    }
                except Exception as e:
                    search_results["js_text_search"] = {"error": str(e)}

                captcha_selectors = [
                    "#baxia-punish",
                    ".nc-lang-cnt",
                    "[class*='captcha']",
                    "[class*='verify']",
                    "[class*='punish']",
                    "[class*='fail']",
                    "[class*='retry']",
                    "[class*='error']",
                    "[class*='tip']",
                    "[class*='message']",
                    "[class*='notice']",
                    "[class*='alert']",
                ]

                for selector in captcha_selectors:
                    try:
                        elements = page.eles(selector)
                        if elements:
                            search_results[f"selector_{selector}"] = {
                                "count": len(elements),
                                "elements": []
                            }
                            for i, elem in enumerate(elements[:3]):
                                search_results[f"selector_{selector}"]["elements"].append({
                                    "tag": elem.tag,
                                    "text": elem.text[:200] if elem.text else "",
                                    "classes": elem.attr("class") or "",
                                    "id": elem.attr("id") or "",
                                })
                    except Exception:
                        pass

                with open(output_path / "search_results.json", "w", encoding="utf-8") as f:
                    json.dump(search_results, f, ensure_ascii=False, indent=2)

                print(f"\nSearch results saved to {output_path / 'search_results.json'}")

                from ali_mvp.captcha_solver import _find_failure_retry_element
                found_element = _find_failure_retry_element(page)
                print(f"\n_find_failure_retry_element result: {found_element is not None}")

                if found_element:
                    print(f"Element tag: {found_element.tag}")
                    print(f"Element text: {found_element.text[:100] if found_element.text else 'empty'}")
                    page.get_screenshot(path=str(output_path / "03_element_found.png"))
                else:
                    print("Element not found by _find_failure_retry_element")

                retry_selectors = [
                    "#nc_1_refresh1",
                    ".nc-lang-cnt .btn_refresh",
                    "[class*='btn_refresh']",
                    "[class*='refresh']",
                    ".nc_iconfont.btn_refresh",
                ]

                print("\nChecking for standard retry buttons...")
                for selector in retry_selectors:
                    try:
                        elem = page.ele(selector)
                        if elem:
                            print(f"  Found: {selector} -> text: '{elem.text[:50] if elem.text else ''}'")
                    except Exception:
                        pass

            else:
                print("SUCCESS: Captcha solved after drag!")

        print(f"\nAll output saved to {output_path}/")

    finally:
        page.quit()
        print("\nBrowser closed")


if __name__ == "__main__":
    capture_failure_retry_element()
