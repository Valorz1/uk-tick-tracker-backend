import httpx
import pytest

from app.db import connect
from app.ingest import FetchError, clean_all, fetch_sightings, run_ingestion

GOOD_RECORD = {
    "id": "abc123",
    "date": "2022-08-01T06:40:31",
    "location": "Manchester",
    "species": "Marsh tick",
    "latinName": "Ixodes apronophorus",
}


def fake_client(responses):
    """Return an httpx client that replies with `responses` in order, instead of
    calling the real API. Also returns a list that records every request made."""
    calls = []
    replies = iter(responses)

    def handler(request):
        calls.append(request)
        return next(replies)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


@pytest.fixture
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


def test_fetch_returns_the_list_of_sightings():
    client, calls = fake_client([httpx.Response(200, json=[GOOD_RECORD])])

    assert fetch_sightings(client, wait_seconds=0) == [GOOD_RECORD]
    assert len(calls) == 1


def test_fetch_retries_after_a_server_error():
    client, calls = fake_client([
        httpx.Response(500),
        httpx.Response(200, json=[GOOD_RECORD]),
    ])

    assert fetch_sightings(client, wait_seconds=0) == [GOOD_RECORD]
    assert len(calls) == 2


def test_fetch_retries_after_invalid_json():
    client, calls = fake_client([
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=[GOOD_RECORD]),
    ])

    assert fetch_sightings(client, wait_seconds=0) == [GOOD_RECORD]
    assert len(calls) == 2


def test_fetch_gives_up_after_every_attempt_fails():
    # A fresh response object for each attempt (not one object reused 3 times).
    client, calls = fake_client([httpx.Response(503) for _ in range(3)])

    with pytest.raises(FetchError, match="after 3 attempts"):
        fetch_sightings(client, attempts=3, wait_seconds=0)
    assert len(calls) == 3


def test_fetch_does_not_retry_a_client_error():
    client, calls = fake_client([httpx.Response(404)])

    with pytest.raises(FetchError, match="404"):
        fetch_sightings(client, wait_seconds=0)
    assert len(calls) == 1


def test_fetch_retries_when_rate_limited():
    client, calls = fake_client([
        httpx.Response(429),
        httpx.Response(200, json=[GOOD_RECORD]),
    ])

    assert fetch_sightings(client, wait_seconds=0) == [GOOD_RECORD]
    assert len(calls) == 2


def test_fetch_rejects_a_response_that_is_not_a_list():
    client, _ = fake_client([httpx.Response(200, json={"error": "oops"})])

    with pytest.raises(FetchError, match="expected a JSON list"):
        fetch_sightings(client, wait_seconds=0)


def test_clean_all_keeps_good_records_and_counts_bad_ones():
    bad = dict(GOOD_RECORD, id="bad", date="not a date")

    cleaned, rejected = clean_all([GOOD_RECORD, bad])

    assert [record["id"] for record in cleaned] == ["abc123"]
    assert rejected == 1


def test_run_ingestion_stores_data_and_reports_a_summary(conn):
    raw = [
        GOOD_RECORD,
        dict(GOOD_RECORD),  # same id again: a duplicate
        dict(GOOD_RECORD, id="xyz789", location=" leeds "),
        dict(GOOD_RECORD, id="bad", location=None),  # incomplete
    ]
    client, _ = fake_client([httpx.Response(200, json=raw)])

    summary = run_ingestion(client, conn)

    assert summary == {
        "fetched": 4,
        "valid": 3,
        "rejected": 1,
        "duplicate_ids": 1,
        "total_in_database": 2,
    }


def test_running_ingestion_twice_does_not_duplicate_rows(conn):
    client, _ = fake_client([httpx.Response(200, json=[GOOD_RECORD]) for _ in range(2)])

    run_ingestion(client, conn)
    summary = run_ingestion(client, conn)

    assert summary["total_in_database"] == 1
