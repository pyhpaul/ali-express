from __future__ import annotations

import re
import random
import time
from urllib.parse import urlparse

try:
    from DrissionPage import ChromiumPage
    from DrissionPage.common import Actions
except Exception:  # pragma: no cover - import fallback for test/runtime environments without DrissionPage
    ChromiumPage = object  # type: ignore[assignment]
    Actions = None  # type: ignore[assignment]


_SLIDER_WRAPPER_ID = "nc_1_wrapper"
_SLIDER_TRACK_ID = "nc_1_n1t"
_SLIDER_BUTTON_ID = "nc_1_n1z"
_CAPTCHA_CONTAINER_ID = "baxia-punish"
_CAPTCHA_URL_MARKER = "_____tmd_____"
_SLIDER_READY_WAIT_SECONDS = 1.5
_SLIDER_READY_POLL_SECONDS = 0.1


def is_slider_captcha(page: ChromiumPage) -> bool:
    try:
        payload = page.run_js(
            r"""
return (() => {
    const wrapper = document.getElementById('SLIDER_WRAPPER_ID');
    const track = document.getElementById('SLIDER_TRACK_ID');
    const button = document.getElementById('SLIDER_BUTTON_ID');
    if (wrapper && track && button) return true;
    const container = document.getElementById('CAPTCHA_CONTAINER_ID');
    if (container && container.querySelector('[class*="nc_"], [class*="slider"], [class*="btn_slide"]')) return true;
    return false;
})()
""".replace("SLIDER_WRAPPER_ID", _SLIDER_WRAPPER_ID)
            .replace("SLIDER_TRACK_ID", _SLIDER_TRACK_ID)
            .replace("SLIDER_BUTTON_ID", _SLIDER_BUTTON_ID)
            .replace("CAPTCHA_CONTAINER_ID", _CAPTCHA_CONTAINER_ID)
        )
    except Exception:
        return False
    return bool(payload)


def _get_slider_distance(page: ChromiumPage) -> int:
    try:
        payload = page.run_js(
            r"""
return (() => {
    const track = document.getElementById('SLIDER_TRACK_ID');
    const button = document.getElementById('SLIDER_BUTTON_ID');
    if (!track || !button) return 0;
    return track.getBoundingClientRect().right - button.getBoundingClientRect().width - track.getBoundingClientRect().left;
})()
""".replace("SLIDER_TRACK_ID", _SLIDER_TRACK_ID)
            .replace("SLIDER_BUTTON_ID", _SLIDER_BUTTON_ID)
        )
    except Exception:
        return 0
    try:
        return int(payload) if payload else 0
    except (TypeError, ValueError):
        return 0


def _generate_slider_trajectory(distance: int) -> list[dict[str, int]]:
    if distance <= 0:
        return []

    accel_end = distance * 0.3
    const_end = distance * 0.7
    base_step = 5
    points: list[dict[str, int]] = []
    current_x = 0.0
    accum_y = 0.0

    while current_x < distance:
        if current_x < accel_end:
            step = base_step * (0.5 + (current_x / accel_end) * 1.5)
            delay = random.randint(10, 30)
        elif current_x < const_end:
            step = base_step * 2
            delay = random.randint(5, 15)
        else:
            progress = (current_x - const_end) / max(distance - const_end, 1)
            step = base_step * (2 - progress * 1.5)
            delay = random.randint(15, 40)

        current_x = min(current_x + step, distance)
        accum_y += random.uniform(-3, 3)
        points.append({"x": round(current_x), "y": round(accum_y), "delay": delay})

    if points:
        points[-1]["x"] = distance
        points[-1]["y"] = 0
    return points


def _perform_slider_drag(page: ChromiumPage, slider_button, trajectory: list[dict[str, int]]) -> None:
    if Actions is None:
        raise RuntimeError("DrissionPage is required to drag the slider captcha")

    actions = Actions(page)
    actions.move_to(slider_button)
    actions.hold(slider_button)
    try:
        prev_x = 0
        prev_y = 0
        for point in trajectory:
            dx = point["x"] - prev_x
            dy = point["y"] - prev_y
            actions.move(dx, dy, duration=0.01)
            if point["delay"] > 0:
                time.sleep(point["delay"] / 1000.0)
            prev_x = point["x"]
            prev_y = point["y"]
    finally:
        actions.release(slider_button)


def _wait_for_condition(condition, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while True:
        if condition():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_SLIDER_READY_POLL_SECONDS)


def _is_verification_gate_page(page: ChromiumPage) -> bool:
    url = str(getattr(page, "url", "") or "")
    title = str(getattr(page, "title", "") or "")
    lowered_url = url.lower()
    lowered_title = title.lower()
    parsed = urlparse(url)
    url_scope = f"{parsed.netloc} {parsed.path}".lower()
    text_scope = f"{url_scope} {lowered_title}"

    if _CAPTCHA_URL_MARKER.lower() in lowered_url:
        return True
    if "/punish" in url_scope:
        return True
    if re.search(r"\b(?:captcha|verify|verification|login|signin|sign-in|sign in|auth)\b", text_scope):
        return True
    if re.search(r"\b(?:phone\s*(?:verify|verification|code|number)|verification\s*code|phone\s+verification|手机号|短信验证码|手机验证)\b", text_scope):
        return True
    return False


def _solve_slider_captcha(page: ChromiumPage, timeout_seconds: float = 30.0) -> bool:
    ready_timeout = min(timeout_seconds, _SLIDER_READY_WAIT_SECONDS)
    if not _wait_for_condition(
        lambda: _get_slider_distance(page) > 0 and bool(page.ele(f"#{_SLIDER_BUTTON_ID}")),
        ready_timeout,
    ):
        return False

    distance = _get_slider_distance(page)
    slider_button = page.ele(f"#{_SLIDER_BUTTON_ID}")
    if not slider_button:
        return False

    trajectory = _generate_slider_trajectory(distance)
    if not trajectory:
        return False

    _perform_slider_drag(page, slider_button, trajectory)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(1.0)
        if not _is_verification_gate_page(page) and not is_slider_captcha(page):
            return True
    return False


def try_solve_captcha(page: ChromiumPage, timeout_seconds: float = 30.0) -> bool:
    if _is_verification_gate_page(page):
        ready_timeout = min(timeout_seconds, _SLIDER_READY_WAIT_SECONDS)
        if not _wait_for_condition(lambda: is_slider_captcha(page), ready_timeout):
            return False
    elif not is_slider_captcha(page):
        return False
    try:
        return _solve_slider_captcha(page, timeout_seconds=timeout_seconds)
    except Exception:
        return False
