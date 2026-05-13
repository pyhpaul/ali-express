# Captcha Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add lightweight captcha diagnostics that persist the latest captcha handling outcome into run artifacts and print one concise CLI summary line, without changing scrape control-flow semantics.

**Architecture:** Extend the shared captcha solver to produce a small structured attempt result while preserving the existing boolean APIs used by `browser.py` and `session_guard.py`. Thread that latest diagnostic into `RunState`, carry it through scrape checkpoints and blocked/failure states, persist it in both `run_state.json` and `run_summary.json`, and surface it in CLI output as a single grep-friendly line.

**Tech Stack:** Python 3, dataclasses, DrissionPage, pytest, existing AliExpress scrape/session/detail pipeline

---

## File Map

- Modify: `ali_mvp/captcha_solver.py`
  - Add a bounded diagnostic payload and a helper API that returns both boolean success and structured reason fields.
- Modify: `ali_mvp/browser.py`
  - Capture detail-stage captcha diagnostics from `_wait_for_captcha_resolution(...)` and expose them to callers without changing existing status strings.
- Modify: `ali_mvp/session_guard.py`
  - Capture preflight-stage captcha diagnostics alongside the existing `SessionPreflightResult` classification flow.
- Modify: `ali_mvp/run_state.py`
  - Add `captcha_diagnostic` to `RunState`, round-trip it in JSON, and include it in `run_summary.json`.
- Modify: `ali_mvp/scrape_runner.py`
  - Preserve and checkpoint the latest captcha diagnostic during preflight, detail blocking, resume, and failure paths.
- Modify: `ali_mvp/cli.py`
  - Print a single final captcha diagnostic line for `scrape` and `resume` when the run state contains one.
- Modify: `tests/test_captcha_solver.py`
  - Add unit coverage for ready wait, skipped/non-slider, distance-not-ready, gate-not-cleared, and solved outcomes.
- Modify: `tests/test_browser.py`
  - Add regression tests for detail-stage diagnostic capture and overwrite behavior.
- Modify: `tests/test_session_guard.py`
  - Add regression tests for preflight-stage diagnostic capture on success and failure.
- Modify: `tests/test_run_state.py`
  - Add round-trip and summary persistence tests for `captcha_diagnostic`.
- Modify: `tests/test_scrape_runner.py`
  - Add state-persistence regression tests proving detail/preflight diagnostics survive blocked and completed flows.
- Modify: `tests/test_cli.py`
  - Add scrape/resume output tests for the one-line captcha diagnostic summary.

---

### Task 1: Add solver-level captcha diagnostic payloads without breaking boolean callers

**Files:**
- Modify: `ali_mvp/captcha_solver.py`
- Test: `tests/test_captcha_solver.py`

- [ ] **Step 1: Write the failing solver diagnostic tests**

```python
def test_try_solve_captcha_returns_skipped_diagnostic_for_non_slider_page():
    page = FakePage(js_result=False)

    solved, diagnostic = captcha_solver.try_solve_captcha_with_result(page, timeout_seconds=12.0)

    assert solved is False
    assert diagnostic == {
        "solver_attempted": False,
        "slider_detected": False,
        "waited_for_ready": False,
        "ready_wait_ms": 0,
        "result": "skipped",
        "fail_reason": "not_slider_gate",
    }


def test_try_solve_captcha_reports_wait_before_slider_becomes_ready(monkeypatch):
    page = FakePage(
        js_result=False,
        url="https://www.aliexpress.com/verify?x5step=1",
        title="验证码拦截",
    )
    state = {"probe_count": 0, "ticks": 0}

    def fake_is_slider_captcha(page):
        state["probe_count"] += 1
        return state["probe_count"] >= 3

    monkeypatch.setattr(captcha_solver, "is_slider_captcha", fake_is_slider_captcha)
    monkeypatch.setattr(captcha_solver, "_solve_slider_captcha_with_result", lambda page, timeout_seconds=30.0: (True, {
        "solver_attempted": True,
        "slider_detected": True,
        "waited_for_ready": False,
        "ready_wait_ms": 0,
        "result": "solved",
        "fail_reason": "",
    }))
    monkeypatch.setattr(captcha_solver.time, "monotonic", lambda: state["ticks"] * 0.1)
    monkeypatch.setattr(captcha_solver.time, "sleep", lambda seconds: state.__setitem__("ticks", state["ticks"] + 1))

    solved, diagnostic = captcha_solver.try_solve_captcha_with_result(page, timeout_seconds=1.0)

    assert solved is True
    assert diagnostic["slider_detected"] is True
    assert diagnostic["waited_for_ready"] is True
    assert diagnostic["ready_wait_ms"] >= 200
    assert diagnostic["result"] == "solved"


def test_solve_slider_captcha_reports_distance_not_ready(monkeypatch):
    page = FakePage(
        js_result=True,
        url="https://www.aliexpress.com/verify?x5step=1",
        title="验证码拦截",
        button=object(),
    )
    state = {"ticks": 0}

    monkeypatch.setattr(captcha_solver, "_get_slider_distance", lambda page: 0)
    monkeypatch.setattr(captcha_solver.time, "monotonic", lambda: state["ticks"] * 0.1)
    monkeypatch.setattr(captcha_solver.time, "sleep", lambda seconds: state.__setitem__("ticks", state["ticks"] + 1))

    solved, diagnostic = captcha_solver._solve_slider_captcha_with_result(page, timeout_seconds=0.5)

    assert solved is False
    assert diagnostic["solver_attempted"] is False
    assert diagnostic["slider_detected"] is True
    assert diagnostic["result"] == "failed"
    assert diagnostic["fail_reason"] == "distance_not_ready"


def test_solve_slider_captcha_reports_gate_not_cleared_after_drag(monkeypatch):
    page = FakePage(
        js_result=True,
        url="https://www.aliexpress.com/verify?x5step=1",
        title="验证码拦截",
        button=object(),
    )
    state = {"ticks": 0}

    monkeypatch.setattr(captcha_solver, "_get_slider_distance", lambda page: 60)
    monkeypatch.setattr(captcha_solver, "_generate_slider_trajectory", lambda distance: [{"x": distance, "y": 0, "delay": 0}])
    monkeypatch.setattr(captcha_solver, "_perform_slider_drag", lambda page, slider_button, trajectory: None)
    monkeypatch.setattr(captcha_solver, "is_slider_captcha", lambda page: True)
    monkeypatch.setattr(captcha_solver.time, "monotonic", lambda: state["ticks"] * 0.1)
    monkeypatch.setattr(captcha_solver.time, "sleep", lambda seconds: state.__setitem__("ticks", state["ticks"] + 1))

    solved, diagnostic = captcha_solver._solve_slider_captcha_with_result(page, timeout_seconds=0.3)

    assert solved is False
    assert diagnostic["solver_attempted"] is True
    assert diagnostic["result"] == "failed"
    assert diagnostic["fail_reason"] == "gate_not_cleared"
```

- [ ] **Step 2: Run the solver diagnostic tests to confirm they fail**

Run:

```bash
python -m pytest tests/test_captcha_solver.py -q
```

Expected:

```text
FAIL because try_solve_captcha_with_result / _solve_slider_captcha_with_result do not exist yet.
```

- [ ] **Step 3: Implement the diagnostic-aware solver helpers while keeping the old boolean API**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class CaptchaAttemptResult:
    solver_attempted: bool
    slider_detected: bool
    waited_for_ready: bool
    ready_wait_ms: int
    result: str
    fail_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "solver_attempted": self.solver_attempted,
            "slider_detected": self.slider_detected,
            "waited_for_ready": self.waited_for_ready,
            "ready_wait_ms": self.ready_wait_ms,
            "result": self.result,
            "fail_reason": self.fail_reason,
        }


def _solve_slider_captcha_with_result(page: ChromiumPage, timeout_seconds: float = 30.0) -> tuple[bool, dict[str, object]]:
    ready_timeout = min(timeout_seconds, _SLIDER_READY_WAIT_SECONDS)
    ready_started = time.monotonic()
    ready = _wait_for_condition(
        lambda: _get_slider_distance(page) > 0 and bool(page.ele(f"#{_SLIDER_BUTTON_ID}")),
        ready_timeout,
    )
    ready_wait_ms = int((time.monotonic() - ready_started) * 1000)
    if not ready:
        return False, CaptchaAttemptResult(
            solver_attempted=False,
            slider_detected=True,
            waited_for_ready=ready_wait_ms > 0,
            ready_wait_ms=ready_wait_ms,
            result="failed",
            fail_reason="distance_not_ready",
        ).to_dict()

    distance = _get_slider_distance(page)
    slider_button = page.ele(f"#{_SLIDER_BUTTON_ID}")
    if distance <= 0:
        return False, CaptchaAttemptResult(True, True, ready_wait_ms > 0, ready_wait_ms, "failed", "distance_not_ready").to_dict()
    if not slider_button:
        return False, CaptchaAttemptResult(False, True, ready_wait_ms > 0, ready_wait_ms, "failed", "slider_not_ready").to_dict()

    trajectory = _generate_slider_trajectory(distance)
    if not trajectory:
        return False, CaptchaAttemptResult(True, True, ready_wait_ms > 0, ready_wait_ms, "failed", "distance_not_ready").to_dict()

    try:
        _perform_slider_drag(page, slider_button, trajectory)
    except Exception:
        return False, CaptchaAttemptResult(True, True, ready_wait_ms > 0, ready_wait_ms, "failed", "drag_failed").to_dict()

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(1.0)
        if not _is_verification_gate_page(page) and not is_slider_captcha(page):
            return True, CaptchaAttemptResult(True, True, ready_wait_ms > 0, ready_wait_ms, "solved").to_dict()
    return False, CaptchaAttemptResult(True, True, ready_wait_ms > 0, ready_wait_ms, "failed", "gate_not_cleared").to_dict()


def try_solve_captcha_with_result(page: ChromiumPage, timeout_seconds: float = 30.0) -> tuple[bool, dict[str, object]]:
    if _is_verification_gate_page(page):
        ready_timeout = min(timeout_seconds, _SLIDER_READY_WAIT_SECONDS)
        ready_started = time.monotonic()
        slider_detected = _wait_for_condition(lambda: is_slider_captcha(page), ready_timeout)
        ready_wait_ms = int((time.monotonic() - ready_started) * 1000)
        if not slider_detected:
            return False, CaptchaAttemptResult(
                solver_attempted=False,
                slider_detected=False,
                waited_for_ready=ready_wait_ms > 0,
                ready_wait_ms=ready_wait_ms,
                result="failed",
                fail_reason="slider_not_ready",
            ).to_dict()
        solved, diagnostic = _solve_slider_captcha_with_result(page, timeout_seconds=timeout_seconds)
        diagnostic["waited_for_ready"] = diagnostic.get("waited_for_ready", False) or ready_wait_ms > 0
        diagnostic["ready_wait_ms"] = max(int(diagnostic.get("ready_wait_ms", 0)), ready_wait_ms)
        diagnostic["slider_detected"] = True
        return solved, diagnostic

    if not is_slider_captcha(page):
        return False, CaptchaAttemptResult(
            solver_attempted=False,
            slider_detected=False,
            waited_for_ready=False,
            ready_wait_ms=0,
            result="skipped",
            fail_reason="not_slider_gate",
        ).to_dict()

    try:
        return _solve_slider_captcha_with_result(page, timeout_seconds=timeout_seconds)
    except Exception:
        return False, CaptchaAttemptResult(True, True, False, 0, "failed", "exception").to_dict()


def try_solve_captcha(page: ChromiumPage, timeout_seconds: float = 30.0) -> bool:
    solved, _diagnostic = try_solve_captcha_with_result(page, timeout_seconds=timeout_seconds)
    return solved
```

- [ ] **Step 4: Run the solver diagnostic tests to confirm they pass**

Run:

```bash
python -m pytest tests/test_captcha_solver.py -q
```

Expected:

```text
all captcha solver tests pass, including the new diagnostic assertions.
```

- [ ] **Step 5: Commit the solver diagnostic layer**

```bash
git add ali_mvp/captcha_solver.py tests/test_captcha_solver.py
git commit -m "feat(captcha): add solver diagnostics"
```

---

### Task 2: Thread detail-stage diagnostics through browser captcha waits

**Files:**
- Modify: `ali_mvp/browser.py`
- Test: `tests/test_browser.py`

- [ ] **Step 1: Write the failing browser diagnostic tests**

```python
def test_wait_for_captcha_resolution_returns_detail_diagnostic_on_solver_success(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1"
            self.title = "验证码拦截"

    page = FakePage()
    monkeypatch.setattr(
        browser,
        "try_solve_captcha_with_result",
        lambda target, timeout_seconds=30.0: (True, {
            "solver_attempted": True,
            "slider_detected": True,
            "waited_for_ready": True,
            "ready_wait_ms": 900,
            "result": "solved",
            "fail_reason": "",
        }),
    )
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)

    solved, diagnostic = browser._wait_for_captcha_resolution(page, timeout_seconds=2.0, interval_seconds=0.1)

    assert solved is True
    assert diagnostic == {
        "stage": "detail",
        "solver_attempted": True,
        "slider_detected": True,
        "waited_for_ready": True,
        "ready_wait_ms": 900,
        "result": "solved",
        "fail_reason": "",
        "page_url": "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1",
    }


def test_wait_for_captcha_resolution_returns_failed_detail_diagnostic_when_solver_fails(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "https://www.aliexpress.com//item/1.html/_____tmd_____/punish?x5step=1"
            self.title = "验证码拦截"

    page = FakePage()
    moments = iter([0.0, 0.2, 0.6, 1.2])
    monkeypatch.setattr(
        browser,
        "try_solve_captcha_with_result",
        lambda target, timeout_seconds=30.0: (False, {
            "solver_attempted": True,
            "slider_detected": True,
            "waited_for_ready": True,
            "ready_wait_ms": 700,
            "result": "failed",
            "fail_reason": "gate_not_cleared",
        }),
    )
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser.time, "monotonic", lambda: next(moments))
    monkeypatch.setattr(browser, "_wait_for_page_ready", lambda page, timeout_seconds=8.0: None)

    solved, diagnostic = browser._wait_for_captcha_resolution(page, timeout_seconds=1.0, interval_seconds=0.1)

    assert solved is False
    assert diagnostic["stage"] == "detail"
    assert diagnostic["result"] == "failed"
    assert diagnostic["fail_reason"] == "gate_not_cleared"
```

- [ ] **Step 2: Run the browser diagnostic tests to confirm they fail**

Run:

```bash
python -m pytest tests/test_browser.py::test_wait_for_captcha_resolution_returns_detail_diagnostic_on_solver_success tests/test_browser.py::test_wait_for_captcha_resolution_returns_failed_detail_diagnostic_when_solver_fails -q
```

Expected:

```text
FAIL because browser does not yet import try_solve_captcha_with_result or return diagnostics.
```

- [ ] **Step 3: Update browser captcha waiting to return `(solved, diagnostic)` and keep detail statuses unchanged**

```python
from .captcha_solver import try_solve_captcha, try_solve_captcha_with_result


def _with_captcha_stage(diagnostic: dict[str, object] | None, *, stage: str, page_url: str) -> dict[str, object] | None:
    if not diagnostic:
        return None
    return {
        "stage": stage,
        "solver_attempted": bool(diagnostic.get("solver_attempted", False)),
        "slider_detected": bool(diagnostic.get("slider_detected", False)),
        "waited_for_ready": bool(diagnostic.get("waited_for_ready", False)),
        "ready_wait_ms": int(diagnostic.get("ready_wait_ms", 0) or 0),
        "result": str(diagnostic.get("result") or "skipped"),
        "fail_reason": str(diagnostic.get("fail_reason") or ""),
        "page_url": page_url,
    }


def _wait_for_captcha_resolution(
    page: ChromiumPage,
    timeout_seconds: float = 60.0,
    interval_seconds: float = 1.0,
) -> tuple[bool, dict[str, object] | None]:
    deadline = time.monotonic() + timeout_seconds
    solver_attempted = False
    latest_diagnostic: dict[str, object] | None = None
    initial_url = str(getattr(page, "url", "") or "")
    while True:
        now = time.monotonic()
        if now >= deadline:
            break
        if not _is_captcha_page(str(getattr(page, "url", "")), str(getattr(page, "title", ""))):
            return True, latest_diagnostic
        if not solver_attempted:
            solver_attempted = True
            solve_timeout = max(0.0, min(30.0, deadline - now))
            if solve_timeout > 0:
                solved, diagnostic = try_solve_captcha_with_result(page, timeout_seconds=solve_timeout)
                latest_diagnostic = _with_captcha_stage(diagnostic, stage="detail", page_url=initial_url)
                if solved:
                    _wait_for_page_ready(page)
                    return True, latest_diagnostic
            now = time.monotonic()
            if now >= deadline:
                break
        time.sleep(interval_seconds)
        _wait_for_page_ready(page)
    solved = not _is_captcha_page(str(getattr(page, "url", "")), str(getattr(page, "title", "")))
    return solved, latest_diagnostic
```

- [ ] **Step 4: Update `enrich_single_product_detail(...)` to stash the latest diagnostic on the product for the runner to consume**

```python
        if _is_captcha_page(str(detail_page.url), str(getattr(detail_page, "title", ""))):
            solved, diagnostic = _wait_for_captcha_resolution(detail_page)
            if diagnostic:
                product["_captchaDiagnostic"] = dict(diagnostic)
            if not solved:
                product["detailStatus"] = "captcha_blocked"
                return "captcha_blocked"
```

- [ ] **Step 5: Run the browser regression tests to confirm they pass**

Run:

```bash
python -m pytest tests/test_browser.py -q
```

Expected:

```text
all browser tests pass, including the new detail diagnostic assertions.
```

- [ ] **Step 6: Commit the detail diagnostic wiring**

```bash
git add ali_mvp/browser.py tests/test_browser.py
git commit -m "feat(captcha): capture detail diagnostics"
```

---

### Task 3: Thread preflight-stage diagnostics through session classification

**Files:**
- Modify: `ali_mvp/session_guard.py`
- Test: `tests/test_session_guard.py`

- [ ] **Step 1: Write the failing session diagnostic tests**

```python
def test_run_session_preflight_returns_preflight_diagnostic_after_solver_success(monkeypatch):
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
    monkeypatch.setattr(
        "ali_mvp.session_guard.try_solve_captcha_with_result",
        lambda page, timeout_seconds=30.0: (True, {
            "solver_attempted": True,
            "slider_detected": True,
            "waited_for_ready": True,
            "ready_wait_ms": 850,
            "result": "solved",
            "fail_reason": "",
        }),
    )

    outcome = run_session_preflight(page, search_url=page.url, warm_up=False)

    assert outcome.result.status == "ready"
    assert outcome.captcha_diagnostic == {
        "stage": "preflight",
        "solver_attempted": True,
        "slider_detected": True,
        "waited_for_ready": True,
        "ready_wait_ms": 850,
        "result": "solved",
        "fail_reason": "",
        "page_url": page.url,
    }


def test_run_session_preflight_returns_failed_preflight_diagnostic_when_solver_fails(monkeypatch):
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
    monkeypatch.setattr(
        "ali_mvp.session_guard.try_solve_captcha_with_result",
        lambda page, timeout_seconds=30.0: (False, {
            "solver_attempted": True,
            "slider_detected": True,
            "waited_for_ready": True,
            "ready_wait_ms": 900,
            "result": "failed",
            "fail_reason": "gate_not_cleared",
        }),
    )

    outcome = run_session_preflight(page, search_url=page.url, warm_up=True)

    assert outcome.result.status == "captcha_blocked"
    assert outcome.captcha_diagnostic["stage"] == "preflight"
    assert outcome.captcha_diagnostic["result"] == "failed"
    assert outcome.captcha_diagnostic["fail_reason"] == "gate_not_cleared"
```

- [ ] **Step 2: Run the session diagnostic tests to confirm they fail**

Run:

```bash
python -m pytest tests/test_session_guard.py::test_run_session_preflight_returns_preflight_diagnostic_after_solver_success tests/test_session_guard.py::test_run_session_preflight_returns_failed_preflight_diagnostic_when_solver_fails -q
```

Expected:

```text
FAIL because run_session_preflight currently returns only SessionPreflightResult.
```

- [ ] **Step 3: Add a small wrapper result type or tuple return for preflight diagnostics and adapt the runner call site**

```python
@dataclass(frozen=True)
class SessionPreflightOutcome:
    result: SessionPreflightResult
    captcha_diagnostic: dict[str, object] | None


def run_session_preflight(page, *, search_url: str, warm_up: bool) -> SessionPreflightOutcome:
    initial_payload = collect_session_signals(page)
    initial_result = _classify_session_payload(initial_payload)
    diagnostic: dict[str, object] | None = None
    current_url = str(getattr(page, "url", "") or search_url)

    if initial_result.status == "captcha_blocked":
        solved, raw_diagnostic = try_solve_captcha_with_result(page, timeout_seconds=30.0)
        diagnostic = _with_stage(raw_diagnostic, stage="preflight", page_url=current_url)
        if solved:
            initial_payload = collect_session_signals(page)
            initial_result = _classify_session_payload(initial_payload)
        else:
            return SessionPreflightOutcome(result=initial_result, captcha_diagnostic=diagnostic)

    if initial_result.status in {"phone_verification_required", "login_required"}:
        return SessionPreflightOutcome(result=initial_result, captcha_diagnostic=diagnostic)

    if initial_result.status == "search_not_ready" and warm_up:
        _run_warm_up(page, search_url=search_url)
        warmed_payload = collect_session_signals(page)
        warmed_result = _classify_session_payload(warmed_payload)
        return SessionPreflightOutcome(
            result=SessionPreflightResult(
                status=warmed_result.status,
                risk_level=warmed_result.risk_level,
                page_type=warmed_result.page_type,
                reasons=warmed_result.reasons,
                warmed_up=True,
            ),
            captcha_diagnostic=diagnostic,
        )

    return SessionPreflightOutcome(
        result=SessionPreflightResult(
            status=initial_result.status,
            risk_level=initial_result.risk_level,
            page_type=initial_result.page_type,
            reasons=initial_result.reasons,
            warmed_up=False,
        ),
        captcha_diagnostic=diagnostic,
    )
```

- [ ] **Step 4: Update the scrape runner call site to consume `preflight_outcome.result` and preserve `preflight_outcome.captcha_diagnostic`**

```python
preflight_outcome = _resolve_session_preflight(manifest=manifest, page=page)
if preflight_outcome is None:
    running_state = replace(session_seed_state, status="running", last_session_preflight_status="skipped")
else:
    preflight = preflight_outcome.result
    running_state = _next_session_state(
        existing=session_seed_state,
        preflight_status=preflight.status,
        risk_level=preflight.risk_level,
        now_iso=manifest.created_at,
    )
    if preflight_outcome.captcha_diagnostic:
        running_state = replace(running_state, captcha_diagnostic=preflight_outcome.captcha_diagnostic)
```

- [ ] **Step 5: Run the session guard and affected scrape runner tests to confirm they pass**

Run:

```bash
python -m pytest tests/test_session_guard.py tests/test_scrape_runner.py -q
```

Expected:

```text
all affected tests pass after adapting the preflight call chain.
```

- [ ] **Step 6: Commit the preflight diagnostic wiring**

```bash
git add ali_mvp/session_guard.py ali_mvp/scrape_runner.py tests/test_session_guard.py tests/test_scrape_runner.py
git commit -m "feat(captcha): persist preflight diagnostics"
```

---

### Task 4: Persist the latest captcha diagnostic into run state and summary

**Files:**
- Modify: `ali_mvp/run_state.py`
- Modify: `ali_mvp/scrape_runner.py`
- Test: `tests/test_run_state.py`
- Test: `tests/test_scrape_runner.py`

- [ ] **Step 1: Write the failing run state persistence tests**

```python
def test_run_state_round_trip_preserves_captcha_diagnostic(tmp_path):
    store = RunStateStore(tmp_path)
    state = RunState(
        status="blocked",
        captcha_diagnostic={
            "stage": "detail",
            "solver_attempted": True,
            "slider_detected": True,
            "waited_for_ready": True,
            "ready_wait_ms": 900,
            "result": "failed",
            "fail_reason": "gate_not_cleared",
            "page_url": "https://www.aliexpress.com/item/9.html/_____tmd_____/punish?x5step=1",
        },
    )

    store.save_state(state)

    assert store.load_state().captcha_diagnostic == state.captcha_diagnostic


def test_run_state_summary_includes_captcha_diagnostic(tmp_path):
    store = RunStateStore(tmp_path)
    state = RunState(
        status="completed",
        accepted_count=5,
        captcha_diagnostic={
            "stage": "preflight",
            "solver_attempted": True,
            "slider_detected": True,
            "waited_for_ready": True,
            "ready_wait_ms": 850,
            "result": "solved",
            "fail_reason": "",
            "page_url": "https://www.aliexpress.com/wholesale?SearchText=home+appliance+accessories",
        },
    )

    store.save_summary(state)

    assert store.load_summary()["captcha_diagnostic"] == state.captcha_diagnostic
```

- [ ] **Step 2: Run the state persistence tests to confirm they fail**

Run:

```bash
python -m pytest tests/test_run_state.py -q
```

Expected:

```text
FAIL because RunState has no captcha_diagnostic field and summary omits it.
```

- [ ] **Step 3: Add `captcha_diagnostic` to `RunState` and `RunStateStore._build_summary(...)`**

```python
@dataclass(frozen=True)
class RunState:
    status: str = ""
    current_listing_page: int = 0
    raw_products_count: int = 0
    normalized_count: int = 0
    accepted_count: int = 0
    seen_product_keys: list[str] = field(default_factory=list)
    accepted_products: list[ProductRecord] = field(default_factory=list)
    audit_rows: list[dict[str, Any]] = field(default_factory=list)
    pending_detail_queue: list[dict[str, Any]] = field(default_factory=list)
    current_proxy_key: str = ""
    current_proxy_index: int = 0
    block_events_on_current_proxy: int = 0
    last_block_reason: str = ""
    last_blocked_url: str = ""
    session_risk_level: str = "low"
    last_session_preflight_status: str = ""
    consecutive_captcha_count: int = 0
    last_session_ok_at: str = ""
    cooldown_until: str = ""
    identity_warning: dict[str, Any] = field(default_factory=dict)
    captcha_diagnostic: dict[str, Any] = field(default_factory=dict)
    last_error: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunState":
        return cls(
            status=payload.get("status", ""),
            current_listing_page=payload.get("current_listing_page", 0),
            raw_products_count=payload.get("raw_products_count", 0),
            normalized_count=payload.get("normalized_count", 0),
            accepted_count=payload.get("accepted_count", 0),
            seen_product_keys=list(payload.get("seen_product_keys", [])),
            accepted_products=[_deserialize_product_record(item) for item in payload.get("accepted_products", [])],
            audit_rows=list(payload.get("audit_rows", [])),
            pending_detail_queue=_deserialize_pending_detail_queue(payload.get("pending_detail_queue", [])),
            current_proxy_key=payload.get("current_proxy_key", ""),
            current_proxy_index=payload.get("current_proxy_index", 0),
            block_events_on_current_proxy=payload.get("block_events_on_current_proxy", 0),
            last_block_reason=payload.get("last_block_reason", ""),
            last_blocked_url=payload.get("last_blocked_url", ""),
            session_risk_level=payload.get("session_risk_level", "low"),
            last_session_preflight_status=payload.get("last_session_preflight_status", ""),
            consecutive_captcha_count=payload.get("consecutive_captcha_count", 0),
            last_session_ok_at=payload.get("last_session_ok_at", ""),
            cooldown_until=payload.get("cooldown_until", ""),
            identity_warning=_deserialize_identity_warning(payload),
            captcha_diagnostic=_deserialize_captcha_diagnostic(payload.get("captcha_diagnostic")),
            last_error=payload.get("last_error", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "current_listing_page": self.current_listing_page,
            "raw_products_count": self.raw_products_count,
            "normalized_count": self.normalized_count,
            "accepted_count": self.accepted_count,
            "seen_product_keys": list(self.seen_product_keys),
            "accepted_products": [asdict(product) for product in self.accepted_products],
            "audit_rows": list(self.audit_rows),
            "pending_detail_queue": [dict(item) for item in self.pending_detail_queue],
            "current_proxy_key": self.current_proxy_key,
            "current_proxy_index": self.current_proxy_index,
            "block_events_on_current_proxy": self.block_events_on_current_proxy,
            "last_block_reason": self.last_block_reason,
            "last_blocked_url": self.last_blocked_url,
            "session_risk_level": self.session_risk_level,
            "last_session_preflight_status": self.last_session_preflight_status,
            "consecutive_captcha_count": self.consecutive_captcha_count,
            "last_session_ok_at": self.last_session_ok_at,
            "cooldown_until": self.cooldown_until,
            "identity_warning": dict(self.identity_warning),
            "captcha_diagnostic": dict(self.captcha_diagnostic),
            "last_error": self.last_error,
        }


def _deserialize_captcha_diagnostic(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    stage = str(payload.get("stage") or "")
    result = str(payload.get("result") or "")
    if not stage or not result:
        return {}
    return {
        "stage": stage,
        "solver_attempted": bool(payload.get("solver_attempted", False)),
        "slider_detected": bool(payload.get("slider_detected", False)),
        "waited_for_ready": bool(payload.get("waited_for_ready", False)),
        "ready_wait_ms": int(payload.get("ready_wait_ms", 0) or 0),
        "result": result,
        "fail_reason": str(payload.get("fail_reason") or ""),
        "page_url": str(payload.get("page_url") or ""),
    }
```

- [ ] **Step 4: Preserve the latest diagnostic in scrape runner state transitions**

```python
def _extract_captcha_diagnostic(product: dict[str, Any]) -> dict[str, Any]:
    payload = product.get("_captchaDiagnostic")
    return dict(payload) if isinstance(payload, dict) else {}


# inside blocked detail path
blocked_state = replace(
    _with_session_fields(state, state),
    status="blocked",
    normalized_count=normalized_count + normalized_delta,
    accepted_count=len(accepted_products),
    accepted_products=accepted_products,
    audit_rows=audit_rows,
    pending_detail_queue=blocked_queue,
    last_block_reason="captcha_blocked",
    last_blocked_url=_product_url(raw_product),
    captcha_diagnostic=_extract_captcha_diagnostic(raw_product),
)

# inside listing loop checkpoint path
checkpoint_state = _with_session_fields(
    state,
    RunState(
        status="blocked" if blocked else "running",
        current_listing_page=current_page,
        raw_products_count=raw_products_count,
        normalized_count=normalized_count,
        accepted_count=len(accepted_products),
        seen_product_keys=list(seen_key_order),
        accepted_products=list(accepted_products),
        audit_rows=list(audit_rows),
        pending_detail_queue=pending_detail_queue,
        current_proxy_index=proxy_pool.current_index,
        current_proxy_key=proxy_pool.current_key(),
        block_events_on_current_proxy=proxy_pool.block_events_on_current,
        last_block_reason=last_block_reason,
        last_blocked_url=last_blocked_url,
        captcha_diagnostic=(
            _extract_captcha_diagnostic(pending_detail_queue[0])
            if pending_detail_queue
            else dict(state.captcha_diagnostic)
        ),
    ),
)
```

- [ ] **Step 5: Run the run state and scrape runner tests to confirm persistence works**

Run:

```bash
python -m pytest tests/test_run_state.py tests/test_scrape_runner.py -q
```

Expected:

```text
all state/scrape runner tests pass, including new captcha_diagnostic persistence assertions.
```

- [ ] **Step 6: Commit the persistence layer**

```bash
git add ali_mvp/run_state.py ali_mvp/scrape_runner.py tests/test_run_state.py tests/test_scrape_runner.py
git commit -m "feat(captcha): persist latest captcha diagnostic"
```

---

### Task 5: Print one final captcha diagnostic summary line from the CLI

**Files:**
- Modify: `ali_mvp/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI output tests**

```python
def test_run_scrape_prints_captcha_diagnostic_when_present(monkeypatch, tmp_path, capsys):
    fixed_now = datetime.fromisoformat("2026-05-11T08:00:00+00:00")
    args = argparse.Namespace(
        keyword="home appliance accessories",
        url=None,
        category_url=None,
        max_items=1,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        pages=1,
        blacklist_file=None,
        reject_keyword=[],
        browser_hardening="minimal",
        proxy_provider="manual",
        v2rayn_dir="",
        proxy="",
        proxy_file="",
        max_blocks_per_proxy=2,
        user_agent="",
        accept_language="en-US,en;q=0.9",
        session_preflight="on",
        llm_review=False,
        llm_base_url="",
        llm_api_key="",
        llm_model="",
        llm_force=False,
        llm_max_items=None,
    )

    class FakeDateTime:
        @classmethod
        def now(cls):
            return fixed_now

    def fake_run_new_scrape(*, manifest, groups, run_dir):
        run_dir.mkdir(parents=True, exist_ok=True)
        store = RunStateStore(run_dir)
        store.save_state(RunState(
            status="completed",
            accepted_count=1,
            captcha_diagnostic={
                "stage": "detail",
                "solver_attempted": True,
                "slider_detected": True,
                "waited_for_ready": True,
                "ready_wait_ms": 900,
                "result": "failed",
                "fail_reason": "gate_not_cleared",
                "page_url": "https://www.aliexpress.com/item/9.html/_____tmd_____/punish?x5step=1",
            },
        ))
        for name in ("products.csv", "products_filter_audit.csv", "products_review.csv", "category_rank.csv"):
            (run_dir / name).write_text("", encoding="utf-8")
        return cli.scrape_runner.RunResult(exit_code=0, accepted_count=1, blocked=False)

    monkeypatch.setattr(cli, "datetime", FakeDateTime)
    monkeypatch.setattr(cli, "load_filter_groups", lambda path, keywords: [])
    monkeypatch.setattr(cli.scrape_runner, "run_new_scrape", fake_run_new_scrape)

    code = cli.run_scrape(args)
    output = capsys.readouterr().out

    assert code == 0
    assert "Captcha diagnostic: stage=detail result=failed reason=gate_not_cleared slider_detected=true waited_for_ready=true ready_wait_ms=900" in output


def test_run_resume_skips_captcha_diagnostic_line_when_absent(monkeypatch, tmp_path, capsys):
    from ali_mvp.scrape_runner import RunResult

    monkeypatch.setattr(
        "ali_mvp.scrape_runner.resume_scrape",
        lambda *args, **kwargs: RunResult(exit_code=0, accepted_count=7, blocked=False),
    )
    monkeypatch.setattr(cli, "_load_run_state_if_present", lambda run_dir: RunState(status="completed", accepted_count=7))

    args = argparse.Namespace(
        run_dir=str(tmp_path / "run-1"),
        details_only=True,
        proxy="",
        proxy_file="",
        user_agent="",
        accept_language="",
    )

    code = cli.run_resume(args)
    output = capsys.readouterr().out

    assert code == 0
    assert "Captcha diagnostic:" not in output
```

- [ ] **Step 2: Run the CLI output tests to confirm they fail**

Run:

```bash
python -m pytest tests/test_cli.py::test_run_scrape_prints_captcha_diagnostic_when_present tests/test_cli.py::test_run_resume_skips_captcha_diagnostic_line_when_absent -q
```

Expected:

```text
FAIL because CLI does not print captcha diagnostics yet.
```

- [ ] **Step 3: Add a small CLI formatter and call it from both scrape and resume**

```python
def _print_captcha_diagnostic_if_present(run_dir: Path) -> None:
    state = _load_run_state_if_present(run_dir)
    if state is None:
        return
    diagnostic = dict(getattr(state, "captcha_diagnostic", {}) or {})
    if not diagnostic:
        return
    stage = str(diagnostic.get("stage") or "")
    result = str(diagnostic.get("result") or "")
    if not stage or not result:
        return
    reason = str(diagnostic.get("fail_reason") or "") or "-"
    slider_detected = "true" if diagnostic.get("slider_detected") else "false"
    waited_for_ready = "true" if diagnostic.get("waited_for_ready") else "false"
    ready_wait_ms = int(diagnostic.get("ready_wait_ms", 0) or 0)
    print(
        "Captcha diagnostic: "
        f"stage={stage} result={result} reason={reason} "
        f"slider_detected={slider_detected} waited_for_ready={waited_for_ready} ready_wait_ms={ready_wait_ms}"
    )


def run_resume(args: argparse.Namespace) -> int:
    result = scrape_runner.resume_scrape(
        Path(args.run_dir),
        details_only=args.details_only,
        proxy_override=args.proxy,
        proxy_file_override=args.proxy_file,
        user_agent_override=args.user_agent,
        accept_language_override=args.accept_language,
    )
    print(f"Resumed run: {Path(args.run_dir)}")
    print(f"Accepted products: {result.accepted_count}")
    _print_captcha_diagnostic_if_present(Path(args.run_dir))
    return result.exit_code


def run_scrape(args: argparse.Namespace) -> int:
    source_type, source_value, url = _resolve_source(args)
    browser_hardening = getattr(args, "browser_hardening", "minimal")
    proxy_provider = getattr(args, "proxy_provider", "manual")
    v2rayn_dir = getattr(args, "v2rayn_dir", "")
    session_preflight = getattr(args, "session_preflight", "on")
    _validate_llm_max_items(args)
    if args.max_items < 1:
        raise SystemExit("--max-items must be greater than 0")
    if args.pages is not None and args.pages < 1:
        raise SystemExit("--pages must be greater than 0")
    if proxy_provider == "v2rayn" and not v2rayn_dir:
        raise SystemExit("--v2rayn-dir is required when --proxy-provider v2rayn")
    if proxy_provider != "manual" and (args.proxy or args.proxy_file):
        raise SystemExit("--proxy and --proxy-file are only supported with --proxy-provider manual")

    run_at = datetime.now().replace(microsecond=0)
    scraped_at = run_at.astimezone(timezone.utc).isoformat()
    run_dir = build_output_dir(Path(args.output_dir), source_type=source_type, source_value=source_value, run_at=run_at)
    manifest = RunManifest(
        source_type=source_type,
        source_value=source_value,
        url=url,
        max_items=args.max_items,
        pages=args.pages,
        output_dir=str(run_dir),
        user_data_dir=args.user_data_dir,
        port=args.port,
        enrich_detail=args.enrich_detail,
        blacklist_file=args.blacklist_file,
        reject_keyword=list(args.reject_keyword),
        browser_hardening=browser_hardening,
        proxy_provider=proxy_provider,
        v2rayn_dir=v2rayn_dir,
        proxy=args.proxy,
        proxy_file=args.proxy_file,
        max_blocks_per_proxy=args.max_blocks_per_proxy,
        user_agent=args.user_agent,
        accept_language=args.accept_language,
        session_preflight=session_preflight,
        created_at=scraped_at,
    )
    groups = load_filter_groups(args.blacklist_file, args.reject_keyword)

    result = scrape_runner.run_new_scrape(
        manifest=manifest,
        groups=groups,
        run_dir=run_dir,
    )

    state = _load_run_state_if_present(run_dir)
    if state is not None:
        print(f"Scraped raw items: {state.raw_products_count}")
        print(f"Normalized products: {state.normalized_count}")
    print(f"Accepted products: {result.accepted_count}")
    print(f"Wrote: {run_dir / 'products.csv'}")
    print(f"Wrote: {run_dir / 'products_filter_audit.csv'}")
    print(f"Wrote: {run_dir / 'products_review.csv'}")
    print(f"Wrote: {run_dir / 'category_rank.csv'}")
    _print_captcha_diagnostic_if_present(run_dir)
    if result.exit_code == 2:
        print("No accepted products extracted. Check login state, CAPTCHA, selector changes, or blacklist rules.")
    if result.exit_code in (0, 2):
        if not getattr(args, "llm_review", False):
            return result.exit_code
        llm_exit_code = _run_llm_review_after_scrape(run_dir=run_dir, args=args)
        if llm_exit_code is not None:
            return llm_exit_code
        return result.exit_code
    return result.exit_code
```

- [ ] **Step 4: Run the CLI tests to confirm they pass**

Run:

```bash
python -m pytest tests/test_cli.py -q
```

Expected:

```text
all CLI tests pass, including the new captcha summary line assertions.
```

- [ ] **Step 5: Commit the CLI diagnostic output**

```bash
git add ali_mvp/cli.py tests/test_cli.py
git commit -m "feat(captcha): print diagnostic summary"
```

---

### Task 6: Final regression and real-profile smoke validation

**Files:**
- Modify: none
- Test: `tests/test_captcha_solver.py`
- Test: `tests/test_browser.py`
- Test: `tests/test_session_guard.py`
- Test: `tests/test_run_state.py`
- Test: `tests/test_scrape_runner.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Run focused captcha diagnostic regression**

Run:

```bash
python -m pytest tests/test_captcha_solver.py tests/test_browser.py tests/test_session_guard.py tests/test_run_state.py tests/test_scrape_runner.py tests/test_cli.py -q
```

Expected:

```text
all focused captcha diagnostic tests pass.
```

- [ ] **Step 2: Run the full test suite**

Run:

```bash
python -m pytest -q
```

Expected:

```text
full suite passes with 0 failures.
```

- [ ] **Step 3: Run a real-profile smoke using the project profile**

Run:

```bash
python -m ali_mvp scrape --keyword "Home appliance accessories" --max-items 5 --pages 1 --enrich-detail --user-data-dir E:\AliExpress\.browser-profile --output-dir E:\AliExpress\data\captcha_diagnostics_smoke
```

Expected:

```text
If captcha appears during preflight or detail, the run still keeps existing blocked/completed semantics and leaves a latest captcha diagnostic in the run artifacts.
```

- [ ] **Step 4: Inspect the latest smoke artifacts for the persisted diagnostic**

Run:

```bash
python - <<'PY'
import json
from pathlib import Path
run_root = Path(r"E:\AliExpress\data\captcha_diagnostics_smoke")
latest = sorted(run_root.glob("*/*"), key=lambda p: p.name)[-1]
print(latest)
print(json.loads((latest / "run_summary.json").read_text(encoding="utf-8")).get("captcha_diagnostic", {}))
print(json.loads((latest / "run_state.json").read_text(encoding="utf-8")).get("captcha_diagnostic", {}))
PY
```

Expected:

```text
Both files contain the same compact latest captcha_diagnostic payload when a captcha occurred.
```

- [ ] **Step 5: Verify no semantics drift in final outputs**

Run:

```bash
git status --short
```

Expected:

```text
No unexpected files beyond the intended code/test/doc changes and optional smoke output under data/.
```
