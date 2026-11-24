"""Conversión entre UTC (base de datos) y hora de Lima (-05:00)."""

from datetime import UTC, datetime, timedelta, timezone

LIMA = timezone(timedelta(hours=-5))


def a_utc(value: datetime | str | None) -> datetime | None:
    """Interpreta las fechas naive (o textos ISO) como hora de Lima."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=LIMA)
    return value.astimezone(UTC)


def a_lima(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(LIMA)
