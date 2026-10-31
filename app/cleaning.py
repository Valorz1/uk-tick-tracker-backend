"""Check and tidy raw tick-sighting records from the Elanco API.

Every record passes through `clean_record` before it is stored, so the
database only ever contains complete, consistently formatted sightings.
"""

import string
from datetime import datetime

# Fields a sighting cannot be stored or searched without.
# `latinName` is deliberately not here: a record missing it is still useful.
REQUIRED_FIELDS = ("id", "date", "location", "species")


class InvalidRecordError(ValueError):
    """Raised when a raw record cannot be stored.

    A dedicated error type lets ingestion catch bad records specifically,
    without also hiding unrelated bugs that raise other errors.
    """


def _clean_text(value) -> str | None:
    """Trim a text value, treating anything unusable as missing.

    Args:
        value: Any value taken from a raw record.

    Returns:
        The text without surrounding spaces, or None if the value is not
        text or is empty after trimming. Callers can therefore test for
        "missing" with a single `is None` check.
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None  # "" is falsy, so blank text becomes None


def normalise_location(text: str) -> str:
    """Tidy a city name into one consistent form.

    Used both when storing records and when searching, so a search always
    uses the same rule as the stored data and cannot miss on capitals or spaces.

    Args:
        text: A city name in any capitalisation, possibly with extra spaces.

    Returns:
        The name with each word capitalised and single spaces between words,
        e.g. " king's  lynn " -> "King's Lynn". `string.capwords` is used
        instead of `str.title()`, which would give "King'S Lynn".
    """
    return string.capwords(text)


def clean_record(raw: dict, now: datetime | None = None) -> dict:
    """Validate one raw sighting and return a tidied copy.

    Args:
        raw: One record as received from the API.
        now: Current time for the future-date check; tests pass a fixed value.

    Returns:
        A new dict with `id`, `date`, `location`, `species` and `latin_name`
        (which may be None), named to match the database columns.

    Raises:
        InvalidRecordError: With the first problem found.
    """
    if not isinstance(raw, dict):
        raise InvalidRecordError("record is not a JSON object")

    for field in REQUIRED_FIELDS:
        if _clean_text(raw.get(field)) is None:
            raise InvalidRecordError(f"missing {field}")

    try:
        date = datetime.fromisoformat(raw["date"].strip())
    except ValueError:
        # Replace Python's generic message with one that shows the bad value.
        raise InvalidRecordError(f"invalid date: {raw['date']!r}")

    # Source dates have no timezone. One that does is inconsistent data,
    # and comparing it with `now` below would crash, so reject it.
    if date.tzinfo is not None:
        raise InvalidRecordError(f"unexpected timezone in date: {raw['date']!r}")

    if date > (now or datetime.now()):
        raise InvalidRecordError(f"date is in the future: {raw['date']!r}")

    return {
        "id": _clean_text(raw["id"]),
        # One fixed format means dates sort correctly as text in SQLite.
        "date": date.isoformat(timespec="seconds"),
        "location": normalise_location(raw["location"]),
        "species": _clean_text(raw["species"]),
        "latin_name": _clean_text(raw.get("latinName")),
    }
