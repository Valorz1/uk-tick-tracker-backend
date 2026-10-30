from datetime import datetime

import pytest

from app.cleaning import InvalidRecordError, clean_record

# A fixed "now", so the future-date test gives the same result on any day.
NOW = datetime(2026, 1, 1)


def make_record(**changes):
    """Return a valid raw record, with any fields replaced by `changes`."""
    record = {
        "id": "abc123",
        "date": "2022-08-01T06:40:31",
        "location": "Manchester",
        "species": "Marsh tick",
        "latinName": "Ixodes apronophorus",
    }
    record.update(changes)
    return record


def test_valid_record_is_returned_tidied():
    raw = make_record(id=" abc123 ", location="  manchester ", species="Marsh tick ")

    assert clean_record(raw, now=NOW) == {
        "id": "abc123",
        "date": "2022-08-01T06:40:31",
        "location": "Manchester",
        "species": "Marsh tick",
        "latin_name": "Ixodes apronophorus",
    }


def test_date_only_is_stored_in_full_format():
    assert clean_record(make_record(date="2022-08-01"), now=NOW)["date"] == "2022-08-01T00:00:00"


@pytest.mark.parametrize("field", ["id", "date", "location", "species"])
@pytest.mark.parametrize("bad_value", [None, "", "   "])
def test_missing_or_blank_required_field_is_rejected(field, bad_value):
    with pytest.raises(InvalidRecordError, match=f"missing {field}"):
        clean_record(make_record(**{field: bad_value}), now=NOW)


def test_absent_required_key_is_rejected():
    raw = make_record()
    del raw["location"]

    with pytest.raises(InvalidRecordError, match="missing location"):
        clean_record(raw, now=NOW)


def test_missing_latin_name_is_allowed():
    raw = make_record()
    del raw["latinName"]

    assert clean_record(raw, now=NOW)["latin_name"] is None


def test_invalid_date_is_rejected():
    with pytest.raises(InvalidRecordError, match="invalid date"):
        clean_record(make_record(date="01/08/2022"), now=NOW)


def test_date_with_timezone_is_rejected():
    with pytest.raises(InvalidRecordError, match="unexpected timezone"):
        clean_record(make_record(date="2022-08-01T06:40:31+00:00"), now=NOW)


def test_future_date_is_rejected():
    with pytest.raises(InvalidRecordError, match="in the future"):
        clean_record(make_record(date="2030-01-01T00:00:00"), now=NOW)


def test_non_dict_record_is_rejected():
    with pytest.raises(InvalidRecordError, match="not a JSON object"):
        clean_record(["not", "a", "dict"], now=NOW)
