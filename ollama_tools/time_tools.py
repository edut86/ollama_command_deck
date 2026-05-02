"""Local time and date helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class TimeInfo:
    timezone: str
    iso: str
    date: str
    time: str
    weekday: str
    utc_iso: str


def current_time(tz: str | None = None) -> TimeInfo:
    """Return current local time details for the requested IANA timezone."""
    zone = _resolve_zone(tz)
    now = datetime.now(zone)
    utc_now = now.astimezone(timezone.utc)
    return TimeInfo(
        timezone=getattr(zone, "key", str(zone)),
        iso=now.isoformat(timespec="seconds"),
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M:%S"),
        weekday=now.strftime("%A"),
        utc_iso=utc_now.isoformat(timespec="seconds").replace("+00:00", "Z"),
    )


def _resolve_zone(tz: str | None):
    if not tz:
        return datetime.now().astimezone().tzinfo or timezone.utc
    try:
        return ZoneInfo(tz)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {tz}") from exc
