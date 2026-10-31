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


def test_blank_location_means_no_filter(client):
    response = client.get("/sightings", params={"location": "   "})

    assert response.json()["total"] == 4


def test_latest_possible_end_date_does_not_crash(client):
    response = client.get("/sightings", params={"end": "9999-12-31"})

    assert response.status_code == 200
    assert response.json()["total"] == 4


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


# ---------- Reports ----------


def test_regions_report_counts_each_city_highest_first(client):
    response = client.get("/reports/regions")

    assert response.status_code == 200
    assert response.json() == [
        {"region": "London", "count": 2},
        {"region": "Glasgow", "count": 1},  # ties are sorted alphabetically
        {"region": "Manchester", "count": 1},
    ]


def test_monthly_trends_count_each_month_oldest_first(client):
    response = client.get("/reports/trends", params={"period": "monthly"})

    assert response.json() == [
        {"period": "2022-01", "count": 2},
        {"period": "2022-02", "count": 1},
        {"period": "2023-06", "count": 1},
    ]


def test_monthly_is_the_default_period(client):
    assert client.get("/reports/trends").json()[0]["period"] == "2022-01"


def test_weekly_trends_are_labelled_by_the_monday_each_week_starts(client):
    response = client.get("/reports/trends", params={"period": "weekly"})

    # 2022-01-10 is a Monday. 2022-01-31 (Mon) and 2022-02-01 (Tue) fall in
    # the same week, even though they are in different months.
    assert response.json() == [
        {"period": "2022-01-10", "count": 1},
        {"period": "2022-01-31", "count": 2},
        {"period": "2023-06-12", "count": 1},
    ]


def test_unknown_period_is_rejected(client):
    assert client.get("/reports/trends", params={"period": "daily"}).status_code == 422


# ---------- If no data loaded yet ----------


@pytest.mark.parametrize("path", ["/sightings", "/reports/regions", "/reports/trends"])
def test_empty_database_gives_a_clear_503_error(path):
    empty = connect(":memory:")
    app.dependency_overrides[get_db] = lambda: empty
    try:
        response = TestClient(app).get(path)
    finally:
        app.dependency_overrides.clear()
        empty.close()

    assert response.status_code == 503
    assert "run 'python -m app.ingest' first" in response.json()["detail"]
