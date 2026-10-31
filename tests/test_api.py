import pytest
from fastapi.testclient import TestClient

from app.db import connect, upsert_sightings
from app.main import app, get_db


def sighting(id, date, location="Manchester", species="Marsh tick"):
    return {
        "id": id,
        "date": date,
        "location": location,
        "species": species,
        "latin_name": "Ixodes apronophorus",
    }


TEST_DATA = [
    sighting("a", "2022-01-10T09:00:00", "London"),
    sighting("b", "2022-01-31T23:59:59", "London"),
    sighting("c", "2022-02-01T00:00:00", "Manchester"),
    sighting("d", "2023-06-15T12:00:00", "Glasgow"),
]


@pytest.fixture
def client():
    """A test client whose endpoints use a small in-memory database."""
    conn = connect(":memory:")
    upsert_sightings(conn, TEST_DATA)
    app.dependency_overrides[get_db] = lambda: conn
    yield TestClient(app)
    app.dependency_overrides.clear()
    conn.close()


def ids(response):
    return [s["id"] for s in response.json()["results"]]


def test_no_filters_returns_everything_newest_first(client):
    response = client.get("/sightings")

    assert response.status_code == 200
    assert response.json()["total"] == 4
    assert ids(response) == ["d", "c", "b", "a"]


def test_date_range_includes_the_whole_end_day(client):
    response = client.get("/sightings", params={"start": "2022-01-01", "end": "2022-01-31"})

    assert ids(response) == ["b", "a"]


def test_location_filter_ignores_case_and_spaces(client):
    response = client.get("/sightings", params={"location": "  london "})

    assert ids(response) == ["b", "a"]


def test_filters_can_be_combined(client):
    response = client.get(
        "/sightings", params={"start": "2022-01-15", "end": "2022-12-31", "location": "London"}
    )

    assert ids(response) == ["b"]


def test_unknown_location_returns_empty_list(client):
    response = client.get("/sightings", params={"location": "Atlantis"})

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert ids(response) == []


def test_limit_and_offset_page_through_results(client):
    response = client.get("/sightings", params={"limit": 2, "offset": 1})

    assert response.json()["total"] == 4  # total ignores paging
    assert ids(response) == ["c", "b"]


def test_start_after_end_is_rejected(client):
    response = client.get("/sightings", params={"start": "2023-01-01", "end": "2022-01-01"})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "params",
    [{"start": "not-a-date"}, {"limit": 0}, {"limit": 501}, {"offset": -1}],
)
def test_invalid_parameters_are_rejected(client, params):
    assert client.get("/sightings", params=params).status_code == 422
