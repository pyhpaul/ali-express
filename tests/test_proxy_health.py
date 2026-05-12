from pathlib import Path

from ali_mvp.proxy_health import ProxyHealthStore


def test_proxy_health_store_round_trips_records(tmp_path: Path):
    store = ProxyHealthStore(tmp_path / "_proxy_health.json")
    store.mark_result("node-a", event="captcha", now_iso="2026-05-12T10:00:00Z")
    store.mark_result("node-a", event="timeout", now_iso="2026-05-12T10:10:00Z")

    restored = ProxyHealthStore(tmp_path / "_proxy_health.json")
    record = restored.load()["node-a"]

    assert record.captcha_count == 1
    assert record.timeout_count == 1
    assert record.cooldown_until == "2026-05-12T10:25:00Z"
