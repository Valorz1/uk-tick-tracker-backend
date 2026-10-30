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


def clean_record(raw: dict, now: datetime | None = None) -> dict:
    """Return a tidied copy of one raw sighting, or raise InvalidRecordError.

    `now` is only passed in by tests, so they can fix the current time.
    """
    if not isinstance(raw, dict):
        raise InvalidRecordError("record is not a JSON object")

    for field in REQUIRED_FIELDS:
        if _clean_text(raw.get(field)) is None:
            raise InvalidRecordError(f"missing {field}")

    try:
        date = datetime.fromisoformat(raw["date"].strip())
    except ValueError:
        raise InvalidRecordError(f"invalid date: {raw['date']!r}")

    # Source dates have no timezone. One that does is inconsistent data,
    # and comparing it with `now` below would crash, so reject it.
    if date.tzinfo is not None:
        raise InvalidRecordError(f"unexpected timezone in date: {raw['date']!r}")

    if date > (now or datetime.now()):
        raise InvalidRecordError(f"date is in the future: {raw['date']!r}")

    return {
        "id": _clean_text(raw["id"]),
        "date": date.isoformat(timespec="seconds"),
        "location": _clean_text(raw["location"]).title(),
        "species": _clean_text(raw["species"]),
        "latin_name": _clean_text(raw.get("latinName")),
    }
