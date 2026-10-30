"""Check and tidy raw tick-sighting records from the Elanco API."""

from datetime import datetime

REQUIRED_FIELDS = ("id", "date", "location", "species")


class InvalidRecordError(ValueError):
    """Raised when a raw record cannot be stored."""


def _clean_text(value) -> str | None:
    """Return the text with outer spaces removed, or None if it is missing or blank."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None



