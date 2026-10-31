"""FastAPI app: search and report on tick sightings stored in SQLite.

Run from the project root with:  uvicorn app.main:app --reload
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
    """Give each request its own database connection, and close it afterwards."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def get_db_with_data(conn: Annotated[sqlite3.Connection, Depends(get_db)]):
    """Stop with a clear 503 error if ingestion has not been run yet.

    Without this, every endpoint would quietly return empty results,
    which looks like "no ticks in the UK" rather than "no data loaded".
    """
    if count_sightings(conn) == 0:
        raise HTTPException(
            status_code=503, detail="No data yet: run 'python -m app.ingest' first"
        )
    return conn


DB = Annotated[sqlite3.Connection, Depends(get_db_with_data)]


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
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")

    total, results = search_sightings(conn, start, end, location, limit, offset)
    return {"total": total, "limit": limit, "offset": offset, "results": results}


@app.get("/reports/regions", response_model=list[RegionCount])
def report_regions(conn: DB):
    """Number of sightings per region (each city is a region), highest first."""
    return sightings_per_region(conn)


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
