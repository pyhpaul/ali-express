from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from collections.abc import Mapping

from .scoring import ProductRecord


@dataclass(frozen=True)
class RunManifest:
    source_type: str
    source_value: str
    url: str
    max_items: int
    pages: int | None
    output_dir: str
    user_data_dir: str
    port: int
    enrich_detail: bool
    blacklist_file: str | None
    reject_keyword: list[str] = field(default_factory=list)
    browser_hardening: str = "off"
    proxy_provider: str = "manual"
    v2rayn_dir: str = ""
    proxy: str = ""
    proxy_file: str = ""
    max_blocks_per_proxy: int = 0
    user_agent: str = ""
    accept_language: str = ""
    session_preflight: str = "on"
    created_at: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunManifest":
        return cls(
            source_type=payload["source_type"],
            source_value=payload["source_value"],
            url=payload["url"],
            max_items=payload["max_items"],
            pages=payload["pages"],
            output_dir=payload["output_dir"],
            user_data_dir=payload["user_data_dir"],
            port=payload["port"],
            enrich_detail=payload["enrich_detail"],
            blacklist_file=payload["blacklist_file"],
            reject_keyword=list(payload.get("reject_keyword", [])),
            browser_hardening=_normalize_browser_hardening(payload.get("browser_hardening", "off")),
            proxy_provider=_normalize_proxy_provider(payload.get("proxy_provider", "manual")),
            v2rayn_dir=payload.get("v2rayn_dir", ""),
            proxy=payload.get("proxy", ""),
            proxy_file=payload.get("proxy_file", ""),
            max_blocks_per_proxy=payload.get("max_blocks_per_proxy", 0),
            user_agent=payload.get("user_agent", ""),
            accept_language=payload.get("accept_language", ""),
            session_preflight=_normalize_session_preflight(payload.get("session_preflight", "on")),
            created_at=payload.get("created_at", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunState:
    status: str = ""
    current_listing_page: int = 0
    raw_products_count: int = 0
    normalized_count: int = 0
    accepted_count: int = 0
    seen_product_keys: list[str] = field(default_factory=list)
    accepted_products: list[ProductRecord] = field(default_factory=list)
    audit_rows: list[dict[str, Any]] = field(default_factory=list)
    pending_detail_queue: list[dict[str, Any]] = field(default_factory=list)
    current_proxy_key: str = ""
    current_proxy_index: int = 0
    block_events_on_current_proxy: int = 0
    last_block_reason: str = ""
    last_blocked_url: str = ""
    session_risk_level: str = "low"
    last_session_preflight_status: str = ""
    consecutive_captcha_count: int = 0
    last_session_ok_at: str = ""
    cooldown_until: str = ""
    identity_warning: dict[str, Any] = field(default_factory=dict)
    last_error: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunState":
        return cls(
            status=payload.get("status", ""),
            current_listing_page=payload.get("current_listing_page", 0),
            raw_products_count=payload.get("raw_products_count", 0),
            normalized_count=payload.get("normalized_count", 0),
            accepted_count=payload.get("accepted_count", 0),
            seen_product_keys=list(payload.get("seen_product_keys", [])),
            accepted_products=[_deserialize_product_record(item) for item in payload.get("accepted_products", [])],
            audit_rows=list(payload.get("audit_rows", [])),
            pending_detail_queue=_deserialize_pending_detail_queue(payload.get("pending_detail_queue", [])),
            current_proxy_key=payload.get("current_proxy_key", ""),
            current_proxy_index=payload.get("current_proxy_index", 0),
            block_events_on_current_proxy=payload.get("block_events_on_current_proxy", 0),
            last_block_reason=payload.get("last_block_reason", ""),
            last_blocked_url=payload.get("last_blocked_url", ""),
            session_risk_level=payload.get("session_risk_level", "low"),
            last_session_preflight_status=payload.get("last_session_preflight_status", ""),
            consecutive_captcha_count=payload.get("consecutive_captcha_count", 0),
            last_session_ok_at=payload.get("last_session_ok_at", ""),
            cooldown_until=payload.get("cooldown_until", ""),
            identity_warning=_deserialize_identity_warning(payload),
            last_error=payload.get("last_error", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "current_listing_page": self.current_listing_page,
            "raw_products_count": self.raw_products_count,
            "normalized_count": self.normalized_count,
            "accepted_count": self.accepted_count,
            "seen_product_keys": list(self.seen_product_keys),
            "accepted_products": [asdict(product) for product in self.accepted_products],
            "audit_rows": list(self.audit_rows),
            "pending_detail_queue": [dict(item) for item in self.pending_detail_queue],
            "current_proxy_key": self.current_proxy_key,
            "current_proxy_index": self.current_proxy_index,
            "block_events_on_current_proxy": self.block_events_on_current_proxy,
            "last_block_reason": self.last_block_reason,
            "last_blocked_url": self.last_blocked_url,
            "session_risk_level": self.session_risk_level,
            "last_session_preflight_status": self.last_session_preflight_status,
            "consecutive_captcha_count": self.consecutive_captcha_count,
            "last_session_ok_at": self.last_session_ok_at,
            "cooldown_until": self.cooldown_until,
            "identity_warning": dict(self.identity_warning),
            "last_error": self.last_error,
        }


class RunStateStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.manifest_path = self.root / "run_manifest.json"
        self.state_path = self.root / "run_state.json"
        self.summary_path = self.root / "run_summary.json"

    def save_manifest(self, manifest: RunManifest) -> None:
        self._write_json(self.manifest_path, manifest.to_dict())

    def load_manifest(self) -> RunManifest:
        return RunManifest.from_dict(self._read_json(self.manifest_path))

    def save_state(self, state: RunState) -> None:
        self._write_json(self.state_path, state.to_dict())

    def load_state(self) -> RunState:
        if not self.state_path.exists():
            return RunState()
        return RunState.from_dict(self._read_json(self.state_path))

    def save_summary(self, state: RunState) -> None:
        self._write_json(self.summary_path, self._build_summary(state))

    def load_summary(self) -> dict[str, Any]:
        return self._read_json(self.summary_path)

    def _build_summary(self, state: RunState) -> dict[str, Any]:
        summary = {
            "status": state.status,
            "current_listing_page": state.current_listing_page,
            "accepted_count": state.accepted_count,
            "last_block_reason": state.last_block_reason,
            "last_blocked_url": state.last_blocked_url,
            "resume_recommended": state.status in {"blocked", "failed"},
        }
        if state.identity_warning:
            summary["identity_warning"] = dict(state.identity_warning)
        return summary

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)

    def _read_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


def _deserialize_product_record(payload: ProductRecord | dict[str, Any]) -> ProductRecord:
    if isinstance(payload, ProductRecord):
        return payload
    return ProductRecord(**payload)


def _deserialize_pending_detail_queue(payload: Any) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    if not isinstance(payload, list):
        return queue
    for item in payload:
        if isinstance(item, dict):
            queue.append(dict(item))
            continue
        url = str(item or "")
        if not url:
            continue
        queue.append(
            {
                "url": url,
                "resolvedProductUrl": url,
            }
        )
    return queue


def _deserialize_identity_warning(payload: dict[str, Any]) -> dict[str, Any]:
    warning = payload.get("identity_warning")
    if isinstance(warning, dict):
        code = str(warning.get("code") or "")
        if not code:
            return {}
        configured = warning.get("configured")
        effective = warning.get("effective")
        if not isinstance(configured, Mapping) or not isinstance(effective, Mapping):
            return {}
        return {
            "code": code,
            "configured": dict(configured),
            "effective": dict(effective),
        }
    legacy_code = str(payload.get("identity_warning_code") or "")
    if not legacy_code:
        return {}
    return {
        "code": legacy_code,
        "configured": {},
        "effective": {},
    }


def _normalize_browser_hardening(value: Any) -> str:
    if value in {"off", "minimal"}:
        return value
    return "off"


def _normalize_proxy_provider(value: Any) -> str:
    if value in {"manual", "v2rayn"}:
        return str(value)
    return "manual"


def _normalize_session_preflight(value: Any) -> str:
    if value in {"on", "off"}:
        return str(value)
    return "on"
