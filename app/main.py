"""FastAPI app: search tick sightings stored in SQLite.

Run from the project root with:  uvicorn app.main:app --reload
"""

import sqlite3
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query

from app.db import connect
from app.models import SearchResults
from app.queries import search_sightings

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


DB = Annotated[sqlite3.Connection, Depends(get_db)]


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
