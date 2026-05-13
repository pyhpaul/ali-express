from __future__ import annotations

import random
import time

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
    return int(payload) if payload else 0


def _generate_slider_trajectory(distance: int) -> list[dict[str, int]]:
    if distance <= 0:
        return []

    accel_end = distance * 0.3
    const_end = distance * 0.7
    base_step = 5
    points: list[dict[str, int]] = []
    current_x = 0.0
    accum_y = 0.0

    while current_x < distance and len(points) < 100:
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

    actions.release(slider_button)


def _solve_slider_captcha(page: ChromiumPage, timeout_seconds: float = 30.0) -> bool:
    distance = _get_slider_distance(page)
    if distance <= 0:
        return False

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
        if not is_slider_captcha(page):
            return True
        if _CAPTCHA_URL_MARKER not in str(getattr(page, "url", "")):
            return True
    return False


def try_solve_captcha(page: ChromiumPage, timeout_seconds: float = 30.0) -> bool:
    if not is_slider_captcha(page):
        return False
    try:
        return _solve_slider_captcha(page, timeout_seconds=timeout_seconds)
    except Exception:
        return False
