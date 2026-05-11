from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProxyPool:
    proxies: list[str]
    max_blocks_per_proxy: int = 2
    current_index: int = 0
    block_events_on_current: int = 0

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

    def mark_blocked(self) -> str:
        if not self.proxies:
            return ""
        self.block_events_on_current += 1
        if self.block_events_on_current >= self.max_blocks_per_proxy and len(self.proxies) > 1:
            self.current_index = min(self.current_index + 1, len(self.proxies) - 1)
            self.block_events_on_current = 0
        return self.current()
