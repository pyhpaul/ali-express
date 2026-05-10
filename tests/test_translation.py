import json

from ali_mvp.translation import build_reason_zh, load_translation_cache, summarize_attributes_text, translate_texts


def test_summarize_attributes_returns_first_pairs_from_json():
    text = "{\"Color\":\"Blue\",\"Type\":\"Pad\",\"Material\":\"Rubber\"}"

    summary = summarize_attributes_text(text, limit=2)

    assert summary == "Color: Blue; Type: Pad"


def test_translate_texts_falls_back_to_source_when_backend_raises(tmp_path):
    cache_path = tmp_path / "translation_cache.json"

    rows = translate_texts(
        ["Shock pad"],
        cache_path=cache_path,
        translator=lambda text: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert rows == {"Shock pad": "Shock pad"}


def test_translate_texts_reuses_cache_without_reinvoking_backend(tmp_path):
    cache_path = tmp_path / "translation_cache.json"
    calls = {"count": 0}

    def fake_translator(text: str) -> str:
        calls["count"] += 1
        return "减震垫"

    first = translate_texts(["Shock pad"], cache_path=cache_path, translator=fake_translator)
    second = translate_texts(["Shock pad"], cache_path=cache_path, translator=fake_translator)

    assert first["Shock pad"] == "减震垫"
    assert second["Shock pad"] == "减震垫"
    assert calls["count"] == 1


def test_translate_texts_does_not_cache_fallback_when_backend_raises(tmp_path):
    cache_path = tmp_path / "translation_cache.json"
    calls = {"count": 0}

    def flaky_translator(text: str) -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")
        return "减震垫"

    first = translate_texts(["Shock pad"], cache_path=cache_path, translator=flaky_translator)
    second = translate_texts(["Shock pad"], cache_path=cache_path, translator=flaky_translator)

    assert first["Shock pad"] == "Shock pad"
    assert second["Shock pad"] == "减震垫"
    assert calls["count"] == 2
    assert load_translation_cache(cache_path) == {"Shock pad": "减震垫"}


def test_load_translation_cache_returns_empty_for_invalid_json(tmp_path):
    cache_path = tmp_path / "translation_cache.json"
    cache_path.write_text("{", encoding="utf-8")

    assert load_translation_cache(cache_path) == {}


def test_load_translation_cache_returns_empty_for_non_dict_json(tmp_path):
    cache_path = tmp_path / "translation_cache.json"
    cache_path.write_text(json.dumps(["Shock pad"]), encoding="utf-8")

    assert load_translation_cache(cache_path) == {}


def test_summarize_attributes_returns_empty_for_invalid_inputs():
    assert summarize_attributes_text("{", limit=2) == ""
    assert summarize_attributes_text("[]", limit=2) == ""
    assert summarize_attributes_text("{\"Color\":\"Blue\"}", limit=0) == ""


def test_build_reason_zh_prefers_rule_mapping_over_raw_translation():
    row = {
        "reject_terms": "battery | charger",
        "reject_groups": "electrical_power",
        "warning_terms": "",
        "filter_decision": "rejected",
    }

    assert build_reason_zh(row) == "带电供电类"


def test_build_reason_zh_prefers_canonical_group_mapping_over_terms():
    row = {
        "reject_groups": "electrical_power",
        "warning_groups": "",
        "reject_terms": "power bank | power supply | rechargeable",
        "warning_terms": "",
    }

    assert build_reason_zh(row) == "带电供电类"


def test_build_reason_zh_returns_group_mapping_without_terms():
    row = {
        "reject_groups": "remote_control_device",
        "warning_groups": "",
        "reject_terms": "",
        "warning_terms": "",
    }

    assert build_reason_zh(row) == "遥控控制类"


def test_build_reason_zh_returns_fallback_for_unknown_group_and_terms():
    row = {
        "reject_groups": "unknown_group",
        "warning_groups": "mystery_group",
        "reject_terms": "unknown term",
        "warning_terms": "another mystery",
    }

    assert build_reason_zh(row) == "未命中中文规则说明"


def test_build_reason_zh_normalizes_group_case():
    row = {
        "reject_groups": "ELECTRICAL_POWER",
        "warning_groups": "",
        "reject_terms": "",
        "warning_terms": "",
    }

    assert build_reason_zh(row) == "带电供电类"


def test_build_reason_zh_uses_first_known_group_in_input_order():
    row = {
        "reject_groups": "chip_pcb | electrical_power | remote_control_device",
        "warning_groups": "",
        "reject_terms": "",
        "warning_terms": "",
    }

    assert build_reason_zh(row) == "电子控制或芯片类"


def test_build_reason_zh_falls_back_to_terms_when_group_missing():
    row = {
        "reject_groups": "",
        "warning_groups": "",
        "reject_terms": "relay module | sensor",
        "warning_terms": "",
    }

    assert build_reason_zh(row) == "电子元件或控制器类"
