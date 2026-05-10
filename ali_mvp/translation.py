from __future__ import annotations

import json
import re
from pathlib import Path


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
    ({"remote control", "controller", "pcb", "chip", "pcba", "remote control socket", "gsm gate opener", "relay module", "smart switch", "wifi switch", "zigbee switch"}, "电子元件或控制器类"),
    ({"sensor", "ignition", "timer switch", "relay module", "timing switch", "timer knob", "rotary knob timer"}, "电子元件或控制器类"),
    ({"universal remote control", "air conditioner remote control", "ac remote control", "remote control"}, "遥控控制类"),
    ({"pulse igniter", "gas stove igniter", "igniter"}, "点火控制类"),
    ({"massager", "therapy", "light therapy", "rehabilitation", "stimulation"}, "治疗理疗设备类"),
    ({"steam cleaner"}, "整机清洁设备类"),
    ({"beauty machine", "facial beauty", "electroporation", "skin strengthening"}, "美容仪器设备类"),
    ({"timer switch", "timing switch", "rotary knob timer", "timer knob"}, "定时控制类"),
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


def _build_reason_from_groups(row: dict[str, str]) -> str:
    groups = _split_rule_values(row.get("reject_groups", "")) + _split_rule_values(row.get("warning_groups", ""))
    group_to_label = dict(REASON_ZH_GROUP_RULES)
    for group in groups:
        if group in group_to_label:
            return group_to_label[group]
    return ""


def _build_reason_from_terms(row: dict[str, str]) -> str:
    haystack = " | ".join(
        part
        for part in (
            row.get("reject_terms", ""),
            row.get("warning_terms", ""),
        )
        if part
    ).lower()
    for terms, label in REASON_ZH_TERM_RULES:
        if any(term in haystack for term in terms):
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
