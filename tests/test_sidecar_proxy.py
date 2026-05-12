from types import SimpleNamespace

import pytest

from ali_mvp.sidecar_proxy import build_sidecar_config, start_sidecar_runtime
from ali_mvp.v2rayn import V2RayNNode, V2RayNSource


def test_build_sidecar_config_overrides_port_server_and_routing():
    node = V2RayNNode(
        index_id="node-a",
        remarks="HK A",
        address="1.1.1.1",
        port=1111,
        password="secret-a",
        method="aes-256-gcm",
        subid="sub-1",
        sort_index=1,
    )
    base_config = {
        "inbounds": [{"port": 10808}],
        "outbounds": [{"settings": {"servers": []}}, {"tag": "direct"}, {"tag": "block"}],
        "routing": {"domainStrategy": "AsIs", "rules": []},
    }

    config = build_sidecar_config(base_config, node=node, local_port=11081)

    server = config["outbounds"][0]["settings"]["servers"][0]
    assert config["inbounds"][0]["port"] == 11081
    assert server["address"] == "1.1.1.1"
    assert server["port"] == 1111
    assert server["method"] == "aes-256-gcm"
    assert server["password"] == "secret-a"
    assert config["routing"]["rules"][-1]["outboundTag"] == "proxy"


def test_build_sidecar_config_raises_when_first_outbound_has_no_servers():
    node = V2RayNNode(
        index_id="node-a",
        remarks="HK A",
        address="1.1.1.1",
        port=1111,
        password="secret-a",
        method="aes-256-gcm",
        subid="sub-1",
        sort_index=1,
    )
    base_config = {
        "inbounds": [{"port": 10808}],
        "outbounds": [{"settings": {}}, {"tag": "direct"}, {"tag": "block"}],
        "routing": {"domainStrategy": "AsIs", "rules": []},
    }

    with pytest.raises(ValueError, match="base config missing outbounds\\[0\\]\\.settings\\.servers"):
        build_sidecar_config(base_config, node=node, local_port=11081)


def test_start_sidecar_runtime_filters_unhealthy_nodes(monkeypatch, tmp_path):
    source = V2RayNSource(
        root=tmp_path,
        db_path=tmp_path / "guiConfigs" / "guiNDB.db",
        base_config_path=tmp_path / "binConfigs" / "config.json",
        xray_path=tmp_path / "bin" / "xray.exe",
        asset_dir=tmp_path / "bin",
        nodes=[
            V2RayNNode("node-a", "HK A", "1.1.1.1", 1111, "secret-a", "aes-256-gcm", "sub-1", 1),
            V2RayNNode("node-b", "TW B", "2.2.2.2", 2222, "secret-b", "aes-256-gcm", "sub-1", 2),
        ],
    )
    source.base_config_path.parent.mkdir(parents=True, exist_ok=True)
    source.xray_path.parent.mkdir(parents=True, exist_ok=True)
    source.base_config_path.write_text(
        '{"inbounds":[{"port":10808}],"outbounds":[{"settings":{"servers":[]}}, {"tag":"direct"}, {"tag":"block"}],"routing":{"domainStrategy":"AsIs","rules":[]}}',
        encoding="utf-8",
    )
    source.xray_path.write_text("", encoding="utf-8")

    started = []
    monkeypatch.setattr(
        "ali_mvp.sidecar_proxy._launch_process",
        lambda **kwargs: started.append(kwargs["node"].index_id)
        or SimpleNamespace(
            pid=len(started),
            poll=lambda: None,
            terminate=lambda: None,
            kill=lambda: None,
            wait=lambda timeout=None: 0,
        ),
    )
    monkeypatch.setattr("ali_mvp.sidecar_proxy._wait_for_port", lambda host, port, timeout: True)
    monkeypatch.setattr(
        "ali_mvp.sidecar_proxy._probe_tls_over_socks",
        lambda proxy_url, host, timeout: proxy_url.endswith("11081"),
    )

    runtime = start_sidecar_runtime(source=source, runtime_dir=tmp_path / "runtime", start_port=11081)

    assert started == ["node-a", "node-b"]
    assert [endpoint.key for endpoint in runtime.healthy_endpoints()] == ["node-a"]
    unhealthy_endpoint = next(endpoint for endpoint in runtime.endpoints if endpoint.key == "node-b")
    assert unhealthy_endpoint.process is None
    assert unhealthy_endpoint.failure_reason == "probe_failed"


def test_start_sidecar_runtime_cleans_up_started_processes_when_later_launch_fails(monkeypatch, tmp_path):
    source = V2RayNSource(
        root=tmp_path,
        db_path=tmp_path / "guiConfigs" / "guiNDB.db",
        base_config_path=tmp_path / "binConfigs" / "config.json",
        xray_path=tmp_path / "bin" / "xray.exe",
        asset_dir=tmp_path / "bin",
        nodes=[
            V2RayNNode("node-a", "HK A", "1.1.1.1", 1111, "secret-a", "aes-256-gcm", "sub-1", 1),
            V2RayNNode("node-b", "TW B", "2.2.2.2", 2222, "secret-b", "aes-256-gcm", "sub-1", 2),
        ],
    )
    source.base_config_path.parent.mkdir(parents=True, exist_ok=True)
    source.xray_path.parent.mkdir(parents=True, exist_ok=True)
    source.base_config_path.write_text(
        '{"inbounds":[{"port":10808}],"outbounds":[{"settings":{"servers":[]}}, {"tag":"direct"}, {"tag":"block"}],"routing":{"domainStrategy":"AsIs","rules":[]}}',
        encoding="utf-8",
    )
    source.xray_path.write_text("", encoding="utf-8")

    class FakeProcess:
        def __init__(self):
            self.terminated = 0
            self.killed = 0
            self.wait_calls = []

        def poll(self):
            return None

        def terminate(self):
            self.terminated += 1

        def kill(self):
            self.killed += 1

        def wait(self, timeout=None):
            self.wait_calls.append(timeout)
            return 0

    first_process = FakeProcess()

    def fake_launch_process(**kwargs):
        if kwargs["node"].index_id == "node-a":
            return first_process
        raise RuntimeError("launch failed")

    monkeypatch.setattr("ali_mvp.sidecar_proxy._launch_process", fake_launch_process)
    monkeypatch.setattr("ali_mvp.sidecar_proxy._wait_for_port", lambda host, port, timeout: True)
    monkeypatch.setattr("ali_mvp.sidecar_proxy._probe_tls_over_socks", lambda proxy_url, host, timeout: True)

    with pytest.raises(RuntimeError, match="launch failed"):
        start_sidecar_runtime(source=source, runtime_dir=tmp_path / "runtime", start_port=11081)

    assert first_process.terminated == 1
    assert first_process.killed == 0
    assert first_process.wait_calls == [5.0]
