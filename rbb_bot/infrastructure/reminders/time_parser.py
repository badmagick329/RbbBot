from datetime import datetime, timezone

import dateparser


def parse_reminder_time(value: str, now: datetime) -> datetime:
    """Interpret unqualified times as UTC regardless of the deployment host timezone."""
    parsed = dateparser.parse(
        value,
        settings={
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": "UTC",
            "RETURN_AS_TIMEZONE_AWARE": True,
            "RELATIVE_BASE": now,
        },
    )
    if parsed is None:
        raise ValueError("Please specify a valid time.")
    return parsed.astimezone(timezone.utc)
