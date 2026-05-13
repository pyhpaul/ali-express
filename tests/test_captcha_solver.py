from __future__ import annotations

from ali_mvp import captcha_solver


class FakePage:
    def __init__(
        self,
        *,
        js_result=None,
        url: str = "https://www.aliexpress.com/verify",
        title: str = "",
        button=None,
    ):
        self._js_result = js_result
        self.url = url
        self.title = title
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


def test_generate_slider_trajectory_scales_beyond_the_old_step_cap(monkeypatch):
    monkeypatch.setattr(captcha_solver.random, "randint", lambda a, b: a)
    monkeypatch.setattr(captcha_solver.random, "uniform", lambda a, b: 0.0)

    trajectory = captcha_solver._generate_slider_trajectory(1000)

    assert len(trajectory) > 100
    assert trajectory[-1]["x"] == 1000
    assert trajectory[-1]["x"] - trajectory[-2]["x"] <= 20


def test_perform_slider_drag_releases_even_when_move_raises(monkeypatch):
    class FakeActions:
        def __init__(self, page):
            self.calls: list[tuple[str, object]] = []

        def move_to(self, slider_button):
            self.calls.append(("move_to", slider_button))

        def hold(self, slider_button):
            self.calls.append(("hold", slider_button))

        def move(self, dx, dy, duration=0.01):
            self.calls.append(("move", (dx, dy, duration)))
            raise RuntimeError("boom")

        def release(self, slider_button):
            self.calls.append(("release", slider_button))

    fake_actions = FakeActions(None)
    monkeypatch.setattr(captcha_solver, "Actions", lambda page: fake_actions)

    try:
        captcha_solver._perform_slider_drag(FakePage(), object(), [{"x": 1, "y": 0, "delay": 0}])
    except RuntimeError:
        pass

    assert any(name == "release" for name, _ in fake_actions.calls)


def test_solve_slider_captcha_returns_false_when_slider_disappears_but_page_is_still_blocked(monkeypatch):
    page = FakePage(
        js_result=False,
        url="https://www.aliexpress.com/verify?x5step=1",
        title="verify",
        button=object(),
    )
    monkeypatch.setattr(captcha_solver, "_get_slider_distance", lambda page: 60)
    monkeypatch.setattr(captcha_solver, "_generate_slider_trajectory", lambda distance: [{"x": distance, "y": 0, "delay": 0}])
    monkeypatch.setattr(captcha_solver, "_perform_slider_drag", lambda page, slider_button, trajectory: None)
    monkeypatch.setattr(captcha_solver.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(captcha_solver, "is_slider_captcha", lambda page: False)

    assert captcha_solver._solve_slider_captcha(page, timeout_seconds=0.01) is False


def test_solve_slider_captcha_returns_true_only_after_gate_is_cleared(monkeypatch):
    page = FakePage(
        js_result=False,
        url="https://www.aliexpress.com/verify?x5step=1",
        title="verify",
        button=object(),
    )
    monkeypatch.setattr(captcha_solver, "_get_slider_distance", lambda page: 60)
    monkeypatch.setattr(captcha_solver, "_generate_slider_trajectory", lambda distance: [{"x": distance, "y": 0, "delay": 0}])
    monkeypatch.setattr(captcha_solver, "_perform_slider_drag", lambda page, slider_button, trajectory: None)

    def clear_gate(seconds):
        page.url = "https://www.aliexpress.com/item/1.html"
        page.title = "product"
        return None

    monkeypatch.setattr(captcha_solver.time, "sleep", clear_gate)
    monkeypatch.setattr(captcha_solver, "is_slider_captcha", lambda page: False)

    assert captcha_solver._solve_slider_captcha(page, timeout_seconds=0.01) is True


def test_solve_slider_captcha_returns_false_when_gate_remains_blocked(monkeypatch):
    page = FakePage(
        js_result=True,
        url="https://www.aliexpress.com/verify?x5step=1",
        title="verify",
        button=object(),
    )
    monkeypatch.setattr(captcha_solver, "_get_slider_distance", lambda page: 60)
    monkeypatch.setattr(captcha_solver, "_generate_slider_trajectory", lambda distance: [{"x": distance, "y": 0, "delay": 0}])
    monkeypatch.setattr(captcha_solver, "_perform_slider_drag", lambda page, slider_button, trajectory: None)
    monkeypatch.setattr(captcha_solver.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(captcha_solver, "is_slider_captcha", lambda page: True)

    assert captcha_solver._solve_slider_captcha(page, timeout_seconds=0.01) is False


def test_is_verification_gate_page_ignores_normal_phone_words():
    page = FakePage(
        url="https://www.aliexpress.com/wholesale?SearchText=phone+case",
        title="iphone case",
    )

    assert captcha_solver._is_verification_gate_page(page) is False


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
