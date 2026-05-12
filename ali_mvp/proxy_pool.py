from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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

    @classmethod
    def from_manifest(cls, *, manifest: RunManifest, run_dir: Path) -> "ProxyPool":
        if manifest.proxy_provider == "manual":
            return cls.from_sources(
                proxy=manifest.proxy,
                proxy_file=manifest.proxy_file,
                max_blocks_per_proxy=manifest.max_blocks_per_proxy,
            )

        source = load_v2rayn_source(Path(manifest.v2rayn_dir))
        runtime = start_sidecar_runtime(source, runtime_dir=run_dir / "proxy_runtime")
        healthy = runtime.healthy_endpoints()
        if not healthy:
            runtime.close()
            raise NoHealthyProxyError(f"No healthy v2rayN sidecar proxies under {manifest.v2rayn_dir}")
        return cls(
            proxies=[endpoint.proxy_url for endpoint in healthy],
            proxy_keys=[endpoint.key for endpoint in healthy],
            proxy_labels=[endpoint.label for endpoint in healthy],
            max_blocks_per_proxy=max(1, manifest.max_blocks_per_proxy),
            runtime=runtime,
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
