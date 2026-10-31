"""SQL queries used by the API endpoints."""

import sqlite3
from datetime import date, timedelta

from app.cleaning import normalise_location


def search_sightings(
    conn: sqlite3.Connection,
    start: date | None = None,
    end: date | None = None,
    location: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[dict]]:
    """Return (total matches, one page of matching sightings, newest first)."""
    conditions = []
    params = []

    if start:
        conditions.append("date >= ?")
        params.append(start.isoformat())

    # date.max (9999-12-31) has no "next day", and every stored date is
    # before it anyway, so it needs no condition.
    if end and end < date.max:
        # Dates are stored with a time, so "up to and including end" means
        # "before the start of the next day".
        conditions.append("date < ?")
        params.append((end + timedelta(days=1)).isoformat())

    # A blank or spaces-only location means "no location filter".
    if location and location.strip():
        # Tidy the input with the same function used on stored cities.
        conditions.append("location = ?")
        params.append(normalise_location(location))

    # Only our own fixed condition strings go into the SQL text.
    # Every value the user sends goes through a ? placeholder.
    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    total = conn.execute(
        f"SELECT COUNT(*) FROM sightings{where}",
        params,
    ).fetchone()[0]

    rows = conn.execute(
        "SELECT id, date, location, species, latin_name FROM sightings"
        f"{where} ORDER BY date DESC, id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()

    return total, [dict(row) for row in rows]


def sightings_per_region(conn: sqlite3.Connection) -> list[dict]:
    """Return the number of sightings in each region (city), highest first."""
    rows = conn.execute(
        "SELECT location AS region, COUNT(*) AS count FROM sightings"
        " GROUP BY location ORDER BY count DESC, region"
    ).fetchall()
    return [dict(row) for row in rows]


# How each period is worked out from a stored date, in SQLite.
# Weekly: 'weekday 0' moves forward to the next Sunday (or stays if already
# Sunday), then '-6 days' goes back to that week's Monday. So every date in
# a week gets the same label: the date the week starts.
PERIOD_SQL = {
    "monthly": "strftime('%Y-%m', date)",
    "weekly": "date(date, 'weekday 0', '-6 days')",
}


def sightings_over_time(conn: sqlite3.Connection, period: str) -> list[dict]:
    """Return the number of sightings per week or month, oldest first.

    `period` must be "weekly" or "monthly". The endpoint checks this, and the
    SQL text below only ever comes from PERIOD_SQL, never from the user.
    """
    period_sql = PERIOD_SQL[period]
    rows = conn.execute(
        f"SELECT {period_sql} AS period, COUNT(*) AS count FROM sightings"
        " GROUP BY period ORDER BY period"
    ).fetchall()
    return [dict(row) for row in rows]
