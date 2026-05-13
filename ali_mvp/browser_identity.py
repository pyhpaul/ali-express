from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Sequence
import re
from typing import Any


@dataclass(frozen=True)
class BrowserIdentityWarning:
    code: str
    configured: dict[str, Any] = field(default_factory=dict)
    effective: dict[str, Any] = field(default_factory=dict)


def validate_browser_identity(
    *,
    configured_user_agent: str,
    configured_accept_language: str,
    effective_user_agent: str,
    effective_language: str,
    effective_languages: list[str] | None,
) -> BrowserIdentityWarning | None:
    configured_major = _extract_chrome_major(configured_user_agent)
    effective_major = _extract_chrome_major(effective_user_agent)
    if configured_major is not None and effective_major is not None and configured_major != effective_major:
        return BrowserIdentityWarning(
            code="user_agent_major_mismatch",
            configured={"user_agent_major": configured_major},
            effective={"user_agent_major": effective_major},
        )

    configured_primary = _accept_language_primary(configured_accept_language)
    effective_primary = _effective_primary_language(effective_language, effective_languages)
    if configured_primary and effective_primary and configured_primary.lower() != effective_primary.lower():
        return BrowserIdentityWarning(
            code="accept_language_mismatch",
            configured={"accept_language_primary": configured_primary},
            effective={"navigator_language": effective_primary},
        )

    return None


def _extract_chrome_major(user_agent: str) -> int | None:
    match = re.search(r"(?:Chrome|CriOS)/(\d+)", str(user_agent or ""))
    if match is None:
        return None
    return int(match.group(1))


def _accept_language_primary(value: str) -> str:
    primary = str(value or "").split(",", 1)[0].strip()
    if ";" in primary:
        primary = primary.split(";", 1)[0].strip()
    return primary


def _effective_primary_language(language: str, languages: list[str] | None) -> str:
    primary = str(language or "").strip()
    if primary:
        return primary
    if not isinstance(languages, Sequence) or isinstance(languages, (str, bytes)):
        return ""
    for item in languages:
        candidate = str(item or "").strip()
        if candidate:
            return candidate
    return ""
