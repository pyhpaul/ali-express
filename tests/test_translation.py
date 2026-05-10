from ali_mvp.translation import summarize_attributes_text, translate_texts


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
