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
    initial_payload = collect_session_signals(page)
    initial_result = _classify_session_payload(initial_payload)
    if initial_result.status in {"captcha_blocked", "phone_verification_required", "login_required"}:
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


def _classify_session_payload(payload: dict[str, object]) -> SessionPreflightResult:
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

    return SessionPreflightResult(
        status=status,
        risk_level=risk_level,
        page_type=page_type,
        reasons=reasons,
        warmed_up=False,
    )


def _run_warm_up(page, *, search_url: str) -> None:
    del search_url
    warm_up_search_session(page)
