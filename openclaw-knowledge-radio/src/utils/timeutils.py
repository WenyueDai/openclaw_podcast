from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def load_tz(tz_name: str) -> ZoneInfo:
    return ZoneInfo(tz_name)


def now_local_date(tz: ZoneInfo) -> str:
    return datetime.now(tz).date().isoformat()


def iso_now_local(tz: ZoneInfo) -> str:
    return datetime.now(tz).isoformat(timespec="seconds")


def cutoff_datetime(tz: ZoneInfo, lookback_hours: int, now_dt: datetime | None = None) -> datetime:
    base = now_dt if now_dt is not None else datetime.now(tz)
    return base - timedelta(hours=lookback_hours)
