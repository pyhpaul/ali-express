from __future__ import annotations

import json
from pathlib import Path


REASON_ZH_RULES = (
    ({"battery", "lithium", "charger", "power adapter"}, "带电供电类"),
    ({"remote control", "controller", "pcb", "chip", "pcba"}, "电子控制或芯片类"),
    ({"sensor", "ignition", "timer switch", "relay module"}, "电子元件或控制器类"),
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


def build_reason_zh(row: dict[str, str]) -> str:
    haystack = " | ".join(
        part
        for part in (
            row.get("reject_terms", ""),
            row.get("warning_terms", ""),
            row.get("reject_groups", ""),
        )
        if part
    ).lower()
    for terms, label in REASON_ZH_RULES:
        if any(term in haystack for term in terms):
            return label
    return "未命中中文规则说明"


def load_translation_cache(cache_path: Path) -> dict[str, str]:
    if not cache_path.exists():
        return {}
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    cache: dict[str, str] = {}
    for key, value in raw.items():
        cache[str(key)] = str(value)
    return cache


def save_translation_cache(cache_path: Path, cache: dict[str, str]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def translate_texts(texts: list[str], *, cache_path: Path, translator) -> dict[str, str]:
    cache = load_translation_cache(cache_path)
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
        cache[text] = translated or text
        result[text] = cache[text]
    save_translation_cache(cache_path, cache)
    return result
