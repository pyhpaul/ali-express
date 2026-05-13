from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


LLM_USER_AGENT = "ali_mvp/1.0"


@dataclass(frozen=True)
class LlmConfig:
    base_url: str
    api_key: str
    model: str
    provider: str = "openai-compatible"


def _read_dotenv(env_path: Path) -> dict[str, str]:
    if not env_path.exists() or not env_path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        stripped_value = value.strip()
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
) -> LlmConfig:
    dotenv_path = env_path or _find_nearest_dotenv(run_dir)
    env_values = _read_dotenv(dotenv_path) if dotenv_path else {}

    resolved_base_url = base_url or env_values.get("ALI_MVP_LLM_BASE_URL", "")
    resolved_api_key = api_key or env_values.get("ALI_MVP_LLM_API_KEY", "")
    resolved_model = model or env_values.get("ALI_MVP_LLM_MODEL", "")

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
    )


def build_llm_messages(row: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Review the product and return JSON with keys: decision, reason, "
                "risk_tags, confidence, summary_zh."
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

    decision = parsed.get("decision")
    if decision not in {"keep", "drop"}:
        raise ValueError("decision must be one of: keep, drop")

    confidence = parsed.get("confidence")
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
