from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
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
) -> LlmConfig:
    dotenv_path = env_path or _find_nearest_dotenv(run_dir)
    env_values = _read_dotenv(dotenv_path) if dotenv_path else {}

    resolved_base_url = _normalize_base_url(base_url or env_values.get("ALI_MVP_LLM_BASE_URL", ""))
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
