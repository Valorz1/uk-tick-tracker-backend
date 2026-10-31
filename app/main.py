"""FastAPI app: search and report on tick sightings stored in SQLite.

Run from the project root with:  uvicorn app.main:app --reload

Note: FastAPI shows each endpoint's docstring on the /docs page, so those
docstrings are written for API users. Notes for developers use # comments.
"""

import sqlite3
from datetime import date
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query

from app.db import connect, count_sightings
from app.models import PeriodCount, RegionCount, SearchResults
from app.queries import search_sightings, sightings_over_time, sightings_per_region

app = FastAPI(
    title="UK Tick Tracker API",
    description="Search and analyse UK tick sightings. Load data first with: python -m app.ingest",
)


def get_db():
    """Give each request its own database connection, and close it afterwards.

    Tests replace this with an in-memory database via `app.dependency_overrides`.

    Yields:
        An open SQLite connection.
    """
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def get_db_with_data(conn: Annotated[sqlite3.Connection, Depends(get_db)]):
    """Stop with a clear 503 error if ingestion has not been run yet.

    Without this, every endpoint would quietly return empty results,
    which looks like "no ticks in the UK" rather than "no data loaded".

    Args:
        conn: The connection provided by `get_db`. Because this builds on
            `get_db`, the check still runs when tests override `get_db`.

    Returns:
        The same connection, once it is known to contain data.

    Raises:
        HTTPException: 503 Service Unavailable if the table is empty.
    """
    if count_sightings(conn) == 0:
        raise HTTPException(
            status_code=503, detail="No data yet: run 'python -m app.ingest' first"
        )
    return conn


# A reusable type: any endpoint parameter declared as `DB` receives a
# connection that has already passed the "data is loaded" check.
DB = Annotated[sqlite3.Connection, Depends(get_db_with_data)]


# FastAPI validates every parameter from its type before this function runs:
# a bad date, or a limit/offset outside its range (ge = minimum,
# le = maximum), is rejected with a 422 error automatically.
@app.get("/sightings", response_model=SearchResults)
def search(
    conn: DB,
    start: Annotated[date | None, Query(description="Earliest date, e.g. 2023-01-01")] = None,
    end: Annotated[date | None, Query(description="Latest date (inclusive)")] = None,
    location: Annotated[str | None, Query(description="City, e.g. London")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Search sightings by date range and location, newest first."""
    # The one rule FastAPI cannot check alone, because it involves two parameters.
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")

    total, results = search_sightings(conn, start, end, location, limit, offset)
    return {"total": total, "limit": limit, "offset": offset, "results": results}


@app.get("/reports/regions", response_model=list[RegionCount])
def report_regions(conn: DB):
    """Number of sightings per region (each city is a region), highest first."""
    return sightings_per_region(conn)


# `Literal` allows only these two values: anything else gets a 422 error,
# and /docs shows them as a dropdown.
@app.get("/reports/trends", response_model=list[PeriodCount])
def report_trends(
    conn: DB,
    period: Annotated[
        Literal["weekly", "monthly"],
        Query(description="weekly: labelled by the Monday each week starts; monthly: YYYY-MM"),
    ] = "monthly",
):
    """Number of sightings per week or month, oldest first."""
    return sightings_over_time(conn, period)
