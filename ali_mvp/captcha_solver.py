from __future__ import annotations

import re
import random
import time
from dataclasses import dataclass
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


@dataclass
class _CaptchaSolverDiagnostic:
    solver_attempted: bool = False
    slider_detected: bool = False
    waited_for_ready: bool = False
    ready_wait_ms: int = 0
    result: str = "skipped"
    fail_reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "solver_attempted": self.solver_attempted,
            "slider_detected": self.slider_detected,
            "waited_for_ready": self.waited_for_ready,
            "ready_wait_ms": self.ready_wait_ms,
            "result": self.result,
            "fail_reason": self.fail_reason,
        }


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
    query_scope = parsed.query.lower()

    if _CAPTCHA_URL_MARKER.lower() in lowered_url:
        return True
    if "/punish" in url_scope:
        return True
    if re.search(r"\b(?:captcha|verify|verification|login|signin|sign-in|sign in|auth)\b", text_scope):
        return True
    if re.search(r"\b(?:phone\s*(?:verify|verification|code|number)|verification\s*code|phone\s+verification|手机号|短信验证码|手机验证)\b", text_scope):
        return True
    return False


def _wait_for_slider_ready(page: ChromiumPage, timeout_seconds: float) -> tuple[bool, bool, int]:
    start = time.monotonic()

    ready = _wait_for_condition(lambda: is_slider_captcha(page), timeout_seconds)
    ready_wait_ms = int((time.monotonic() - start) * 1000)
    return ready, ready_wait_ms > 0, ready_wait_ms


def _wait_for_slider_distance_ready(page: ChromiumPage, timeout_seconds: float) -> tuple[bool, bool, int]:
    start = time.monotonic()

    def ready() -> bool:
        distance = _get_slider_distance(page)
        slider_button = page.ele(f"#{_SLIDER_BUTTON_ID}")
        return distance > 0 and bool(slider_button)

    ready_result = _wait_for_condition(ready, timeout_seconds)
    ready_wait_ms = int((time.monotonic() - start) * 1000)
    return ready_result, ready_wait_ms > 0, ready_wait_ms


def _solve_slider_captcha(page: ChromiumPage, timeout_seconds: float = 30.0) -> bool:
    solved, _ = _solve_slider_captcha_with_result(page, timeout_seconds=timeout_seconds)
    return solved


def _solve_slider_captcha_with_result(page: ChromiumPage, timeout_seconds: float = 30.0) -> tuple[bool, dict[str, object]]:
    diagnostic = _CaptchaSolverDiagnostic()
    ready_timeout = min(timeout_seconds, _SLIDER_READY_WAIT_SECONDS)
    try:
        diagnostic.slider_detected = is_slider_captcha(page)
        ready, waited_for_ready, ready_wait_ms = _wait_for_slider_distance_ready(page, ready_timeout)
        diagnostic.waited_for_ready = waited_for_ready
        diagnostic.ready_wait_ms = ready_wait_ms
        if not ready:
            diagnostic.result = "failed"
            diagnostic.fail_reason = "distance_not_ready"
            return False, diagnostic.as_dict()

        distance = _get_slider_distance(page)
        slider_button = page.ele(f"#{_SLIDER_BUTTON_ID}")
        if not slider_button:
            diagnostic.result = "failed"
            diagnostic.fail_reason = "distance_not_ready"
            return False, diagnostic.as_dict()

        trajectory = _generate_slider_trajectory(distance)
        if not trajectory:
            diagnostic.result = "failed"
            diagnostic.fail_reason = "distance_not_ready"
            return False, diagnostic.as_dict()

        diagnostic.solver_attempted = True
        try:
            _perform_slider_drag(page, slider_button, trajectory)
        except Exception:
            diagnostic.result = "failed"
            diagnostic.fail_reason = "drag_failed"
            return False, diagnostic.as_dict()

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            time.sleep(1.0)
            if not _is_verification_gate_page(page) and not is_slider_captcha(page):
                diagnostic.result = "solved"
                diagnostic.fail_reason = ""
                return True, diagnostic.as_dict()

        diagnostic.result = "failed"
        diagnostic.fail_reason = "gate_not_cleared"
        return False, diagnostic.as_dict()
    except Exception:
        diagnostic.result = "failed"
        diagnostic.fail_reason = "exception"
        return False, diagnostic.as_dict()


def try_solve_captcha_with_result(page: ChromiumPage, timeout_seconds: float = 30.0) -> tuple[bool, dict[str, object]]:
    diagnostic = _CaptchaSolverDiagnostic()

    try:
        if _is_verification_gate_page(page):
            ready_timeout = min(timeout_seconds, _SLIDER_READY_WAIT_SECONDS)
            ready, waited_for_ready, ready_wait_ms = _wait_for_slider_ready(page, ready_timeout)
            diagnostic.slider_detected = ready
            diagnostic.waited_for_ready = waited_for_ready
            diagnostic.ready_wait_ms = ready_wait_ms
            if not ready:
                diagnostic.result = "failed"
                diagnostic.fail_reason = "slider_not_ready"
                return False, diagnostic.as_dict()
        elif not is_slider_captcha(page):
            diagnostic.result = "skipped"
            diagnostic.fail_reason = "not_slider_gate"
            return False, diagnostic.as_dict()
        else:
            diagnostic.slider_detected = True

        solved, solver_diagnostic = _solve_slider_captcha_with_result(page, timeout_seconds=timeout_seconds)
        solver_diagnostic = dict(solver_diagnostic)
        if diagnostic.waited_for_ready:
            solver_diagnostic["waited_for_ready"] = True
            solver_diagnostic["ready_wait_ms"] = max(
                int(solver_diagnostic.get("ready_wait_ms", 0)),
                diagnostic.ready_wait_ms,
            )
        solver_diagnostic["slider_detected"] = True
        return solved, solver_diagnostic
    except Exception:
        diagnostic.result = "failed"
        diagnostic.fail_reason = "exception"
        return False, diagnostic.as_dict()


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
