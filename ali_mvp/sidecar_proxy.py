import copy
import json
import os
import socket
import ssl
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ali_mvp.v2rayn import V2RayNNode, V2RayNSource

DEFAULT_START_PORT = 11081
DEFAULT_PROBE_HOST = "www.aliexpress.com"
DEFAULT_PROBE_TIMEOUT = 10.0
CLOSE_TIMEOUT = 5.0


@dataclass
class SidecarEndpoint:
    key: str
    label: str
    proxy_url: str
    local_port: int
    config_path: Path
    process: Any
    healthy: bool
    failure_reason: str = ""


@dataclass
class SidecarRuntime:
    runtime_dir: Path
    endpoints: list[SidecarEndpoint]

    def healthy_endpoints(self) -> list[SidecarEndpoint]:
        return [endpoint for endpoint in self.endpoints if endpoint.healthy]

    def close(self) -> None:
        for endpoint in self.endpoints:
            _stop_process(endpoint.process)
            endpoint.process = None


def build_sidecar_config(base_config: dict[str, Any], *, node: V2RayNNode, local_port: int) -> dict[str, Any]:
    _validate_base_config(base_config)
    config = copy.deepcopy(base_config)
    config["inbounds"][0]["port"] = local_port
    config["outbounds"][0]["settings"]["servers"] = [
        {
            "address": node.address,
            "method": node.method,
            "ota": False,
            "password": node.password,
            "port": node.port,
            "level": 1,
        }
    ]
    config["routing"] = {
        "domainStrategy": "AsIs",
        "rules": [
            {"type": "field", "inboundTag": ["api"], "outboundTag": "api"},
            {"type": "field", "port": "443", "network": "udp", "outboundTag": "block"},
            {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
            {"type": "field", "domain": ["geosite:private"], "outboundTag": "direct"},
            {"type": "field", "inboundTag": ["direct-dns-1", "direct-dns-2"], "outboundTag": "direct"},
            {"type": "field", "inboundTag": ["dns-module"], "outboundTag": "proxy"},
            {"type": "field", "port": "0-65535", "outboundTag": "proxy"},
        ],
    }
    return config


def start_sidecar_runtime(source: V2RayNSource, *, runtime_dir: Path, start_port: int = DEFAULT_START_PORT) -> SidecarRuntime:
    base_config = json.loads(source.base_config_path.read_text(encoding="utf-8"))
    runtime_dir.mkdir(parents=True, exist_ok=True)
    endpoints: list[SidecarEndpoint] = []
    runtime = SidecarRuntime(runtime_dir=runtime_dir, endpoints=endpoints)
    try:
        for offset, node in enumerate(source.nodes):
            local_port = start_port + offset
            config_path = runtime_dir / f"{node.sort_index:03d}-{node.index_id}.json"
            config = build_sidecar_config(base_config, node=node, local_port=local_port)
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            process = _launch_process(
                node=node,
                xray_path=source.xray_path,
                asset_dir=source.asset_dir,
                config_path=config_path,
            )
            proxy_url = f"socks5://127.0.0.1:{local_port}"
            healthy = _wait_for_port("127.0.0.1", local_port, DEFAULT_PROBE_TIMEOUT) and _probe_tls_over_socks(
                proxy_url, DEFAULT_PROBE_HOST, DEFAULT_PROBE_TIMEOUT
            )
            if not healthy:
                _stop_process(process)
                process = None
            endpoints.append(
                SidecarEndpoint(
                    key=node.index_id,
                    label=node.remarks,
                    proxy_url=proxy_url,
                    local_port=local_port,
                    config_path=config_path,
                    process=process,
                    healthy=healthy,
                    failure_reason="" if healthy else "probe_failed",
                )
            )
    except Exception:
        runtime.close()
        raise
    return runtime


def _launch_process(*, node: V2RayNNode, xray_path: Path, asset_dir: Path, config_path: Path) -> Any:
    env = os.environ.copy()
    env["xray_location_asset"] = str(asset_dir)
    return subprocess.Popen(
        [str(xray_path), "run", "-config", str(config_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )


def _validate_base_config(base_config: dict[str, Any]) -> None:
    if not isinstance(base_config.get("inbounds"), list) or not base_config["inbounds"]:
        raise ValueError("base config missing inbounds[0]")
    if not isinstance(base_config.get("outbounds"), list) or not base_config["outbounds"]:
        raise ValueError("base config missing outbounds[0]")
    first_outbound = base_config["outbounds"][0]
    if not isinstance(first_outbound, dict) or not isinstance(first_outbound.get("settings"), dict):
        raise ValueError("base config missing outbounds[0].settings")
    if "servers" not in first_outbound["settings"]:
        raise ValueError("base config missing outbounds[0].settings.servers")


def _stop_process(process: Any) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=CLOSE_TIMEOUT)
        except Exception:
            process.kill()


def _wait_for_port(host: str, port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _probe_tls_over_socks(proxy_url: str, host: str, timeout: float) -> bool:
    if not proxy_url.startswith("socks5://"):
        raise ValueError(f"unsupported proxy URL: {proxy_url}")
    _, address = proxy_url.split("://", 1)
    proxy_host, proxy_port_text = address.rsplit(":", 1)
    proxy_port = int(proxy_port_text)
    try:
        with socket.create_connection((proxy_host, proxy_port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            _socks5_connect(sock, host=host, port=443)
            context = ssl.create_default_context()
            with context.wrap_socket(sock, server_hostname=host) as tls_sock:
                tls_sock.do_handshake()
        return True
    except OSError:
        return False
    except ssl.SSLError:
        return False


def _socks5_connect(sock: socket.socket, *, host: str, port: int) -> None:
    sock.sendall(b"\x05\x01\x00")
    response = _recv_exact(sock, 2)
    if response != b"\x05\x00":
        raise OSError("SOCKS5 method negotiation failed")

    host_bytes = host.encode("idna")
    request = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + port.to_bytes(2, "big")
    sock.sendall(request)
    reply = _recv_exact(sock, 4)
    if reply[1] != 0x00:
        raise OSError(f"SOCKS5 connect failed: {reply[1]}")
    atyp = reply[3]
    if atyp == 0x01:
        _recv_exact(sock, 4)
    elif atyp == 0x03:
        length = _recv_exact(sock, 1)[0]
        _recv_exact(sock, length)
    elif atyp == 0x04:
        _recv_exact(sock, 16)
    else:
        raise OSError(f"SOCKS5 reply ATYP not supported: {atyp}")
    _recv_exact(sock, 2)


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise OSError("unexpected EOF from socket")
        chunks.extend(chunk)
    return bytes(chunks)
