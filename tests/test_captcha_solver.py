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
