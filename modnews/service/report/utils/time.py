from __future__ import annotations

from datetime import date, datetime, timezone


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def parse_report_date(value: str | None) -> date:
    if not value:
        return datetime.now().date()
    return date.fromisoformat(value)
