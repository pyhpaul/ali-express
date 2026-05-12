from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path


@dataclass(frozen=True)
class ProxyHealthRecord:
    success_count: int = 0
    timeout_count: int = 0
    captcha_count: int = 0
    block_count: int = 0
    last_event: str = ""
    last_failed_at: str = ""
    cooldown_until: str = ""


class ProxyHealthStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, ProxyHealthRecord]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {key: ProxyHealthRecord(**value) for key, value in payload.items()}

    def mark_result(self, proxy_key: str, *, event: str, now_iso: str) -> ProxyHealthRecord:
        records = self.load()
        current = records.get(proxy_key, ProxyHealthRecord())
        updated = ProxyHealthRecord(
            success_count=current.success_count + (1 if event == "success" else 0),
            timeout_count=current.timeout_count + (1 if event == "timeout" else 0),
            captcha_count=current.captcha_count + (1 if event == "captcha" else 0),
            block_count=current.block_count + (1 if event == "captcha" else 0),
            last_event=event,
            last_failed_at=now_iso if event != "success" else current.last_failed_at,
            cooldown_until=_event_cooldown(event=event, now_iso=now_iso),
        )
        records[proxy_key] = updated
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({key: asdict(value) for key, value in records.items()}, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return updated


def _event_cooldown(*, event: str, now_iso: str) -> str:
    if event == "success":
        return ""
    if event == "captcha":
        return _add_minutes(now_iso, 30)
    if event == "timeout":
        return _add_minutes(now_iso, 15)
    return ""


def _add_minutes(now_iso: str, minutes: int) -> str:
    current = _parse_iso_utc(now_iso)
    if current is None:
        return ""
    scheduled = current + timedelta(minutes=minutes)
    return scheduled.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
