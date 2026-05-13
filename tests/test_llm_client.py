import json
from pathlib import Path

import pytest

from ali_mvp.llm_client import (
    LlmConfig,
    build_llm_messages,
    normalize_llm_review_response,
    request_llm_review,
    resolve_llm_config,
)


def test_resolve_llm_config_prefers_cli_over_dotenv(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "ALI_MVP_LLM_BASE_URL=https://env.example/v1",
                "ALI_MVP_LLM_API_KEY=env-key",
                "ALI_MVP_LLM_MODEL=env-model",
            ]
        ),
        encoding="utf-8",
    )

    config = resolve_llm_config(
        tmp_path / "data" / "slug" / "20260513-120000",
        base_url="https://cli.example/v1",
        api_key="cli-key",
        model="cli-model",
        env_path=env_path,
    )

    assert config == LlmConfig(
        base_url="https://cli.example/v1",
        api_key="cli-key",
        model="cli-model",
        provider="openai-compatible",
    )


def test_resolve_llm_config_raises_when_required_values_missing(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="Missing LLM configuration: base_url, api_key, model"):
        resolve_llm_config(
            tmp_path / "data" / "slug" / "20260513-120000",
            base_url="",
            api_key="",
            model="",
            env_path=env_path,
        )


def test_resolve_llm_config_searches_upward_for_nearest_dotenv(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                'ALI_MVP_LLM_BASE_URL="https://env.example/v1"',
                "ALI_MVP_LLM_API_KEY='env-key'",
                "ALI_MVP_LLM_MODEL=env-model",
            ]
        ),
        encoding="utf-8",
    )
    run_dir = tmp_path / "data" / "slug" / "20260513-120000"
    run_dir.mkdir(parents=True)

    config = resolve_llm_config(
        run_dir,
        base_url="",
        api_key="",
        model="",
    )

    assert config == LlmConfig(
        base_url="https://env.example/v1",
        api_key="env-key",
        model="env-model",
        provider="openai-compatible",
    )


def test_resolve_llm_config_appends_v1_when_provider_base_url_has_no_api_prefix(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "ALI_MVP_LLM_BASE_URL=https://env.example/",
                "ALI_MVP_LLM_API_KEY=env-key",
                "ALI_MVP_LLM_MODEL=env-model",
            ]
        ),
        encoding="utf-8",
    )

    config = resolve_llm_config(
        tmp_path / "data" / "slug" / "20260513-120000",
        base_url="",
        api_key="",
        model="",
        env_path=env_path,
    )

    assert config == LlmConfig(
        base_url="https://env.example/v1",
        api_key="env-key",
        model="env-model",
        provider="openai-compatible",
    )


def test_resolve_llm_config_preserves_non_root_provider_path(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "ALI_MVP_LLM_BASE_URL=https://env.example/openai-compatible/",
                "ALI_MVP_LLM_API_KEY=env-key",
                "ALI_MVP_LLM_MODEL=env-model",
            ]
        ),
        encoding="utf-8",
    )

    config = resolve_llm_config(
        tmp_path / "data" / "slug" / "20260513-120000",
        base_url="",
        api_key="",
        model="",
        env_path=env_path,
    )

    assert config == LlmConfig(
        base_url="https://env.example/openai-compatible",
        api_key="env-key",
        model="env-model",
        provider="openai-compatible",
    )


def test_resolve_llm_config_supports_utf8_sig_export_and_inline_comments(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "\ufeffexport ALI_MVP_LLM_BASE_URL=https://env.example/v1 # provider endpoint",
                "export ALI_MVP_LLM_API_KEY='env-key' # secret",
                'ALI_MVP_LLM_MODEL="env-model" # selected model',
            ]
        ),
        encoding="utf-8",
    )

    config = resolve_llm_config(
        tmp_path / "data" / "slug" / "20260513-120000",
        base_url="",
        api_key="",
        model="",
        env_path=env_path,
    )

    assert config == LlmConfig(
        base_url="https://env.example/v1",
        api_key="env-key",
        model="env-model",
        provider="openai-compatible",
    )


def test_resolve_llm_config_ignores_dotenv_directory(tmp_path: Path):
    (tmp_path / ".env").mkdir()

    with pytest.raises(ValueError, match="Missing LLM configuration: base_url, api_key, model"):
        resolve_llm_config(
            tmp_path / "data" / "slug" / "20260513-120000",
            base_url="",
            api_key="",
            model="",
        )


def test_request_llm_review_parses_json_string_content(monkeypatch):
    response_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "decision": "keep",
                            "reason": "Non-electric appliance accessory.",
                            "risk_tags": [],
                            "confidence": "high",
                            "summary_zh": "非带电家电配件，可入库。",
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(response_payload, ensure_ascii=False).encode("utf-8")

    def fake_urlopen(request, timeout):
        assert request.full_url == "https://api.example/v1/chat/completions"
        assert request.get_header("Authorization") == "Bearer test-key"
        assert request.get_header("Content-type") == "application/json"
        body = json.loads(request.data.decode("utf-8"))
        assert body["model"] == "test-model"
        assert body["temperature"] == 0
        assert timeout == 30
        return FakeResponse()

    monkeypatch.setattr("ali_mvp.llm_client.urlopen", fake_urlopen)

    result = request_llm_review(
        [{"role": "user", "content": "{}"}],
        config=LlmConfig(
            base_url="https://api.example/v1",
            api_key="test-key",
            model="test-model",
        ),
    )

    assert result["decision"] == "keep"
    assert result["confidence"] == "high"
    assert result["summary_zh"] == "非带电家电配件，可入库。"


def test_request_llm_review_posts_stream_false(monkeypatch):
    response_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "decision": "keep",
                            "reason": "ok",
                            "risk_tags": [],
                            "confidence": "high",
                            "summary_zh": "可入库。",
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(response_payload, ensure_ascii=False).encode("utf-8")

    def fake_urlopen(request, timeout):
        body = json.loads(request.data.decode("utf-8"))
        assert body["stream"] is False
        return FakeResponse()

    monkeypatch.setattr("ali_mvp.llm_client.urlopen", fake_urlopen)

    request_llm_review(
        [{"role": "user", "content": "{}"}],
        config=LlmConfig(
            base_url="https://api.example/v1",
            api_key="test-key",
            model="test-model",
        ),
    )


def test_build_llm_messages_constrains_decision_and_confidence_values():
    messages = build_llm_messages({"title": "test item"})

    assert len(messages) == 2
    assert "keep or drop" in messages[0]["content"]
    assert "high, medium, or low" in messages[0]["content"]


def test_build_llm_messages_marks_controller_like_products_as_drop_and_passive_accessories_as_keep():
    messages = build_llm_messages({"title": "test item"})
    prompt = messages[0]["content"]

    assert "remote control" in prompt
    assert "controller" in prompt
    assert "chip" in prompt
    assert "battery" in prompt
    assert "drop" in prompt
    assert "drain pipe" in prompt
    assert "screen protector" in prompt
    assert "keep" in prompt


def test_normalize_llm_review_response_raises_when_risk_tags_not_list():
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "decision": "keep",
                            "reason": "ok",
                            "risk_tags": "not-a-list",
                            "confidence": "high",
                            "summary_zh": "可入库。",
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }

    with pytest.raises(ValueError, match="risk_tags must be a list"):
        normalize_llm_review_response(payload)


def test_normalize_llm_review_response_raises_when_decision_invalid():
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "decision": "maybe",
                            "reason": "ok",
                            "risk_tags": [],
                            "confidence": "high",
                            "summary_zh": "待定。",
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }

    with pytest.raises(ValueError, match="decision must be one of: keep, drop"):
        normalize_llm_review_response(payload)


def test_normalize_llm_review_response_maps_reject_to_drop():
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "decision": "reject",
                            "reason": "controller-like product",
                            "risk_tags": ["controller"],
                            "confidence": "high",
                            "summary_zh": "控制类，不建议入库。",
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }

    result = normalize_llm_review_response(payload)

    assert result["decision"] == "drop"


@pytest.mark.parametrize(
    ("raw_confidence", "expected"),
    [
        (0.97, "high"),
        (0.8, "high"),
        (0.79, "medium"),
        (0.5, "medium"),
        (0.49, "low"),
        (0, "low"),
    ],
)
def test_normalize_llm_review_response_maps_numeric_confidence(raw_confidence, expected):
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "decision": "keep",
                            "reason": "ok",
                            "risk_tags": [],
                            "confidence": raw_confidence,
                            "summary_zh": "可入库。",
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }

    result = normalize_llm_review_response(payload)

    assert result["confidence"] == expected


def test_normalize_llm_review_response_raises_stable_error_for_invalid_json():
    payload = {
        "choices": [
            {
                "message": {
                    "content": '{"decision":"keep"',
                }
            }
        ]
    }

    with pytest.raises(ValueError, match="LLM response content must be valid JSON"):
        normalize_llm_review_response(payload)
