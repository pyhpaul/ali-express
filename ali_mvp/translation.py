from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REASON_ZH_GROUP_RULES = (
    ("electrical_power", "带电供电类"),
    ("relay_switch_sensor", "电子元件或控制器类"),
    ("chip_pcb", "电子控制或芯片类"),
    ("remote_control_device", "遥控控制类"),
    ("ignition_control", "点火控制类"),
    ("medical_therapy", "治疗理疗设备类"),
    ("steam_cleaner_device", "整机清洁设备类"),
    ("beauty_device", "美容仪器设备类"),
    ("appliance_timer_switch", "定时控制类"),
)

REASON_ZH_TERM_RULES = (
    ({"battery", "lithium", "charger", "power adapter", "power bank", "power supply", "rechargeable"}, "带电供电类"),
    ({"remote control", "universal remote control", "air conditioner remote control", "ac remote control"}, "遥控控制类"),
    ({"controller", "pcb", "chip", "pcba", "remote control socket", "gsm gate opener", "relay module", "smart switch", "wifi switch", "zigbee switch", "sensor"}, "电子元件或控制器类"),
    ({"igniter", "pulse igniter", "gas stove igniter"}, "点火控制类"),
    ({"timer switch", "timing switch", "rotary knob timer", "timer knob"}, "定时控制类"),
    ({"massager", "therapy", "light therapy", "rehabilitation", "stimulation"}, "治疗理疗设备类"),
    ({"steam cleaner"}, "整机清洁设备类"),
    ({"beauty machine", "facial beauty", "electroporation", "skin strengthening"}, "美容仪器设备类"),
)


def summarize_attributes_text(raw_text: str, limit: int = 3) -> str:
    try:
        parsed = json.loads(raw_text) if raw_text else {}
    except json.JSONDecodeError:
        return ""
    if not isinstance(parsed, dict):
        return ""
    parts = []
    for key, value in list(parsed.items())[:limit]:
        if str(key).strip() and str(value).strip():
            parts.append(f"{key}: {value}")
    return "; ".join(parts)


def _split_rule_values(raw_value: str) -> list[str]:
    if not raw_value:
        return []
    return [part.strip().lower() for part in re.split(r"[|,;\n]+", raw_value) if part.strip()]


def _build_term_to_label_map() -> dict[str, str]:
    term_to_label: dict[str, str] = {}
    for terms, label in REASON_ZH_TERM_RULES:
        for term in terms:
            term_to_label.setdefault(term, label)
    return term_to_label


TERM_TO_REASON_ZH = _build_term_to_label_map()
MYMEMORY_API_URL = "https://api.mymemory.translated.net/get"
TRANSLATION_HTTP_TIMEOUT_SECONDS = 15
TRANSLATION_USER_AGENT = "ali_mvp/1.0"


def _build_reason_from_groups(row: dict[str, str]) -> str:
    groups = _split_rule_values(row.get("reject_groups", "")) + _split_rule_values(row.get("warning_groups", ""))
    group_to_label = dict(REASON_ZH_GROUP_RULES)
    for group in groups:
        if group in group_to_label:
            return group_to_label[group]
    return ""


def _build_reason_from_terms(row: dict[str, str]) -> str:
    tokens = _split_rule_values(row.get("reject_terms", "")) + _split_rule_values(row.get("warning_terms", ""))
    for token in tokens:
        label = TERM_TO_REASON_ZH.get(token)
        if label:
            return label
    return ""


def build_reason_zh(row: dict[str, str]) -> str:
    group_reason = _build_reason_from_groups(row)
    if group_reason:
        return group_reason
    term_reason = _build_reason_from_terms(row)
    if term_reason:
        return term_reason
    return "未命中中文规则说明"


def load_translation_cache(cache_path: Path) -> dict[str, str]:
    raw_payload = load_translation_cache_payload(cache_path)
    return _coerce_cache_namespace(raw_payload, "default")


def save_translation_cache(cache_path: Path, cache: dict[str, str]) -> None:
    save_translation_cache_payload(cache_path, cache)


def build_translator(provider: str, *, email: str = ""):
    normalized = provider.strip().lower()
    if normalized == "identity":
        return lambda text: text
    if normalized == "mymemory":
        return lambda text: mymemory_translate_text(text, email=email)
    raise ValueError(f"Unsupported translator provider: {provider}")


def build_translation_cache_namespace(provider: str) -> str:
    normalized = provider.strip().lower()
    if not normalized:
        return "default"
    return normalized


def mymemory_translate_text(text: str, *, email: str = "") -> str:
    query = {
        "q": text,
        "langpair": "en|zh-CN",
    }
    if email:
        query["de"] = email
    request = Request(
        f"{MYMEMORY_API_URL}?{urlencode(query)}",
        headers={"User-Agent": TRANSLATION_USER_AGENT},
    )
    try:
        with urlopen(request, timeout=TRANSLATION_HTTP_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"MyMemory translation HTTP error {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"MyMemory translation network error: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("MyMemory translation returned invalid JSON") from exc

    status = payload.get("responseStatus")
    if status != 200:
        details = str(payload.get("responseDetails", "")).strip() or "unknown error"
        raise RuntimeError(f"MyMemory translation failed with status {status}: {details}")
    response_data = payload.get("responseData")
    if not isinstance(response_data, dict):
        raise RuntimeError("MyMemory translation response missing responseData")
    translated_text = response_data.get("translatedText")
    if not isinstance(translated_text, str) or not translated_text.strip():
        raise RuntimeError("MyMemory translation response missing translatedText")
    return translated_text


def translate_texts(texts: list[str], *, cache_path: Path, translator, cache_namespace: str = "default") -> dict[str, str]:
    raw_cache = load_translation_cache_payload(cache_path)
    cache = _coerce_cache_namespace(raw_cache, cache_namespace)
    result: dict[str, str] = {}
    for text in texts:
        if not text:
            result[text] = ""
            continue
        if text in cache:
            result[text] = cache[text]
            continue
        try:
            translated = translator(text)
        except Exception:
            result[text] = text
            continue
        if translated is None:
            translated_text = text
        elif isinstance(translated, str):
            translated_text = translated or text
        else:
            result[text] = text
            continue
        cache[text] = translated_text
        result[text] = cache[text]
    if cache:
        raw_cache[cache_namespace] = cache
    elif cache_namespace in raw_cache:
        del raw_cache[cache_namespace]
    save_translation_cache_payload(cache_path, raw_cache)
    return result


def load_translation_cache_payload(cache_path: Path) -> dict[str, object]:
    if not cache_path.exists():
        return {}
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return raw


def save_translation_cache_payload(cache_path: Path, cache: dict[str, object]) -> None:
    normalized = _normalize_translation_cache_payload(cache)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _coerce_cache_namespace(raw_cache: dict[str, object], cache_namespace: str) -> dict[str, str]:
    namespaced = raw_cache.get(cache_namespace)
    if isinstance(namespaced, dict):
        return {str(key): str(value) for key, value in namespaced.items()}
    legacy_entries = {
        str(key): str(value)
        for key, value in raw_cache.items()
        if isinstance(value, str)
    }
    if cache_namespace == "default":
        return legacy_entries
    return {}


def _normalize_translation_cache_payload(raw_cache: dict[str, object]) -> dict[str, dict[str, str]]:
    normalized: dict[str, dict[str, str]] = {}
    legacy_entries = {
        str(key): str(value)
        for key, value in raw_cache.items()
        if isinstance(value, str)
    }
    if legacy_entries:
        normalized["default"] = legacy_entries
    for key, value in raw_cache.items():
        if not isinstance(value, dict):
            continue
        normalized_entries = {str(entry_key): str(entry_value) for entry_key, entry_value in value.items()}
        if normalized_entries:
            normalized[str(key)] = normalized_entries
    return normalized
