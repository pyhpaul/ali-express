from ali_mvp.proxy_pool import ProxyPool


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
