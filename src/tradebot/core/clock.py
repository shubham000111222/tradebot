"""UTC clock helpers used by all domain events."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(UTC)


def require_utc(value: datetime) -> datetime:
    """Reject naive or non-UTC timestamps at the application boundary."""
    if value.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(UTC)
