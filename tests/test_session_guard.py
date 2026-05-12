from __future__ import annotations

from ali_mvp.session_guard import SessionPreflightResult, run_session_preflight


class FakePage:
    def __init__(self, url: str, payload: dict[str, object]) -> None:
        self.url = url
        self._payload = payload
        self.js_calls: list[str] = []

    def run_js(self, script: str):
        self.js_calls.append(script)
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
