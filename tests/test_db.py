import pytest

from app.db import connect, count_sightings, upsert_sightings


@pytest.fixture
def conn():
    """A fresh in-memory database for each test, thrown away afterwards."""
    connection = connect(":memory:")
    yield connection
    connection.close()


def make_clean_record(**changes):
    record = {
        "id": "abc123",
        "date": "2022-08-01T06:40:31",
        "location": "Manchester",
        "species": "Marsh tick",
        "latin_name": "Ixodes apronophorus",
    }
    record.update(changes)
    return record


def test_records_are_saved(conn):
    upsert_sightings(conn, [make_clean_record(id="a"), make_clean_record(id="b")])

    assert count_sightings(conn) == 2


def test_saving_the_same_records_twice_does_not_duplicate(conn):
    records = [make_clean_record(id="a"), make_clean_record(id="b")]

    upsert_sightings(conn, records)
    upsert_sightings(conn, records)

    assert count_sightings(conn) == 2


def test_newer_copy_of_a_record_replaces_the_old_one(conn):
    upsert_sightings(conn, [make_clean_record(location="Manchester")])
    upsert_sightings(conn, [make_clean_record(location="Leeds")])

    row = conn.execute("SELECT location FROM sightings WHERE id = 'abc123'").fetchone()
    assert row["location"] == "Leeds"
    assert count_sightings(conn) == 1


def test_missing_latin_name_is_stored_as_null(conn):
    upsert_sightings(conn, [make_clean_record(latin_name=None)])

    row = conn.execute("SELECT latin_name FROM sightings").fetchone()
    assert row["latin_name"] is None
