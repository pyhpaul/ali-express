from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ali_mvp.proxy_health import ProxyHealthRecord, ProxyHealthStore
from ali_mvp.run_state import RunManifest
from ali_mvp.sidecar_proxy import SidecarRuntime, start_sidecar_runtime
from ali_mvp.v2rayn import load_v2rayn_source


class NoHealthyProxyError(RuntimeError):
    pass


@dataclass
class ProxyPool:
    proxies: list[str]
    proxy_keys: list[str] = field(default_factory=list)
    proxy_labels: list[str] = field(default_factory=list)
    max_blocks_per_proxy: int = 2
    current_index: int = 0
    block_events_on_current: int = 0
    runtime: SidecarRuntime | None = None
    health_store: ProxyHealthStore | None = None
    health_records: dict[str, ProxyHealthRecord] = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, *, manifest: RunManifest, run_dir: Path) -> "ProxyPool":
        if manifest.proxy_provider == "manual":
            return cls.from_sources(
                proxy=manifest.proxy,
                proxy_file=manifest.proxy_file,
                max_blocks_per_proxy=manifest.max_blocks_per_proxy,
            )

        health_store = ProxyHealthStore(run_dir.parent / "_proxy_health.json")
        health_records = health_store.load()
        source = load_v2rayn_source(Path(manifest.v2rayn_dir))
        runtime = start_sidecar_runtime(source, runtime_dir=run_dir / "proxy_runtime")
        healthy = [
            endpoint
            for endpoint in runtime.healthy_endpoints()
            if not _is_in_cooldown(health_records.get(endpoint.key), now_iso=_utc_now())
        ]
        if not healthy:
            runtime.close()
            raise NoHealthyProxyError(f"No healthy v2rayN sidecar proxies under {manifest.v2rayn_dir}")
        return cls(
            proxies=[endpoint.proxy_url for endpoint in healthy],
            proxy_keys=[endpoint.key for endpoint in healthy],
            proxy_labels=[endpoint.label for endpoint in healthy],
            max_blocks_per_proxy=max(1, manifest.max_blocks_per_proxy),
            runtime=runtime,
            health_store=health_store,
            health_records=health_records,
        )

    @classmethod
    def from_sources(cls, *, proxy: str, proxy_file: str, max_blocks_per_proxy: int) -> "ProxyPool":
        proxies: list[str] = []
        if proxy.strip():
            proxies.append(proxy.strip())
        if proxy_file:
            for line in Path(proxy_file).read_text(encoding="utf-8").splitlines():
                candidate = line.strip()
                if candidate and candidate not in proxies:
                    proxies.append(candidate)
        return cls(proxies=proxies, max_blocks_per_proxy=max(1, max_blocks_per_proxy))

    def current(self) -> str:
        if not self.proxies:
            return ""
        return self.proxies[self.current_index]

    def current_key(self) -> str:
        if not self.proxy_keys:
            return self.current()
        return self.proxy_keys[self.current_index]

    def restore_selection(self, *, current_key: str, current_index: int, block_events: int) -> None:
        if current_key and current_key in self.proxy_keys:
            self.current_index = self.proxy_keys.index(current_key)
        elif self.proxies:
            self.current_index = max(0, min(current_index, len(self.proxies) - 1))
        self.block_events_on_current = max(0, block_events)

    def mark_blocked(self) -> str:
        if not self.proxies:
            return ""
        self.block_events_on_current += 1
        if self.block_events_on_current >= self.max_blocks_per_proxy and len(self.proxies) > 1:
            self.current_index = min(self.current_index + 1, len(self.proxies) - 1)
            self.block_events_on_current = 0
        return self.current()

    def close(self) -> None:
        if self.runtime is not None:
            self.runtime.close()

    def record_event(self, event: str, *, now_iso: str) -> None:
        proxy_key = self.current_key()
        if not proxy_key or self.health_store is None:
            return
        self.health_records[proxy_key] = self.health_store.mark_result(proxy_key, event=event, now_iso=now_iso)

    def _eligible_indices(self, *, now_iso: str) -> list[int]:
        return [
            index
            for index, proxy in enumerate(self.proxies)
            if not _is_in_cooldown(self.health_records.get(self._proxy_key_at(index, proxy)), now_iso=now_iso)
        ]

    def _proxy_key_at(self, index: int, proxy: str) -> str:
        if index < len(self.proxy_keys):
            return self.proxy_keys[index]
        return proxy


def _is_in_cooldown(record: ProxyHealthRecord | None, *, now_iso: str) -> bool:
    if record is None or not record.cooldown_until or not now_iso:
        return False
    cooldown_at = _parse_iso_utc(record.cooldown_until)
    now_at = _parse_iso_utc(now_iso)
    if cooldown_at is None or now_at is None:
        return False
    return cooldown_at > now_at


def _parse_iso_utc(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
