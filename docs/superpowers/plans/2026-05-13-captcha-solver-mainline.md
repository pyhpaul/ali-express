# Captcha Solver Mainline Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared slider captcha solver to the mainline and call it once from session preflight and detail captcha waits before falling back to the existing blocked logic.

**Architecture:** Introduce a small `ali_mvp/captcha_solver.py` module that owns slider detection, distance calculation, trajectory generation, and one-shot drag attempts. Keep the existing high-level scrape/session/detail state machine unchanged by only calling the solver from `session_guard.py` and `browser.py` when captcha is already detected.

**Tech Stack:** Python 3, DrissionPage, pytest, existing AliExpress browser/session pipeline

---

## File Map

- Create: `ali_mvp/captcha_solver.py`
  - Shared slider captcha detection and one-shot solve attempt helpers.
- Modify: `ali_mvp/browser.py`
  - Import the shared solver and call it once inside `_wait_for_captcha_resolution(...)`.
- Modify: `ali_mvp/session_guard.py`
  - Import the shared solver and retry session classification once after a successful captcha solve.
- Create: `tests/test_captcha_solver.py`
  - Unit tests for solver detection, distance fallback, trajectory generation, and solve dispatch.
- Modify: `tests/test_browser.py`
  - Regression tests for one-shot solver use inside `_wait_for_captcha_resolution(...)`.
- Modify: `tests/test_session_guard.py`
  - Regression tests for preflight captcha retry success/failure behavior.

---

### Task 1: Add the shared captcha solver module with unit tests

**Files:**
- Create: `ali_mvp/captcha_solver.py`
- Test: `tests/test_captcha_solver.py`

- [ ] **Step 1: Write the failing solver tests**

```python
from __future__ import annotations

from ali_mvp import captcha_solver


class FakePage:
    def __init__(self, *, js_result=None, url: str = "https://www.aliexpress.com/verify", button=None):
        self._js_result = js_result
        self.url = url
        self._button = button

    def run_js(self, script: str):
        if isinstance(self._js_result, Exception):
            raise self._js_result
        return self._js_result

    def ele(self, selector: str):
        return self._button


def test_is_slider_captcha_returns_true_when_dom_probe_matches():
    page = FakePage(js_result=True)

    assert captcha_solver.is_slider_captcha(page) is True


def test_get_slider_distance_returns_zero_on_exception():
    page = FakePage(js_result=RuntimeError("boom"))

    assert captcha_solver._get_slider_distance(page) == 0


def test_generate_slider_trajectory_returns_empty_when_distance_is_not_positive():
    assert captcha_solver._generate_slider_trajectory(0) == []
    assert captcha_solver._generate_slider_trajectory(-5) == []


def test_try_solve_captcha_returns_false_for_non_slider_page(monkeypatch):
    page = FakePage(js_result=False)
    monkeypatch.setattr(captcha_solver, "_solve_slider_captcha", lambda page, timeout_seconds=30.0: True)

    assert captcha_solver.try_solve_captcha(page, timeout_seconds=12.0) is False


def test_try_solve_captcha_returns_solver_result_for_slider(monkeypatch):
    page = FakePage(js_result=True)
    calls: list[float] = []

    def fake_solve(page, timeout_seconds=30.0):
        calls.append(timeout_seconds)
        return True

    monkeypatch.setattr(captcha_solver, "_solve_slider_captcha", fake_solve)

    assert captcha_solver.try_solve_captcha(page, timeout_seconds=12.0) is True
    assert calls == [12.0]
```

- [ ] **Step 2: Run the solver tests to confirm they fail**

Run:

```bash
python -m pytest tests/test_captcha_solver.py -q
```

Expected:

```text
ERROR tests/test_captcha_solver.py
E   ModuleNotFoundError: No module named 'ali_mvp.captcha_solver'
```

- [ ] **Step 3: Write the minimal shared solver implementation**

```python
from __future__ import annotations

import random
import time

from DrissionPage import ChromiumPage
from DrissionPage.common import Actions


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
```

- [ ] **Step 4: Run the solver tests to confirm they pass**

Run:

```bash
python -m pytest tests/test_captcha_solver.py -q
```

Expected:

```text
5 passed
```

- [ ] **Step 5: Commit the solver module**

```bash
git add ali_mvp/captcha_solver.py tests/test_captcha_solver.py
git commit -m "feat(captcha): add shared slider solver"
```

---

### Task 2: Route detail captcha waits through the shared solver once

**Files:**
- Modify: `ali_mvp/browser.py`
- Test: `tests/test_browser.py`

- [ ] **Step 1: Write the failing browser regression tests**

```python
def test_wait_for_captcha_resolution_tries_solver_once_and_returns_true_on_success(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1"
            self.title = "验证码拦截"

    page = FakePage()
    calls = {"solve": 0, "ready": 0}

    def fake_solve(target, timeout_seconds=30.0):
        calls["solve"] += 1
        target.url = "https://www.aliexpress.com/item/1.html"
        target.title = "detail"
        return True

    monkeypatch.setattr(browser, "try_solve_captcha", fake_solve)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: calls.__setitem__("ready", calls["ready"] + 1))
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)

    assert browser._wait_for_captcha_resolution(page, timeout_seconds=2.0, interval_seconds=0.1) is True
    assert calls["solve"] == 1


def test_wait_for_captcha_resolution_keeps_existing_timeout_path_when_solver_fails(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1"
            self.title = "验证码拦截"

    page = FakePage()
    calls = {"solve": 0}
    moments = iter([0.0, 0.2, 1.5])

    monkeypatch.setattr(browser, "try_solve_captcha", lambda target, timeout_seconds=30.0: calls.__setitem__("solve", calls["solve"] + 1) or False)
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser.time, "monotonic", lambda: next(moments))

    assert browser._wait_for_captcha_resolution(page, timeout_seconds=1.0, interval_seconds=0.1) is False
    assert calls["solve"] == 1
```

- [ ] **Step 2: Run the browser regression tests to confirm they fail**

Run:

```bash
python -m pytest tests/test_browser.py::test_wait_for_captcha_resolution_tries_solver_once_and_returns_true_on_success tests/test_browser.py::test_wait_for_captcha_resolution_keeps_existing_timeout_path_when_solver_fails -q
```

Expected:

```text
AttributeError: module 'ali_mvp.browser' has no attribute 'try_solve_captcha'
```

- [ ] **Step 3: Update `ali_mvp/browser.py` to use the shared solver once**

```python
from .captcha_solver import try_solve_captcha


def _wait_for_captcha_resolution(
    page: ChromiumPage,
    timeout_seconds: float = 60.0,
    interval_seconds: float = 1.0,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    solver_attempted = False
    while time.monotonic() < deadline:
        if not _is_captcha_page(str(getattr(page, "url", "")), str(getattr(page, "title", ""))):
            return True

        if not solver_attempted:
            solver_attempted = True
            solve_timeout = max(0.0, min(30.0, deadline - time.monotonic()))
            if solve_timeout > 0 and try_solve_captcha(page, timeout_seconds=solve_timeout):
                return True

        time.sleep(interval_seconds)
        _wait_for_page_ready(page)
    return not _is_captcha_page(str(getattr(page, "url", "")), str(getattr(page, "title", "")))
```

- [ ] **Step 4: Run the browser regression tests to confirm they pass**

Run:

```bash
python -m pytest tests/test_browser.py::test_wait_for_captcha_resolution_tries_solver_once_and_returns_true_on_success tests/test_browser.py::test_wait_for_captcha_resolution_keeps_existing_timeout_path_when_solver_fails -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit the browser integration**

```bash
git add ali_mvp/browser.py tests/test_browser.py
git commit -m "feat(captcha): route detail waits through solver"
```

---

### Task 3: Retry session preflight once after a successful captcha solve

**Files:**
- Modify: `ali_mvp/session_guard.py`
- Test: `tests/test_session_guard.py`

- [ ] **Step 1: Write the failing session preflight tests**

```python
def test_run_session_preflight_rechecks_after_captcha_solver_success(monkeypatch):
    page = FakePage(
        "https://www.aliexpress.com/wholesale?SearchText=home+appliance+accessories",
        [
            {
                "pageType": "search",
                "captcha": True,
                "loginRequired": False,
                "phoneVerifyRequired": False,
                "searchResultsVisible": False,
            },
            {
                "pageType": "search",
                "captcha": False,
                "loginRequired": False,
                "phoneVerifyRequired": False,
                "searchResultsVisible": True,
            },
        ],
    )
    monkeypatch.setattr("ali_mvp.session_guard.try_solve_captcha", lambda page, timeout_seconds=30.0: True)

    result = run_session_preflight(page, search_url=page.url, warm_up=False)

    assert result == SessionPreflightResult(
        status="ready",
        risk_level="low",
        page_type="search",
        reasons=[],
        warmed_up=False,
    )
    assert len(page.js_calls) == 2


def test_run_session_preflight_keeps_captcha_blocked_when_solver_fails(monkeypatch):
    page = FakePage(
        "https://www.aliexpress.com/wholesale?SearchText=home+appliance+accessories",
        {
            "pageType": "search",
            "captcha": True,
            "loginRequired": False,
            "phoneVerifyRequired": False,
            "searchResultsVisible": False,
        },
    )
    monkeypatch.setattr("ali_mvp.session_guard.try_solve_captcha", lambda page, timeout_seconds=30.0: False)

    result = run_session_preflight(page, search_url=page.url, warm_up=True)

    assert result == SessionPreflightResult(
        status="captcha_blocked",
        risk_level="high",
        page_type="search",
        reasons=["captcha"],
        warmed_up=False,
    )
```

- [ ] **Step 2: Run the session preflight tests to confirm they fail**

Run:

```bash
python -m pytest tests/test_session_guard.py::test_run_session_preflight_rechecks_after_captcha_solver_success tests/test_session_guard.py::test_run_session_preflight_keeps_captcha_blocked_when_solver_fails -q
```

Expected:

```text
AttributeError: module 'ali_mvp.session_guard' has no attribute 'try_solve_captcha'
```

- [ ] **Step 3: Update `ali_mvp/session_guard.py` to retry classification once**

```python
from .browser import collect_session_signals, warm_up_search_session
from .captcha_solver import try_solve_captcha


def run_session_preflight(page, *, search_url: str, warm_up: bool) -> SessionPreflightResult:
    initial_payload = collect_session_signals(page)
    initial_result = _classify_session_payload(initial_payload)

    if initial_result.status == "captcha_blocked":
        if try_solve_captcha(page, timeout_seconds=30.0):
            initial_payload = collect_session_signals(page)
            initial_result = _classify_session_payload(initial_payload)
        else:
            return initial_result

    if initial_result.status in {"phone_verification_required", "login_required"}:
        return initial_result

    if initial_result.status == "search_not_ready" and warm_up:
        _run_warm_up(page, search_url=search_url)
        warmed_payload = collect_session_signals(page)
        warmed_result = _classify_session_payload(warmed_payload)
        return SessionPreflightResult(
            status=warmed_result.status,
            risk_level=warmed_result.risk_level,
            page_type=warmed_result.page_type,
            reasons=warmed_result.reasons,
            warmed_up=True,
        )

    return SessionPreflightResult(
        status=initial_result.status,
        risk_level=initial_result.risk_level,
        page_type=initial_result.page_type,
        reasons=initial_result.reasons,
        warmed_up=False,
    )
```

- [ ] **Step 4: Run the session preflight tests to confirm they pass**

Run:

```bash
python -m pytest tests/test_session_guard.py::test_run_session_preflight_rechecks_after_captcha_solver_success tests/test_session_guard.py::test_run_session_preflight_keeps_captcha_blocked_when_solver_fails -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit the preflight integration**

```bash
git add ali_mvp/session_guard.py tests/test_session_guard.py
git commit -m "feat(captcha): retry preflight after solver success"
```

---

### Task 4: Run regression and real-profile verification

**Files:**
- Modify: none
- Test: `tests/test_captcha_solver.py`
- Test: `tests/test_browser.py`
- Test: `tests/test_session_guard.py`

- [ ] **Step 1: Run focused regression for the new solver integration**

Run:

```bash
python -m pytest tests/test_captcha_solver.py tests/test_session_guard.py tests/test_browser.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 2: Run the full test suite**

Run:

```bash
python -m pytest -q
```

Expected:

```text
full suite passes with 0 failures
```

- [ ] **Step 3: Run a real-profile smoke command that can hit detail captcha**

Run:

```bash
python -m ali_mvp scrape --keyword "Home appliance accessories" --max-items 5 --pages 1 --enrich-detail --user-data-dir E:\AliExpress\.browser-profile --output-dir E:\AliExpress\data\captcha_solver_smoke
```

Expected:

```text
If slider captcha appears during preflight or detail:
- the run attempts one automatic drag
- success resumes the flow
- failure falls back to existing captcha_blocked behavior
```

- [ ] **Step 4: Inspect the run result for unchanged fallback semantics**

Run:

```bash
python - <<'PY'
from pathlib import Path
from ali_mvp.output import read_csv_rows
run_root = Path(r"E:\AliExpress\data\captcha_solver_smoke")
latest = sorted(run_root.glob("*/*"), key=lambda p: p.name)[-1]
rows = read_csv_rows(latest / "products.csv")
print(latest)
print([row.get("detail_status", "") for row in rows[:5]])
PY
```

Expected:

```text
When captcha solve fails, rows still show existing statuses such as captcha_blocked or detail_skipped_after_captcha rather than a new custom state.
```

- [ ] **Step 5: Commit after verification if no extra code changes were needed**

```bash
git status --short
```

Expected:

```text
No unstaged code changes. If verification added no code changes, do not create an extra commit.
```
