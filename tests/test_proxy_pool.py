from ali_mvp.proxy_pool import ProxyPool
from ali_mvp.run_state import RunManifest
from ali_mvp.sidecar_proxy import SidecarEndpoint, SidecarRuntime


def test_proxy_pool_from_sources_dedupes_and_skips_blank_lines(tmp_path):
    proxy_file = tmp_path / "proxies.txt"
    proxy_file.write_text("http://a:1\n\nhttp://b:2\nhttp://a:1\n", encoding="utf-8")

    pool = ProxyPool.from_sources(
        proxy="http://seed:0",
        proxy_file=str(proxy_file),
        max_blocks_per_proxy=2,
    )

    assert pool.proxies == [
        "http://seed:0",
        "http://a:1",
        "http://b:2",
    ]
    assert pool.current() == "http://seed:0"


def test_proxy_pool_rotates_after_threshold(tmp_path):
    proxy_file = tmp_path / "proxies.txt"
    proxy_file.write_text("http://a:1\nhttp://b:2\n", encoding="utf-8")

    pool = ProxyPool.from_sources(proxy="", proxy_file=str(proxy_file), max_blocks_per_proxy=2)

    assert pool.current() == "http://a:1"

    pool.mark_blocked()
    assert pool.current() == "http://a:1"
    assert pool.current_index == 0
    assert pool.block_events_on_current == 1

    pool.mark_blocked()
    assert pool.current() == "http://b:2"
    assert pool.current_index == 1
    assert pool.block_events_on_current == 0


def test_proxy_pool_from_manifest_uses_v2rayn_runtime(monkeypatch, tmp_path):
    runtime = SidecarRuntime(
        runtime_dir=tmp_path / "runtime",
        endpoints=[
            SidecarEndpoint("node-a", "HK A", "socks5://127.0.0.1:11081", 11081, tmp_path / "a.json", None, True),
            SidecarEndpoint("node-b", "TW B", "socks5://127.0.0.1:11082", 11082, tmp_path / "b.json", None, True),
        ],
    )
    monkeypatch.setattr("ali_mvp.proxy_pool.load_v2rayn_source", lambda root: "SOURCE")
    monkeypatch.setattr("ali_mvp.proxy_pool.start_sidecar_runtime", lambda source, runtime_dir, start_port=11081: runtime)

    manifest = RunManifest(
        source_type="keyword",
        source_value="fan motor",
        url="https://www.aliexpress.com/wholesale?SearchText=fan+motor",
        max_items=20,
        pages=None,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        blacklist_file=None,
        proxy_provider="v2rayn",
        v2rayn_dir="C:/Users/test/v2rayN",
        max_blocks_per_proxy=2,
    )

    pool = ProxyPool.from_manifest(manifest=manifest, run_dir=tmp_path)

    assert pool.current() == "socks5://127.0.0.1:11081"
    assert pool.current_key() == "node-a"


def test_proxy_pool_restore_selection_prefers_current_key(tmp_path):
    pool = ProxyPool(
        proxies=["socks5://127.0.0.1:11081", "socks5://127.0.0.1:11082"],
        proxy_keys=["node-a", "node-b"],
        proxy_labels=["HK A", "TW B"],
        max_blocks_per_proxy=2,
    )

    pool.restore_selection(current_key="node-b", current_index=0, block_events=1)

    assert pool.current() == "socks5://127.0.0.1:11082"
    assert pool.current_index == 1
    assert pool.block_events_on_current == 1
