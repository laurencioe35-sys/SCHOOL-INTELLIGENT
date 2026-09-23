from __future__ import annotations

from datetime import UTC, datetime, timedelta


def is_within_24_hour_window(last_user_message_at: datetime, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    return current - last_user_message_at <= timedelta(hours=24)