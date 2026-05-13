from __future__ import annotations

from ali_mvp.session_guard import SessionPreflightResult, run_session_preflight


class FakePage:
    def __init__(self, url: str, payload: dict[str, object] | list[dict[str, object]]) -> None:
        self.url = url
        self._payload = payload
        self.js_calls: list[str] = []
        self.warm_up_calls = 0

    def run_js(self, script: str):
        self.js_calls.append(script)
        if isinstance(self._payload, list):
            index = min(len(self.js_calls) - 1, len(self._payload) - 1)
            return dict(self._payload[index])
        return dict(self._payload)


def test_run_session_preflight_classifies_ready_page():
    page = FakePage(
        "https://www.aliexpress.com/wholesale?SearchText=home+appliance+accessories",
        {
            "pageType": "search",
            "captcha": False,
            "loginRequired": False,
            "phoneVerifyRequired": False,
            "searchResultsVisible": True,
        },
    )

    result = run_session_preflight(page, search_url=page.url, warm_up=False)

    assert result == SessionPreflightResult(
        status="ready",
        risk_level="low",
        page_type="search",
        reasons=[],
        warmed_up=False,
    )


def test_run_session_preflight_classifies_phone_verification():
    page = FakePage(
        "https://login.aliexpress.com/phone",
        {
            "pageType": "verify",
            "captcha": False,
            "loginRequired": False,
            "phoneVerifyRequired": True,
            "searchResultsVisible": False,
        },
    )

    result = run_session_preflight(
        page,
        search_url="https://www.aliexpress.com/wholesale?SearchText=home+appliance+accessories",
        warm_up=False,
    )

    assert result.status == "phone_verification_required"
    assert result.risk_level == "high"
    assert result.reasons == ["phone_verification_required"]


def test_run_session_preflight_warm_up_rechecks_search_readiness():
    page = FakePage(
        "https://www.aliexpress.com/wholesale?SearchText=home+appliance+accessories",
        [
            {
                "pageType": "search",
                "captcha": False,
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

    result = run_session_preflight(page, search_url=page.url, warm_up=True)

    assert result == SessionPreflightResult(
        status="ready",
        risk_level="low",
        page_type="search",
        reasons=[],
        warmed_up=True,
    )
    assert len(page.js_calls) == 4


def test_run_session_preflight_classifies_captcha_without_warm_up():
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

    result = run_session_preflight(page, search_url=page.url, warm_up=True)

    assert result == SessionPreflightResult(
        status="captcha_blocked",
        risk_level="high",
        page_type="search",
        reasons=["captcha"],
        warmed_up=False,
    )


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
