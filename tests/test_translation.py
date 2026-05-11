import json
from urllib.error import HTTPError

import pytest

from ali_mvp.translation import (
    build_reason_zh,
    build_translator,
    load_translation_cache,
    mymemory_translate_text,
    summarize_attributes_text,
    translate_texts,
)


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


def test_translate_texts_falls_back_without_caching_when_backend_returns_non_string(tmp_path):
    cache_path = tmp_path / "translation_cache.json"

    rows = translate_texts(
        ["Shock pad"],
        cache_path=cache_path,
        translator=lambda text: 123,
    )

    assert rows == {"Shock pad": "Shock pad"}
    assert load_translation_cache(cache_path) == {}


def test_translate_texts_isolates_cache_by_namespace(tmp_path):
    cache_path = tmp_path / "translation_cache.json"

    first = translate_texts(
        ["Shock pad"],
        cache_path=cache_path,
        translator=lambda text: text,
        cache_namespace="identity",
    )
    second = translate_texts(
        ["Shock pad"],
        cache_path=cache_path,
        translator=lambda text: "减震垫",
        cache_namespace="mymemory",
    )

    assert first["Shock pad"] == "Shock pad"
    assert second["Shock pad"] == "减震垫"


def test_translate_texts_rewrites_legacy_flat_cache_to_default_namespace(tmp_path):
    cache_path = tmp_path / "translation_cache.json"
    cache_path.write_text(
        json.dumps({"Shock pad": "减震垫"}, ensure_ascii=False),
        encoding="utf-8",
    )
    calls = {"count": 0}

    def fake_translator(text: str) -> str:
        calls["count"] += 1
        return "不应被调用"

    rows = translate_texts(
        ["Shock pad"],
        cache_path=cache_path,
        translator=fake_translator,
    )
    payload = json.loads(cache_path.read_text(encoding="utf-8"))

    assert rows == {"Shock pad": "减震垫"}
    assert calls["count"] == 0
    assert payload == {"default": {"Shock pad": "减震垫"}}


def test_translate_texts_normalizes_mixed_legacy_and_namespaced_cache_payload(tmp_path):
    cache_path = tmp_path / "translation_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "Shock pad": "Shock pad",
                "Store A": "Store A",
                "mymemory": {
                    "Shock pad": "减震垫",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    calls = {"count": 0}

    def fake_translator(text: str) -> str:
        calls["count"] += 1
        return "店铺A"

    rows = translate_texts(
        ["Shock pad", "Store A"],
        cache_path=cache_path,
        translator=fake_translator,
        cache_namespace="mymemory",
    )
    payload = json.loads(cache_path.read_text(encoding="utf-8"))

    assert rows == {
        "Shock pad": "减震垫",
        "Store A": "店铺A",
    }
    assert calls["count"] == 1
    assert payload == {
        "default": {
            "Shock pad": "Shock pad",
            "Store A": "Store A",
        },
        "mymemory": {
            "Shock pad": "减震垫",
            "Store A": "店铺A",
        },
    }


def test_build_translator_returns_identity_translator():
    translator = build_translator("identity")

    assert translator("Shock pad") == "Shock pad"


def test_build_translator_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported translator provider: unknown"):
        build_translator("unknown")


def test_mymemory_translate_text_extracts_translated_text(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "responseData": {
                        "translatedText": "减震垫",
                    },
                    "responseStatus": 200,
                }
            ).encode("utf-8")

    captured: dict[str, str] = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["user_agent"] = request.get_header("User-agent")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("ali_mvp.translation.urlopen", fake_urlopen)

    translated = mymemory_translate_text("Shock pad", email="test@example.com")

    assert translated == "减震垫"
    assert "q=Shock+pad" in captured["url"]
    assert "langpair=en%7Czh-CN" in captured["url"]
    assert "de=test%40example.com" in captured["url"]
    assert captured["user_agent"] == "ali_mvp/1.0"
    assert captured["timeout"] == 15


def test_mymemory_translate_text_raises_for_non_200_response_status(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "responseData": {
                        "translatedText": "减震垫",
                    },
                    "responseStatus": 429,
                    "responseDetails": "rate limit",
                }
            ).encode("utf-8")

    monkeypatch.setattr("ali_mvp.translation.urlopen", lambda request, timeout: FakeResponse())

    with pytest.raises(RuntimeError, match="MyMemory translation failed with status 429: rate limit"):
        mymemory_translate_text("Shock pad")


def test_mymemory_translate_text_raises_for_missing_translated_text(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "responseData": {},
                    "responseStatus": 200,
                }
            ).encode("utf-8")

    monkeypatch.setattr("ali_mvp.translation.urlopen", lambda request, timeout: FakeResponse())

    with pytest.raises(RuntimeError, match="MyMemory translation response missing translatedText"):
        mymemory_translate_text("Shock pad")


def test_mymemory_translate_text_wraps_http_errors(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 503, "Service Unavailable", hdrs=None, fp=None)

    monkeypatch.setattr("ali_mvp.translation.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="MyMemory translation HTTP error 503: Service Unavailable"):
        mymemory_translate_text("Shock pad")


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


@pytest.mark.parametrize(
    ("reject_terms", "expected"),
    [
        ("remote control", "遥控控制类"),
        ("ac remote control", "遥控控制类"),
        ("timer switch", "定时控制类"),
        ("rotary knob timer", "定时控制类"),
    ],
)
def test_build_reason_zh_uses_exact_term_fallback_without_group(reject_terms, expected):
    row = {
        "reject_groups": "",
        "warning_groups": "",
        "reject_terms": reject_terms,
        "warning_terms": "",
    }

    assert build_reason_zh(row) == expected
