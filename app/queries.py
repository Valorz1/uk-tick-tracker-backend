"""SQL queries used by the API endpoints.

Keeping the SQL here, away from the endpoint code, means each endpoint
stays short and each query can be read and changed in one place.
"""

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
    """Find sightings matching optional filters, one page at a time.

    The WHERE clause is built only from the filters actually given, so
    any combination of start, end and location works.

    Args:
        conn: An open database connection.
        start: Earliest date to include, or None for no lower limit.
        end: Latest date to include (the whole day), or None for no upper limit.
        location: City name in any capitalisation, or None for all cities.
        limit: The maximum number of sightings to return (the page size).
        offset: How many matching sightings to skip (for later pages).

    Returns:
        A tuple of (total number of matches across all pages,
        this page of sightings as dicts, newest first).
    """
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

    # `id` breaks ties between identical dates, so the order is always the
    # same and paging never shows a sighting twice or skips one.
    rows = conn.execute(
        "SELECT id, date, location, species, latin_name FROM sightings"
        f"{where} ORDER BY date DESC, id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()

    return total, [dict(row) for row in rows]


def sightings_per_region(conn: sqlite3.Connection) -> list[dict]:
    """Count sightings in each region (each city counts as a region).

    Args:
        conn: An open database connection.

    Returns:
        A list of {"region": ..., "count": ...} dicts, highest count first.
        Ties are sorted alphabetically so the order never changes.
    """
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
    """Count sightings per week or month.

    Args:
        conn: An open database connection.
        period: "weekly" or "monthly". The endpoint checks this, and the SQL
            text below only ever comes from PERIOD_SQL, never from the user,
            so it is safe from SQL injection.

    Returns:
        A list of {"period": ..., "count": ...} dicts, oldest first.
        Periods with no sightings are not included.

    Raises:
        KeyError: If `period` is not a key of PERIOD_SQL.
    """
    period_sql = PERIOD_SQL[period]
    rows = conn.execute(
        f"SELECT {period_sql} AS period, COUNT(*) AS count FROM sightings"
        " GROUP BY period ORDER BY period"
    ).fetchall()
    return [dict(row) for row in rows]
