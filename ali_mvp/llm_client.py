from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


LLM_USER_AGENT = "ali_mvp/1.0"
PROJECT_BASE_URL_ENV = "ALI_MVP_LLM_BASE_URL"
PROJECT_API_KEY_ENV = "ALI_MVP_LLM_API_KEY"
PROJECT_MODEL_ENV = "ALI_MVP_LLM_MODEL"
PROJECT_PROFILE_ENV = "ALI_MVP_LLM_PROFILE"
GENERIC_PROFILE_ENV = "LLM_PROFILE"
PROFILES_PATH_ENV = "LLM_PROFILES_PATH"
OPENAI_BASE_URL_ENV = "OPENAI_BASE_URL"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_ENV = "OPENAI_MODEL"


@dataclass(frozen=True)
class LlmConfig:
    base_url: str
    api_key: str
    model: str
    provider: str = "openai-compatible"


@dataclass(frozen=True)
class LlmProfile:
    name: str
    base_url: str
    api_key_env: str
    model: str
    provider: str = "openai-compatible"


def _read_dotenv(env_path: Path) -> dict[str, str]:
    if not env_path.exists() or not env_path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        stripped_value = _strip_inline_comment(value)
        if len(stripped_value) >= 2 and stripped_value[0] == stripped_value[-1] and stripped_value[0] in {"'", '"'}:
            stripped_value = stripped_value[1:-1]
        values[key] = stripped_value
    return values


def _find_nearest_dotenv(start_path: Path) -> Path | None:
    current = start_path.resolve()
    for directory in (current, *current.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def resolve_llm_config(
    run_dir: Path,
    base_url: str,
    api_key: str,
    model: str,
    env_path: Path | None = None,
    profiles_path: Path | None = None,
) -> LlmConfig:
    dotenv_path = env_path or _find_nearest_dotenv(run_dir)
    env_values = _read_dotenv(dotenv_path) if dotenv_path else {}
    environ = os.environ
    profile = _load_selected_profile(env_values, environ, dotenv_path=dotenv_path, profiles_path=profiles_path)
    profile_api_key = _profile_api_key(profile, environ)

    resolved_base_url = _normalize_base_url(
        _first_nonempty(
            base_url,
            env_values.get(PROJECT_BASE_URL_ENV, ""),
            environ.get(PROJECT_BASE_URL_ENV, ""),
            profile.base_url if profile else "",
            environ.get(OPENAI_BASE_URL_ENV, ""),
        )
    )
    resolved_api_key = _first_nonempty(
        api_key,
        env_values.get(PROJECT_API_KEY_ENV, ""),
        environ.get(PROJECT_API_KEY_ENV, ""),
        profile_api_key,
        environ.get(OPENAI_API_KEY_ENV, ""),
    )
    resolved_model = _first_nonempty(
        model,
        env_values.get(PROJECT_MODEL_ENV, ""),
        environ.get(PROJECT_MODEL_ENV, ""),
        profile.model if profile else "",
        environ.get(OPENAI_MODEL_ENV, ""),
    )

    missing: list[str] = []
    if not resolved_base_url:
        missing.append("base_url")
    if not resolved_api_key:
        missing.append("api_key")
    if not resolved_model:
        missing.append("model")
    if missing:
        raise ValueError(f"Missing LLM configuration: {', '.join(missing)}")

    return LlmConfig(
        base_url=resolved_base_url,
        api_key=resolved_api_key,
        model=resolved_model,
        provider=profile.provider if profile else "openai-compatible",
    )


def _load_selected_profile(
    env_values: dict[str, str],
    environ: os._Environ[str],
    *,
    dotenv_path: Path | None,
    profiles_path: Path | None,
) -> LlmProfile | None:
    profile_name = _first_nonempty(
        env_values.get(PROJECT_PROFILE_ENV, ""),
        environ.get(PROJECT_PROFILE_ENV, ""),
        env_values.get(GENERIC_PROFILE_ENV, ""),
        environ.get(GENERIC_PROFILE_ENV, ""),
    )
    if not profile_name:
        return None

    profile_path = _resolve_profiles_path(
        profiles_path,
        dotenv_value=env_values.get(PROFILES_PATH_ENV, ""),
        environ_value=environ.get(PROFILES_PATH_ENV, ""),
        dotenv_path=dotenv_path,
    )
    if profile_path is None:
        raise ValueError(f"LLM profile '{profile_name}' selected but no profiles file was found")
    return _read_profile(profile_name, profile_path)


def _resolve_profiles_path(
    explicit_path: Path | None,
    *,
    dotenv_value: str,
    environ_value: str,
    dotenv_path: Path | None,
) -> Path | None:
    if explicit_path is not None:
        return explicit_path.expanduser()
    if dotenv_value:
        return _profile_path_from_text(dotenv_value, base_dir=dotenv_path.parent if dotenv_path else Path.cwd())
    if environ_value:
        return _profile_path_from_text(environ_value, base_dir=Path.cwd())
    for candidate in _default_profile_paths():
        if candidate.is_file():
            return candidate
    return None


def _default_profile_paths() -> list[Path]:
    paths = [Path.home() / ".config" / "llm-profiles" / "profiles.toml"]
    if os.name != "nt":
        paths.append(Path("/etc/llm-profiles/profiles.toml"))
    return paths


def _profile_path_from_text(raw_path: str, *, base_dir: Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return base_dir / path


def _read_profile(profile_name: str, profiles_path: Path) -> LlmProfile:
    if not profiles_path.is_file():
        raise ValueError(f"LLM profiles file does not exist: {profiles_path}")
    raw = tomllib.loads(profiles_path.read_text(encoding="utf-8"))
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict):
        raise ValueError(f"LLM profiles file has no [profiles] table: {profiles_path}")
    raw_profile = profiles.get(profile_name)
    if not isinstance(raw_profile, dict):
        raise ValueError(f"LLM profile '{profile_name}' not found in {profiles_path}")
    return LlmProfile(
        name=profile_name,
        base_url=_string_value(raw_profile.get("base_url")),
        api_key_env=_string_value(raw_profile.get("api_key_env")),
        model=_string_value(raw_profile.get("model")),
        provider=_string_value(raw_profile.get("provider")) or "openai-compatible",
    )


def _profile_api_key(profile: LlmProfile | None, environ: os._Environ[str]) -> str:
    if profile is None or not profile.api_key_env:
        return ""
    return environ.get(profile.api_key_env, "")


def _string_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_nonempty(*values: str) -> str:
    for value in values:
        text = value.strip()
        if text:
            return text
    return ""


def _normalize_base_url(raw_base_url: str) -> str:
    base_url = raw_base_url.strip().rstrip("/")
    if not base_url:
        return ""
    parsed = urlsplit(base_url)
    path = parsed.path.rstrip("/")
    if path:
        return urlunsplit(parsed._replace(path=path))
    return urlunsplit(parsed._replace(path="/v1"))


def _strip_inline_comment(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""

    in_quote = ""
    chars: list[str] = []
    for index, char in enumerate(value):
        if in_quote:
            chars.append(char)
            if char == in_quote:
                in_quote = ""
            continue
        if char in {"'", '"'}:
            in_quote = char
            chars.append(char)
            continue
        if char == "#" and (index == 0 or value[index - 1].isspace()):
            break
        chars.append(char)
    return "".join(chars).strip()


def build_llm_messages(row: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Review AliExpress products for broad home appliance accessory intake and return JSON only "
                "with keys: decision, reason, risk_tags, confidence, summary_zh. "
                "decision must be keep or drop. "
                "confidence must be high, medium, or low. "
                "risk_tags must be a JSON array of strings. "
                "Default to drop for controller-like, electrical, or active components such as remote control, "
                "controller, chip, circuit board, PCB, battery, motor, ignition control, or wireless module. "
                "Default to keep for passive non-electric accessories that clearly match home appliance accessories, "
                "such as drain pipe, hose, clamp, blade cover, screen protector, glass protector, bracket, or seal. "
                "Do not keep a product only because it mentions an appliance brand or appliance model. "
                "If the product is a powered control device or an electronic control accessory, return drop."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(row, ensure_ascii=False),
        },
    ]


def request_llm_review(
    messages: list[dict[str, str]],
    *,
    config: LlmConfig,
    timeout_seconds: int = 30,
) -> dict[str, object]:
    request = Request(
        f"{config.base_url.rstrip('/')}/chat/completions",
        data=json.dumps(
            {
                "model": config.model,
                "messages": messages,
                "temperature": 0,
                "stream": False,
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "User-Agent": LLM_USER_AGENT,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"LLM review HTTP error {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"LLM review network error: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM review returned invalid JSON") from exc

    return normalize_llm_review_response(payload)


def normalize_llm_review_response(payload: dict[str, object]) -> dict[str, object]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LLM response missing choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("LLM response choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("LLM response missing message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM response missing content")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response content must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM response content must be a JSON object")

    decision = _normalize_decision(parsed.get("decision"))
    if decision not in {"keep", "drop"}:
        raise ValueError("decision must be one of: keep, drop")

    confidence = _normalize_confidence(parsed.get("confidence"))
    if confidence not in {"high", "medium", "low"}:
        raise ValueError("confidence must be one of: high, medium, low")

    risk_tags = parsed.get("risk_tags")
    if not isinstance(risk_tags, list):
        raise ValueError("risk_tags must be a list")

    return {
        "decision": decision,
        "reason": str(parsed.get("reason", "")),
        "risk_tags": [str(tag) for tag in risk_tags],
        "confidence": confidence,
        "summary_zh": str(parsed.get("summary_zh", "")),
    }


def _normalize_decision(raw_decision: object) -> str:
    decision = str(raw_decision or "").strip().lower()
    if decision == "reject":
        return "drop"
    return decision


def _normalize_confidence(raw_confidence: object) -> str:
    if isinstance(raw_confidence, str):
        normalized = raw_confidence.strip().lower()
        if normalized in {"high", "medium", "low"}:
            return normalized
        try:
            raw_confidence = float(normalized)
        except ValueError:
            return normalized
    if isinstance(raw_confidence, (int, float)):
        if raw_confidence >= 0.8:
            return "high"
        if raw_confidence >= 0.5:
            return "medium"
        return "low"
    return str(raw_confidence or "").strip().lower()
