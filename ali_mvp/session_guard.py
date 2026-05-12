from __future__ import annotations

from dataclasses import dataclass

from .browser import collect_session_signals, warm_up_search_session


@dataclass(frozen=True)
class SessionPreflightResult:
    status: str
    risk_level: str
    page_type: str
    reasons: list[str]
    warmed_up: bool


def run_session_preflight(page, *, search_url: str, warm_up: bool) -> SessionPreflightResult:
    payload = _collect_session_signals(page, search_url=search_url)
    page_type = str(payload.get("pageType") or "")
    reasons: list[str] = []
    status = "ready"
    risk_level = "low"

    if bool(payload.get("captcha")):
        status = "captcha_blocked"
        risk_level = "high"
        reasons.append("captcha")
    elif bool(payload.get("phoneVerifyRequired")):
        status = "phone_verification_required"
        risk_level = "high"
        reasons.append("phone_verification_required")
    elif bool(payload.get("loginRequired")):
        status = "login_required"
        risk_level = "high"
        reasons.append("login_required")
    elif not bool(payload.get("searchResultsVisible")):
        status = "search_not_ready"
        risk_level = "medium"
        reasons.append("search_not_ready")

    warmed_up = False
    if status == "ready" and warm_up:
        _run_warm_up(page, search_url=search_url)
        warmed_up = True

    return SessionPreflightResult(
        status=status,
        risk_level=risk_level,
        page_type=page_type,
        reasons=reasons,
        warmed_up=warmed_up,
    )


def _collect_session_signals(page, *, search_url: str) -> dict[str, object]:
    if hasattr(page, "run_js"):
        return collect_session_signals(page)

    current_url = str(getattr(page, "url", "") or search_url)
    is_search_page = "wholesale" in current_url or "SearchText" in current_url
    is_verify_page = "login" in current_url or "verify" in current_url or "phone" in current_url
    return {
        "pageType": "search" if is_search_page else ("verify" if is_verify_page else "unknown"),
        "captcha": False,
        "loginRequired": False,
        "phoneVerifyRequired": "phone" in current_url,
        "searchResultsVisible": is_search_page,
    }


def _run_warm_up(page, *, search_url: str) -> None:
    del search_url
    if not hasattr(page, "run_js"):
        return
    warm_up_search_session(page)
